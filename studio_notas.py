#!/usr/bin/env python3
"""Leitura das notas e dos documentos de estudo do cofre (brain/) e da pasta knowledge/, usada pela aba Notas do Studio Hub.

Aqui ficam só as funções de leitura: pastas e temas, título e data de cada nota, áudio, Markdown em HTML, busca e o
contexto do campo Perguntar. A tela e o login são do Studio Hub (studio_hub_notas.py). Somente leitura: nada aqui grava ou
apaga arquivos; caminhos conferidos contra fuga de pasta; HTML sempre escapado.

Variáveis opcionais: STUDIO_NOTAS_PASTAS, STUDIO_NOTAS_EXCLUIR, STUDIO_VAULT_DIR, STUDIO_KNOWLEDGE_DIR.

    python3 studio_notas.py --titulos-suspeitos     (lista as notas cujo título parece cortado)
"""
import html
import studio_pastas
import mimetypes
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

PROJECT_DIR = Path(__file__).resolve().parent


def carregar_env() -> None:
    """Do .env lê só as variáveis do Studio Hub e as pastas do cofre (as outras chaves do projeto não entram aqui)."""
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
        if chave.startswith("STUDIO_BIBLIOTECA_"):  # nome antigo das variáveis: continua valendo
            chave = "STUDIO_NOTAS_" + chave[len("STUDIO_BIBLIOTECA_"):]
        elif not (chave.startswith("STUDIO_NOTAS_") or chave in ("STUDIO_VAULT_DIR", "STUDIO_KNOWLEDGE_DIR", "STUDIO_LEARN")):
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        os.environ.setdefault(chave, valor)


carregar_env()
for _k in [k for k in os.environ if k.startswith("STUDIO_BIBLIOTECA_")]:  # idem para variáveis já no ambiente
    os.environ.setdefault("STUDIO_NOTAS_" + _k[len("STUDIO_BIBLIOTECA_"):], os.environ[_k])

import studio_lab as nuvem  # noqa: E402  (login, senha, código de 6 dígitos e sessões: o mesmo do painel Lab)
import studio_design as design  # noqa: E402  (padrão de interface: link lê, botão age)
import studio_paginacao as paginacao  # noqa: E402  (paginação em botões, igual no News e no Notas)

VAULT = Path(os.environ.get("STUDIO_VAULT_DIR", str(studio_pastas.brain(PROJECT_DIR)))).expanduser()
KNOWLEDGE = Path(os.environ.get("STUDIO_KNOWLEDGE_DIR", str(PROJECT_DIR / "knowledge"))).expanduser()
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


def learn_ativo() -> bool:
    """Com o Learn ligado, os estudos (os temas dos livros e os documentos de knowledge/) ficam só nele; o Notes mostra o resto do cofre
    (triagem, diários, privacidade, Second Brain, saúde). STUDIO_LEARN=0 devolve os estudos ao Notes."""
    return os.environ.get("STUDIO_LEARN", "0") == "1"


