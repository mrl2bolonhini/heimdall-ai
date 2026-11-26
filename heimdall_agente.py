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
    POST /avisos/gravar                 {"servico": "saude"|"financas", "titulo": "...", "markdown": "...", "bark": true (opcional)}
    POST /calendario/desfazer           {"titulo": "...", "data": "AAAA-MM-DD"}  (apaga o evento criado; o Studio Notes usa no botão Desfazer)
    POST /lembretes/desfazer            {"titulo": "..."}
    POST /notas/gravar                  {"pasta": "Digest", "titulo": "...", "markdown": "...", "audio": "texto a narrar (opcional)"}
                                        cria ou atualiza uma nota e grava uma cópia .md na pasta do cofre
    GET  /banco/resumo                  contagens e período de cada tabela do banco pessoal (SQLite)
    GET  /banco/esquema                 descrição das tabelas
    POST /saude/hae                     corpo do Health Auto Export (treinos, ECG, frequência cardíaca, sintomas...); grava no banco (heimdall_saude.py)
    POST /banco/gravar                  {"tabela": "saude_diaria", "registros": [{"dia": "2026-11-10", "metrica": "passos", "valor": 8000}]}
                                        insere ou atualiza pela chave primária (tabelas: saude_diaria, saude_resumos, diarios, analises)
    POST /banco/consultar               {"sql": "SELECT ...", "limite": 200}  só um SELECT, em conexão somente leitura
    POST /saude/documento               corpo = o arquivo (PDF, JPG, PNG ou HEIC) de um exame, receita ou encaminhamento; cabeçalho X-Heimdall-Nome com o nome.
                                        Aceita o X-Heimdall-Token ou o código de envio do atalho (X-Heimdall-Upload = HEIMDALL_EXAMES_TOKEN). O arquivo vai para a
                                        pasta de entrada, é lido no Mac e fica pendente até você confirmar (heimdall_exames.py)
    POST /saude/relatorio-semanal       {}  monta o relatório da semana, grava na aba Avisos do Studio Health e avisa pelo Bark (texto genérico)
    POST /triagem/criar                 {"id": "origem estável", "titulo": "...", "resumo": "...", "nivel": "critico|alto|medio", "fonte": "justica"}
                                        cria um lembrete na lista "Heimdall: Triagem" (não duplica) e o registra no banco
    POST /triagem/ciclo                 {}  lê os lembretes, registra o que você concluiu, reclassificou ou adiou e avisa pelo Bark
                                        quem está pendente (chamado pelo n8n a cada 15 minutos; regras em heimdall_triagem.py)
    GET  /triagem/estado                itens pendentes da triagem
    POST /backup/executar               {}  cópia criptografada do banco para os destinos do .env (pasta e/ou R2); regras em heimdall_backup.py
    POST /backup/verificar              {}  baixa a cópia mais recente de cada destino, decifra e confere a integridade
    POST /seguranca/executar            {"tarefa": "logs|commits|exposicao"}  o dolphin3-cyber-8b analisa os dados que o script coleta, grava a nota em
                                        Segurança e devolve {gravidade, linha, gravar...} para o n8n decidir o aviso (regras em heimdall_seguranca.py)
    GET  /backup/estado                 última cópia bem-sucedida e última tentativa

Pastas privadas: notas da pasta "Privado" (e de outras listadas em HEIMDALL_NOTAS_PRIVADAS) nunca são listadas nem lidas.
Segurança: LÊ qualquer nota (menos as privadas), mas só ESCREVE em pastas cujo nome começa com "Heimdall" (as notas
pessoais nunca são alteradas) e só grava arquivos dentro do cofre (HEIMDALL_VAULT_DIR, padrão
./brain). Notas das pastas "Heimdall*" e da lixeira não entram na lista de alteradas.

Teste (precisa autorizar o controle do app Notas na primeira vez):
    python heimdall_agente.py --teste
