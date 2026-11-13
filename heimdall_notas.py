#!/usr/bin/env python3
"""Heimdall Notas: um site simples e agradável para LER as notas de estudo e OUVIR os áudios.

Lê direto do cofre (cerebro/: notas em Markdown e áudios .m4a) e da pasta knowledge/ (seus documentos). Não depende de
nenhum app: abre no Safari do Mac ou do iPhone, funciona com VoiceOver e usa o mesmo login do painel Cloud
(a mesma senha e o mesmo código de 6 dígitos).

O que tem:
  - Início com as últimas notas, os temas e os documentos.
  - Cada nota vira uma página limpa (títulos, listas, tabelas), com o leitor de áudio no topo: velocidade 0,75x a 1,5x,
    botões de voltar e avançar 15 segundos, e a página lembra onde você parou.
  - Anterior e próxima nota dentro do tema; busca por texto; documentos de knowledge/ (PDF abre na página).

Pastas: por padrão aparece o cofre inteiro (temas de estudo, Second Brain, Monitor de Privacidade, Saúde etc.), menos o
Digest. Para tirar mais pastas: HEIMDALL_NOTAS_EXCLUIR="heimdall-digest,saude". Para mostrar só algumas pastas além
dos temas de estudo: HEIMDALL_NOTAS_PASTAS="heimdall-cerebro,outra-pasta".

Segurança (pode ficar público em notes.heimdall-ai.tech): escuta só em 127.0.0.1; senha forte + código de 6 dígitos
(HEIMDALL_CLOUD_SENHA_HASH e HEIMDALL_CLOUD_TOTP_SEGREDO, os mesmos do painel Cloud); limite de tentativas; sessão em cookie
HttpOnly e SameSite=Strict; só nomes de site permitidos; somente leitura (nada aqui grava ou apaga arquivos); caminhos
conferidos contra fuga de pasta; HTML sempre escapado; documentos que não são PDF ou áudio só baixam, nunca executam.

Variáveis opcionais: HEIMDALL_NOTAS_PORT (8011), HEIMDALL_NOTAS_HOST (127.0.0.1), HEIMDALL_NOTAS_HOSTS
(notes.heimdall-ai.tech,localhost,127.0.0.1), HEIMDALL_NOTAS_PASTAS, HEIMDALL_NOTAS_EXCLUIR, HEIMDALL_VAULT_DIR, HEIMDALL_KNOWLEDGE_DIR.

    python3 heimdall_notas.py     (o start_heimdall.sh sobe sozinho se houver senha e código no .env)

Usa só a biblioteca padrão do Python.
"""
import html
import mimetypes
import os
import re
import secrets
import sys
import time
import unicodedata
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

PROJECT_DIR = Path(__file__).resolve().parent


def carregar_env() -> None:
    """Do .env lê só as variáveis do Heimdall Notas e as pastas do cofre (as outras chaves do projeto não entram aqui)."""
    try:
        linhas = (PROJECT_DIR / ".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for linha in linhas:
        linha = linha.strip()
        if linha.startswith("export "):
            linha = linha[7:]
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        chave, valor = chave.strip(), valor.strip()
        if chave.startswith("HEIMDALL_BIBLIOTECA_"):  # nome antigo das variáveis: continua valendo
            chave = "HEIMDALL_NOTAS_" + chave[len("HEIMDALL_BIBLIOTECA_"):]
        elif not (chave.startswith("HEIMDALL_NOTAS_") or chave in ("HEIMDALL_VAULT_DIR", "HEIMDALL_KNOWLEDGE_DIR")):
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        os.environ.setdefault(chave, valor)


carregar_env()
for _k in [k for k in os.environ if k.startswith("HEIMDALL_BIBLIOTECA_")]:  # idem para variáveis já no ambiente
    os.environ.setdefault("HEIMDALL_NOTAS_" + _k[len("HEIMDALL_BIBLIOTECA_"):], os.environ[_k])

import heimdall_cloud as nuvem  # noqa: E402  (login, senha, código de 6 dígitos e sessões: o mesmo do painel Cloud)

HOST = os.environ.get("HEIMDALL_NOTAS_HOST", "127.0.0.1")
PORT = int(os.environ.get("HEIMDALL_NOTAS_PORT", "8011"))
HOSTS_OK = {h.strip().lower() for h in os.environ.get("HEIMDALL_NOTAS_HOSTS", "notes.heimdall-ai.tech,localhost,127.0.0.1").split(",") if h.strip()}
VAULT = Path(os.environ.get("HEIMDALL_VAULT_DIR", str(PROJECT_DIR / "cerebro"))).expanduser()
KNOWLEDGE = Path(os.environ.get("HEIMDALL_KNOWLEDGE_DIR", str(PROJECT_DIR / "knowledge"))).expanduser()
COOKIE = "hbib"
NOMES = {"heimdall-privacidade": "Monitor de Privacidade", "heimdall-cerebro": "Second Brain", "saude": "Saúde", "heimdall-digest": "Digest"}
EXT_NOTA = {".md", ".markdown", ".txt"}
EXT_AUDIO = {".m4a", ".mp3"}
EXT_DOC = {".pdf", ".md", ".markdown", ".txt", ".docx", ".epub", ".m4a", ".mp3"}
MAX_TEXTO = 2 * 1024 * 1024  # nota maior que isso não é lida como texto
NOME_RE = re.compile(r"^[^\W_][\w .,()+-]{0,118}\.[A-Za-z0-9]{1,8}$")
e = lambda t: html.escape(str(t), quote=True)  # noqa: E731


# ----------------------------------------------------------------------------------------
# Pastas e arquivos
# ----------------------------------------------------------------------------------------
def slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:80] or "geral"


def sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def nome_bonito(chave: str) -> str:
    if chave in NOMES:
        return NOMES[chave]
    base = chave[len("heimdall-"):] if chave.startswith("heimdall-") else chave
    return base.replace("-", " ").strip().capitalize() or chave


def _subdirs(raiz: Path) -> list:
    try:
        return sorted(d for d in raiz.iterdir() if d.is_dir() and not d.name.startswith(".") and not d.is_symlink())
    except OSError:
        return []


def pastas() -> dict:
    """Pastas liberadas: chave (slug) -> {'nome', 'cofre' (notas e áudios), 'docs' (documentos de knowledge)}."""
    cfg = os.environ.get("HEIMDALL_NOTAS_PASTAS", "*").strip() or "*"
    tudo = cfg == "*"
    liberadas = {slug(x) for x in cfg.split(",") if x.strip()}
    fora = {slug(x) for x in os.environ.get("HEIMDALL_NOTAS_EXCLUIR", "heimdall-digest").split(",") if x.strip()}
    res = {}
    for d in _subdirs(KNOWLEDGE):
        if slug(d.name) not in fora:
            res.setdefault(slug(d.name), {"nome": d.name[:1].upper() + d.name[1:], "cofre": None, "docs": d})
    for d in _subdirs(VAULT):
        k = slug(d.name)
        if k in fora:
            continue
        if tudo or k in liberadas or k in res:
            r = res.setdefault(k, {"nome": nome_bonito(k), "cofre": None, "docs": None})
            r["cofre"] = d
    return res


def dentro(base: Path, alvo: Path) -> bool:
    try:
        alvo.resolve().relative_to(base.resolve())
        return True
    except (ValueError, OSError):
        return False


def arquivo_seguro(base, nome: str, extensoes: set):
    """Arquivo de nome simples dentro da pasta, ou None."""
    if base is None or not NOME_RE.match(nome or "") or ".." in nome:
        return None
    p = base / nome
    if p.suffix.lower() not in extensoes or p.is_symlink() or not p.is_file() or not dentro(base, p):
        return None
    return p


def doc_seguro(raiz, rel: str):
    """Documento em qualquer subpasta de knowledge/<tema>/, ou None."""
    if raiz is None or not rel or len(rel) > 400:
        return None
    partes = rel.split("/")
    if len(partes) > 6 or any(not NOME_RE.match(x) if i == len(partes) - 1 else not re.match(r"^[^\W_][\w .,()+-]{0,118}$", x) for i, x in enumerate(partes)):
        return None
    p = raiz.joinpath(*partes)
    if p.suffix.lower() not in EXT_DOC or not p.is_file() or not dentro(raiz, p):
        return None
    if any(parte.is_symlink() for parte in [p, *p.parents] if dentro(raiz, parte) and parte != raiz.resolve()):
        return None
    return p


def separa_frontmatter(md: str) -> tuple:
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", md, re.S)
    if not m:
        return {}, md
    meta = {}
    for l in m.group(1).splitlines():
        k, _, v = l.partition(":")
        k = k.strip().lower()
        if k in ("tags", "conceitos", "entidades"):
            itens = [x.strip().strip('"\'') for x in v.strip().strip("[]").split(",") if x.strip()]
            if itens:
                meta[k] = itens
    return meta, md[m.end():].lstrip("\r\n")


def ler_texto(p: Path) -> str:
    if p.stat().st_size > MAX_TEXTO:
        return "Esta nota é grande demais para abrir aqui."
    return p.read_text(encoding="utf-8", errors="replace")


def titulo_de(p: Path, md: str = None) -> str:
    try:
        corpo = separa_frontmatter(md if md is not None else p.read_text(encoding="utf-8", errors="replace")[:4000])[1]
    except OSError:
        corpo = ""
    for l in corpo.splitlines():
        m = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", l)
        if m:
            return re.sub(r"[*`_]", "", m.group(1)).strip()[:200]
        if l.strip():
            break
    return p.stem.replace("-", " ").replace("_", " ").strip().capitalize()[:200] or p.name


GENERICO_RE = re.compile(r"^(resumo|resumos|nota|notas|anotações|anotacoes|sem t[ií]tulo|untitled|rascunho|ideia|ideias|lembrete|geral|diversos|teste)?\s*[-:–]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(/\d{2,4})?)?\s*(\d{1,2}h(\d{2})?)?$", re.I)
DATA_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _data_br(texto: str, p: Path) -> str:
    m = DATA_RE.search(texto)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y")


def primeira_frase(corpo: str, maximo: int = 140) -> str:
    """Primeira frase com texto de verdade, sem marcas de Markdown. Se for longa, corta numa vírgula ou num espaço."""
    for l in corpo.splitlines():
        t = re.sub(r"^\s*(#{1,6}\s+|[-*+>]\s+|\d+[.)]\s+)", "", l).strip()
        t = re.sub(r"[*_`]|\[\[|\]\]", "", t)
        t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t).strip()
        if len(re.findall(r"[^\W\d_]", t)) < 15 or re.match(r"^(tema|livro|origem|pasta|tags?|nota_id|endere[cç]o)\s*:", t, re.I):
            continue
        m = re.match(r"(.+?[.!?…])(\s|$)", t)
        f = (m.group(1) if m else t).rstrip(".")
        if len(f) <= maximo:
            return f
        corte = max((f.rfind(c, 0, maximo) for c in (",", ";", ":", " — ", " - ")), default=-1)
        if corte >= 35:
            return f[:corte].rstrip()
        corte = f.rfind(" ", 0, maximo)
        return f[:corte if corte >= 35 else maximo].rstrip(" ,;:-") + "…"
    return ""


