#!/usr/bin/env python3
"""Painel web do emulador de AWS (LocalStack ou Moto) do Heimdall.

Serve páginas simples (texto, títulos, tabelas e formulários, bons para leitor de tela) para usar o emulador
pelo navegador: S3 (buckets e arquivos), Lambda (criar, executar, apagar), Glue, Athena e um console geral que chama qualquer
operação de qualquer serviço da AWS (DynamoDB, SQS, SNS, Kinesis, IAM, CloudFormation etc.), além de páginas próprias para Glue
(bancos, tabelas, crawlers e jobs) e Athena (consultas SQL sobre o S3).

Segurança (o painel pode ficar público em cloud.heimdall-ai.tech, então tem camadas):
  1. Escuta só em 127.0.0.1. O emulador (porta 4566) nunca é exposto: não tem senha.
  2. Entrada com senha forte (guardada só como hash PBKDF2 no .env) E código de 6 dígitos (TOTP, o mesmo do app Senhas).
  3. Limite de tentativas por endereço e global, com bloqueio temporário; o código de 6 dígitos não pode ser reaproveitado.
  4. Sessão em cookie HttpOnly, SameSite=Strict, com validade; formulários com token contra CSRF.
  5. Só atende os nomes de site permitidos (HEIMDALL_CLOUD_HOSTS) e manda cabeçalhos de segurança.
  6. Sem senha e sem código configurados, o painel não sobe.

Configuração (tudo no .env):
    python3 heimdall_cloud.py --definir-senha   pede a senha (sem mostrar), gera o código TOTP e grava no .env
    python3 heimdall_cloud.py --novo-codigo     gera só um novo código TOTP (perdeu o app, por exemplo)
    python3 heimdall_cloud.py                   sobe o painel (o start_heimdall.sh faz isso sozinho se houver senha e código)

Variáveis opcionais: HEIMDALL_CLOUD_PORT (8010), HEIMDALL_CLOUD_HOST (127.0.0.1), HEIMDALL_CLOUD_ENDPOINT
(http://127.0.0.1:4566), HEIMDALL_CLOUD_HOSTS (cloud.heimdall-ai.tech,localhost,127.0.0.1), HEIMDALL_CLOUD_SESSAO_HORAS (8),
HEIMDALL_CLOUD_MAX_MB (50, tamanho máximo de envio ao S3).

Usa a biblioteca padrão do Python e o boto3 (já está no requirements.txt).
"""
import argparse
import base64
import getpass
import hashlib
import hmac
import html
import io
import json
import os
import re
import secrets
import struct
import sys
import threading
import time
import urllib.request
import zipfile
from email import policy
from email.parser import BytesParser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlparse

PROJECT_DIR = Path(__file__).resolve().parent


def carregar_env() -> None:
    """Lê do .env só as variáveis HEIMDALL_CLOUD_* (as outras chaves do projeto não entram neste processo)."""
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
        if not chave.startswith("HEIMDALL_CLOUD_"):
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        os.environ.setdefault(chave, valor)


carregar_env()

HOST = os.environ.get("HEIMDALL_CLOUD_HOST", "127.0.0.1")
PORT = int(os.environ.get("HEIMDALL_CLOUD_PORT", "8010"))
ENDPOINT = os.environ.get("HEIMDALL_CLOUD_ENDPOINT", "http://127.0.0.1:4566").rstrip("/")
REGIAO = os.environ.get("HEIMDALL_CLOUD_REGIAO", "us-east-1")
HOSTS_OK = {h.strip().lower() for h in os.environ.get("HEIMDALL_CLOUD_HOSTS", "cloud.heimdall-ai.tech,localhost,127.0.0.1").split(",") if h.strip()}
SENHA_HASH = os.environ.get("HEIMDALL_CLOUD_SENHA_HASH", "")
TOTP_SEGREDO = os.environ.get("HEIMDALL_CLOUD_TOTP_SEGREDO", "")
SESSAO_SEG = int(float(os.environ.get("HEIMDALL_CLOUD_SESSAO_HORAS", "8")) * 3600)
OCIOSA_SEG = 2 * 3600  # sem usar por 2 horas, a sessão cai
MAX_ENVIO = int(float(os.environ.get("HEIMDALL_CLOUD_MAX_MB", "50")) * 1024 * 1024)
ITERACOES = 600_000
COOKIE = "hcloud"

_lock = threading.Lock()


# ----------------------------------------------------------------------------------------
# Senha e código de 6 dígitos (TOTP, RFC 6238)
# ----------------------------------------------------------------------------------------
def hash_senha(senha: str, sal: bytes = None, iteracoes: int = ITERACOES) -> str:
    sal = sal or secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, iteracoes)
    return f"pbkdf2-sha256:{iteracoes}:{sal.hex()}:{h.hex()}"  # sem "$": o .env é lido pelo bash


def confere_senha(senha: str, guardado: str) -> bool:
    try:
        alg, it, sal, esperado = guardado.split(":")
        it, sal, esperado = int(it), bytes.fromhex(sal), bytes.fromhex(esperado)
        if alg != "pbkdf2-sha256" or not 100_000 <= it <= 5_000_000:
            raise ValueError
    except ValueError:
        hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), b"0" * 16, ITERACOES)  # mesmo tempo de uma conferência real
        return False
    calc = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, it)
    return hmac.compare_digest(calc, esperado)


def _chave_totp(segredo: str) -> bytes:
    s = re.sub(r"\s", "", segredo).upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def _hotp(chave: bytes, contador: int, digitos: int = 6) -> str:
    h = hmac.new(chave, struct.pack(">Q", contador), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    n = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** digitos)
    return str(n).zfill(digitos)


_ultimo_contador = 0