"""
import argparse
import heimdall_pastas
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
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import urllib.parse

import heimdall_backup as backup
import heimdall_continuidade as continuidade
import heimdall_banco as banco
import heimdall_exames as exames
import heimdall_saude as saude
import heimdall_avisos as avisos
import heimdall_avisos_mac as avisos_mac
import heimdall_seguranca as seguranca
import heimdall_triagem as triagem
import heimdall_eventkit as eventkit
import heimdall_voz as dicionario_voz

PROJECT_DIR = Path(__file__).resolve().parent


def _carregar_env_da_voz() -> None:
    """Quando rodado à mão (python3 heimdall_agente.py --voz), o terminal não leu o .env: pega só as opções de voz de lá."""
    try:
        for linha in (PROJECT_DIR / ".env").read_text(encoding="utf-8").splitlines():
            chave, sep, valor = linha.partition("=")
            chave = chave.strip()
            if sep and (chave.startswith("HEIMDALL_VOZ") or chave == "HEIMDALL_ESTUDO_AUDIO") and chave not in os.environ:
                os.environ[chave] = valor.strip().strip("'\"")
    except OSError:
        pass


_carregar_env_da_voz()
HOST = os.environ.get("HEIMDALL_AGENTE_HOST", "127.0.0.1")
PORT = int(os.environ.get("HEIMDALL_AGENTE_PORT", "8003"))
TOKEN = os.environ.get("HEIMDALL_AGENTE_TOKEN", "")
VAULT = Path(os.environ.get("HEIMDALL_VAULT_DIR", str(heimdall_pastas.brain(PROJECT_DIR)))).expanduser()
PREFIXO_ESCRITA = "Heimdall"  # nomes antigos ("Heimdall Cérebro" etc.) continuam aceitos e ignorados
# Pastas do app Notas que o Heimdall cria e onde só ele escreve. Nunca são lidas como fonte (evita laço) e as
# suas notas pessoais nunca são alteradas. Para mudar, use no .env: HEIMDALL_PASTAS_PROPRIAS="Monitor de Privacidade,Digest,Cérebro"
PASTAS_PROPRIAS = [p.strip() for p in os.environ.get("HEIMDALL_PASTAS_PROPRIAS", "Monitor de Privacidade,Digest,Second Brain,Cérebro").split(",") if p.strip()]
for _p in ("Saúde", "Segurança", "GitOps", "Second Brain", "Cérebro"):  # sempre permitidas, mesmo com o .env personalizado ("Cérebro" é o nome antigo)
    if _p not in PASTAS_PROPRIAS:
        PASTAS_PROPRIAS.append(_p)
# No app Notas, tudo que o Heimdall grava fica dentro de uma pasta-raiz: Heimdall-ai/Digest, Heimdall-ai/Saúde,
# Heimdall-ai/Estudos/<tema> etc. Os fluxos continuam mandando só o nome da pasta; o agente monta o caminho.
# Para voltar às pastas soltas: HEIMDALL_NOTAS_RAIZ="" no .env.
RAIZ_NOTAS = os.environ.get("HEIMDALL_NOTAS_RAIZ", "Heimdall-ai").strip()
# Subpasta do cofre de cada pasta (mantém os nomes antigos para não separar o que já foi gravado).
PASTA_DO_COFRE = {"Monitor de Privacidade": "heimdall-privacidade", "Digest": "heimdall-digest", "Cérebro": "heimdall-cerebro", "Second Brain": "heimdall-cerebro"}


# Temas de estudo: cada subpasta de knowledge/ vira uma pasta no app Notas com o nome da tag do tema (o mesmo nome que
# o ingest_docs.py usa: minúsculas, sem acentos, hífens). Pastas novas de conhecimento ganham a pasta de notas sozinhas.
KNOWLEDGE = Path(os.environ.get("HEIMDALL_KNOWLEDGE_DIR", str(PROJECT_DIR / "knowledge"))).expanduser()
# Voz do áudio dos estudos. Vazio (padrão) = a melhor voz em português instalada (Premium, depois Aprimorada, depois a padrão).
# Para fixar uma: HEIMDALL_VOZ="Luciana (Enhanced)" ((Aprimorada) vale igual). Os nomes saem de: say -v '?' | grep pt_
VOZ = os.environ.get("HEIMDALL_VOZ", "").strip()
# Velocidade na escala de porcentagem da fala do macOS (0 a 100). 65 ≈ 350 palavras por minuto. Para fixar palavras por minuto: HEIMDALL_VOZ_PPM=300
try:
    VELOCIDADE = max(0.0, min(100.0, float(os.environ.get("HEIMDALL_VOZ_VELOCIDADE", "65"))))
except ValueError:
    VELOCIDADE = 65.0
try:
    PPM = int(os.environ.get("HEIMDALL_VOZ_PPM", "0"))
except ValueError:
    PPM = 0
AUDIO_ATIVO = os.environ.get("HEIMDALL_ESTUDO_AUDIO", "1") != "0"
# Atalho do app Atalhos que gera o áudio (permite vozes que o say não enxerga, como a Siri). O atalho recebe o texto como entrada
# e devolve o áudio ("Criar áudio falado a partir de texto"); a velocidade e a voz ficam no próprio atalho. Vazio = usa o say.
ATALHO = os.environ.get("HEIMDALL_VOZ_ATALHO", "").strip()


def tema_slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "geral"


def temas_conhecimento() -> set:
    temas = {"geral"}
    try:
        for d in KNOWLEDGE.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                temas.add(tema_slug(d.name))
    except OSError:
        pass
    return temas


def norm_nome(s: str) -> str:
    """Compara nomes de pasta sem ligar para maiúsculas, acentos, espaços e pontos no começo (".privado" = "Privado")."""
    t = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip(" .")
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
MAX_CORPO_SAUDE = 64 * 1024 * 1024   # exportações com ECG (milhares de leituras por gravação) são grandes
MAX_CORPO_DOC = exames.MAX_BYTES + 4096   # um exame, receita ou encaminhamento enviado do iPhone
TOKEN_UPLOAD = os.environ.get("HEIMDALL_EXAMES_TOKEN", "")   # só serve para /saude/documento
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
on partes(txt)
	set AppleScript's text item delimiters to "/"
	set l to text items of txt
	set AppleScript's text item delimiters to ""
	return l
end partes
-- Acha (ou cria) a pasta pelo caminho "Raiz/Sub/Sub". A primeira só vale se estiver no nível de cima da conta;
-- as seguintes, só se forem filhas da anterior. Assim "Digest" solto e "Heimdall-ai/Digest" não se confundem.
on achar_pasta(caminho)
	tell application "Notes"
		tell default account
			set atual to missing value
			repeat with nm in my partes(caminho)
				set nome to contents of nm
				set achada to missing value
				if atual is missing value then
					set cand to every folder
				else
					set cand to every folder of atual
				end if
				repeat with f in cand
					if (name of f) is nome then
						set vale to true
						if atual is missing value then
							try
								set vale to ((class of (container of f)) is account)
							on error
								set vale to true
							end try
						end if
						if vale then
							set achada to contents of f
							exit repeat
						end if
					end if
				end repeat
				if achada is missing value then
					if atual is missing value then
						set achada to make new folder with properties {name:nome}
					else
						set achada to make new folder at atual with properties {name:nome}
					end if
				end if
				set atual to achada
			end repeat
			return atual
		end tell
	end tell
end achar_pasta
on run argv
	set folderName to item 1 of argv
	set noteTitle to item 2 of argv
	set htmlBody to item 3 of argv
	tell application "Notes"
		tell default account
			set f to my achar_pasta(folderName)
			set found to (every note of f whose name is noteTitle)
			if (count of found) > 0 then
				set body of (item 1 of found) to htmlBody
				return "atualizada"
			else
				make new note at f with properties {body:htmlBody}
				return "criada"
			end if
		end tell
	end tell
end run
'''

AS_NOMES_PASTAS = r'''-- heimdall:nomes-pastas
set t to ""
tell application "Notes"
	repeat with f in (every folder)
		try
			set t to t & (name of f) & linefeed
		end try
	end repeat
end tell
return t
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


# Apps do macOS que o Heimdall usa por AppleScript. Um "tell application" abre o app na sua frente se ele estiver fechado.
# Por isso o Heimdall abre cada um escondido e em segundo plano (open -g -j), e fecha de novo depois de alguns segundos
# sem uso, mas SÓ se foi ele que abriu e se você não estiver com o app na frente. Se você já deixou o app aberto, nada muda.
APPS_ALVO = ("Notes", "Reminders", "Calendar")
SOSSEGO_APP = 20          # segundos sem uso até fechar um app que o Heimdall abriu (só se HEIMDALL_APPS_FECHAR=1)
# Por padrão o Heimdall NÃO fecha o app depois de usar: fechar e abrir de novo a cada ciclo é justamente o que faz o app aparecer toda hora.
FECHAR_APPS = os.environ.get("HEIMDALL_APPS_FECHAR", "0").strip() == "1"
_apps_lock = threading.RLock()
_apps_nossos: set[str] = set()                   # apps abertos pelo Heimdall
_apps_timers: dict[str, threading.Timer] = {}    # fechamento agendado de cada um


def _app_rodando(nome: str) -> bool:
    try:
        return subprocess.run(["pgrep", "-x", nome], capture_output=True, timeout=10).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _app_na_frente(nome: str) -> bool:
    """True se o app está em primeiro plano (você está usando). Em caso de dúvida, diz que não."""
    try:
        asn = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True, timeout=10).stdout.strip()
        if not asn:
            return False
        info = subprocess.run(["lsappinfo", "info", "-only", "name", asn], capture_output=True, text=True, timeout=10).stdout
        return f'"{nome}"' in info
    except Exception:  # noqa: BLE001
        return False


def _fechar_app(nome: str) -> None:
    with _apps_lock:
        _apps_timers.pop(nome, None)
        if nome not in _apps_nossos:
            return
        _apps_nossos.discard(nome)
        if _app_na_frente(nome):
            return  # você abriu ou está usando: deixa aberto
        try:
            subprocess.run(["osascript", "-e", f'tell application "{nome}" to quit'], capture_output=True, timeout=30)
        except Exception:  # noqa: BLE001
            pass


def _apps_do_script(script: str) -> list[str]:
    return [n for n in APPS_ALVO if f'application "{n}"' in script]


BUNDLES_APPS = {"Notes": "com.apple.Notes", "Reminders": "com.apple.reminders", "Calendar": "com.apple.iCal"}
ASSENTAR_APP_S = 1.2      # espera o app terminar de abrir antes de escondê-lo e de mandar o AppleScript


def _esconder_app(nome: str) -> None:
    """Esconde o app (como Command+H), sem permissão especial. Só é chamado logo depois de o próprio Heimdall abri-lo:
    o Notas e o Lembretes passam à frente ao abrir mesmo com open -g -j."""
    bundle = BUNDLES_APPS.get(nome)
    if not bundle:
        return
    # no JXA um método sem argumento pode ser chamado como propriedade ou como função; o código aceita os dois jeitos
    js = ("ObjC.import('AppKit'); var a = $.NSRunningApplication.runningApplicationsWithBundleIdentifier('%s'); "
          "for (var i = 0; i < a.count; i++) { var r = a.objectAtIndex(i); var h = r.hide; if (typeof h === 'function') { r.hide(); } }" % bundle)
    try:
        r = subprocess.run(["osascript", "-l", "JavaScript", "-e", js], capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} não consegui esconder {nome}: {(r.stderr or r.stdout).strip()[:200]}\n")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} não consegui esconder {nome}: {type(e).__name__}\n")


def _preparar_apps(script: str) -> tuple[list[str], list[str]]:
    """Abre escondido os apps que o script usa e que estão fechados. Devolve (apps usados, apps que o Heimdall acabou de abrir)."""
    usados = _apps_do_script(script)
    abertos_agora: list[str] = []
    with _apps_lock:
        for nome in usados:
            t = _apps_timers.pop(nome, None)
            if t:
                t.cancel()  # voltou a ser usado: adia o fechamento
            if nome in _apps_nossos or _app_rodando(nome):
                continue  # já aberto (por nós ou por você)
            primeira = (script.strip().splitlines() or [""])[0][:60]
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} abrindo {nome} escondido (pedido: {primeira})\n")
            try:
                subprocess.run(["open", "-g", "-j", "-a", nome], capture_output=True, timeout=20)
            except Exception:  # noqa: BLE001
                continue
            for _ in range(60):  # espera até 15 s o app subir
                if _app_rodando(nome):
                    _apps_nossos.add(nome)
                    abertos_agora.append(nome)
                    break
                time.sleep(0.25)
            if nome in abertos_agora:
                time.sleep(ASSENTAR_APP_S)   # deixa o app terminar de abrir (ele passa à frente ao final)
                _esconder_app(nome)
    return usados, abertos_agora


def _agendar_fechamento(usados: list[str]) -> None:
    if not FECHAR_APPS:
        return
    with _apps_lock:
        for nome in usados:
            if nome not in _apps_nossos:
                continue
            t = _apps_timers.pop(nome, None)
            if t:
                t.cancel()
            t = threading.Timer(SOSSEGO_APP, _fechar_app, args=(nome,))
            t.daemon = True
            _apps_timers[nome] = t
            t.start()


def osascript(script: str, *args: str, timeout: int = 0) -> str:
    """Roda um AppleScript (arquivo temporário) com argumentos e devolve a saída.
    Os apps Notas, Lembretes e Calendário são abertos escondidos (sem aparecer na tela) e fechados depois, se estavam fechados."""
    ok_ek, resultado_ek = eventkit.tentar(script, args)   # Lembretes e Calendário pelo EventKit: não abre app nenhum
    if ok_ek:
        return resultado_ek
    usados, abertos_agora = _preparar_apps(script)
    with tempfile.NamedTemporaryFile("w", suffix=".applescript", delete=False, encoding="utf-8") as f:
        f.write(script)
        caminho = f.name
    limite = timeout or OSASCRIPT_TIMEOUT
    try:
        r = subprocess.run(
            ["osascript", caminho, *args],
            capture_output=True, text=True, timeout=limite,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("o macOS não respondeu em %d s (provável pedido de permissão aberto na tela do Mac)" % limite) from None
    finally:
        for nome in abertos_agora:
            _esconder_app(nome)   # esconde de novo no fim da primeira chamada, caso o app tenha passado à frente durante ela
        _agendar_fechamento(usados)
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
# Só os espelhos do próprio Second Brain ficam de fora da análise (evita laço). Todo o resto entra: suas notas, os
# estudos, o digest, os diários oficiais, os monitores e a saúde (as pastas privadas continuam protegidas). Também são ignoradas pelo título,
# para não entrarem num laço caso o app Notas não informe a pasta de uma nota.
TITULO_DO_HEIMDALL = re.compile(r"^(C[ée]rebro: |Second Brain: )")


def pasta_ignorada(nome: str) -> bool:
    n = nome.strip().lower()
    nn = norm_nome(nome)
    return (n.startswith(PREFIXO_ESCRITA.lower()) or n == "estudos" or n in IGNORAR_PASTAS or nn in {norm_nome(p) for p in PRIVADAS}
            or nn in {"second brain", "cerebro"})


_cache_privadas: tuple[float, set] = (0.0, set())
_nomes_privados: list = []


def ids_privados() -> set:
    """Identificadores das notas das pastas privadas (e subpastas). Se não der para consultar, falha: na dúvida,
    nenhuma nota é entregue (a privacidade não pode depender de a consulta ter funcionado)."""
    global _cache_privadas
    if time.time() - _cache_privadas[0] < 20:
        return _cache_privadas[1]
    with _lock:
        existentes = {l.strip() for l in osascript(AS_NOMES_PASTAS).splitlines() if l.strip()}
        alvo = {norm_nome(p) for p in PRIVADAS}
        nomes = sorted({n for n in existentes if norm_nome(n) in alvo} | set(PRIVADAS))
        saida = osascript(AS_PRIVADAS, *nomes)
    ids = {l.strip() for l in saida.splitlines() if l.strip()}
    _nomes_privados[:] = nomes
    _cache_privadas = (time.time(), ids)
    return ids


# --- Second Brain só quando há nota nova -------------------------------------------------------------------------
# O fluxo do Second Brain pergunta a cada 5 min quais notas mudaram, e cada pergunta abria o app Notas. Agora o agente primeiro olha, sem abrir
# o Notas, se o banco de dados das notas mudou desde a última verificação (data do arquivo). Só se mudou, ou se o Heimdall acabou de gravar
# uma nota, ele consulta o app. Se o macOS não deixar ver o arquivo (falta Acesso Total ao Disco), o agente só consulta o Notas depois de uma
# gravação do Heimdall e, se HEIMDALL_NOTAS_VARREDURA_MIN estiver ligado, a cada tantos minutos (padrão 0: desligado).
_gravacao_nova = threading.Event()
_verificado_mtime = 0.0
_ultima_varredura = 0.0
_aviso_sem_acesso = [False]
VARREDURA_MIN = int(os.environ.get("HEIMDALL_NOTAS_VARREDURA_MIN", "0") or 0)
_ARQUIVOS_NOTAS = [Path.home() / "Library/Group Containers/group.com.apple.notes" / n for n in ("NoteStore.sqlite", "NoteStore.sqlite-wal")]


def _mtime_notas():
    """Data da última mudança do banco do Notas (sem abrir o app), ou None se o macOS não deixar ver."""
    try:
        return max(a.stat().st_mtime for a in _ARQUIVOS_NOTAS)
    except (OSError, ValueError):
        return None


def _consultar_notas_agora(quieto: int):
    """(consulta?, mtime): decide se vale abrir o Notas para listar as alteradas."""
    global _ultima_varredura
    m = _mtime_notas()
    if _gravacao_nova.is_set():
        return True, m
    if m is not None:
        return m > _verificado_mtime, m
    if not _aviso_sem_acesso[0]:
        _aviso_sem_acesso[0] = True
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} Second Brain: não consigo ver o banco do Notas (dê Acesso Total ao Disco ao Terminal); "
                         "só consulto o Notas depois de uma gravação do Heimdall" + (f" e a cada {VARREDURA_MIN} min\n" if VARREDURA_MIN else "\n"))
    if VARREDURA_MIN and time.time() - _ultima_varredura >= VARREDURA_MIN * 60:
        return True, None
    return False, None


def notas_alteradas(desde: float, quieto: int, limite: int) -> list[dict]:
    global _verificado_mtime, _ultima_varredura
    consultar, m_antes = _consultar_notas_agora(quieto)
    if not consultar:
        return []
    notas = _listar_alteradas(desde, quieto, limite)
    _gravacao_nova.clear()   # só depois de a consulta dar certo; se falhar, a próxima tenta de novo
    _ultima_varredura = time.time()
    if m_antes is not None and time.time() - m_antes > quieto + 30:
        _verificado_mtime = m_antes   # banco quieto há mais que o "quieto": esta consulta já viu tudo o que havia
    return notas


def _listar_alteradas(desde: float, quieto: int, limite: int) -> list[dict]:
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


def frontmatter_legivel(md: str) -> str:
    """No app Notas o bloco YAML do começo vira ruído (traços e chaves). Mantém só tags, conceitos e entidades,
    em linhas legíveis; o arquivo do cofre continua com o YAML inteiro."""
    m = re.match(r"^---\n(.*?)\n---\n?", md, re.S)
    if not m:
        return md
    linhas = []
    for l in m.group(1).splitlines():
        k, _, v = l.partition(":")
        if k.strip() in ("tags", "conceitos", "entidades"):
            itens = [x.strip().strip('"') for x in v.strip().strip("[]").split(",") if x.strip()]
            if itens:
                linhas.append(k.strip().capitalize() + ": " + ", ".join(itens) + ".")
    resto = md[m.end():].lstrip("\n")
    return ("\n".join(linhas) + "\n\n" if linhas else "") + resto


def markdown_para_html(titulo: str, md: str) -> str:
    partes = [f"<div><h1>{html.escape(titulo, quote=False)}</h1></div>"]
    em_lista = False
    primeira = True
    for bruta in md.splitlines():
        linha = bruta.rstrip()
        if primeira and linha.strip():
            primeira = False
            m0 = re.match(r"^#{1,3}\s+(.*)$", linha)
            if m0 and re.sub(r"\s+", " ", m0.group(1)).strip().lower() == re.sub(r"\s+", " ", titulo).strip().lower():
                continue  # o título já aparece no topo da nota
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


_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ufffe\uffff]")


def _limpar(s: str) -> str:
    """Tira caracteres de controle (comuns em texto extraído de PDF; o byte nulo derruba o osascript)."""
    return _CONTROLE.sub("", str(s))


def caminho_notas(pasta: str) -> str:
    """Caminho da pasta no app Notas, com "/" entre os níveis. Pastas antigas (Heimdall ...) ficam soltas."""
    if not RAIZ_NOTAS or pasta.startswith(PREFIXO_ESCRITA):
        return pasta
    if pasta in PASTAS_PROPRIAS:
        return RAIZ_NOTAS + "/" + pasta
    return RAIZ_NOTAS + "/Estudos/" + pasta


def gravar(pasta: str, titulo: str, markdown: str, audio: str = "") -> dict:
    titulo, markdown, audio = _limpar(titulo), _limpar(markdown), _limpar(audio)
    if pasta not in PASTAS_PROPRIAS and not pasta.startswith(PREFIXO_ESCRITA) and pasta not in temas_conhecimento():
        raise PermissionError("só escrevo nas pastas do Heimdall e nas pastas de temas de knowledge/: " + ", ".join(PASTAS_PROPRIAS))
    if not titulo.strip() or len(titulo) > 200:
        raise ValueError("título vazio ou longo demais")
    if not re.fullmatch(r"[\w][\w .-]{0,60}", pasta):
        raise ValueError("nome de pasta inválido (use letras, números, espaço, ponto, hífen)")
    titulo = titulo.replace("\n", " ").replace("\t", " ").strip()
    # Pastas de tema (estudo): o título agora é só o conceito, e dois estudos podem ter o mesmo conceito. Se já existe
    # uma nota com esse nome e conteúdo diferente, esta ganha " (2)", " (3)"... em vez de substituir a anterior.
    if pasta not in PASTAS_PROPRIAS and not pasta.startswith(PREFIXO_ESCRITA) and pasta in temas_conhecimento():
        base_t, n_t = titulo, 1

        def _com(t: str) -> str:
            return markdown if t == base_t else re.sub(r"^#\s+" + re.escape(base_t) + r"\s*$", lambda _m: "# " + t, markdown, count=1, flags=re.M)

        while n_t <= 50:
            ja = VAULT / PASTA_DO_COFRE.get(pasta, slug(pasta)) / f"{slug(titulo)}.md"
            if not ja.is_file() or ja.read_text(encoding="utf-8", errors="replace") == _com(titulo):
                break
            n_t += 1
            titulo = f"{base_t} ({n_t})"
        markdown = _com(titulo)
    # Cópia em Markdown no cofre (arquivo de verdade, com o frontmatter intacto).
    destino = VAULT / PASTA_DO_COFRE.get(pasta, slug(pasta))
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"{slug(titulo)}.md"
    if arquivo.resolve().parent != destino.resolve():
        raise PermissionError("caminho fora do cofre")
    arquivo.write_text(markdown, encoding="utf-8")
    # Áudio (opcional): gerado antes, para a própria nota dizer onde ele está.
    m4a, motivo_audio = (None, "")
    markdown_puro = markdown
    if audio.strip():
        m4a, motivo_audio = fazer_audio(titulo, audio, destino)
        if m4a:
            markdown = _com_dica(markdown, f"Áudio desta leitura: é o anexo no fim desta nota, arquivo {m4a.name}. Toque nele para ouvir.")
    # Nota no app Notas (a primeira linha vira o nome da nota).
    corpo_html = markdown_para_html(titulo, frontmatter_legivel(markdown))
    caminho = caminho_notas(pasta)
    aviso_pasta = ""
    try:
        with _lock:
            estado = osascript(AS_GRAVAR, caminho, titulo, corpo_html)
    except RuntimeError as e:
        if caminho == pasta:
            raise
        # as subpastas falharam: grava na pasta solta para a nota não se perder
        aviso_pasta = "subpasta indisponível (" + str(e)[:120] + "); gravei em pasta solta"
        caminho = pasta
        with _lock:
            estado = osascript(AS_GRAVAR, caminho, titulo, corpo_html)
    r = {"ok": True, "nota": estado, "arquivo": str(arquivo), "pasta": caminho}
    if aviso_pasta:
        r["aviso"] = aviso_pasta
    if m4a:
        try:
            with _lock:
                osascript(AS_ANEXAR, caminho, titulo, str(m4a))
            r["audio"] = "anexado"
        except Exception:  # noqa: BLE001
            r["audio"] = "salvo:" + str(m4a)
            with _lock:
                osascript(AS_GRAVAR, caminho, titulo, markdown_para_html(titulo, frontmatter_legivel(_com_dica(markdown_puro, f"Áudio desta leitura: não consegui anexar. Está no Mac, na pasta {m4a.parent}, arquivo {m4a.name}."))))
    elif audio.strip():
        r["audio"] = motivo_audio
    return r


AS_ANEXAR = r'''-- heimdall:anexar
on partes(txt)
	set AppleScript's text item delimiters to "/"
	set l to text items of txt
	set AppleScript's text item delimiters to ""
	return l
end partes
-- Acha (ou cria) a pasta pelo caminho "Raiz/Sub/Sub". A primeira só vale se estiver no nível de cima da conta;
-- as seguintes, só se forem filhas da anterior. Assim "Digest" solto e "Heimdall-ai/Digest" não se confundem.
on achar_pasta(caminho)
	tell application "Notes"
		tell default account
			set atual to missing value
			repeat with nm in my partes(caminho)
				set nome to contents of nm
				set achada to missing value
				if atual is missing value then
					set cand to every folder
				else
					set cand to every folder of atual
				end if
				repeat with f in cand
					if (name of f) is nome then
						set vale to true
						if atual is missing value then
							try
								set vale to ((class of (container of f)) is account)
							on error
								set vale to true
							end try
						end if
						if vale then
							set achada to contents of f
							exit repeat
						end if
					end if
				end repeat
				if achada is missing value then
					if atual is missing value then
						set achada to make new folder with properties {name:nome}
					else
						set achada to make new folder at atual with properties {name:nome}
					end if
				end if
				set atual to achada
			end repeat
			return atual
		end tell
	end tell
end achar_pasta
on run argv
	set folderName to item 1 of argv
	set noteTitle to item 2 of argv
	set audioPath to item 3 of argv
	tell application "Notes"
		tell default account
			set f to my achar_pasta(folderName)
			set n to item 1 of (every note of f whose name is noteTitle)
			make new attachment at end of attachments of n with data (POSIX file audioPath)
			return "anexado"
		end tell
	end tell
end run
'''


def palavras_por_minuto() -> int:
    if PPM > 0:
        return max(80, min(PPM, 720))
    return int(round(90 * 8 ** (VELOCIDADE / 100)))  # 0% = 90, 50% = 255, 65% = 348, 100% = 720


def vozes_pt() -> list:
    """Vozes em português instaladas, da melhor para a pior."""
    saida = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=20).stdout
    achadas = []
    for linha in saida.splitlines():
        m = re.match(r"^(.+?)\s+([a-z]{2,3}_[A-Za-z]{2,3})\s+#", linha)
        if not m or not m.group(2).lower().startswith("pt_"):
            continue
        nome, lang = m.group(1).strip(), m.group(2)
        nivel = 3 if re.search(r"premium", nome, re.I) else 2 if re.search(r"aprimorad|melhorad|enhanced", nome, re.I) else 1
        achadas.append((-nivel, 0 if lang == "pt_BR" else 1, nome))
    return [n for _, _, n in sorted(achadas)]


def _chave_voz(nome: str) -> str:
    """Compara nomes de voz sem ligar para maiúsculas nem para o idioma do sistema: (Aprimorada), (Melhorada) e (Enhanced) são a mesma coisa."""
    return re.sub(r"\s+", " ", re.sub(r"aprimorad[oa]|melhorad[oa]", "enhanced", nome.strip().lower()))


def escolher_voz():
    vozes = vozes_pt()
    if VOZ:
        for v in vozes:
            if _chave_voz(v) == _chave_voz(VOZ):
                return v  # devolve o nome como o macOS lista, que é o que o say aceita
        if vozes:  # a voz fixada não existe: melhor um áudio com a melhor voz instalada do que nota sem áudio
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} a voz '{VOZ}' não está instalada; usando {vozes[0]}\n")
            return vozes[0]
        return None
    return vozes[0] if vozes else None


def _com_dica(md: str, linha: str) -> str:
    """Insere uma linha logo depois do título (primeiro cabeçalho) do markdown."""
    linhas = md.splitlines()
    for n, l in enumerate(linhas):
        if re.match(r"^#{1,3}\s+", l):
            return "\n".join(linhas[:n + 1] + ["", linha] + linhas[n + 1:])
    return linha + "\n\n" + md


def audio_por_atalho(txt: str, base: Path) -> str:
    """Gera base.m4a com o atalho do app Atalhos (entrada: o arquivo de texto). Devolve "" se deu certo ou o motivo da falha."""
    saida = str(base) + ".atalho.m4a"   # a extensão diz ao Atalhos que tipo de arquivo gravar
    sobras = lambda: [x for x in Path(saida).parent.glob(Path(saida).name.split(".atalho")[0] + ".atalho*")]  # noqa: E731
    try:
        r = subprocess.run(["shortcuts", "run", ATALHO, "-i", txt, "-o", saida], capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            return "o atalho '%s' falhou: %s" % (ATALHO, (r.stderr or r.stdout or "sem mensagem").strip()[:120])
        achados = sorted((x for x in sobras() if x.is_file() and x.stat().st_size >= 2000), key=lambda x: x.stat().st_size, reverse=True)
        if not achados:
            vistos = ", ".join("%s (%d bytes)" % (x.name.split(".atalho")[-1] or "sem nome", x.stat().st_size) for x in sobras() if x.is_file()) or "nenhum arquivo"
            return "o atalho '%s' não devolveu áudio (arquivo gravado: %s; saída do atalho: %s)" % (ATALHO, vistos, (r.stdout or r.stderr or "vazia").strip()[:80])
        origem = achados[0]
        c = subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", str(origem), str(base) + ".m4a"], capture_output=True, timeout=300)
        if c.returncode != 0:
            with open(origem, "rb") as f:
                if f.read(12)[4:8] == b"ftyp":   # já é m4a: só renomeia
                    os.replace(origem, str(base) + ".m4a")
                    return ""
            return "não consegui converter o áudio do atalho"
        return ""
    except (OSError, subprocess.SubprocessError) as e:
        return "o atalho '%s' falhou: %s" % (ATALHO, str(e)[:100])
    finally:
        try:
            for x in sobras():
                x.unlink()
        except OSError:
            pass


def fazer_audio(titulo: str, texto: str, destino: Path):
    """Lê o texto em voz alta (say, voz em português) e salva em .m4a na pasta do cofre.
    Devolve (caminho, "") ou (None, motivo). Nunca levanta erro: a nota é gravada de qualquer jeito."""
    if not AUDIO_ATIVO:
        return None, "desligado"
    if sys.platform != "darwin" or (VOZ and not re.fullmatch(r"[\w .()-]{1,40}", VOZ)):
        return None, "indisponível neste sistema"
    try:
        voz = None if ATALHO else escolher_voz()
        if not voz and not ATALHO:
            return None, ("a voz '%s' não está instalada" % VOZ if VOZ else "nenhuma voz em português instalada") + " (Ajustes do Sistema > Acessibilidade > Conteúdo falado > Vozes do sistema > Gerenciar vozes)"
        pasta_audio = destino / "audio"
        pasta_audio.mkdir(parents=True, exist_ok=True)
        base = pasta_audio / slug(titulo)
        if base.resolve().parent != pasta_audio.resolve():
            return None, "caminho inválido"
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(dicionario_voz.aplicar(re.sub(r"https?://\S+", " ", texto)[:12000]))
            txt = f.name
        try:
            if ATALHO:
                motivo = audio_por_atalho(txt, base)
                if not motivo:
                    sys.stderr.write(f"{time.strftime('%H:%M:%S')} áudio feito pelo atalho {ATALHO}\n")
                    return Path(str(base) + ".m4a"), ""
                sys.stderr.write(f"{time.strftime('%H:%M:%S')} {motivo}; usando o say\n")
                voz = escolher_voz()
                if not voz:
                    return None, motivo
            subprocess.run(["say", "-v", voz, "-r", str(palavras_por_minuto()), "-o", str(base) + ".aiff", "-f", txt], check=True, timeout=240, capture_output=True)
            subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", str(base) + ".aiff", str(base) + ".m4a"], check=True, timeout=120, capture_output=True)
        finally:
            for x in (txt, str(base) + ".aiff"):
                try:
                    os.unlink(x)
                except OSError:
                    pass
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} áudio com a voz {voz} a {palavras_por_minuto()} palavras por minuto\n")
        return Path(str(base) + ".m4a"), ""
    except Exception as e:  # noqa: BLE001
        return None, "falhou: " + str(e)[:120]


# ----------------------------------------------------------------------------------------
# Servidor HTTP
# ----------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------
# Calendário, Lembretes e busca em sites públicos (usados pelos fluxos de avisos)
# ----------------------------------------------------------------------------------------
NOME_AGENDA = "Heimdall"  # calendário e lista de lembretes que o Heimdall cria; nunca mexe nos seus outros
AS_EVENTO = r'''
on run argv
    set tit to item 1 of argv
    set y to (item 2 of argv) as integer
    set m to (item 3 of argv) as integer
    set dd to (item 4 of argv) as integer
    set notas to item 5 of argv
    set antes to (item 6 of argv) as integer
    set nomeCal to item 7 of argv
    set d to current date
    set day of d to 1
    set year of d to y
    set month of d to m
    set day of d to dd
    set time of d to 0
    tell application "Calendar"
        if not (exists calendar nomeCal) then make new calendar with properties {name:nomeCal}
        set cal to calendar nomeCal
        if (count of (events of cal whose summary is tit and start date is d)) > 0 then return "ja_existe"
        set ev to make new event at end of events of cal with properties {summary:tit, start date:d, end date:(d + 1 * days), allday event:true, description:notas}
        if antes > 0 then
            tell ev to make new display alarm at end of display alarms with properties {trigger interval:(-1440 * antes + 540)}
        end if
        return "criado"
    end tell
end run
'''
AS_EVENTO_HORARIO = r'''
on run argv
    set tit to item 1 of argv
    set y to (item 2 of argv) as integer
    set m to (item 3 of argv) as integer
    set dd to (item 4 of argv) as integer
    set hh to (item 5 of argv) as integer
    set mi to (item 6 of argv) as integer
    set dur to (item 7 of argv) as integer
    set notas to item 8 of argv
    set lugar to item 9 of argv
    set alarmes to item 10 of argv
    set nomeCal to item 11 of argv
    set d to current date
    set day of d to 1
    set year of d to y
    set month of d to m
    set day of d to dd
    set time of d to (hh * 3600 + mi * 60)
    tell application "Calendar"
        if not (exists calendar nomeCal) then make new calendar with properties {name:nomeCal}
        set cal to calendar nomeCal
        if (count of (events of cal whose summary is tit and start date is d)) > 0 then return "ja_existe"
        set ev to make new event at end of events of cal with properties {summary:tit, start date:d, end date:(d + dur * minutes), description:notas, location:lugar}
        if alarmes is not "" then
            set AppleScript's text item delimiters to ","
            repeat with a in text items of alarmes
                tell ev to make new display alarm at end of display alarms with properties {trigger interval:(-1 * (a as integer))}
            end repeat
        end if
        return "criado"
    end tell
end run
'''
AS_LEMBRETE = r'''
on run argv
    set tit to item 1 of argv
    set y to (item 2 of argv) as integer
    set m to (item 3 of argv) as integer
    set dd to (item 4 of argv) as integer
    set h to (item 5 of argv) as integer
    set notas to item 6 of argv
    set nomeLista to item 7 of argv
    set d to current date
    set day of d to 1
    set year of d to y
    set month of d to m
    set day of d to dd
    set time of d to (h * 3600)
    tell application "Reminders"
        if not (exists list nomeLista) then make new list with properties {name:nomeLista}
        set l to list nomeLista
        if (count of (reminders of l whose name is tit and completed is false)) > 0 then return "ja_existe"
        make new reminder at end of reminders of l with properties {name:tit, body:notas, due date:d, remind me date:d}
        return "criado"
    end tell
end run
'''

AS_DESFAZER_EVENTO = r'''
on run argv
    set tit to item 1 of argv
    set y to (item 2 of argv) as integer
    set m to (item 3 of argv) as integer
    set dd to (item 4 of argv) as integer
    set nomeCal to item 5 of argv
    set d0 to current date
    set day of d0 to 1
    set year of d0 to y
    set month of d0 to m
    set day of d0 to dd
    set time of d0 to 0
    tell application "Calendar"
        if not (exists calendar nomeCal) then return "nada"
        set achados to (events of calendar nomeCal whose summary is tit and start date >= d0 and start date < (d0 + 1 * days))
        set n to count of achados
        repeat with ev in achados
            delete ev
        end repeat
        if n is 0 then return "nada"
        return "apagado"
    end tell
end run
'''
AS_DESFAZER_LEMBRETE = r'''
on run argv
    set tit to item 1 of argv
    set nomeLista to item 2 of argv
    tell application "Reminders"
        if not (exists list nomeLista) then return "nada"
        set achados to (reminders of list nomeLista whose name is tit and completed is false)
        set n to count of achados
        repeat with r in achados
            delete r
        end repeat
        if n is 0 then return "nada"
        return "apagado"
    end tell
end run
'''


AS_PREPARAR_CAL = r'''
on run argv
    set nomeCal to item 1 of argv
    tell application "Calendar"
        if not (exists calendar nomeCal) then
            make new calendar with properties {name:nomeCal}
            return "calendário criado"
        end if
        return "calendário já existe"
    end tell
end run
'''
AS_PREPARAR_LEM = r'''
on run argv
    set nomeLista to item 1 of argv
    tell application "Reminders"
        if not (exists list nomeLista) then
            make new list with properties {name:nomeLista}
            return "lista criada"
        end if
        return "lista já existe"
    end tell
end run
'''


# Estes scripts rodam pelo EventKit quando possível (heimdall_eventkit.py); o AppleScript acima fica como recuo.
for _script, _funcao in ((AS_EVENTO, eventkit.evento_dia_inteiro), (AS_EVENTO_HORARIO, eventkit.evento_com_hora),
                         (AS_LEMBRETE, eventkit.lembrete_simples), (AS_PREPARAR_CAL, eventkit.preparar_calendario),
                         (AS_PREPARAR_LEM, eventkit.preparar_lista), (triagem.AS_CRIAR, eventkit.triagem_criar),
                         (triagem.AS_LER, eventkit.triagem_ler)):
    eventkit.registrar(_script, _funcao)


def _data(s: str) -> tuple:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(s)):
        raise ValueError("data inválida (use AAAA-MM-DD)")
    y, m, d = (int(x) for x in s.split("-"))
    datetime(y, m, d)  # levanta ValueError se não existir
    if not (2020 <= y <= 2100):
        raise ValueError("ano fora do intervalo")
    return str(y), str(m), str(d)


def _texto_curto(s, limite: int) -> str:
    return re.sub(r"[\x00-\x08\x0b-\x1f]", " ", str(s or "")).strip()[:limite]


def criar_evento(dado: dict) -> dict:
    """Evento do Calendário (calendário "Heimdall"). Sem "hora" é de dia inteiro; com "hora" (HH:MM) tem início, "duracao_min" e "local".
    Evento é o que acontece numa data e hora (consulta) ou tem data-limite fixa. O que você precisa fazer e marcar como feito é lembrete (criar_lembrete)."""
    titulo = _texto_curto(dado.get("titulo"), 200)
    if not titulo:
        raise ValueError("título vazio")
    y, m, d = _data(dado.get("data", ""))
    hora = str(dado.get("hora") or "").strip()
    if hora:
        mm = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", hora)
        if not mm:
            raise ValueError("hora inválida (use HH:MM)")
        dur = max(15, min(int(dado.get("duracao_min", 60)), 720))
        alarmes = ",".join(str(max(0, min(int(x), 20160)) * 60) for x in (dado.get("alertas_min_antes") or [60, 1440])[:4])
        with _lock:
            r = osascript(AS_EVENTO_HORARIO, titulo, y, m, d, str(int(mm.group(1))), str(int(mm.group(2))), str(dur),
                          _texto_curto(dado.get("notas"), 1000), _texto_curto(dado.get("local"), 200), alarmes, NOME_AGENDA)
        return {"ok": True, "evento": r}
    antes = max(0, min(int(dado.get("alerta_dias_antes", 1)), 14))
    with _lock:
        r = osascript(AS_EVENTO, titulo, y, m, d, _texto_curto(dado.get("notas"), 1000), str(antes), NOME_AGENDA)
    return {"ok": True, "evento": r}


def criar_lembrete(dado: dict) -> dict:
    titulo = _texto_curto(dado.get("titulo"), 200)
    if not titulo:
        raise ValueError("título vazio")
    y, m, d = _data(dado.get("vencimento", ""))
    hora = max(0, min(int(dado.get("hora", 9)), 23))
    with _lock:
        r = osascript(AS_LEMBRETE, titulo, y, m, d, str(hora), _texto_curto(dado.get("notas"), 1000), NOME_AGENDA)
    return {"ok": True, "lembrete": r}


def desfazer_evento(dado: dict) -> dict:
    """Apaga o evento do calendário Heimdall com este título e data (usado pelo botão Desfazer do Studio Notes)."""
    titulo = _texto_curto(dado.get("titulo"), 200)
    if not titulo:
        raise ValueError("título vazio")
    y, m, d = _data(dado.get("data", ""))
    with _lock:
        r = osascript(AS_DESFAZER_EVENTO, titulo, y, m, d, NOME_AGENDA)
    return {"ok": True, "resultado": r}


def desfazer_lembrete(dado: dict) -> dict:
    titulo = _texto_curto(dado.get("titulo"), 200)
    if not titulo:
        raise ValueError("título vazio")
    with _lock:
        r = osascript(AS_DESFAZER_LEMBRETE, titulo, NOME_AGENDA)
    return {"ok": True, "resultado": r}


def osascript_travado(script: str, *args: str) -> str:
    """O app Lembretes também atende um pedido de cada vez."""
    with _lock:
        return osascript(script, *args, timeout=45)


# Só estes sites podem ser buscados por aqui (o n8n no Docker às vezes falha no TLS com o Querido Diário e o DOU).
SITES_PERMITIDOS = {"api.queridodiario.org.br", "www.in.gov.br", "comunicaapi.pje.jus.br"}


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def buscar_site(url: str) -> str:
    u = urlparse(url)
    if u.scheme != "https" or (u.hostname or "").lower() not in SITES_PERMITIDOS or u.username or u.port not in (None, 443):
        raise PermissionError("site não permitido")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh) Heimdall", "Accept": "application/json, text/html;q=0.9, */*;q=0.8"})
    with urllib.request.build_opener(_SemRedirecionar).open(req, timeout=40) as r:
        return r.read(2_000_000).decode("utf-8", "replace")



_analise_saude_rodando = threading.Lock()


def _analise_de_saude_em_segundo_plano() -> None:
    """Depois que chegam dados de saúde, roda o analista (modelo + PubMed) numa thread. Ele mesmo respeita o intervalo mínimo e o interruptor HEIMDALL_SAUDE_ANALISTA=0."""
    def tarefa():
        if not _analise_saude_rodando.acquire(blocking=False):
            return
        try:
            import heimdall_analista_saude as analista
            analista.rodar()
        except Exception as e:  # noqa: BLE001 - a análise é um extra; nunca derruba o agente
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} análise de saúde falhou: {str(e)[:120]}\n")
        finally:
            _analise_saude_rodando.release()
    threading.Thread(target=tarefa, daemon=True).start()


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
            if u.path == "/web/get":
                try:
                    corpo = buscar_site(q.get("u", [""])[0]).encode("utf-8")
                except PermissionError:
                    raise
                except Exception as e:  # noqa: BLE001
                    return self._json(502, {"erro": "falha ao buscar: " + str(e)[:200]})
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
                return
            if u.path == "/banco/resumo":
                return self._json(200, banco.resumo())
            if u.path == "/banco/esquema":
                return self._json(200, {"esquema": banco.tabelas_para_modelo()})
            if u.path == "/triagem/estado":
                return self._json(200, triagem.estado())
            if u.path == "/backup/estado":
                return self._json(200, backup.estado())
            if u.path == "/notas/privadas":
                return self._json(200, {"pastas": PRIVADAS, "ids": sorted(ids_privados())})
            if u.path == "/notas/nota":
                nid = q.get("id", [""])[0]
                if not nid:
                    return self._json(400, {"erro": "falta o id"})
                return self._json(200, ler_nota(nid))
            return self._json(404, {"erro": "rota desconhecida"})
        except PermissionError as e:
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} recusado em {u.path}: {e}\n")
            return self._json(403, {"erro": str(e)})
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} erro em {u.path}: {type(e).__name__}: {str(e)[:300]}\n")
            return self._json(500, {"erro": str(e)[:400]})

    def _autorizado_envio(self) -> bool:
        """O código de envio do atalho do iPhone vale só para /saude/documento; o token do agente também vale."""
        enviado = self.headers.get("X-Heimdall-Upload", "")
        return self._autorizado() or (len(TOKEN_UPLOAD) >= 16 and hmac.compare_digest(enviado.encode(), TOKEN_UPLOAD.encode()))

    def _receber_documento(self):
        try:
            tam = int(self.headers.get("Content-Length", "0"))
            if tam <= 0 or tam > MAX_CORPO_DOC:
                return self._json(413, {"erro": "arquivo ausente ou maior que 25 MB"})
            dados = self.rfile.read(tam)
            nome = urllib.parse.unquote(self.headers.get("X-Heimdall-Nome", "documento"))[:120]
            r = exames.receber(dados, nome)
            threading.Thread(target=_ler_documentos, daemon=True).start()   # lê já, sem esperar o minuto da vigia
            return self._json(200, {"ok": True, "arquivo": r["arquivo"], "mensagem": "Recebido. O Heimdall vai ler o documento; você será avisado quando houver o que conferir."})
        except exames.ErroExames as e:
            return self._json(400, {"erro": str(e)[:200]})
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} erro em /saude/documento: {type(e).__name__}: {str(e)[:200]}\n")
            return self._json(500, {"erro": "não consegui guardar o arquivo"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/saude/documento":
            if not self._autorizado_envio():
                return self._json(401, {"erro": "token inválido"})
            return self._receber_documento()
        if not self._autorizado():
            return self._json(401, {"erro": "token inválido"})
        try:
            tam = int(self.headers.get("Content-Length", "0"))
            if tam <= 0 or tam > (MAX_CORPO_SAUDE if u.path == "/saude/hae" else MAX_CORPO):
                return self._json(413, {"erro": "corpo ausente ou grande demais"})
            dado = json.loads(self.rfile.read(tam).decode("utf-8"))
            if u.path == "/avisos/gravar":
                serv = str(dado.get("servico", ""))
                if serv not in avisos.SERVICOS:
                    return self._json(400, {"erro": "servico deve ser saude ou financas"})
                try:
                    novo = avisos.do_servico(serv).gravar(str(dado.get("titulo", "")), str(dado.get("markdown", "")))
                except ValueError as ex:
                    return self._json(400, {"erro": str(ex)})
                return self._json(200, {"ok": True, "id": novo, "bark": triagem.enviar_bark(avisos.texto_bark(serv)) if dado.get("bark") and avisos.bark_ligado(serv) else None})
            if u.path == "/saude/analise":   # roda agora a análise completa e devolve o texto (o aviso também vai para a aba Avisos do Health)
                import heimdall_analista_saude as analista
                a = analista.rodar(forcar=True)
                return self._json(200, {"ok": True, "gravidade": a["resultado"]["gravidade"], "com_modelo": a["com_modelo"], "texto": a["texto"], "avisou": a["avisou"]})
            if u.path == "/avisos/mac":   # os fluxos do n8n mandam aqui o mesmo aviso do Bark, completo, para virar notificação do macOS
                ok = avisos_mac.publicar(dado)
                return self._json(200, {"ok": ok})
            if u.path == "/notas/gravar":
                serv = avisos.PASTAS_SENSIVEIS.get(str(dado.get("pasta", "")).strip())
                if serv:   # saúde e finanças não vão mais para o app Notas: viram aviso na aba Avisos do serviço
                    novo = avisos.do_servico(serv).gravar(str(dado.get("titulo", "")) or "Aviso", str(dado.get("markdown", "")))
                    return self._json(200, {"ok": True, "aviso": novo, "destino": "avisos"})
                r = gravar(str(dado.get("pasta", "")), str(dado.get("titulo", "")), str(dado.get("markdown", "")), str(dado.get("audio", "")))
                _gravacao_nova.set()   # nota nova: o Second Brain pode olhar na próxima verificação
                return self._json(200, r)
            if u.path == "/saude/relatorio-semanal":
                rel = saude.relatorio_semanal()
                novo = avisos.do_servico("saude").gravar(rel["titulo"], rel["markdown"])   # o relatório fica na aba Avisos do Studio Health, não no Notas
                r = {"ok": True, "titulo": rel["titulo"], "aviso": novo, "bark": triagem.enviar_bark(avisos.texto_bark("saude"))}
                if not r["bark"]:
                    sys.stderr.write(f"{time.strftime('%H:%M:%S')} relatório semanal gravado, mas o Bark não confirmou (HEIMDALL_BARK_KEY?)\n")
                return self._json(200, r)
            if u.path == "/saude/hae":
                r = saude.processar_hae(dado)
                for f in r.pop("ecg_fibrilacao", []):   # a Apple classificou como fibrilação atrial: entra na triagem (não é diagnóstico)
                    try:
                        triagem.criar({"id": f["id"], "titulo": "ECG classificado pela Apple como fibrilação atrial",
                                       "resumo": f"Gravação de {f['inicio']}. Não é diagnóstico: mostre ao seu médico. Detalhes: python3 heimdall_saude.py --ecg.",
                                       "nivel": "alto", "fonte": "saude"}, osascript_travado)
                        r["triagem"] = r.get("triagem", 0) + 1
                    except Exception as e:  # noqa: BLE001 - a gravação já foi feita; a triagem é um aviso a mais
                        sys.stderr.write(f"{time.strftime('%H:%M:%S')} triagem do ECG falhou: {str(e)[:120]}\n")
                try:   # frequência cardíaca da madrugada bem acima do normal: entra na triagem (a mesma id no dia não duplica)
                    alerta = saude.alerta_fc() if r.get("fc_horas") else None
                    if alerta:
                        triagem.criar(alerta, osascript_travado)
                        r["triagem"] = r.get("triagem", 0) + 1
                except Exception as e:  # noqa: BLE001 - os dados já foram gravados; a triagem é um aviso a mais
                    sys.stderr.write(f"{time.strftime('%H:%M:%S')} alerta de frequência cardíaca falhou: {str(e)[:120]}\n")
                try:   # anomalias em todas as medidas e cruzamentos de sinais: um item de triagem consolidado por dia
                    import heimdall_anomalias as anomalias
                    alerta = anomalias.alerta()
                    if alerta:
                        estado_novo = alerta.pop("_estado", None)
                        triagem.criar(alerta, osascript_travado)
                        if estado_novo:
                            anomalias.salvar_estado(estado_novo)   # só depois de entrar na triagem: aviso perdido não conta como entregue
                        r["triagem"] = r.get("triagem", 0) + 1
                except Exception as e:  # noqa: BLE001 - os dados já foram gravados; a triagem é um aviso a mais
                    sys.stderr.write(f"{time.strftime('%H:%M:%S')} alerta de anomalias falhou: {str(e)[:120]}\n")
                _analise_de_saude_em_segundo_plano()   # análise completa por modelo, no máximo uma vez por dia; não segura a resposta da importação
                return self._json(200, r)
            if u.path == "/banco/gravar":
                return self._json(200, banco.gravar(str(dado.get("tabela", "")), dado.get("registros", [])))
            if u.path == "/banco/consultar":
                return self._json(200, banco.consulta_sql(str(dado.get("sql", "")), dado.get("limite", 200)))
            if u.path == "/calendario/evento":
                return self._json(200, criar_evento(dado))
            if u.path == "/lembretes/criar":
                return self._json(200, criar_lembrete(dado))
            if u.path == "/calendario/desfazer":
                return self._json(200, desfazer_evento(dado))
            if u.path == "/lembretes/desfazer":
                return self._json(200, desfazer_lembrete(dado))
            if u.path == "/triagem/criar":
                return self._json(200, triagem.criar(dado, osascript_travado))
            if u.path == "/triagem/ciclo":
                return self._json(200, triagem.ciclo(osascript_travado))
            if u.path == "/seguranca/executar":
                r = seguranca.executar(str(dado.get("tarefa", "")))
                if r["gravar"]:
                    r["nota"] = gravar("Segurança", r["titulo"], r["markdown"])
                r.pop("markdown", None)
                r.pop("dados", None)
                return self._json(200, r)
            if u.path == "/backup/executar":
                return self._json(200, backup.fazer())
            if u.path == "/backup/verificar":
                r = backup.verificar()
                return self._json(200, {"ok": bool(r) and all(v.get("ok") for v in r.values()), "destinos": r})
            return self._json(404, {"erro": "rota desconhecida"})
        except PermissionError as e:
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} recusado em {u.path}: {e}\n")
            return self._json(403, {"erro": str(e)})
        except (ValueError, json.JSONDecodeError) as e:
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} pedido inválido em {u.path}: {e}\n")
            return self._json(400, {"erro": str(e)[:200]})
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} erro em {u.path}: {type(e).__name__}: {str(e)[:300]}\n")
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
        n_priv = len(ids_privados())
        print(f"   Pastas privadas encontradas: {', '.join(_nomes_privados) or 'nenhuma'}: {n_priv} nota(s) protegida(s), nunca lidas.")
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
    print("4. Conferindo o Calendário e os Lembretes (cria o calendário e a lista \"%s\", se ainda não existirem; autorize se pedir)..." % NOME_AGENDA)
    try:
        print("   Calendário:", osascript(AS_PREPARAR_CAL, NOME_AGENDA))
        print("   Lembretes:", osascript(AS_PREPARAR_LEM, NOME_AGENDA))
        print("   Triagem:", osascript(AS_PREPARAR_LEM, triagem.NOME_LISTA))
    except Exception as e:  # noqa: BLE001
        print(f"   Falhou: {e}")
        print("   Autorize o Terminal em Ajustes do Sistema > Privacidade e Segurança > Automação > Calendário e Lembretes, e rode de novo.")
        return 1
    print("Tudo certo." if total.isdigit() else "Resposta inesperada do app Notas.")
    return 0


_trava_docs = threading.Lock()


def _ler_documentos() -> None:
    """Lê a pasta de entrada de documentos clínicos (exames, receitas, encaminhamentos) e avisa pelo Bark, sem nomes nem números."""
    if not _trava_docs.acquire(blocking=False):
        return
    try:
        rs = exames.processar_entrada()
        novos = [r for r in rs if r.get("ok") and not r.get("duplicado")]
        falhos = [r for r in rs if not r.get("ok")]
        if novos:
            triagem.enviar_bark({"title": "Saúde: documento para conferir", "group": "saude", "level": "active",
                                 "body": f"{len(novos)} documento(s) lido(s). Para ouvir o que foi lido: heimdall health --labs pending."})
        if falhos:
            triagem.enviar_bark({"title": "Saúde: documento não lido", "group": "saude", "level": "active",
                                 "body": f"{len(falhos)} documento(s) não puderam ser lidos e estão na pasta health/review, com o motivo."})
    except Exception as e:  # noqa: BLE001 - a vigia nunca derruba o agente
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} documentos de saúde: {type(e).__name__}: {str(e)[:160]}\n")
    finally:
        _trava_docs.release()


def _vigiar_documentos() -> None:
    """A cada minuto lê o que foi solto na pasta de entrada dos documentos de saúde."""
    while True:
        _ler_documentos()
        time.sleep(60)


def main() -> int:
    ap = argparse.ArgumentParser(description="Agente local do Heimdall para o app Notas")
    ap.add_argument("--teste", action="store_true", help="só confere o acesso ao app Notas e sai")
    ap.add_argument("--voz", action="store_true", help="lista as vozes em português, diz qual será usada e fala uma amostra")
    args = ap.parse_args()
    if args.voz and ATALHO:
        import tempfile as _t
        print(f"Voz pelo atalho '{ATALHO}' (HEIMDALL_VOZ_ATALHO). Gerando uma amostra...")
        with _t.TemporaryDirectory() as d:
            t = Path(d) / "amostra.txt"
            t.write_text(dicionario_voz.aplicar("Esta é uma amostra da voz do Heimdall, para os áudios de estudo."), encoding="utf-8")
            motivo = audio_por_atalho(str(t), Path(d) / "amostra")
            if motivo:
                print("Não deu certo: " + motivo)
                return 1
            subprocess.run(["afplay", str(Path(d) / "amostra.m4a")])
        return 0
    if args.voz:
        vs = vozes_pt()
        print("Vozes em português instaladas (da melhor para a pior):", ", ".join(vs) or "nenhuma")
        voz = escolher_voz()
        if not voz:
            print("Nenhuma voz utilizável. Baixe uma em Ajustes do Sistema > Acessibilidade > Conteúdo falado > Vozes do sistema > Gerenciar vozes (procure Luciana ou Felipe, versão Aprimorada ou Premium).")
            return 1
        ppm = palavras_por_minuto()
        print(f"Voz escolhida: {voz}. Velocidade: {ppm} palavras por minuto (HEIMDALL_VOZ_VELOCIDADE={VELOCIDADE:g}).")
        subprocess.run(["say", "-v", voz, "-r", str(ppm), "Esta é uma amostra da voz e da velocidade usadas nos áudios de estudo."])
        return 0
    if args.teste:
        return teste()
    if not TOKEN or len(TOKEN) < 16:
        print("Erro: defina HEIMDALL_AGENTE_TOKEN (16+ caracteres) no .env.", file=sys.stderr)
        return 1
    VAULT.mkdir(parents=True, exist_ok=True)
    banco.iniciar()
    exames.preparar_pasta()
    threading.Thread(target=eventkit.verificar_na_partida, daemon=True).start()   # pede as permissões de Lembretes e Calendário e registra no log
    threading.Thread(target=_vigiar_documentos, daemon=True).start()
    threading.Thread(target=continuidade.vigiar, daemon=True).start()   # cópia cifrada dos bancos para o R2, só com HEIMDALL_CONTINUIDADE=1
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Agente do Heimdall em http://{HOST}:{PORT} (cofre: {VAULT})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