def titulo_exibicao(titulo: str, corpo: str, p: Path) -> str:
    """Nome de leitura da nota: tira prefixos repetidos (Estudo, data, Second Brain) e dá sentido a títulos vagos."""
    t = re.sub(r"\s+", " ", titulo).strip()
    m = re.match(r"^Estudo\s+\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}h)?\s*[:\-–]\s*(.+)$", t, re.I)
    if m:
        return m.group(1)[:1].upper() + m.group(1)[1:]
    m = re.match(r"^(?:Second Brain|C[ée]rebro)\s*:\s*(.+)$", t, re.I)
    if m:
        t = m.group(1).strip()
    data = _data_br(t, p)
    if re.match(r"^Monitor(?: de privacidade)?\s*[-:]?\s*\d{4}-\d{2}-\d{2}\s*$", t, re.I):
        m = re.search(r"Nível de atenção:\s*([^.*]+)\.?\*{0,2}\s*(\d+)\s*achado", corpo)
        extra = f": {m.group(2)} {'achado' if m.group(2) == '1' else 'achados'}, atenção {m.group(1).strip().lower()}" if m else ""
        return f"Monitor de privacidade de {data}{extra}"
    if re.match(r"^Di[áa]rios oficiais\s*[-:]?\s*\d{4}-\d{2}-\d{2}(\s*\(.*\))?\s*$", t, re.I):
        n = len(re.findall(r"^\d+\.\s", corpo, re.M))
        fontes = [x.strip() for x in re.findall(r"^##\s+(.+)$", corpo, re.M)][:3]
        extra = (f": {n} {'menção' if n == 1 else 'menções'}" if n else "") + (f" ({', '.join(fontes)})" if fontes else "")
        return f"Diários oficiais de {data}{extra}"
    if re.match(r"^Sa[úu]de\s*[-:]?\s*\d{4}-\d{2}-\d{2}\s*$", t, re.I):
        f = primeira_frase(corpo)
        return f"Saúde de {data}" + (f": {f}" if f else "")
    if GENERICO_RE.match(t) or len(t) < 4:
        f = primeira_frase(corpo)
        base = re.sub(r"\s*[-:–]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(/\d{2,4})?)\s*$", "", t).strip() or "Nota"
        if f:
            return f"{base[:1].upper() + base[1:]} de {data}: {f}" if DATA_RE.search(t) else f"{base[:1].upper() + base[1:]}: {f}"
        return f"{base[:1].upper() + base[1:]} de {data}"
    return t


def titulo_da_nota(p: Path, md: str = None) -> str:
    """Título de exibição de um arquivo de nota."""
    try:
        texto = md if md is not None else p.read_text(encoding="utf-8", errors="replace")[:20000]
    except OSError:
        return p.stem
    bruto = titulo_de(p, texto)
    return titulo_exibicao(bruto, separa_frontmatter(texto)[1], p)[:220]


def data_de(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y %H:%M")


def audio_da_nota(chave: str, p: Path):
    base = pastas().get(chave, {}).get("cofre")
    if base is None:
        return None
    for ext in (".m4a", ".mp3"):
        a = base / "audio" / (p.stem + ext)
        if a.is_file() and not a.is_symlink() and dentro(base, a):
            return a
    return None


def notas_da_pasta(chave: str) -> list:
    """Notas do cofre, da mais nova para a mais antiga: [(caminho, título, mtime, tem_audio)]."""
    base = pastas().get(chave, {}).get("cofre")
    if base is None:
        return []
    saida = []
    try:
        for p in base.iterdir():
            if p.suffix.lower() in EXT_NOTA and p.is_file() and not p.is_symlink() and not p.name.startswith("."):
                saida.append((p, titulo_da_nota(p), p.stat().st_mtime, audio_da_nota(chave, p) is not None))
    except OSError:
        return []
    return sorted(saida, key=lambda t: t[2], reverse=True)


def documentos_da_pasta(chave: str) -> list:
    raiz = pastas().get(chave, {}).get("docs")
    if raiz is None:
        return []
    saida = []
    try:
        for p in sorted(raiz.rglob("*")):
            if len(saida) >= 300:
                break
            rel = p.relative_to(raiz)
            if len(rel.parts) > 6 or any(x.startswith(".") for x in rel.parts):
                continue
            if p.suffix.lower() in EXT_DOC and p.is_file() and doc_seguro(raiz, rel.as_posix()):
                saida.append((rel.as_posix(), p))
    except OSError:
        pass
    return saida


# ----------------------------------------------------------------------------------------
# Markdown para HTML (pequeno e seguro: tudo é escapado; links só https ou http)
# ----------------------------------------------------------------------------------------
def inline(t: str) -> str:
    partes = re.split(r"(`[^`]+`)", t)
    saida = []
    for i, parte in enumerate(partes):
        if i % 2:
            saida.append(f"<code>{e(parte[1:-1])}</code>")
            continue
        s = e(parte)
        s = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), s)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", lambda m: f'<a href="{m.group(2)}" rel="noopener noreferrer">{m.group(1)}</a>', s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
        saida.append(s)
    return "".join(saida)