def totp_contador(segredo: str, codigo: str, agora: float = None):
    """Passo (de 30 s) em que o código confere, ou None. Aceita o passo atual e os vizinhos (relógios levemente fora)."""
    codigo = re.sub(r"\s", "", codigo or "")
    if not re.fullmatch(r"\d{6}", codigo):
        return None
    try:
        chave = _chave_totp(segredo)
    except Exception:  # noqa: BLE001
        return None
    atual = int((agora if agora is not None else time.time()) // 30)
    achado = None
    for n in (atual - 1, atual, atual + 1):
        if hmac.compare_digest(_hotp(chave, n), codigo):
            achado = n
    return achado


def usar_contador(n: int) -> bool:
    """Marca o passo como usado; recusa reaproveitar um código (ou um mais antigo)."""
    global _ultimo_contador
    with _lock:
        if n <= _ultimo_contador:
            return False
        _ultimo_contador = n
        return True


def confere_totp(segredo: str, codigo: str, agora: float = None) -> bool:
    n = totp_contador(segredo, codigo, agora)
    return n is not None and usar_contador(n)


# ----------------------------------------------------------------------------------------
# Limite de tentativas e sessões (na memória: reiniciar o painel derruba todas as sessões)
# ----------------------------------------------------------------------------------------
JANELA = 15 * 60
MAX_POR_IP = 5
MAX_GLOBAL = 30
_falhas_ip = {}
_falhas_todas = []
_sessoes = {}


def _podar(lista: list, agora: float) -> list:
    return [t for t in lista if agora - t < JANELA]


def login_bloqueado(ip: str) -> bool:
    agora = time.time()
    with _lock:
        _falhas_ip[ip] = _podar(_falhas_ip.get(ip, []), agora)
        _falhas_todas[:] = _podar(_falhas_todas, agora)
        return len(_falhas_ip[ip]) >= MAX_POR_IP or len(_falhas_todas) >= MAX_GLOBAL


def registrar_falha(ip: str) -> None:
    agora = time.time()
    with _lock:
        _falhas_ip.setdefault(ip, []).append(agora)
        _falhas_todas.append(agora)
        if len(_falhas_ip) > 2000:  # memória limitada
            for k in [k for k, v in _falhas_ip.items() if not _podar(v, agora)]:
                _falhas_ip.pop(k, None)


def nova_sessao() -> tuple:
    token = secrets.token_urlsafe(32)
    agora = time.time()
    with _lock:
        for t in [t for t, s in _sessoes.items() if agora > s["ate"] or agora - s["ultimo"] > OCIOSA_SEG]:
            _sessoes.pop(t, None)
        _sessoes[token] = {"csrf": secrets.token_urlsafe(24), "ate": agora + SESSAO_SEG, "ultimo": agora, "flash": None}
        return token, _sessoes[token]


def sessao_valida(token: str):
    agora = time.time()
    with _lock:
        s = _sessoes.get(token or "")
        if not s:
            return None
        if agora > s["ate"] or agora - s["ultimo"] > OCIOSA_SEG:
            _sessoes.pop(token, None)
            return None
        s["ultimo"] = agora
        return s


# ----------------------------------------------------------------------------------------
# Acesso ao emulador
# ----------------------------------------------------------------------------------------
_clientes = {}


class ErroPainel(Exception):
    """Erro de validação com mensagem própria para o usuário."""


def cli(servico: str):
    import boto3
    from botocore.config import Config
    with _lock:
        c = _clientes.get(servico)
        if c is None:
            c = boto3.client(
                servico, endpoint_url=ENDPOINT, region_name=REGIAO,
                aws_access_key_id="test", aws_secret_access_key="test",
                config=Config(retries={"max_attempts": 1}, connect_timeout=3, read_timeout=120, s3={"addressing_style": "path"}),
            )
            _clientes[servico] = c
        return c


def saude_emulador() -> dict:
    """Estado do emulador. O LocalStack responde em /_localstack/health; o Moto, não (nesse caso só confirma que responde)."""
    try:
        with urllib.request.urlopen(ENDPOINT + "/_localstack/health", timeout=4) as r:
            dados = json.loads(r.read().decode("utf-8", "replace"))
        if isinstance(dados, dict) and "services" in dados:
            return {"ok": True, "servicos": dados.get("services") or {}, "versao": str(dados.get("version", "")), "edicao": str(dados.get("edition", ""))}
    except Exception:  # noqa: BLE001
        pass
    try:
        cli("s3").list_buckets()
        return {"ok": True, "servicos": {}, "versao": "", "edicao": "emulador sem endereço de saúde (Moto?)"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erro": f"{type(e).__name__}: {str(e)[:200]}"}


def _json_padrao(o):
    if hasattr(o, "read"):
        o = o.read(100_000)
    if isinstance(o, (bytes, bytearray)):
        try:
            return bytes(o).decode("utf-8")
        except UnicodeDecodeError:
            return "base64:" + base64.b64encode(bytes(o)).decode()
    return str(o)


def como_json(obj) -> str:
    texto = json.dumps(obj, default=_json_padrao, indent=2, ensure_ascii=False)
    if len(texto) > 200_000:
        texto = texto[:200_000] + "\n... (resultado cortado em 200 mil caracteres)"
    return texto


# ----------------------------------------------------------------------------------------
# HTML (semântico e simples, para leitor de tela)
# ----------------------------------------------------------------------------------------
e = html.escape

CSS = """
:root{color-scheme:light dark;--fundo:#fff;--texto:#111;--suave:#444;--linha:#999;--acento:#0a4fb3;--erro:#a30000;--ok:#0a6b2d}
@media (prefers-color-scheme:dark){:root{--fundo:#111;--texto:#f2f2f2;--suave:#c8c8c8;--linha:#777;--acento:#8ab8ff;--erro:#ff9b9b;--ok:#8be0a4}}
body{background:var(--fundo);color:var(--texto);font:18px/1.5 system-ui,sans-serif;margin:0;padding:0 1rem 3rem;max-width:60rem;margin-inline:auto}
a{color:var(--acento)}a:focus,button:focus,input:focus,select:focus,textarea:focus{outline:3px solid var(--acento);outline-offset:2px}
.pular{position:absolute;left:-999px}.pular:focus{left:0;background:var(--fundo);padding:.5rem}
header{border-bottom:1px solid var(--linha);margin-bottom:1rem}nav ul{list-style:none;display:flex;gap:1.25rem;flex-wrap:wrap;padding:0}
table{border-collapse:collapse;width:100%;margin:.5rem 0 1.5rem}th,td{border:1px solid var(--linha);padding:.4rem .6rem;text-align:left;vertical-align:top}
caption{text-align:left;font-weight:700;padding:.25rem 0}label{display:block;font-weight:700;margin-top:.8rem}
input[type=text],input[type=password],input[type=file],select,textarea{width:100%;box-sizing:border-box;font:inherit;padding:.4rem;background:var(--fundo);color:var(--texto);border:1px solid var(--linha)}
textarea{min-height:9rem;font-family:ui-monospace,Menlo,monospace}button{font:inherit;padding:.45rem .9rem;margin-top:.8rem;cursor:pointer}
pre{white-space:pre-wrap;word-break:break-word;border:1px solid var(--linha);padding:.7rem;overflow:auto}
.ok{color:var(--ok);font-weight:700}.erro{color:var(--erro);font-weight:700}form.linha{display:inline}form.linha button{margin:0}
.nota{color:var(--suave)}
"""


def pagina(titulo: str, corpo: str, sess: dict = None, logado: bool = True) -> bytes:
    aviso = ""
    if sess and sess.get("flash"):
        tipo, texto = sess["flash"]
        sess["flash"] = None
        aviso = f'<p class="{"ok" if tipo == "ok" else "erro"}" role="{"status" if tipo == "ok" else "alert"}">{e(texto)}</p>'
    nav = ""
    if logado and sess:
        nav = ('<nav aria-label="Principal"><ul><li><a href="/">Início</a></li><li><a href="/s3">S3</a></li><li><a href="/lambda">Lambda</a></li>'
               '<li><a href="/glue">Glue</a></li><li><a href="/athena">Athena</a></li><li><a href="/console">Console geral</a></li><li><form class="linha" method="post" action="/sair">'
               f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}"><button type="submit">Sair</button></form></li></ul></nav>')
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow"><title>{e(titulo)} - Heimdall Cloud</title><style>{CSS}</style></head><body>'
            f'<a class="pular" href="#principal">Pular para o conteúdo</a><header><p><strong>Heimdall Cloud</strong></p>{nav}</header>'
            f'<main id="principal"><h1>{e(titulo)}</h1>{aviso}{corpo}</main></body></html>').encode("utf-8")


def csrf(sess: dict) -> str:
    return f'<input type="hidden" name="csrf" value="{e(sess["csrf"])}">'


def pg_entrar(erro: str = "") -> bytes:
    msg = f'<p class="erro" role="alert">{e(erro)}</p>' if erro else ""
    corpo = (f'{msg}<form method="post" action="/entrar"><label for="senha">Senha</label>'
             '<input id="senha" name="senha" type="password" autocomplete="current-password" required>'
             '<label for="codigo">Código de verificação de 6 dígitos</label>'
             '<input id="codigo" name="codigo" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="7" required>'
             '<button type="submit">Entrar</button></form>')
    return pagina("Entrar", corpo, None, logado=False)


def pg_inicio() -> str:
    s = saude_emulador()
    if not s["ok"]:
        estado = f'<p class="erro" role="alert">O emulador não respondeu em {e(ENDPOINT)}. Detalhe: {e(s["erro"])}. Confira com: docker ps | grep -E "localstack|moto"</p>'
        tabela = ""
    else:
        rodando = sorted(k for k, v in s["servicos"].items() if str(v) in ("running", "ready"))
        disp = len([1 for v in s["servicos"].values() if str(v) in ("available", "disabled")])
        extra = f" Versão {e(s['versao'])}." if s["versao"] else ""
        estado = f'<p class="ok">O emulador está respondendo.{extra} {e(s["edicao"])}</p>'
        if s["servicos"]:
            linhas = "".join(f"<tr><td>{e(k)}</td><td>em uso</td></tr>" for k in rodando) or '<tr><td colspan="2">Nenhum serviço em uso ainda.</td></tr>'
            tabela = (f'<table><caption>Serviços em uso agora</caption><thead><tr><th scope="col">Serviço</th><th scope="col">Situação</th></tr></thead>'
                      f'<tbody>{linhas}</tbody></table><p class="nota">Outros {disp} serviços sobem sozinhos na primeira vez que você os usa.</p>')
        else:
            tabela = ""
    return (f'<h2>Estado do emulador</h2>{estado}{tabela}<h2>Para usar de código no Mac</h2>'
            f'<p>Endereço: http://localhost:4566. Chave de acesso e chave secreta: test. Região: {e(REGIAO)}. '
            'Exemplo na AWS CLI: aws --endpoint-url http://localhost:4566 s3 ls</p>'
            '<h2>O que dá para fazer aqui</h2><ol><li><a href="/s3">S3</a>: criar buckets, enviar, baixar e apagar arquivos.</li>'
            '<li><a href="/lambda">Lambda</a>: criar uma função a partir de código, executar e apagar.</li>'
            '<li><a href="/glue">Glue</a>: bancos de dados, tabelas, crawlers e jobs do catálogo de dados.</li>'
            '<li><a href="/athena">Athena</a>: consultas SQL sobre os arquivos do S3, usando as tabelas do Glue.</li>'
            '<li><a href="/console">Console geral</a>: qualquer operação de qualquer serviço (DynamoDB, SQS, SNS, Kinesis, IAM, CloudFormation e outros).</li></ol>'
            '<h2>Roteiro de estudo: do arquivo à consulta</h2><ol><li>No S3, crie um bucket e envie um arquivo CSV.</li>'
            '<li>No Glue, crie um banco de dados.</li><li>No Glue, abra o banco e crie uma tabela apontando para a pasta do S3 onde está o CSV.</li>'
            '<li>No Athena, escolha o banco e rode um SELECT na tabela.</li></ol>')


# ---- S3 ----
BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


def pg_s3(sess: dict) -> str:
    buckets = cli("s3").list_buckets().get("Buckets", [])
    linhas = ""
    for b in buckets:
        n = b["Name"]
        criado = b.get("CreationDate")
        linhas += (f'<tr><td><a href="/s3/b?{urlencode({"bucket": n})}">{e(n)}</a></td><td>{e(str(criado)[:19]) if criado else ""}</td>'
                   f'<td><form class="linha" method="post" action="/s3/apagar">{csrf(sess)}<input type="hidden" name="bucket" value="{e(n)}">'
                   f'<label class="linha"><input type="checkbox" name="esvaziar" value="1"> esvaziar antes</label> '
                   f'<button type="submit">Apagar bucket {e(n)}</button></form></td></tr>')
    tabela = (f'<table><caption>Buckets ({len(buckets)})</caption><thead><tr><th scope="col">Nome</th><th scope="col">Criado em</th><th scope="col">Ações</th></tr></thead>'
              f'<tbody>{linhas or "<tr><td colspan=3>Nenhum bucket ainda.</td></tr>"}</tbody></table>')
    form = (f'<h2>Criar bucket</h2><form method="post" action="/s3/criar">{csrf(sess)}<label for="nb">Nome (letras minúsculas, números, ponto e hífen; 3 a 63 caracteres)</label>'
            '<input id="nb" name="bucket" type="text" required><button type="submit">Criar bucket</button></form>')
    return tabela + form


def pg_s3_bucket(sess: dict, bucket: str, prefixo: str) -> str:
    r = cli("s3").list_objects_v2(Bucket=bucket, Prefix=prefixo, Delimiter="/", MaxKeys=200)
    linhas = ""
    for p in r.get("CommonPrefixes", []):
        pf = p["Prefix"]
        linhas += f'<tr><td><a href="/s3/b?{urlencode({"bucket": bucket, "prefixo": pf})}">{e(pf)}</a> (pasta)</td><td></td><td></td><td></td></tr>'
    for o in r.get("Contents", []):
        k = o["Key"]
        if k == prefixo:
            continue
        linhas += (f'<tr><td>{e(k)}</td><td>{o.get("Size", 0)}</td><td>{e(str(o.get("LastModified", ""))[:19])}</td><td>'
                   f'<a href="/s3/baixar?{urlencode({"bucket": bucket, "chave": k})}">Baixar {e(k)}</a> '
                   f'<form class="linha" method="post" action="/s3/apagar-objeto">{csrf(sess)}<input type="hidden" name="bucket" value="{e(bucket)}">'
                   f'<input type="hidden" name="chave" value="{e(k)}"><input type="hidden" name="prefixo" value="{e(prefixo)}">'
                   f'<button type="submit">Apagar {e(k)}</button></form></td></tr>')
    corte = '<p class="nota">Mostrando os primeiros 200 itens.</p>' if r.get("IsTruncated") else ""
    subir = f'<p><a href="/s3/b?{urlencode({"bucket": bucket, "prefixo": prefixo.rsplit("/", 2)[0] + "/" if prefixo.count("/") > 1 else ""})}">Subir um nível</a></p>' if prefixo else ""
    tabela = (f'<p><a href="/s3">Voltar aos buckets</a></p>{subir}<table><caption>Conteúdo de {e(bucket)}/{e(prefixo)}</caption>'
              '<thead><tr><th scope="col">Nome</th><th scope="col">Tamanho em bytes</th><th scope="col">Modificado em</th><th scope="col">Ações</th></tr></thead>'
              f'<tbody>{linhas or "<tr><td colspan=4>Vazio.</td></tr>"}</tbody></table>{corte}')
    form = (f'<h2>Enviar arquivo</h2><form method="post" action="/s3/enviar" enctype="multipart/form-data">{csrf(sess)}'
            f'<input type="hidden" name="bucket" value="{e(bucket)}"><input type="hidden" name="prefixo" value="{e(prefixo)}">'
            f'<label for="arq">Arquivo (até {MAX_ENVIO // (1024 * 1024)} MB)</label><input id="arq" name="arquivo" type="file" required>'
            '<label for="nome">Nome no bucket (deixe vazio para usar o nome do arquivo)</label><input id="nome" name="nome" type="text">'
            '<button type="submit">Enviar</button></form>')
    return tabela + form


def esvaziar_bucket(s3, bucket: str) -> None:
    for pagina_ in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        objs = [{"Key": o["Key"]} for o in pagina_.get("Contents", [])]
        if objs:
            s3.delete_objects(Bucket=bucket, Delete={"Objects": objs})


# ---- Lambda ----
CODIGO_PADRAO = 'def handler(event, context):\n    print("evento recebido:", event)\n    return {"ok": True, "evento": event}\n'
NOME_FN_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
HANDLER_RE = re.compile(r"^([A-Za-z_]\w*)\.([A-Za-z_]\w*)$")


def pg_lambda(sess: dict, resultado: str = "") -> str:
    fns = cli("lambda").list_functions().get("Functions", [])
    linhas = ""
    for f in fns:
        n = f["FunctionName"]
        linhas += (f'<tr><td>{e(n)}</td><td>{e(f.get("Runtime", ""))}</td><td>{e(f.get("Handler", ""))}</td><td>{e(str(f.get("LastModified", ""))[:19])}</td><td>'
                   f'<form class="linha" method="post" action="/lambda/apagar">{csrf(sess)}<input type="hidden" name="nome" value="{e(n)}">'
                   f'<button type="submit">Apagar {e(n)}</button></form></td></tr>')
    tabela = (f'<table><caption>Funções ({len(fns)})</caption><thead><tr><th scope="col">Nome</th><th scope="col">Runtime</th><th scope="col">Handler</th>'
              f'<th scope="col">Modificada em</th><th scope="col">Ações</th></tr></thead><tbody>{linhas or "<tr><td colspan=5>Nenhuma função ainda.</td></tr>"}</tbody></table>')
    nota = ('<p class="nota">As funções executam em contêineres do Docker, que o LocalStack controla. Na primeira execução de cada runtime o Docker baixa a imagem, '
            'o que pode demorar. Para desligar a execução: HEIMDALL_LOCALSTACK_DOCKER=0 no .env.</p>')
    opcoes = "".join(f'<option value="{e(f["FunctionName"])}">{e(f["FunctionName"])}</option>' for f in fns)
    res = f'<h2>Resultado da execução</h2><pre>{e(resultado)}</pre>' if resultado else ""
    invocar = (f'<h2>Executar função</h2><form method="post" action="/lambda/invocar">{csrf(sess)}<label for="fn">Função</label>'
               f'<select id="fn" name="nome" required>{opcoes}</select><label for="pl">Evento em JSON</label><textarea id="pl" name="payload">{{}}</textarea>'
               '<button type="submit">Executar</button></form>') if fns else ""
    criar = (f'<h2>Criar função</h2><form method="post" action="/lambda/criar">{csrf(sess)}<label for="n">Nome</label><input id="n" name="nome" type="text" required>'
             '<label for="rt">Runtime</label><select id="rt" name="runtime"><option>python3.12</option><option>python3.13</option></select>'
             '<label for="h">Handler (arquivo.função)</label><input id="h" name="handler" type="text" value="app.handler" required>'
             f'<label for="c">Código Python (vira o arquivo do handler)</label><textarea id="c" name="codigo">{e(CODIGO_PADRAO)}</textarea>'
             '<button type="submit">Criar função</button></form>')
    return nota + tabela + res + invocar + criar


# ---- Glue ----
BANCO_RE = re.compile(r"^[a-z_][a-z0-9_]{0,127}$")  # bancos e tabelas em minúsculas, como o Athena exige
TRABALHO_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")  # crawlers e jobs
COLUNA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
TIPO_RE = re.compile(r"^[A-Za-z0-9_<>,():. ]{1,200}$")
S3_RE = re.compile(r"^s3://[a-z0-9][a-z0-9.-]{1,61}[a-z0-9](/[^\s]*)?$")
PAPEL_GLUE = "arn:aws:iam::000000000000:role/glue-role"
BUCKET_SCRIPTS = "glue-scripts"
BUCKET_ATHENA = "athena-resultados"
SCRIPT_GLUE_PADRAO = ('import sys\nfrom awsglue.utils import getResolvedOptions\n\nargs = getResolvedOptions(sys.argv, ["JOB_NAME"])\n'
                      'print("Job", args["JOB_NAME"], "executado")\n')
_TEXTO = "org.apache.hadoop.mapred.TextInputFormat"
_SAIDA_TEXTO = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"
FORMATOS = {
    "csv": (_TEXTO, _SAIDA_TEXTO, "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe", {"field.delim": ","}),
    "json": (_TEXTO, _SAIDA_TEXTO, "org.openx.data.jsonserde.JsonSerDe", {}),
    "parquet": ("org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat", "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe", {}),
}


def valida(regex, valor: str, o_que: str) -> str:
    valor = (valor or "").strip()
    if not regex.match(valor):
        raise ErroPainel(f"{o_que} inválido")
    return valor


def garantir_bucket(nome: str) -> None:
    s3 = cli("s3")
    try:
        s3.head_bucket(Bucket=nome)
    except Exception:  # noqa: BLE001
        s3.create_bucket(Bucket=nome)


def montar_tabela(nome: str, local: str, formato: str, colunas_txt: str, cabecalho: bool) -> dict:
    if formato not in FORMATOS:
        raise ErroPainel("formato inválido")
    cols = []
    for linha in colunas_txt.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        partes = linha.split(None, 1)
        if len(partes) != 2 or not COLUNA_RE.match(partes[0]) or not TIPO_RE.match(partes[1].strip()):
            raise ErroPainel(f"coluna inválida: '{linha[:60]}'. Escreva uma por linha, com nome e tipo, como: id int")
        cols.append({"Name": partes[0].lower(), "Type": partes[1].strip().lower()})
    if not cols or len(cols) > 300:
        raise ErroPainel("informe de 1 a 300 colunas")
    entrada, saida, serde, par_serde = FORMATOS[formato]
    params = {"EXTERNAL": "TRUE", "classification": formato}
    if formato == "csv" and cabecalho:
        params["skip.header.line.count"] = "1"
    return {"Name": nome, "TableType": "EXTERNAL_TABLE", "Parameters": params,
            "StorageDescriptor": {"Columns": cols, "Location": local, "InputFormat": entrada, "OutputFormat": saida,
                                  "SerdeInfo": {"SerializationLibrary": serde, "Parameters": dict(par_serde)}}}


def _botao(sess: dict, acao: str, campos: dict, rotulo: str) -> str:
    ocultos = "".join(f'<input type="hidden" name="{e(k)}" value="{e(v)}">' for k, v in campos.items())
    return f'<form class="linha" method="post" action="{e(acao)}">{csrf(sess)}{ocultos}<button type="submit">{e(rotulo)}</button></form>'


def pg_glue(sess: dict) -> str:
    g = cli("glue")
    bancos = g.get_databases().get("DatabaseList", [])
    linhas = "".join(
        f'<tr><td><a href="/glue/tabelas?{urlencode({"banco": b["Name"]})}">{e(b["Name"])}</a></td><td>'
        f'{_botao(sess, "/glue/banco/apagar", {"nome": b["Name"]}, "Apagar banco " + b["Name"])}</td></tr>' for b in bancos)
    t_bancos = (f'<table><caption>Bancos de dados ({len(bancos)})</caption><thead><tr><th scope="col">Nome (abre as tabelas)</th><th scope="col">Ações</th></tr></thead>'
                f'<tbody>{linhas or "<tr><td colspan=2>Nenhum banco ainda.</td></tr>"}</tbody></table>')
    f_banco = (f'<h2>Criar banco de dados</h2><form method="post" action="/glue/banco/criar">{csrf(sess)}'
               '<label for="gb">Nome (minúsculas, números e sublinhado)</label><input id="gb" name="nome" type="text" required>'
               '<button type="submit">Criar banco</button></form>')
    crawlers = g.get_crawlers().get("Crawlers", [])
    lc = ""
    for c in crawlers:
        n = c["Name"]
        alvo = ", ".join(t.get("Path", "") for t in (c.get("Targets") or {}).get("S3Targets", []))
        ultimo = (c.get("LastCrawl") or {}).get("Status", "nunca executou")
        lc += (f'<tr><td>{e(n)}</td><td>{e(c.get("DatabaseName", ""))}</td><td>{e(alvo)}</td><td>{e(str(c.get("State", "")))}; última: {e(str(ultimo))}</td><td>'
               f'{_botao(sess, "/glue/crawler/iniciar", {"nome": n}, "Executar " + n)} {_botao(sess, "/glue/crawler/apagar", {"nome": n}, "Apagar " + n)}</td></tr>')
    t_crawlers = (f'<h2>Crawlers</h2><table><caption>Crawlers ({len(crawlers)})</caption><thead><tr><th scope="col">Nome</th><th scope="col">Banco</th>'
                  f'<th scope="col">Pasta no S3</th><th scope="col">Situação</th><th scope="col">Ações</th></tr></thead>'
                  f'<tbody>{lc or "<tr><td colspan=5>Nenhum crawler ainda.</td></tr>"}</tbody></table>')
    opcoes = "".join(f'<option value="{e(b["Name"])}">{e(b["Name"])}</option>' for b in bancos)
    f_crawler = (f'<h3>Criar crawler</h3><form method="post" action="/glue/crawler/criar">{csrf(sess)}<label for="cn">Nome</label><input id="cn" name="nome" type="text" required>'
                 f'<label for="cb">Banco onde as tabelas serão criadas</label><select id="cb" name="banco" required>{opcoes}</select>'
                 '<label for="cl">Pasta no S3 (como s3://meu-bucket/dados/)</label><input id="cl" name="local" type="text" required>'
                 '<button type="submit">Criar crawler</button></form>') if bancos else '<p class="nota">Crie um banco de dados para poder criar um crawler.</p>'
    jobs = g.get_jobs().get("Jobs", [])
    lj = ""
    for j in jobs:
        n = j["Name"]
        try:
            runs = g.get_job_runs(JobName=n, MaxResults=1).get("JobRuns", [])
            ultimo = f'{runs[0].get("JobRunState", "?")} ({runs[0].get("Id", "")[:12]})' if runs else "nunca executou"
        except Exception:  # noqa: BLE001
            ultimo = "não consegui consultar"
        lj += (f'<tr><td>{e(n)}</td><td>{e(str(j.get("GlueVersion", "")))}</td><td>{e(ultimo)}</td><td>'
               f'{_botao(sess, "/glue/job/iniciar", {"nome": n}, "Executar " + n)} {_botao(sess, "/glue/job/apagar", {"nome": n}, "Apagar " + n)}</td></tr>')
    t_jobs = (f'<h2>Jobs</h2><table><caption>Jobs ({len(jobs)})</caption><thead><tr><th scope="col">Nome</th><th scope="col">Versão do Glue</th>'
              f'<th scope="col">Última execução</th><th scope="col">Ações</th></tr></thead><tbody>{lj or "<tr><td colspan=4>Nenhum job ainda.</td></tr>"}</tbody></table>')
    f_job = (f'<h3>Criar job</h3><form method="post" action="/glue/job/criar">{csrf(sess)}<label for="jn">Nome</label><input id="jn" name="nome" type="text" required>'
             '<label for="jv">Versão do Glue</label><select id="jv" name="versao"><option>4.0</option><option>5.0</option></select>'
             f'<label for="jc">Script Python (é guardado no bucket {BUCKET_SCRIPTS}, criado se faltar)</label><textarea id="jc" name="codigo">{e(SCRIPT_GLUE_PADRAO)}</textarea>'
             '<button type="submit">Criar job</button></form>')
    return t_bancos + f_banco + t_crawlers + f_crawler + t_jobs + f_job


def pg_glue_tabelas(sess: dict, banco: str) -> str:
    tabelas = cli("glue").get_tables(DatabaseName=banco).get("TableList", [])
    linhas = ""
    for t in tabelas:
        sd = t.get("StorageDescriptor") or {}
        cols = ", ".join(f'{c.get("Name")} {c.get("Type")}' for c in sd.get("Columns", []))
        linhas += (f'<tr><td>{e(t["Name"])}</td><td>{e(cols)}</td><td>{e(sd.get("Location", ""))}</td><td>{e((t.get("Parameters") or {}).get("classification", ""))}</td><td>'
                   f'{_botao(sess, "/glue/tabela/apagar", {"banco": banco, "nome": t["Name"]}, "Apagar tabela " + t["Name"])}</td></tr>')
    tabela = (f'<p><a href="/glue">Voltar ao Glue</a></p><table><caption>Tabelas de {e(banco)} ({len(tabelas)})</caption><thead><tr><th scope="col">Nome</th>'
              f'<th scope="col">Colunas</th><th scope="col">Local no S3</th><th scope="col">Formato</th><th scope="col">Ações</th></tr></thead>'
              f'<tbody>{linhas or "<tr><td colspan=5>Nenhuma tabela ainda.</td></tr>"}</tbody></table>')
    form = (f'<h2>Criar tabela</h2><form method="post" action="/glue/tabela/criar">{csrf(sess)}<input type="hidden" name="banco" value="{e(banco)}">'
            '<label for="tn">Nome da tabela (minúsculas, números e sublinhado)</label><input id="tn" name="nome" type="text" required>'
            '<label for="tl">Pasta no S3 onde estão os arquivos (como s3://meu-bucket/clientes/)</label><input id="tl" name="local" type="text" required>'
            '<label for="tf">Formato dos arquivos</label><select id="tf" name="formato"><option>csv</option><option>json</option><option>parquet</option></select>'
            '<label><input type="checkbox" name="cabecalho" value="1" checked> O CSV tem linha de cabeçalho (ela é ignorada)</label>'
            '<label for="tc">Colunas, uma por linha, com nome e tipo (por exemplo: id int, nome string, valor double)</label>'
            '<textarea id="tc" name="colunas">id int\nnome string</textarea><button type="submit">Criar tabela</button></form>')
    return tabela + form


# ---- Athena ----
ID_CONSULTA_RE = re.compile(r"^[0-9A-Za-z-]{8,64}$")
EXEMPLOS_ATHENA = ["SHOW DATABASES", "SHOW TABLES", "SELECT * FROM nome_da_tabela LIMIT 10", "SELECT count(*) AS total FROM nome_da_tabela"]


def esperar_consulta(a, qid: str, limite: float = 60.0) -> str:
    fim = time.time() + limite
    while time.time() < fim:
        est = a.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]["State"]
        if est in ("SUCCEEDED", "FAILED", "CANCELLED"):
            return est
        time.sleep(0.7)
    return "RUNNING"


