#!/usr/bin/env python3
"""Agente local do Heimdall: ponte entre o n8n (no Docker) e o app Notas do Mac.

Só usa a biblioteca padrão do Python. Escuta em 127.0.0.1:8003 (HEIMDALL_AGENTE_HOST /
HEIMDALL_AGENTE_PORT mudam isso) e exige o cabeçalho X-Heimdall-Token igual a
HEIMDALL_AGENTE_TOKEN (o start_heimdall.sh gera e guarda no .env).

Rotas:
    GET  /saude                         sem token; diz se o agente está de pé
    GET  /notas/alteradas?desde=&quieto=&limite=
                                        notas do app Notas alteradas depois de "desde" (segundos desde 1970),
                                        paradas há pelo menos "quieto" segundos, da mais antiga para a mais nova
    GET  /notas/nota?id=                texto simples de uma nota
    GET  /notas/privadas                pastas privadas e os ids das notas protegidas (usado pelo limpar_privadas.py)
    POST /notas/gravar                  {"pasta": "Heimdall ...", "titulo": "...", "markdown": "..."}
                                        cria ou atualiza uma nota e grava uma cópia .md na pasta do cofre

Pastas privadas: notas da pasta "Privado" (e de outras listadas em HEIMDALL_NOTAS_PRIVADAS) nunca são listadas nem lidas.
Segurança: LÊ qualquer nota (menos as privadas), mas só ESCREVE em pastas cujo nome começa com "Heimdall" (as notas
pessoais nunca são alteradas) e só grava arquivos dentro do cofre (HEIMDALL_VAULT_DIR, padrão
./cerebro). Notas das pastas "Heimdall*" e da lixeira não entram na lista de alteradas.

Teste (precisa autorizar o controle do app Notas na primeira vez):
    python heimdall_agente.py --teste
"""
import argparse
import hmac
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_DIR = Path(__file__).resolve().parent
HOST = os.environ.get("HEIMDALL_AGENTE_HOST", "127.0.0.1")
PORT = int(os.environ.get("HEIMDALL_AGENTE_PORT", "8003"))
TOKEN = os.environ.get("HEIMDALL_AGENTE_TOKEN", "")
VAULT = Path(os.environ.get("HEIMDALL_VAULT_DIR", str(PROJECT_DIR / "cerebro"))).expanduser()
PREFIXO_ESCRITA = "Heimdall"
IGNORAR_PASTAS = {
    "recently deleted", "apagadas recentemente", "excluídas recentemente", "notas excluídas",
    "excluidas recentemente", "notas apagadas",
}
IGNORAR_PASTAS |= {p.strip().lower() for p in os.environ.get("HEIMDALL_NOTAS_IGNORAR", "").split(",") if p.strip()}
# Pastas do app Notas que NUNCA são lidas nem analisadas (notas muito pessoais). "Privado" sempre vale; acrescente
# outras no .env com HEIMDALL_NOTAS_PRIVADAS="Privado,Diário". As subpastas também ficam protegidas.
PRIVADAS: list[str] = []
for _nome in ["Privado"] + os.environ.get("HEIMDALL_NOTAS_PRIVADAS", "").split(","):
    _nome = _nome.strip()
    if _nome and _nome.lower() not in [x.lower() for x in PRIVADAS] and re.fullmatch(r'[^"\\\n\r\t]{1,80}', _nome):
        PRIVADAS.append(_nome)
MAX_CORPO = 1_000_000
MAX_TEXTO_NOTA = 20_000
OSASCRIPT_TIMEOUT = 120
_lock = threading.Lock()  # o app Notas atende um pedido de cada vez