def _celulas(linha: str) -> list:
    return [c.strip() for c in linha.strip().strip("|").split("|")]


def markdown_html(md: str, titulo: str = "") -> str:
    linhas = md.replace("\r\n", "\n").split("\n")
    out, i, n = [], 0, len(linhas)
    primeiro = True
    while i < n:
        l = linhas[i]
        if not l.strip():
            i += 1
            continue
        if l.strip().startswith("```"):
            i += 1
            bloco = []
            while i < n and not linhas[i].strip().startswith("```"):
                bloco.append(linhas[i])
                i += 1
            i += 1
            out.append(f"<pre><code>{e(chr(10).join(bloco))}</code></pre>")
            primeiro = False
            continue
        m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", l)
        if m:
            texto = m.group(2)
            if primeiro and sem_acento(re.sub(r"[*`_]", "", texto)).strip() == sem_acento(titulo).strip():
                i += 1  # o título já é o título da página
                primeiro = False
                continue
            nivel = min(6, len(m.group(1)) + 1)
            out.append(f"<h{nivel}>{inline(texto)}</h{nivel}>")
            i += 1
            primeiro = False
            continue
        primeiro = False
        if re.match(r"^\s*([-*_])(\s*\1){2,}\s*$", l):
            out.append("<hr>")
            i += 1
            continue
        if l.lstrip().startswith("|") and i + 1 < n and re.match(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$", linhas[i + 1]):
            cab = _celulas(l)
            i += 2
            linhas_t = []
            while i < n and linhas[i].lstrip().startswith("|"):
                linhas_t.append(_celulas(linhas[i]))
                i += 1
            t = "<table><thead><tr>" + "".join(f'<th scope="col">{inline(c)}</th>' for c in cab) + "</tr></thead><tbody>"
            for r in linhas_t:
                t += "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
            out.append(t + "</tbody></table>")
            continue
        if l.lstrip().startswith(">"):
            citacao = []
            while i < n and linhas[i].lstrip().startswith(">"):
                citacao.append(re.sub(r"^\s*>\s?", "", linhas[i]))
                i += 1
            out.append("<blockquote>" + markdown_html("\n".join(citacao)) + "</blockquote>")
            continue
        m = re.match(r"^\s*(?:([-*+])|(\d+)[.)])\s+(.*)$", l)
        if m:
            ordenada = m.group(2) is not None
            itens = []
            while i < n:
                mm = re.match(r"^\s*(?:([-*+])|(\d+)[.)])\s+(.*)$", linhas[i])
                if not mm or (mm.group(2) is not None) != ordenada:
                    break
                item = mm.group(3)
                i += 1
                while i < n and linhas[i].strip() and re.match(r"^\s{2,}\S", linhas[i]) and not re.match(r"^\s*(?:[-*+]|\d+[.)])\s+", linhas[i]):
                    item += " " + linhas[i].strip()
                    i += 1
                itens.append(item)
            tag = "ol" if ordenada else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in itens) + f"</{tag}>")
            continue
        par = [l.strip()]
        i += 1
        while i < n and linhas[i].strip() and not re.match(r"^(#{1,6}\s|```|>|\s*([-*+]|\d+[.)])\s+|\s*\|)", linhas[i]):
            par.append(linhas[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(par))}</p>")
    return "\n".join(out)


# ----------------------------------------------------------------------------------------
# Páginas
# ----------------------------------------------------------------------------------------
CSS = nuvem.CSS + """
body{font-size:19px;line-height:1.7;max-width:46rem}
main h1{line-height:1.25;margin-top:1rem}h2,h3,h4{line-height:1.3;margin-top:1.8rem}
.lista{list-style:none;padding:0}.lista li{border-bottom:1px solid var(--linha);padding:.7rem 0}
.lista h3{margin:0 0 .2rem;font-size:1.15em}.lista a{font-weight:700;font-size:1.05em}.meta{color:var(--suave);font-size:.9em;display:block}
.leitor{border:2px solid var(--acento);border-radius:.5rem;padding:.8rem;margin:1rem 0}.leitor audio{width:100%}
.leitor button{margin:.4rem .4rem 0 0}.leitor button[aria-pressed=true]{background:var(--acento);color:var(--fundo)}
.ant-prox{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap;border-top:1px solid var(--linha);margin-top:2rem;padding-top:1rem}
blockquote{border-left:4px solid var(--linha);margin-left:0;padding-left:1rem;color:var(--suave)}
code{font-family:ui-monospace,Menlo,monospace;font-size:.92em}form.busca{display:flex;gap:.5rem;align-items:end;flex-wrap:wrap}
form.busca div{flex:1;min-width:12rem}form.busca button{margin-top:0}
"""