def pg_athena(sess: dict, sql: str = "SHOW DATABASES", banco: str = "default", qid: str = "") -> str:
    a = cli("athena")
    nomes = {"default"}
    try:
        nomes |= {b["Name"] for b in cli("glue").get_databases().get("DatabaseList", [])}
    except Exception:  # noqa: BLE001
        pass
    opcoes = "".join(f'<option value="{e(n)}"{" selected" if n == banco else ""}>{e(n)}</option>' for n in sorted(nomes))
    form = (f'<form method="post" action="/athena/executar">{csrf(sess)}<label for="ab">Banco de dados</label><select id="ab" name="banco">{opcoes}</select>'
            f'<label for="aq">Consulta SQL</label><textarea id="aq" name="sql">{e(sql)}</textarea><button type="submit">Executar consulta</button></form>'
            f'<p class="nota">Os resultados ficam no bucket {BUCKET_ATHENA}. Exemplos de consulta: {e("; ".join(EXEMPLOS_ATHENA))}.</p>')
    res = ""
    if qid:
        ex = a.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        est = ex["Status"]["State"]
        motivo = ex["Status"].get("StateChangeReason", "")
        cab = f'<h2>Resultado</h2><p>Consulta {e(qid)}: {e(est)}.</p><pre>{e(ex.get("Query", ""))}</pre>'
        if est == "SUCCEEDED":
            linhas = a.get_query_results(QueryExecutionId=qid, MaxResults=1000).get("ResultSet", {}).get("Rows", [])
            if not linhas:
                res = cab + "<p>Concluída, sem linhas para mostrar.</p>"
            else:
                def cel(l): return [d.get("VarCharValue", "") for d in l.get("Data", [])]
                topo = "".join(f'<th scope="col">{e(c)}</th>' for c in cel(linhas[0]))
                corpo = "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in cel(l)) + "</tr>" for l in linhas[1:501])
                res = (cab + f'<table><caption>{max(len(linhas) - 1, 0)} linha(s) (a primeira linha de dados é a 1)</caption><thead><tr>{topo}</tr></thead>'
                       f'<tbody>{corpo or "<tr><td>Sem linhas de dados.</td></tr>"}</tbody></table>')
        elif est in ("FAILED", "CANCELLED"):
            res = cab + f'<p class="erro" role="alert">{e(motivo or "A consulta não terminou com sucesso.")}</p>'
        else:
            res = cab + f'<p>Ainda executando. <a href="/athena/resultado?{urlencode({"id": qid})}">Atualizar este resultado</a></p>'
    hist = ""
    try:
        ids = a.list_query_executions(MaxResults=10).get("QueryExecutionIds", [])
        if ids:
            itens = a.batch_get_query_execution(QueryExecutionIds=ids).get("QueryExecutions", [])
            lin = "".join(f'<tr><td>{e(i["Status"]["State"])}</td><td>{e(i.get("Query", "")[:100])}</td>'
                          f'<td><a href="/athena/resultado?{urlencode({"id": i["QueryExecutionId"]})}">Ver resultado</a></td></tr>' for i in itens)
            hist = (f'<h2>Últimas consultas</h2><table><caption>Últimas {len(itens)} consultas</caption><thead><tr><th scope="col">Situação</th>'
                    f'<th scope="col">Consulta</th><th scope="col">Ação</th></tr></thead><tbody>{lin}</tbody></table>')
    except Exception:  # noqa: BLE001
        pass
    return form + res + hist