# ----------------------------------------------------------------------------------------
# AppleScript
# ----------------------------------------------------------------------------------------
AS_LISTAR = r'''-- heimdall:listar
on pad(n)
	return text -2 thru -1 of ("0" & (n as integer))
end pad
on iso(d)
	return ((year of d) as string) & "-" & my pad((month of d) as integer) & "-" & my pad(day of d) & " " & my pad(hours of d) & ":" & my pad(minutes of d) & ":" & my pad(seconds of d)
end iso
on run argv
	set secs to (item 1 of argv) as integer
	set quietSecs to (item 2 of argv) as integer
	set cutoff to (current date) - secs
	set recent to (current date) - quietSecs
	set out to ""
	set seen to {}
	tell application "Notes"
		-- 1) pasta por pasta (o app Notas nem sempre deixa ler a pasta a partir da nota)
		try
			repeat with f in (every folder)
				set fname to ""
				try
					set fname to name of f
				end try
				try
					set ns to (every note of f whose modification date > cutoff and modification date < recent)
					repeat with n in ns
						try
							set nid to id of n
							set out to out & nid & tab & fname & tab & (name of n) & tab & (my iso(modification date of n)) & linefeed
							set end of seen to nid
						end try
					end repeat
				end try
			end repeat
		end try
		-- 2) qualquer nota que não apareceu em nenhuma pasta entra com a pasta em branco
		set ns2 to (every note whose modification date > cutoff and modification date < recent)
		repeat with n in ns2
			try
				set nid to id of n
				if seen does not contain nid then
					set out to out & nid & tab & "" & tab & (name of n) & tab & (my iso(modification date of n)) & linefeed
				end if
			end try
		end repeat
	end tell
	return out
end run
'''

AS_LER = r'''-- heimdall:ler
on run argv
	set theId to item 1 of argv
	tell application "Notes"
		set n to first note whose id is theId
		return (name of n) & linefeed & "<<<CORPO>>>" & linefeed & (plaintext of n)
	end tell
end run
'''

AS_GRAVAR = r'''-- heimdall:gravar
on run argv
	set folderName to item 1 of argv
	set noteTitle to item 2 of argv
	set htmlBody to item 3 of argv
	tell application "Notes"
		tell default account
			if not (exists folder folderName) then
				make new folder with properties {name:folderName}
			end if
			set f to folder folderName
			set found to (every note of f whose name is noteTitle)
			if (count of found) > 0 then
				set body of (item 1 of found) to htmlBody
				return "atualizada"
			else
				make new note at f with properties {name:noteTitle, body:htmlBody}
				return "criada"
			end if
		end tell
	end tell
end run
'''

AS_PRIVADAS = r'''-- heimdall:privadas
on lista(f)
	set t to ""
	tell application "Notes"
		try
			set ids to (id of every note of f)
			repeat with i in ids
				set t to t & (i as string) & linefeed
			end repeat
		end try
		try
			repeat with sf in (every folder of f)
				set t to t & my lista(sf)
			end repeat
		end try
	end tell
	return t
end lista
on run argv
	set out to ""
	tell application "Notes"
		repeat with nm in argv
			try
				repeat with f in (every folder whose name is (nm as string))
					set out to out & my lista(f)
				end repeat
			end try
		end repeat
	end tell
	return out
end run
'''

AS_CONTAR = r'''-- heimdall:contar
tell application "Notes" to return (count of notes) as string
'''


def osascript(script: str, *args: str) -> str:
    """Roda um AppleScript (arquivo temporário) com argumentos e devolve a saída."""
    with tempfile.NamedTemporaryFile("w", suffix=".applescript", delete=False, encoding="utf-8") as f:
        f.write(script)
        caminho = f.name
    try:
        r = subprocess.run(
            ["osascript", caminho, *args],
            capture_output=True, text=True, timeout=OSASCRIPT_TIMEOUT,
        )
    finally:
        try:
            os.unlink(caminho)
        except OSError:
            pass
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "osascript falhou").strip()[:400])
    return r.stdout.rstrip("\n")


# ----------------------------------------------------------------------------------------
# Operações
# ----------------------------------------------------------------------------------------
# Notas que o próprio Heimdall cria (espelhos do Second Brain e digests). Também são ignoradas pelo título,
# para não entrarem num laço caso o app Notas não informe a pasta de uma nota.
TITULO_DO_HEIMDALL = re.compile(r"^(C[ée]rebro: |Digest \d{4}-\d{2}-\d{2} \d{2}h$)")


def pasta_ignorada(nome: str) -> bool:
    n = nome.strip().lower()
    return n.startswith(PREFIXO_ESCRITA.lower()) or n in IGNORAR_PASTAS or n in {p.lower() for p in PRIVADAS}


_cache_privadas: tuple[float, set] = (0.0, set())


def ids_privados() -> set:
    """Identificadores das notas das pastas privadas (e subpastas). Se não der para consultar, falha: na dúvida,
    nenhuma nota é entregue (a privacidade não pode depender de a consulta ter funcionado)."""
    global _cache_privadas
    if time.time() - _cache_privadas[0] < 20:
        return _cache_privadas[1]
    with _lock:
        saida = osascript(AS_PRIVADAS, *PRIVADAS)
    ids = {l.strip() for l in saida.splitlines() if l.strip()}
    _cache_privadas = (time.time(), ids)
    return ids