SCRIPT_LEITOR = """(function(){
var a=document.getElementById('leitor');if(!a){return;}
var chave='hbib:'+a.getAttribute('data-chave'),st=document.getElementById('leitor-estado');
function ler(){try{return localStorage.getItem(chave);}catch(x){return null;}}
function gravar(v){try{localStorage.setItem(chave,String(v));}catch(x){}}
function aviso(t){if(st){st.textContent=t;}}
var ponto=parseFloat(ler()),t0=0;
a.addEventListener('loadedmetadata',function(){if(ponto>5&&ponto<a.duration-5){a.currentTime=ponto;aviso('Retomando de '+Math.floor(ponto/60)+' min '+Math.floor(ponto%60)+' s.');}});
a.addEventListener('timeupdate',function(){var n=Date.now();if(n-t0>3000){t0=n;gravar(a.currentTime);}});
a.addEventListener('ended',function(){gravar(0);});
var vs=document.querySelectorAll('[data-vel]');
function marcar(v){for(var i=0;i<vs.length;i++){vs[i].setAttribute('aria-pressed',parseFloat(vs[i].getAttribute('data-vel'))===v?'true':'false');}}
for(var i=0;i<vs.length;i++){vs[i].addEventListener('click',function(){var v=parseFloat(this.getAttribute('data-vel'));a.playbackRate=v;marcar(v);aviso('Velocidade '+String(v).replace('.',',')+' vezes.');});}
var ss=document.querySelectorAll('[data-salto]');
for(var j=0;j<ss.length;j++){ss[j].addEventListener('click',function(){var d=parseFloat(this.getAttribute('data-salto'));a.currentTime=Math.max(0,Math.min(a.duration||1e9,a.currentTime+d));aviso(d<0?'Voltei 15 segundos.':'Avancei 15 segundos.');});}
marcar(1);
})();"""


def pagina(titulo: str, corpo: str, sess: dict = None, nonce: str = "", script: str = "") -> bytes:
    nav = ""
    if sess:
        nav = ('<nav aria-label="Principal"><ul><li><a href="/">Início</a></li><li><a href="/busca">Buscar</a></li>'
               '<li><form class="linha" method="post" action="/sair">'
               f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}"><button type="submit">Sair</button></form></li></ul></nav>')
    js = f'<script nonce="{e(nonce)}">{script}</script>' if script else ""
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{e(titulo)} - Heimdall Notas</title><style>{CSS}</style></head><body>'
            f'<a class="pular" href="#principal">Pular para o conteúdo</a><header><p><strong>Heimdall Notas</strong></p>{nav}</header>'
            f'<main id="principal"><h1>{e(titulo)}</h1>{corpo}</main>{js}</body></html>').encode("utf-8")


def pg_entrar(erro: str = "") -> bytes:
    msg = f'<p class="erro" role="alert">{e(erro)}</p>' if erro else ""
    corpo = (f'{msg}<form method="post" action="/entrar"><label for="senha">Senha</label>'
             '<input id="senha" name="senha" type="password" autocomplete="current-password" required>'
             '<label for="codigo">Código de verificação de 6 dígitos</label>'
             '<input id="codigo" name="codigo" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" required>'
             '<button type="submit">Entrar</button></form>')
    return pagina("Entrar", corpo)


def plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def inicio_do_titulo(titulo: str, limite: int = 110) -> str:
    """Título para o texto do link. Só corta títulos muito longos (sempre num espaço, nunca no meio da palavra) e só então põe reticências."""
    t = re.sub(r"\s+", " ", titulo).strip()
    if len(t) > limite:
        corte = t.rfind(" ", 0, limite)
        t = t[:corte if corte >= limite // 2 else limite].rstrip(" ,;:.-") + "…"
    return t


def item_nota(chave: str, p: Path, titulo: str, mtime: float, audio: bool, mostrar_tema: str = "") -> str:
    extra = " · com áudio" if audio else ""
    tema = f" · {e(mostrar_tema)}" if mostrar_tema else ""
    link = f"/nota?p={quote(chave)}&amp;n={quote(p.name)}"
    return (f'<li><h3>{e(titulo)}</h3><a href="{link}">Leia mais sobre {e(inicio_do_titulo(titulo))}</a>'
            f'<span class="meta">{datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")}{tema}{extra}</span></li>')


def pg_inicio() -> str:
    ps = pastas()
    todas = []
    for k in ps:
        for p, t, m, a in notas_da_pasta(k):
            todas.append((m, k, p, t, a))
    todas.sort(reverse=True)
    corpo = ['<h2 id="ultimas">Últimas notas</h2>']
    if todas:
        corpo.append('<ul class="lista" aria-labelledby="ultimas">' + "".join(item_nota(k, p, t, m, a, ps[k]["nome"]) for m, k, p, t, a in todas[:15]) + "</ul>")
    else:
        corpo.append('<p class="nota">Ainda não há notas aqui. Elas aparecem depois do próximo estudo (6h, 13h ou 20h).</p>')
    corpo.append('<h2 id="temas">Temas</h2>')
    if ps:
        itens = []
        for k, v in sorted(ps.items(), key=lambda kv: sem_acento(kv[1]["nome"])):
            nn, nd = len(notas_da_pasta(k)), len(documentos_da_pasta(k))
            itens.append(f'<li><a href="/tema?t={quote(k)}">{e(v["nome"])}</a><span class="meta">{plural(nn, "nota", "notas")} · {plural(nd, "documento", "documentos")}</span></li>')
        corpo.append('<ul class="lista" aria-labelledby="temas">' + "".join(itens) + "</ul>")
    else:
        corpo.append('<p class="nota">Nenhum tema encontrado. Os temas são as subpastas de knowledge/.</p>')
    return "".join(corpo)


def pg_tema(chave: str) -> tuple:
    v = pastas()[chave]
    notas = notas_da_pasta(chave)
    docs = documentos_da_pasta(chave)
    corpo = ['<h2 id="notas">Notas</h2>']
    if notas:
        corpo.append('<ul class="lista" aria-labelledby="notas">' + "".join(item_nota(chave, p, t, m, a) for p, t, m, a in notas) + "</ul>")
    else:
        corpo.append('<p class="nota">Nenhuma nota neste tema ainda.</p>')
    corpo.append('<h2 id="docs">Documentos</h2>')
    if docs:
        itens = []
        for rel, p in docs:
            tam = p.stat().st_size
            kb = f"{tam / 1024 / 1024:.1f} MB" if tam > 1024 * 1024 else f"{max(1, tam // 1024)} KB"
            itens.append(f'<li><a href="/doc?t={quote(chave)}&amp;c={quote(rel)}">{e(rel)}</a><span class="meta">{e(p.suffix[1:].upper())} · {kb}</span></li>')
        corpo.append('<ul class="lista" aria-labelledby="docs">' + "".join(itens) + "</ul>")
    else:
        corpo.append('<p class="nota">Nenhum documento neste tema.</p>')
    return v["nome"], "".join(corpo)


def leitor(src: str, chave: str, tipo: str) -> str:
    vel = "".join(f'<button type="button" data-vel="{v}" aria-pressed="false">{rot}</button>' for v, rot in (("0.75", "0,75 vezes"), ("1", "1 vez"), ("1.25", "1,25 vezes"), ("1.5", "1,5 vezes")))
    return ('<section class="leitor" aria-labelledby="h-audio"><h2 id="h-audio">Ouvir</h2>'
            f'<audio id="leitor" controls preload="metadata" data-chave="{e(chave)}" src="{e(src)}" type="{e(tipo)}">Seu navegador não toca este áudio. <a href="{e(src)}">Baixar o áudio</a>.</audio>'
            '<div role="group" aria-label="Controles do áudio"><button type="button" data-salto="-15">Voltar 15 segundos</button>'
            f'<button type="button" data-salto="15">Avançar 15 segundos</button></div>'
            f'<div role="group" aria-label="Velocidade">{vel}</div><p id="leitor-estado" class="nota" role="status"></p></section>')


def pg_nota(chave: str, p: Path) -> tuple:
    md = ler_texto(p)
    meta, corpo_md = separa_frontmatter(md)
    titulo_bruto = titulo_de(p, md)
    titulo = titulo_exibicao(titulo_bruto, corpo_md, p)
    a = audio_da_nota(chave, p)
    partes = [f'<p class="meta">{e(pastas()[chave]["nome"])} · {data_de(p)}</p>']
    if a:
        partes.append(leitor(f"/audio?p={quote(chave)}&n={quote(a.name)}", f"{chave}/{p.name}", mimetypes.guess_type(a.name)[0] or "audio/mp4"))
    for k, rot in (("tags", "Tags"), ("conceitos", "Conceitos"), ("entidades", "Entidades")):
        if meta.get(k):
            partes.append(f'<p class="nota"><strong>{rot}:</strong> {e(", ".join(meta[k]))}.</p>')
    partes.append(f'<article aria-label="Texto da nota">{markdown_html(corpo_md, titulo_bruto)}</article>')
    lista = [x[0].name for x in notas_da_pasta(chave)]
    if p.name in lista:
        i = lista.index(p.name)
        nav = []
        if i + 1 < len(lista):  # mais antiga
            nav.append(f'<a href="/nota?p={quote(chave)}&amp;n={quote(lista[i + 1])}" rel="prev">Nota anterior</a>')
        if i > 0:
            nav.append(f'<a href="/nota?p={quote(chave)}&amp;n={quote(lista[i - 1])}" rel="next">Próxima nota</a>')
        nav.append(f'<a href="/tema?t={quote(chave)}">Todas as notas do tema</a>')
        partes.append('<nav class="ant-prox" aria-label="Entre as notas">' + "".join(nav) + "</nav>")
    return titulo, "".join(partes), bool(a)


def pg_doc(chave: str, rel: str, p: Path) -> tuple:
    titulo = p.stem.replace("-", " ").replace("_", " ").strip() or p.name
    voltar = f'<p><a href="/tema?t={quote(chave)}">Voltar ao tema {e(pastas()[chave]["nome"])}</a></p>'
    if p.suffix.lower() in EXT_AUDIO:
        src = f"/arquivo?t={quote(chave)}&c={quote(rel)}"
        return titulo, voltar + leitor(src, f"doc/{chave}/{rel}", mimetypes.guess_type(p.name)[0] or "audio/mp4"), True
    md = ler_texto(p)
    meta, corpo_md = separa_frontmatter(md) if p.suffix.lower() != ".txt" else ({}, md)
    t = titulo_de(p, md) if p.suffix.lower() != ".txt" else titulo
    if p.suffix.lower() == ".txt":
        corpo = f'<article aria-label="Texto do documento"><pre>{e(md)}</pre></article>'
    else:
        corpo = f'<article aria-label="Texto do documento">{markdown_html(corpo_md, t)}</article>'
    return t, voltar + corpo + f'<p><a href="/arquivo?t={quote(chave)}&amp;c={quote(rel)}&amp;baixar=1">Baixar o arquivo original</a></p>', False


def busca(q: str) -> list:
    alvo = sem_acento(q.strip())
    if len(alvo) < 2:
        return []
    ps, res, lidos = pastas(), [], 0
    for k, v in ps.items():
        fontes = [("nota", p, None) for p, _t, _m, _a in notas_da_pasta(k)]
        fontes += [("doc", p, rel) for rel, p in documentos_da_pasta(k) if p.suffix.lower() in EXT_NOTA]
        for tipo, p, rel in fontes:
            lidos += 1
            if lidos > 3000 or len(res) >= 50:
                return res
            try:
                if p.stat().st_size > MAX_TEXTO:
                    continue
                texto = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            plano = sem_acento(texto)
            titulo = titulo_da_nota(p, texto)
            pos = plano.find(alvo)
            if pos < 0 and alvo not in sem_acento(titulo):
                continue
            ini = max(0, pos - 70) if pos >= 0 else 0
            trecho = re.sub(r"\s+", " ", texto[ini:ini + 200]).strip() if len(texto) == len(plano) else re.sub(r"\s+", " ", separa_frontmatter(texto)[1][:200]).strip()
            link = f"/nota?p={quote(k)}&n={quote(p.name)}" if tipo == "nota" else f"/doc?t={quote(k)}&c={quote(rel)}"
            res.append((link, titulo, v["nome"], trecho))
    return res


def pg_busca(q: str) -> str:
    form = ('<form class="busca" method="get" action="/busca" role="search"><div><label for="q">Buscar nas notas e documentos de texto</label>'
            f'<input id="q" name="q" type="text" value="{e(q)}" autocomplete="off"></div><button type="submit">Buscar</button></form>')
    if len(q.strip()) < 2:
        return form + ('<p class="nota">Escreva pelo menos duas letras. A busca ignora acentos e maiúsculas.</p>' if q.strip() else "")
    r = busca(q)
    if not r:
        return form + '<p role="status">Nada encontrado.</p>'
    itens = "".join(f'<li><a href="{e(l)}">{e(t)}</a><span class="meta">{e(tema)}</span><span class="meta">{e(tr)}</span></li>' for l, t, tema, tr in r)
    return form + f'<p role="status">{plural(len(r), "resultado", "resultados")}.</p><ul class="lista">{itens}</ul>'


# ----------------------------------------------------------------------------------------
# Servidor
# ----------------------------------------------------------------------------------------
class Notas(BaseHTTPRequestHandler):
    server_version = "HeimdallNotas"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s %s\n" % (time.strftime("%H:%M:%S"), self.address_string(), (fmt % args).split("?")[0]))

    def _ip(self) -> str:
        return (self.headers.get("CF-Connecting-IP") or self.client_address[0]).strip()[:64]

    def _https(self) -> bool:
        return (self.headers.get("X-Forwarded-Proto", "").lower() == "https") or ("https" in self.headers.get("Cf-Visitor", ""))

    def _cabecalhos_base(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")

    def _enviar(self, status: int, corpo: bytes, tipo: str = "text/html; charset=utf-8", extra: list = None, nonce: str = "") -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        script = f" script-src 'nonce-{nonce}';" if nonce else ""
        self.send_header("Content-Security-Policy", f"default-src 'none'; style-src 'unsafe-inline';{script} media-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self._cabecalhos_base()
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _ir(self, destino: str, extra: list = None) -> None:
        self._enviar(303, b"", extra=[("Location", destino)] + (extra or []))

    def _pagina(self, status: int, titulo: str, corpo: str, sess: dict = None, script: str = "") -> None:
        nonce = secrets.token_urlsafe(12) if script else ""
        self._enviar(status, pagina(titulo, corpo, sess, nonce, script), nonce=nonce)

    def _sessao(self):
        c = SimpleCookie()
        try:
            c.load(self.headers.get("Cookie", ""))
        except Exception:  # noqa: BLE001
            return None, None
        m = c.get(COOKIE)
        token = m.value if m else ""
        return token, nuvem.sessao_valida(token)

    def _cookie(self, token: str, apagar: bool = False) -> tuple:
        v = f"{COOKIE}={'' if apagar else token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if apagar else nuvem.SESSAO_SEG}"
        if self._https():
            v += "; Secure"
        return ("Set-Cookie", v)

    def do_GET(self):  # noqa: N802
        self._despachar("GET")

    def do_POST(self):  # noqa: N802
        self._despachar("POST")

    def do_HEAD(self):  # noqa: N802
        self._despachar("GET")

    def _despachar(self, metodo: str) -> None:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        if host not in HOSTS_OK:
            self._enviar(421, b"Host nao permitido", "text/plain; charset=utf-8")
            return
        url = urlparse(self.path)
        rota, q = url.path, parse_qs(url.query)
        if rota == "/saude":
            self._enviar(200, b"ok", "text/plain; charset=utf-8")
            return
        sess = None
        try:
            if rota == "/entrar":
                self._entrar(metodo)
                return
            token, sess = self._sessao()
            if not sess:
                self._ir("/entrar")
                return
            if metodo == "POST":
                if rota != "/sair":
                    self._pagina(405, "Não permitido", '<p>Este site é somente de leitura.</p>', sess)
                    return
                n = min(int(self.headers.get("Content-Length") or 0), 4096)
                campos = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8", "replace")).items()}
                if not secrets.compare_digest(campos.get("csrf", ""), sess["csrf"]):
                    self._pagina(403, "Pedido recusado", "<p>Token de segurança inválido. Volte e tente de novo.</p>", sess)
                    return
                with nuvem._lock:
                    nuvem._sessoes.pop(token, None)
                self._ir("/entrar", [self._cookie("", apagar=True)])
                return
            self._get(rota, q, sess)
        except Exception as ex:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} erro em {rota}: {type(ex).__name__}: {str(ex)[:200]}\n")
            self._pagina(500, "Erro", '<p class="erro" role="alert">Não consegui abrir esta página.</p><p><a href="/">Voltar ao início</a></p>', sess)

    def _entrar(self, metodo: str) -> None:
        if metodo == "GET":
            self._enviar(200, pg_entrar())
            return
        ip = self._ip()
        if nuvem.login_bloqueado(ip):
            self._enviar(429, pg_entrar("Tentativas demais. Aguarde 15 minutos e tente de novo."), extra=[("Retry-After", "900")])
            return
        n = min(int(self.headers.get("Content-Length") or 0), 4096)
        campos = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode("utf-8", "replace"), keep_blank_values=True).items()}
        senha_ok = nuvem.confere_senha(campos.get("senha", "")[:200], nuvem.SENHA_HASH)
        passo = nuvem.totp_contador(nuvem.TOTP_SEGREDO, campos.get("codigo", ""))
        if not (senha_ok and passo is not None and nuvem.usar_contador(passo)):
            nuvem.registrar_falha(ip)
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} login recusado de {ip}\n")
            self._enviar(401, pg_entrar("Senha ou código incorretos."))
            return
        token, _ = nuvem.nova_sessao()
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} login aceito de {ip}\n")
        self._ir("/", [self._cookie(token)])

    def _get(self, rota: str, q: dict, sess: dict) -> None:
        p = lambda k: (q.get(k) or [""])[0]  # noqa: E731
        ps = pastas()
        if rota == "/":
            self._pagina(200, "Início", pg_inicio(), sess)
        elif rota == "/tema":
            if p("t") not in ps:
                return self._nao_achei(sess)
            nome, corpo = pg_tema(p("t"))
            self._pagina(200, nome, corpo, sess)
        elif rota == "/nota":
            base = ps.get(p("p"), {}).get("cofre")
            arq = arquivo_seguro(base, p("n"), EXT_NOTA)
            if not arq:
                return self._nao_achei(sess)
            titulo, corpo, tem_audio = pg_nota(p("p"), arq)
            self._pagina(200, titulo, corpo, sess, SCRIPT_LEITOR if tem_audio else "")
        elif rota == "/doc":
            arq = doc_seguro(ps.get(p("t"), {}).get("docs"), p("c"))
            if not arq:
                return self._nao_achei(sess)
            if arq.suffix.lower() not in EXT_NOTA | EXT_AUDIO:
                return self._ir(f"/arquivo?t={quote(p('t'))}&c={quote(p('c'))}")
            titulo, corpo, tem_audio = pg_doc(p("t"), p("c"), arq)
            self._pagina(200, titulo, corpo, sess, SCRIPT_LEITOR if tem_audio else "")
        elif rota == "/audio":
            arq = arquivo_seguro(ps.get(p("p"), {}).get("cofre") and ps[p("p")]["cofre"] / "audio", p("n"), EXT_AUDIO)
            self._servir(arq, sess, inline=True) if arq else self._nao_achei(sess)
        elif rota == "/arquivo":
            arq = doc_seguro(ps.get(p("t"), {}).get("docs"), p("c"))
            self._servir(arq, sess, inline=not p("baixar")) if arq else self._nao_achei(sess)
        elif rota == "/busca":
            self._pagina(200, "Buscar", pg_busca(p("q")), sess)
        else:
            self._nao_achei(sess)

    def _nao_achei(self, sess: dict) -> None:
        self._pagina(404, "Não encontrei", '<p>Esta página não existe ou não está liberada.</p><p><a href="/">Voltar ao início</a></p>', sess)

    def _servir(self, arq: Path, sess: dict, inline: bool = True) -> None:
        """Entrega o arquivo com suporte a Range (o Safari do iPhone exige para tocar áudio)."""
        ext = arq.suffix.lower()
        tipos = {".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".pdf": "application/pdf"}
        tipo = tipos.get(ext)
        mostrar = inline and tipo is not None
        tipo = tipo or "application/octet-stream"
        total = arq.stat().st_size
        ini, fim, status = 0, total - 1, 200
        r = self.headers.get("Range", "")
        m = re.match(r"^bytes=(\d*)-(\d*)$", r.strip())
        if m and (m.group(1) or m.group(2)) and total > 0:
            if m.group(1):
                ini = int(m.group(1))
                fim = min(int(m.group(2)), total - 1) if m.group(2) else total - 1
            else:
                ini = max(0, total - int(m.group(2)))
            if ini > fim or ini >= total:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{total}")
                self.send_header("Content-Length", "0")
                self._cabecalhos_base()
                self.end_headers()
                return
            status = 206
        tamanho = max(0, fim - ini + 1)
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(tamanho))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {ini}-{fim}/{total}")
        nome_seguro = re.sub(r'[^\w. -]', "_", arq.name)
        self.send_header("Content-Disposition", f'{"inline" if mostrar else "attachment"}; filename="{nome_seguro}"')
        self.send_header("Cache-Control", "private, max-age=600")
        self._cabecalhos_base()
        if not mostrar:
            self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with arq.open("rb") as f:
                f.seek(ini)
                restante = tamanho
                while restante > 0:
                    bloco = f.read(min(65536, restante))
                    if not bloco:
                        break
                    self.wfile.write(bloco)
                    restante -= len(bloco)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main() -> None:
    if not nuvem.SENHA_HASH or not nuvem.TOTP_SEGREDO:
        sys.exit("Sem senha e código configurados o Heimdall Notas não sobe. Rode: python3 heimdall_acesso.py --tudo")
    srv = ThreadingHTTPServer((HOST, PORT), Notas)
    srv.daemon_threads = True
    sys.stderr.write(f"{time.strftime('%H:%M:%S')} Heimdall Notas em http://{HOST}:{PORT} (cofre: {VAULT}; documentos: {KNOWLEDGE}; sites permitidos: {', '.join(sorted(HOSTS_OK))})\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