# ---- Console geral ----
EXEMPLOS = [
    ("S3: listar buckets", "s3", "list_buckets", "{}"),
    ("DynamoDB: criar tabela clientes", "dynamodb", "create_table", '{"TableName":"clientes","KeySchema":[{"AttributeName":"id","KeyType":"HASH"}],"AttributeDefinitions":[{"AttributeName":"id","AttributeType":"S"}],"BillingMode":"PAY_PER_REQUEST"}'),
    ("DynamoDB: gravar um item", "dynamodb", "put_item", '{"TableName":"clientes","Item":{"id":{"S":"1"},"nome":{"S":"Ana"}}}'),
    ("DynamoDB: ler a tabela", "dynamodb", "scan", '{"TableName":"clientes"}'),
    ("SQS: criar fila", "sqs", "create_queue", '{"QueueName":"fila-teste"}'),
    ("Kinesis: criar stream", "kinesis", "create_stream", '{"StreamName":"fluxo","ShardCount":1}'),
    ("Glue: criar banco de dados", "glue", "create_database", '{"DatabaseInput":{"Name":"meu_banco"}}'),
]


def servicos_aws() -> list:
    import boto3
    return sorted(boto3.session.Session().get_available_services())


def pg_console(sess: dict, servico: str = "s3", operacao: str = "", parametros: str = "{}", resultado: str = "", erro: str = "") -> str:
    ops = ""
    try:
        todos = servicos_aws()
    except Exception as ex:  # noqa: BLE001
        raise ErroPainel("o boto3 não está instalado no ambiente do painel (pip install boto3)") from ex
    if servico not in todos:
        servico = "s3"
    try:
        nomes = sorted(cli(servico).meta.method_to_api_mapping.keys())
        ops = f'<details><summary>Operações de {e(servico)} ({len(nomes)})</summary><ul>{"".join(f"<li>{e(n)}</li>" for n in nomes)}</ul></details>'
    except Exception:  # noqa: BLE001
        pass
    opts = "".join(f'<option value="{e(s)}"{" selected" if s == servico else ""}>{e(s)}</option>' for s in todos)
    ex = "".join(f'<li><a href="/console?{urlencode({"servico": s, "operacao": o, "parametros": p})}">{e(t)}</a></li>' for t, s, o, p in EXEMPLOS)
    res = ""
    if erro:
        res = f'<h2>Erro</h2><pre class="erro" role="alert">{e(erro)}</pre>'
    elif resultado:
        res = f'<h2>Resultado</h2><pre>{e(resultado)}</pre>'
    return (f'<p>Chama qualquer operação da API de um serviço. Use o nome do boto3 (minúsculas com sublinhado, como list_tables) e os parâmetros em JSON.</p>'
            f'<form method="get" action="/console"><label for="sv0">Ver as operações de um serviço</label><select id="sv0" name="servico">{opts}</select>'
            f'<button type="submit">Ver operações</button></form>{ops}'
            f'<h2>Executar</h2><form method="post" action="/console">{csrf(sess)}<label for="sv">Serviço</label><select id="sv" name="servico">{opts}</select>'
            f'<label for="op">Operação</label><input id="op" name="operacao" type="text" value="{e(operacao)}" required autocapitalize="none" autocomplete="off">'
            f'<label for="pa">Parâmetros em JSON</label><textarea id="pa" name="parametros">{e(parametros)}</textarea><button type="submit">Executar</button></form>'
            f'{res}<h2>Exemplos para começar</h2><ol>{ex}</ol>')