def notas_alteradas(desde: float, quieto: int, limite: int) -> list[dict]:
    privadas = ids_privados()
    agora = time.time()
    janela = int(max(agora - desde, 0)) + 5
    janela = min(janela, 60 * 60 * 24 * 90)  # no máximo 90 dias para trás
    with _lock:
        saida = osascript(AS_LISTAR, str(janela), str(max(quieto, 0)))
    notas = []
    for linha in saida.splitlines():
        partes = linha.split("\t")
        if len(partes) < 4:
            continue
        nid, pasta, titulo, data = partes[0], partes[1], "\t".join(partes[2:-1]), partes[-1]
        if nid in privadas or pasta_ignorada(pasta) or TITULO_DO_HEIMDALL.match(titulo.strip()):
            continue
        try:
            mod = datetime.strptime(data.strip(), "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            continue
        if mod <= desde:
            continue
        notas.append({"id": nid, "pasta": pasta, "titulo": titulo, "mod": mod})
    notas.sort(key=lambda n: n["mod"])
    return notas[: max(limite, 1)]


def ler_nota(nid: str) -> dict:
    if nid in ids_privados():
        raise PermissionError("nota de pasta privada")
    with _lock:
        saida = osascript(AS_LER, nid)
    titulo, _, corpo = saida.partition("\n<<<CORPO>>>\n")
    return {"id": nid, "titulo": titulo.strip(), "texto": corpo[:MAX_TEXTO_NOTA]}


def slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()
    return t[:80] or "nota"


def inline(texto: str) -> str:
    """Escapa HTML e converte **negrito**, `codigo` e [texto](url) de uma linha."""
    t = html.escape(texto, quote=False)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`([^`]+)`", r"<tt>\1</tt>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
    return t


def markdown_para_html(titulo: str, md: str) -> str:
    partes = [f"<div><h1>{html.escape(titulo, quote=False)}</h1></div>"]
    em_lista = False
    for bruta in md.splitlines():
        linha = bruta.rstrip()
        m_item = re.match(r"^\s*[-*]\s+(.*)$", linha)
        if m_item:
            if not em_lista:
                partes.append("<ul>")
                em_lista = True
            partes.append(f"<li>{inline(m_item.group(1))}</li>")
            continue
        if em_lista:
            partes.append("</ul>")
            em_lista = False
        m_tit = re.match(r"^(#{1,3})\s+(.*)$", linha)
        if m_tit:
            nivel = min(len(m_tit.group(1)) + 1, 3)  # o título da nota já é h1
            partes.append(f"<div><h{nivel}>{inline(m_tit.group(2))}</h{nivel}></div>")
        elif not linha.strip():
            partes.append("<div><br></div>")
        else:
            partes.append(f"<div>{inline(linha)}</div>")
    if em_lista:
        partes.append("</ul>")
    return "".join(partes)


def gravar(pasta: str, titulo: str, markdown: str) -> dict:
    if not pasta.startswith(PREFIXO_ESCRITA):
        raise PermissionError(f"só escrevo em pastas que começam com '{PREFIXO_ESCRITA}'")
    if not titulo.strip() or len(titulo) > 200:
        raise ValueError("título vazio ou longo demais")
    if not re.fullmatch(r"Heimdall[\w .-]{0,60}", pasta):
        raise ValueError("nome de pasta inválido (use letras, números, espaço, ponto, hífen)")
    titulo = titulo.replace("\n", " ").replace("\t", " ").strip()
    # Cópia em Markdown no cofre (arquivo de verdade, com o frontmatter intacto).
    destino = VAULT / slug(pasta)
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"{slug(titulo)}.md"
    if arquivo.resolve().parent != destino.resolve():
        raise PermissionError("caminho fora do cofre")
    arquivo.write_text(markdown, encoding="utf-8")
    # Nota no app Notas (a primeira linha vira o nome da nota).
    corpo_html = markdown_para_html(titulo, markdown)
    with _lock:
        estado = osascript(AS_GRAVAR, pasta, titulo, corpo_html)
    return {"ok": True, "nota": estado, "arquivo": str(arquivo)}


# ----------------------------------------------------------------------------------------
# Servidor HTTP
# ----------------------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "HeimdallAgente/1.0"

    def log_message(self, fmt, *args):  # sem IP nem parâmetros no log
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args if args else fmt))

    def _json(self, status: int, dado: dict):
        corpo = json.dumps(dado, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _autorizado(self) -> bool:
        enviado = self.headers.get("X-Heimdall-Token", "")
        return bool(TOKEN) and hmac.compare_digest(enviado.encode(), TOKEN.encode())

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/saude":
            return self._json(200, {"ok": True, "versao": 1})
        if not self._autorizado():
            return self._json(401, {"erro": "token inválido"})
        try:
            if u.path == "/notas/alteradas":
                desde = float(q.get("desde", ["0"])[0])
                quieto = int(q.get("quieto", ["120"])[0])
                limite = int(q.get("limite", ["3"])[0])
                notas = notas_alteradas(desde, quieto, limite)
                return self._json(200, {"notas": notas, "total": len(notas)})
            if u.path == "/notas/privadas":
                return self._json(200, {"pastas": PRIVADAS, "ids": sorted(ids_privados())})
            if u.path == "/notas/nota":
                nid = q.get("id", [""])[0]
                if not nid:
                    return self._json(400, {"erro": "falta o id"})
                return self._json(200, ler_nota(nid))
            return self._json(404, {"erro": "rota desconhecida"})
        except PermissionError as e:
            return self._json(403, {"erro": str(e)})
        except Exception as e:  # noqa: BLE001
            return self._json(500, {"erro": str(e)[:400]})

    def do_POST(self):
        u = urlparse(self.path)
        if not self._autorizado():
            return self._json(401, {"erro": "token inválido"})
        try:
            tam = int(self.headers.get("Content-Length", "0"))
            if tam <= 0 or tam > MAX_CORPO:
                return self._json(413, {"erro": "corpo ausente ou grande demais"})
            dado = json.loads(self.rfile.read(tam).decode("utf-8"))
            if u.path == "/notas/gravar":
                r = gravar(str(dado.get("pasta", "")), str(dado.get("titulo", "")), str(dado.get("markdown", "")))
                return self._json(200, r)
            return self._json(404, {"erro": "rota desconhecida"})
        except PermissionError as e:
            return self._json(403, {"erro": str(e)})
        except (ValueError, json.JSONDecodeError) as e:
            return self._json(400, {"erro": str(e)[:200]})
        except Exception as e:  # noqa: BLE001
            return self._json(500, {"erro": str(e)[:400]})


def teste() -> int:
    print("1. Conferindo o acesso ao app Notas (se aparecer um pedido de permissão, autorize)...")
    try:
        total = osascript(AS_CONTAR)
    except Exception as e:  # noqa: BLE001
        print(f"   Falhou: {e}")
        print("   Autorize o Terminal em Ajustes do Sistema > Privacidade e Segurança > Automação > Notas.")
        return 1
    print(f"   Notas encontradas: {total}")
    try:
        print(f"   Pastas privadas ({', '.join(PRIVADAS)}): {len(ids_privados())} nota(s) protegida(s), nunca lidas.")
    except Exception as e:  # noqa: BLE001
        print(f"   Não consegui consultar as pastas privadas ({e}); por segurança o agente não entrega nenhuma nota até isso funcionar.")
        return 1
    print("2. Listando notas alteradas nas últimas 24 horas (sem o intervalo de repouso)...")
    try:
        notas = notas_alteradas(time.time() - 86400, 0, 5)
    except Exception as e:  # noqa: BLE001
        print(f"   Falhou: {e}")
        return 1
    print(f"   Encontradas: {len(notas)}")
    for n in notas:
        print(f"   - {n['titulo']} (pasta {n['pasta']})")
    if notas:
        c = ler_nota(notas[0]["id"])
        print(f"3. Leitura da primeira nota: {len(c['texto'])} caracteres de texto.")
    print("Tudo certo." if total.isdigit() else "Resposta inesperada do app Notas.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Agente local do Heimdall para o app Notas")
    ap.add_argument("--teste", action="store_true", help="só confere o acesso ao app Notas e sai")
    args = ap.parse_args()
    if args.teste:
        return teste()
    if not TOKEN or len(TOKEN) < 16:
        print("Erro: defina HEIMDALL_AGENTE_TOKEN (16+ caracteres) no .env.", file=sys.stderr)
        return 1
    VAULT.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Agente do Heimdall em http://{HOST}:{PORT} (cofre: {VAULT})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