def pastas() -> dict:
    """Pastas liberadas: chave (slug) -> {'nome', 'cofre' (notas e áudios), 'docs' (documentos de knowledge)}."""
    cfg = os.environ.get("STUDIO_NOTAS_PASTAS", "*").strip() or "*"
    tudo = cfg == "*"
    liberadas = {slug(x) for x in cfg.split(",") if x.strip()}
    fora = {slug(x) for x in os.environ.get("STUDIO_NOTAS_EXCLUIR", "heimdall-digest").split(",") if x.strip()}
    res = {}
    estudo_no_learn = learn_ativo()
    temas_de_estudo = {slug(d.name) for d in _subdirs(KNOWLEDGE)}
    if not estudo_no_learn:
        for d in _subdirs(KNOWLEDGE):
            if slug(d.name) not in fora:
                res.setdefault(slug(d.name), {"nome": d.name[:1].upper() + d.name[1:], "cofre": None, "docs": d})
    for d in _subdirs(VAULT):
        k = slug(d.name)
        if k in fora or (estudo_no_learn and k in temas_de_estudo):
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
POR_PAGINA = 10
CSS = nuvem.CSS + paginacao.CSS + """
body{font-size:19px;line-height:1.7;max-width:46rem}
main h1{line-height:1.25;margin-top:1rem}h2,h3,h4{line-height:1.3;margin-top:1.8rem}
body{overflow-wrap:break-word}h1,h2,h3,h4,.lista a,.meta,td,th{overflow-wrap:anywhere;min-width:0}main{overflow-wrap:anywhere}
.lista{list-style:none;padding:0}.lista li{border-bottom:1px solid var(--linha);padding:.7rem 0}
.lista h3{margin:0 0 .2rem;font-size:1.15em}.lista a{font-weight:700;font-size:1.05em}.meta{color:var(--suave);font-size:.9em;display:block}
.leitor{background:var(--superficie);border:2px solid var(--acento);border-radius:.5rem;padding:.8rem;margin:1rem 0}.leitor audio{width:100%}
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





def contexto_notas(pergunta: str) -> str:
    """Trechos das notas que combinam com as palavras da pergunta (busca local, até 8 notas)."""
    palavras = [w for w in dict.fromkeys(sem_acento(pergunta).split()) if len(w) >= 4][:6]
    vistos, partes = set(), []
    for w in palavras:
        for link, titulo, tema, trecho in busca(w):
            if link in vistos:
                continue
            vistos.add(link)
            partes.append(f"Nota \"{titulo}\" ({tema}): {trecho}")
            if len(partes) >= 8:
                return "\n".join(partes)
    return "\n".join(partes) or "Nenhuma nota combina com as palavras da pergunta."









def plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def inicio_do_titulo(titulo: str, limite: int = 110) -> str:
    """Título para o texto do link. Só corta títulos muito longos (sempre num espaço, nunca no meio da palavra) e só então põe reticências."""
    t = re.sub(r"\s+", " ", titulo).strip()
    if len(t) > limite:
        corte = t.rfind(" ", 0, limite)
        t = t[:corte if corte >= limite // 2 else limite].rstrip(" ,;:.-") + "…"
    return t








def leitor(src: str, chave: str, tipo: str) -> str:
    vel = "".join(f'<button type="button" data-vel="{v}" aria-pressed="false">{rot}</button>' for v, rot in (("0.75", "0,75 vezes"), ("1", "1 vez"), ("1.25", "1,25 vezes"), ("1.5", "1,5 vezes")))
    return ('<section class="leitor" aria-labelledby="h-audio"><h2 id="h-audio">Ouvir</h2>'
            f'<audio id="leitor" controls preload="metadata" data-chave="{e(chave)}" src="{e(src)}" type="{e(tipo)}">Seu navegador não toca este áudio. <a href="{e(src)}">Baixar o áudio</a>.</audio>'
            '<div role="group" aria-label="Controles do áudio"><button type="button" data-salto="-15">Voltar 15 segundos</button>'
            f'<button type="button" data-salto="15">Avançar 15 segundos</button></div>'
            f'<div role="group" aria-label="Velocidade">{vel}</div><p id="leitor-estado" class="nota" role="status"></p></section>')




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
    return t, voltar + corpo + design.botao("/arquivo", "Baixar o arquivo original", {"t": chave, "c": rel, "baixar": "1"}), False


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




# ----------------------------------------------------------------------------------------
# Servidor
# ----------------------------------------------------------------------------------------


# ----------------------------------------------------------------------------------------
# Títulos suspeitos (cortados): python3 studio_notas.py --titulos-suspeitos
# ----------------------------------------------------------------------------------------
CONECTIVOS = {"de", "da", "do", "das", "dos", "e", "em", "com", "para", "por", "a", "o", "as", "os", "na", "no", "nas", "nos", "que", "ou", "um", "uma",
              "ao", "à", "sobre", "entre", "como", "se", "pela", "pelo", "sem", "the", "of", "and", "to", "in", "for", "with", "on", "a", "an"}
LIMITES_ANTIGOS = (80, 120, 150, 200, 220)   # tamanhos em que o StudioLibre cortou títulos gravados (45, 60 e 90 só cortavam o que aparece na tela, não o arquivo)


def motivos_de_corte(titulo: str) -> list:
    """Sinais de que o título foi cortado no meio. Lista vazia = parece inteiro."""
    t = unicodedata.normalize("NFC", titulo or "").strip()   # o macOS guarda acentos decompostos (c + cedilha); sem isto "edição" viraria "edi" + "o"
    if len(t) < 4:
        return []
    m = []
    if t.endswith("…") or t.endswith("..."):
        m.append("termina em reticências")
    if re.search(r"[,;:\-–—(/&+]$", t):
        m.append("termina em pontuação que pede continuação")
    ultima = re.findall(r"[\wÀ-ÿ']+", t)[-1:] or [""]
    if ultima[0] in CONECTIVOS and len(t.split()) > 2:
        m.append(f'termina na palavra "{ultima[0]}", que pede continuação')
    if len(t) in LIMITES_ANTIGOS and t[-1].isalnum():
        m.append(f"tem exatamente {len(t)} caracteres, um tamanho em que o StudioLibre já cortou títulos")
    if t.count("(") > t.count(")") or t.count("[") > t.count("]") or t.count('"') % 2 or t.count("“") > t.count("”"):
        m.append("tem parêntese ou aspas sem fechar")
    return m


def titulos_suspeitos() -> list:
    """[(nome da pasta, arquivo, título gravado no arquivo, [motivos])] das notas que o site publica."""
    res = []
    for chave, info in sorted(pastas().items()):
        for p, _, _, _ in notas_da_pasta(chave):
            bruto = titulo_de(p)
            ms = motivos_de_corte(bruto)
            if ms:
                res.append((info["nome"], p, bruto, ms))
    return res


def mostrar_titulos_suspeitos() -> None:
    lista = titulos_suspeitos()
    if not lista:
        print("Nenhum título com sinal de corte nas notas publicadas no site.")
        return
    print(f"{len(lista)} nota(s) com título que parece cortado:")
    for i, (pasta, p, titulo, ms) in enumerate(lista, 1):
        print(f"{i}. Pasta {pasta}, arquivo {p}")
        print(f"   Título: {titulo}")
        print(f"   Motivo: {'; '.join(ms)}.")
    print("\nPara corrigir: abra o arquivo e edite a linha que começa com '# ' (o título); o site passa a mostrar o novo título na hora. "
          "A cópia no app Notas tem o título antigo na primeira linha da nota; se quiser, ajuste lá também.")


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Leitura das notas do Studio Hub")
    ap.add_argument("--titulos-suspeitos", action="store_true", help="lista as notas cujo título parece cortado e sai")
    if ap.parse_args().titulos_suspeitos:
        mostrar_titulos_suspeitos()


if __name__ == "__main__":
    main()