# ----------------------------------------------------------------------------------------
# Servidor
# ----------------------------------------------------------------------------------------
def _formulario(corpo: bytes, tipo: str) -> tuple:
    """Devolve (campos, arquivos). Aceita application/x-www-form-urlencoded e multipart/form-data."""
    if tipo.startswith("multipart/form-data"):
        msg = BytesParser(policy=policy.HTTP).parsebytes(b"Content-Type: " + tipo.encode("latin-1", "replace") + b"\r\nMIME-Version: 1.0\r\n\r\n" + corpo)
        campos, arquivos = {}, {}
        for parte in msg.iter_parts():
            nome = parte.get_param("name", header="content-disposition")
            if not nome:
                continue
            arq = parte.get_filename()
            dados = parte.get_payload(decode=True) or b""
            if arq is not None:
                arquivos[nome] = (arq, dados)
            else:
                campos[nome] = dados.decode("utf-8", "replace")
        return campos, arquivos
    return {k: v[0] for k, v in parse_qs(corpo.decode("utf-8", "replace"), keep_blank_values=True).items()}, {}


class Painel(BaseHTTPRequestHandler):
    server_version = "HeimdallCloud"
    sys_version = ""
    protocol_version = "HTTP/1.0"  # fecha a conexão a cada resposta

    def log_message(self, fmt, *args):  # nunca registra corpo, senha nem parâmetros
        sys.stderr.write("%s %s %s\n" % (time.strftime("%H:%M:%S"), self.address_string(), (fmt % args).split("?")[0]))

    # --- utilidades ---
    def _ip(self) -> str:
        return (self.headers.get("CF-Connecting-IP") or self.client_address[0]).strip()[:64]

    def _https(self) -> bool:
        return (self.headers.get("X-Forwarded-Proto", "").lower() == "https") or ("https" in self.headers.get("Cf-Visitor", ""))

    def _enviar(self, status: int, corpo: bytes, tipo: str = "text/html; charset=utf-8", extra: list = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _ir(self, destino: str, extra: list = None) -> None:
        self._enviar(303, b"", extra=[("Location", destino)] + (extra or []))

    def _sessao(self):
        c = SimpleCookie()
        try:
            c.load(self.headers.get("Cookie", ""))
        except Exception:  # noqa: BLE001
            return None, None
        m = c.get(COOKIE)
        token = m.value if m else ""
        return token, sessao_valida(token)

    def _corpo(self, limite: int) -> bytes:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ErroPainel("tamanho inválido")
        if n < 0 or n > limite:
            raise ErroPainel("pedido grande demais")
        return self.rfile.read(n)

    def _cookie(self, token: str, apagar: bool = False) -> tuple:
        v = f"{COOKIE}={'' if apagar else token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if apagar else SESSAO_SEG}"
        if self._https():
            v += "; Secure"
        return ("Set-Cookie", v)

    # --- despacho ---
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
        try:
            if rota == "/entrar":
                self._entrar(metodo)
                return
            token, sess = self._sessao()
            if not sess:
                self._ir("/entrar")
                return
            if metodo == "POST":
                self._post(rota, token, sess)
            else:
                self._get(rota, q, sess)
        except ErroPainel as ex:
            self._falha(metodo, rota, str(ex))
        except Exception as ex:  # noqa: BLE001
            self._falha(metodo, rota, f"{type(ex).__name__}: {str(ex)[:400]}")

    def _falha(self, metodo: str, rota: str, texto: str) -> None:
        _, sess = self._sessao()
        if not sess:
            self._enviar(400, pagina("Erro", f'<p class="erro" role="alert">{e(texto)}</p>', None, logado=False))
        elif metodo == "POST":
            sess["flash"] = ("erro", texto)
            self._ir("/s3" if rota.startswith("/s3") else "/lambda" if rota.startswith("/lambda") else "/glue" if rota.startswith("/glue") else "/athena" if rota.startswith("/athena") else "/")
        else:
            self._enviar(500, pagina("Erro", '<p><a href="/">Voltar ao início</a></p>', {**sess, "flash": ("erro", texto)}))

    # --- entrar / sair ---
    def _entrar(self, metodo: str) -> None:
        if metodo == "GET":
            self._enviar(200, pg_entrar())
            return
        ip = self._ip()
        if login_bloqueado(ip):
            self._enviar(429, pg_entrar("Tentativas demais. Aguarde 15 minutos e tente de novo."), extra=[("Retry-After", "900")])
            return
        campos, _ = _formulario(self._corpo(4096), self.headers.get("Content-Type", ""))
        senha_ok = confere_senha(campos.get("senha", "")[:200], SENHA_HASH)
        passo = totp_contador(TOTP_SEGREDO, campos.get("codigo", ""))
        if not (senha_ok and passo is not None and usar_contador(passo)):
            registrar_falha(ip)
            sys.stderr.write(f"{time.strftime('%H:%M:%S')} login recusado de {ip}\n")
            self._enviar(401, pg_entrar("Senha ou código incorretos."))
            return
        token, _ = nova_sessao()
        sys.stderr.write(f"{time.strftime('%H:%M:%S')} login aceito de {ip}\n")
        self._ir("/", [self._cookie(token)])

    # --- páginas ---
    def _get(self, rota: str, q: dict, sess: dict) -> None:
        p = lambda k, d="": (q.get(k) or [d])[0]  # noqa: E731
        if rota == "/":
            self._enviar(200, pagina("Início", pg_inicio(), sess))
        elif rota == "/s3":
            self._enviar(200, pagina("S3", pg_s3(sess), sess))
        elif rota == "/s3/b":
            b = p("bucket")
            if not BUCKET_RE.match(b):
                raise ErroPainel("nome de bucket inválido")
            self._enviar(200, pagina(f"Bucket {b}", pg_s3_bucket(sess, b, p("prefixo")), sess))
        elif rota == "/s3/baixar":
            self._baixar(p("bucket"), p("chave"))
        elif rota == "/lambda":
            self._enviar(200, pagina("Lambda", pg_lambda(sess), sess))
        elif rota == "/glue":
            self._enviar(200, pagina("Glue", pg_glue(sess), sess))
        elif rota == "/glue/tabelas":
            b = valida(BANCO_RE, p("banco"), "nome do banco")
            self._enviar(200, pagina(f"Tabelas de {b}", pg_glue_tabelas(sess, b), sess))
        elif rota == "/athena":
            self._enviar(200, pagina("Athena", pg_athena(sess), sess))
        elif rota == "/athena/resultado":
            self._enviar(200, pagina("Athena", pg_athena(sess, qid=valida(ID_CONSULTA_RE, p("id"), "identificador da consulta")), sess))
        elif rota == "/console":
            self._enviar(200, pagina("Console geral", pg_console(sess, p("servico", "s3"), p("operacao"), p("parametros", "{}")), sess))
        else:
            self._enviar(404, pagina("Não encontrado", '<p><a href="/">Voltar ao início</a></p>', sess))

    def _baixar(self, bucket: str, chave: str) -> None:
        if not BUCKET_RE.match(bucket) or not chave:
            raise ErroPainel("pedido inválido")
        r = cli("s3").get_object(Bucket=bucket, Key=chave)
        nome = chave.rsplit("/", 1)[-1] or "arquivo"
        ascii_ = re.sub(r'[^A-Za-z0-9._-]', "_", nome)[:80]
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")  # nunca deixa o navegador interpretar o que foi guardado
        self.send_header("Content-Length", str(r["ContentLength"]))
        self.send_header("Content-Disposition", f"attachment; filename=\"{ascii_}\"; filename*=UTF-8''{quote(nome)}")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            for pedaco in r["Body"].iter_chunks(65536):
                self.wfile.write(pedaco)

    def _post(self, rota: str, token: str, sess: dict) -> None:
        corpo = self._corpo(MAX_ENVIO + 1024 * 1024 if rota == "/s3/enviar" else 256 * 1024)
        campos, arquivos = _formulario(corpo, self.headers.get("Content-Type", ""))
        if not hmac.compare_digest(campos.get("csrf", ""), sess["csrf"]):
            raise ErroPainel("sessão expirada ou pedido inválido; recarregue a página")
        if rota == "/sair":
            with _lock:
                _sessoes.pop(token, None)
            self._ir("/entrar", [self._cookie("", apagar=True)])
            return
        voltar = "/"
        if rota == "/s3/criar":
            b = campos.get("bucket", "").strip()
            if not BUCKET_RE.match(b):
                raise ErroPainel("nome de bucket inválido (3 a 63 caracteres: minúsculas, números, ponto e hífen)")
            cli("s3").create_bucket(Bucket=b)
            sess["flash"] = ("ok", f"Bucket {b} criado.")
            voltar = "/s3"
        elif rota == "/s3/apagar":
            b = campos.get("bucket", "")
            if not BUCKET_RE.match(b):
                raise ErroPainel("nome de bucket inválido")
            if campos.get("esvaziar") == "1":
                esvaziar_bucket(cli("s3"), b)
            cli("s3").delete_bucket(Bucket=b)
            sess["flash"] = ("ok", f"Bucket {b} apagado.")
            voltar = "/s3"
        elif rota == "/s3/enviar":
            b, pref = campos.get("bucket", ""), campos.get("prefixo", "")
            if not BUCKET_RE.match(b) or "arquivo" not in arquivos or not arquivos["arquivo"][0]:
                raise ErroPainel("escolha um arquivo")
            nome_arq, dados = arquivos["arquivo"]
            chave = (campos.get("nome") or "").strip() or (pref + nome_arq.rsplit("/", 1)[-1])
            if len(dados) > MAX_ENVIO:
                raise ErroPainel("arquivo maior que o limite")
            cli("s3").put_object(Bucket=b, Key=chave, Body=dados)
            sess["flash"] = ("ok", f"Arquivo {chave} enviado ({len(dados)} bytes).")
            voltar = "/s3/b?" + urlencode({"bucket": b, "prefixo": pref})
        elif rota == "/s3/apagar-objeto":
            b, k = campos.get("bucket", ""), campos.get("chave", "")
            if not BUCKET_RE.match(b) or not k:
                raise ErroPainel("pedido inválido")
            cli("s3").delete_object(Bucket=b, Key=k)
            sess["flash"] = ("ok", f"Arquivo {k} apagado.")
            voltar = "/s3/b?" + urlencode({"bucket": b, "prefixo": campos.get("prefixo", "")})
        elif rota == "/lambda/criar":
            nome, rt, h, codigo = campos.get("nome", "").strip(), campos.get("runtime", ""), campos.get("handler", "").strip(), campos.get("codigo", "")
            m = HANDLER_RE.match(h)
            if not NOME_FN_RE.match(nome) or not m or rt not in ("python3.12", "python3.13") or not codigo.strip():
                raise ErroPainel("confira o nome (letras, números, hífen e sublinhado), o handler (arquivo.função) e o código")
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr(m.group(1) + ".py", codigo)
            cli("lambda").create_function(FunctionName=nome, Runtime=rt, Handler=h, Role="arn:aws:iam::000000000000:role/lambda-role", Code={"ZipFile": buf.getvalue()})
            sess["flash"] = ("ok", f"Função {nome} criada.")
            voltar = "/lambda"
        elif rota == "/lambda/apagar":
            nome = campos.get("nome", "")
            if not NOME_FN_RE.match(nome):
                raise ErroPainel("nome inválido")
            cli("lambda").delete_function(FunctionName=nome)
            sess["flash"] = ("ok", f"Função {nome} apagada.")
            voltar = "/lambda"
        elif rota == "/lambda/invocar":
            nome = campos.get("nome", "")
            if not NOME_FN_RE.match(nome):
                raise ErroPainel("nome inválido")
            payload = campos.get("payload", "{}").strip() or "{}"
            try:
                json.loads(payload)
            except ValueError as ex:
                raise ErroPainel("o evento não é um JSON válido") from ex
            r = cli("lambda").invoke(FunctionName=nome, Payload=payload.encode("utf-8"), LogType="Tail")
            saida = r["Payload"].read(200_000).decode("utf-8", "replace")
            logs = base64.b64decode(r.get("LogResult", "")).decode("utf-8", "replace") if r.get("LogResult") else ""
            texto = f"Código de status: {r.get('StatusCode')}\nErro da função: {r.get('FunctionError', 'nenhum')}\n\nResposta:\n{saida}\n\nRegistro (últimas linhas):\n{logs}"
            self._enviar(200, pagina("Lambda", pg_lambda(sess, texto), sess))
            return
        elif rota.startswith("/glue/"):
            voltar = self._glue(rota, campos, sess)
        elif rota == "/athena/executar":
            self._athena_executar(campos, sess)
            return
        elif rota == "/console":
            self._console(campos, sess)
            return
        else:
            raise ErroPainel("rota desconhecida")
        self._ir(voltar)

    def _glue(self, rota: str, campos: dict, sess: dict) -> str:
        g = cli("glue")
        nome, banco = campos.get("nome", "").strip(), campos.get("banco", "").strip()
        ok = lambda t: sess.__setitem__("flash", ("ok", t))  # noqa: E731
        if rota == "/glue/banco/criar":
            valida(BANCO_RE, nome, "nome do banco (minúsculas, números e sublinhado)")
            g.create_database(DatabaseInput={"Name": nome})
            ok(f"Banco {nome} criado.")
            return "/glue/tabelas?" + urlencode({"banco": nome})
        if rota == "/glue/banco/apagar":
            valida(BANCO_RE, nome, "nome do banco")
            g.delete_database(Name=nome)
            ok(f"Banco {nome} apagado.")
            return "/glue"
        if rota == "/glue/tabela/criar":
            valida(BANCO_RE, banco, "nome do banco")
            valida(BANCO_RE, nome, "nome da tabela (minúsculas, números e sublinhado)")
            local = valida(S3_RE, campos.get("local", ""), "local no S3 (use s3://bucket/pasta/)")
            if not local.endswith("/"):
                local += "/"
            g.create_table(DatabaseName=banco, TableInput=montar_tabela(nome, local, campos.get("formato", ""), campos.get("colunas", ""), campos.get("cabecalho") == "1"))
            ok(f"Tabela {nome} criada em {banco}.")
            return "/glue/tabelas?" + urlencode({"banco": banco})
        if rota == "/glue/tabela/apagar":
            valida(BANCO_RE, banco, "nome do banco")
            valida(BANCO_RE, nome, "nome da tabela")
            g.delete_table(DatabaseName=banco, Name=nome)
            ok(f"Tabela {nome} apagada.")
            return "/glue/tabelas?" + urlencode({"banco": banco})
        if rota == "/glue/crawler/criar":
            valida(TRABALHO_RE, nome, "nome do crawler")
            valida(BANCO_RE, banco, "nome do banco")
            local = valida(S3_RE, campos.get("local", ""), "local no S3 (use s3://bucket/pasta/)")
            g.create_crawler(Name=nome, Role=PAPEL_GLUE, DatabaseName=banco, Targets={"S3Targets": [{"Path": local}]})
            ok(f"Crawler {nome} criado.")
            return "/glue"
        if rota == "/glue/crawler/iniciar":
            valida(TRABALHO_RE, nome, "nome do crawler")
            g.start_crawler(Name=nome)
            ok(f"Crawler {nome} iniciado. Atualize a página para ver a situação.")
            return "/glue"
        if rota == "/glue/crawler/apagar":
            valida(TRABALHO_RE, nome, "nome do crawler")
            g.delete_crawler(Name=nome)
            ok(f"Crawler {nome} apagado.")
            return "/glue"
        if rota == "/glue/job/criar":
            valida(TRABALHO_RE, nome, "nome do job")
            versao = campos.get("versao", "")
            codigo = campos.get("codigo", "")
            if versao not in ("4.0", "5.0") or not codigo.strip():
                raise ErroPainel("escolha a versão do Glue e informe o script")
            garantir_bucket(BUCKET_SCRIPTS)
            cli("s3").put_object(Bucket=BUCKET_SCRIPTS, Key=f"{nome}.py", Body=codigo.encode("utf-8"))
            g.create_job(Name=nome, Role=PAPEL_GLUE, GlueVersion=versao,
                         Command={"Name": "glueetl", "ScriptLocation": f"s3://{BUCKET_SCRIPTS}/{nome}.py", "PythonVersion": "3"})
            ok(f"Job {nome} criado, com o script em s3://{BUCKET_SCRIPTS}/{nome}.py.")
            return "/glue"
        if rota == "/glue/job/iniciar":
            valida(TRABALHO_RE, nome, "nome do job")
            r = g.start_job_run(JobName=nome)
            ok(f"Job {nome} iniciado (execução {r.get('JobRunId', '')}). Atualize a página para ver a situação.")
            return "/glue"
        if rota == "/glue/job/apagar":
            valida(TRABALHO_RE, nome, "nome do job")
            g.delete_job(JobName=nome)
            ok(f"Job {nome} apagado.")
            return "/glue"
        raise ErroPainel("rota desconhecida")

    def _athena_executar(self, campos: dict, sess: dict) -> None:
        sql, banco = campos.get("sql", "").strip(), valida(BANCO_RE, campos.get("banco", "default"), "nome do banco")
        if not sql or len(sql) > 20000:
            raise ErroPainel("escreva uma consulta SQL de até 20 mil caracteres")
        a = cli("athena")
        garantir_bucket(BUCKET_ATHENA)
        qid = a.start_query_execution(QueryString=sql, QueryExecutionContext={"Database": banco},
                                      ResultConfiguration={"OutputLocation": f"s3://{BUCKET_ATHENA}/consultas/"})["QueryExecutionId"]
        esperar_consulta(a, qid)
        self._enviar(200, pagina("Athena", pg_athena(sess, sql=sql, banco=banco, qid=qid), sess))

    def _console(self, campos: dict, sess: dict) -> None:
        servico, op, par = campos.get("servico", ""), campos.get("operacao", "").strip(), campos.get("parametros", "{}").strip() or "{}"
        resultado = erro = ""
        try:
            if servico not in servicos_aws():
                raise ErroPainel("serviço desconhecido")
            c = cli(servico)
            if op not in c.meta.method_to_api_mapping:
                raise ErroPainel(f"operação '{op}' não existe em {servico}. Veja a lista de operações do serviço.")
            try:
                params = json.loads(par)
            except ValueError as ex:
                raise ErroPainel("os parâmetros não são um JSON válido") from ex
            if not isinstance(params, dict):
                raise ErroPainel("os parâmetros precisam ser um objeto JSON, como {}")
            resp = getattr(c, op)(**params)
            if isinstance(resp, dict):
                meta = resp.pop("ResponseMetadata", {})
                resp = {"HTTPStatusCode": meta.get("HTTPStatusCode"), **resp}
            resultado = como_json(resp)
        except ErroPainel as ex:
            erro = str(ex)
        except Exception as ex:  # noqa: BLE001
            erro = f"{type(ex).__name__}: {str(ex)[:1500]}"
        self._enviar(200, pagina("Console geral", pg_console(sess, servico, op, par, resultado, erro), sess))


# ----------------------------------------------------------------------------------------
# Configuração pela linha de comando
# ----------------------------------------------------------------------------------------
def env_gravar(pares: dict) -> None:
    arq = PROJECT_DIR / ".env"
    try:
        linhas = arq.read_text(encoding="utf-8").splitlines()
    except OSError:
        linhas = []
    manter = [l for l in linhas if not any(re.match(rf"^\s*(export\s+)?{re.escape(k)}\s*=", l) for k in pares)]
    manter += [f"{k}='{v}'" for k, v in pares.items()]
    tmp = arq.with_suffix(".tmp")
    tmp.write_text("\n".join(manter) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, arq)


def novo_segredo_totp() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def mostrar_segredo(segredo: str) -> None:
    grupos = " ".join(segredo[i:i + 4] for i in range(0, len(segredo), 4))
    print("\nCódigo de verificação (TOTP). Cadastre no app Senhas da Apple:")
    print("1. Abra o app Senhas e crie (ou abra) o item cloud.heimdall-ai.tech.")
    print("2. Escolha adicionar código de verificação e depois inserir a chave de configuração (o nome exato do botão varia com a versão do sistema).")
    print("3. Digite a chave abaixo, que é de 6 dígitos, troca a cada 30 segundos e usa SHA-1:")
    print("   " + grupos)
    print("4. Guarde esta chave só aí. Ela não será mostrada de novo.")


def definir_senha(so_codigo: bool) -> None:
    pares = {}
    if not so_codigo:
        s1 = getpass.getpass("Nova senha do painel (mínimo 14 caracteres; não aparece na tela): ")
        if len(s1) < 14:
            sys.exit("Senha curta demais. Use pelo menos 14 caracteres (uma frase longa serve).")
        if getpass.getpass("Repita a senha: ") != s1:
            sys.exit("As senhas não são iguais. Nada foi gravado.")
        pares["HEIMDALL_CLOUD_SENHA_HASH"] = hash_senha(s1)
    segredo = novo_segredo_totp()
    pares["HEIMDALL_CLOUD_TOTP_SEGREDO"] = segredo
    env_gravar(pares)
    print("Gravado no .env (permissão 600)." + (" Senha guardada só como hash." if not so_codigo else ""))
    mostrar_segredo(segredo)
    print("\nReinicie o painel para valer: pkill -f heimdall_cloud.py e suba o sistema como de costume.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Painel web do emulador de AWS do Heimdall")
    ap.add_argument("--definir-senha", action="store_true", help="define a senha e gera o código TOTP, gravando no .env")
    ap.add_argument("--novo-codigo", action="store_true", help="gera só um novo código TOTP")
    args = ap.parse_args()
    if args.definir_senha or args.novo_codigo:
        definir_senha(so_codigo=args.novo_codigo and not args.definir_senha)
        return
    if not SENHA_HASH or not TOTP_SEGREDO:
        sys.exit("Sem senha e código configurados o painel não sobe. Rode: python3 heimdall_cloud.py --definir-senha")
    srv = ThreadingHTTPServer((HOST, PORT), Painel)
    srv.daemon_threads = True
    sys.stderr.write(f"{time.strftime('%H:%M:%S')} Heimdall Cloud em http://{HOST}:{PORT} (emulador em {ENDPOINT}; sites permitidos: {', '.join(sorted(HOSTS_OK))})\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
