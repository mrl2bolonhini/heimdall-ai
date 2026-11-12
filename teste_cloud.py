#!/usr/bin/env python3
"""Teste do painel heimdall_cloud.py sem precisar do LocalStack nem do boto3 (usa um emulador de mentira).

    python3 teste_cloud.py

Confere: código de 6 dígitos (vetor oficial da RFC 6238), senha, bloqueio de tentativas, sessão, proteção contra CSRF,
páginas do S3, Lambda e console geral, envio e download de arquivo, e escape de texto perigoso.
"""
import http.client
import io
import json
import re
import sys
import threading
import time
import types
import zipfile
from datetime import datetime
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

# ---- boto3 de mentira ----
CHAMADAS = []


class Corpo:
    def __init__(self, dados: bytes):
        self.dados = dados

    def read(self, n=None):
        return self.dados if n is None else self.dados[:n]

    def iter_chunks(self, tam):
        yield self.dados


class Falso:
    def __init__(self, servico):
        self.servico = servico
        self.meta = types.SimpleNamespace(method_to_api_mapping={"list_tables": "ListTables", "list_buckets": "ListBuckets", "create_queue": "CreateQueue"})

    def list_buckets(self):
        return {"ResponseMetadata": {"HTTPStatusCode": 200}, "Buckets": [{"Name": "dados", "CreationDate": datetime(2026, 11, 12)}, {"Name": "x<script>", "CreationDate": datetime(2026, 11, 12)}]}

    def list_objects_v2(self, **kw):
        return {"CommonPrefixes": [{"Prefix": "pasta/"}], "Contents": [{"Key": "a.txt", "Size": 3, "LastModified": datetime(2026, 11, 12)}], "IsTruncated": False}

    def create_bucket(self, **kw):
        CHAMADAS.append(("create_bucket", kw))

    def put_object(self, **kw):
        CHAMADAS.append(("put_object", kw))

    def get_object(self, **kw):
        return {"ContentLength": 3, "Body": Corpo(b"abc")}

    def delete_object(self, **kw):
        CHAMADAS.append(("delete_object", kw))

    def list_functions(self):
        return {"Functions": []}

    def create_function(self, **kw):
        CHAMADAS.append(("create_function", kw))

    def list_tables(self, **kw):
        return {"ResponseMetadata": {"HTTPStatusCode": 200}, "TableNames": ["clientes"]}


boto3 = types.ModuleType("boto3")
boto3.client = lambda servico, **kw: Falso(servico)
boto3.session = types.SimpleNamespace(Session=lambda: types.SimpleNamespace(get_available_services=lambda: ["dynamodb", "lambda", "s3", "sqs"]))
botocore = types.ModuleType("botocore")
botocore.config = types.ModuleType("botocore.config")
botocore.config.Config = lambda **kw: None
sys.modules.update({"boto3": boto3, "botocore": botocore, "botocore.config": botocore.config})

import heimdall_cloud as hc  # noqa: E402

falhas = 0


def confere(nome: str, ok: bool, detalhe: str = "") -> None:
    global falhas
    print(("OK    " if ok else "FALHOU ") + nome + ("" if ok else f"  {detalhe}"))
    if not ok:
        falhas += 1


# ---- código de 6 dígitos: vetor da RFC 6238 (segredo "12345678901234567890", instante 59 s) ----
SEG_RFC = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
confere("TOTP confere com o vetor da RFC 6238", hc.totp_contador(SEG_RFC, "287082", agora=59) == 1)
confere("TOTP recusa código errado", hc.totp_contador(SEG_RFC, "000000", agora=59) is None)
confere("TOTP recusa formato inválido", hc.totp_contador(SEG_RFC, "12345", agora=59) is None)

h = hc.hash_senha("uma frase longa e boa", iteracoes=100_000)
confere("senha certa confere", hc.confere_senha("uma frase longa e boa", h))
confere("senha errada não confere", not hc.confere_senha("outra", h))
confere("hash sem cifrão (seguro no .env)", "$" not in h)
confere("hash quebrado não confere", not hc.confere_senha("x", "lixo"))

# ---- servidor ----
SEGREDO = hc.novo_segredo_totp()
hc.SENHA_HASH = h
hc.TOTP_SEGREDO = SEGREDO
hc.ENDPOINT = "http://127.0.0.1:9"
hc.HOSTS_OK = {"localhost", "127.0.0.1"}
srv = ThreadingHTTPServer(("127.0.0.1", 0), hc.Painel)
srv.daemon_threads = True
porta = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


def req(metodo, caminho, corpo=None, cookie="", host="localhost", tipo="application/x-www-form-urlencoded"):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    cab = {"Host": host}
    if cookie:
        cab["Cookie"] = cookie
    if corpo is not None:
        cab["Content-Type"] = tipo
    c.request(metodo, caminho, body=corpo, headers=cab)
    r = c.getresponse()
    dados = r.read()
    heads = {k.lower(): v for k, v in r.getheaders()}
    c.close()
    return r.status, heads, dados.decode("utf-8", "replace")


def form(**kw):
    return urlencode(kw)


def codigo_agora() -> str:
    return hc._hotp(hc._chave_totp(SEGREDO), int(time.time() // 30))


st, hd, _ = req("GET", "/")
confere("sem sessão vai para a entrada", st == 303 and hd["location"] == "/entrar")
st, _, _ = req("GET", "/", host="malvado.exemplo")
confere("nome de site não permitido é recusado", st == 421)
st, _, corpo = req("GET", "/saude")
confere("/saude responde ok sem senha", st == 200 and corpo == "ok")
st, hd, corpo = req("GET", "/entrar")
confere("página de entrada tem campos e cabeçalhos de segurança", st == 200 and 'name="codigo"' in corpo and "default-src 'none'" in hd["content-security-policy"] and hd["cache-control"] == "no-store")

st, _, corpo = req("POST", "/entrar", form(senha="errada", codigo="000000"))
confere("login errado dá 401 sem dizer o que falhou", st == 401 and "Senha ou código incorretos" in corpo)
st, _, _ = req("POST", "/entrar", form(senha="uma frase longa e boa", codigo="000000"))
confere("senha certa com código errado é recusado", st == 401)

cod = codigo_agora()
st, hd, _ = req("POST", "/entrar", form(senha="uma frase longa e boa", codigo=cod))
cookie = hd.get("set-cookie", "").split(";")[0]
confere("login certo entra e define cookie seguro", st == 303 and cookie.startswith("hcloud=") and "HttpOnly" in hd["set-cookie"] and "SameSite=Strict" in hd["set-cookie"])
st, _, _ = req("POST", "/entrar", form(senha="uma frase longa e boa", codigo=cod))
confere("o mesmo código não pode ser reaproveitado", st == 401)

# bloqueio: já houve 3 falhas (errada, código errado, reaproveitado); mais 2 chegam a 5
for _ in range(2):
    req("POST", "/entrar", form(senha="x", codigo="111111"))
st, _, _ = req("POST", "/entrar", form(senha="uma frase longa e boa", codigo="123456"))
confere("depois de 5 falhas vem bloqueio 429", st == 429)

st, _, corpo = req("GET", "/", cookie=cookie)
confere("início abre com sessão", st == 200 and "Estado do emulador" in corpo and "O emulador está respondendo" in corpo)
st, _, corpo = req("GET", "/s3", cookie=cookie)
confere("S3 lista buckets", st == 200 and "dados" in corpo)
confere("nome de bucket perigoso vem escapado", "x<script>" not in corpo and "x&lt;script&gt;" in corpo)
st, _, corpo = req("GET", "/s3/b?bucket=dados", cookie=cookie)
confere("bucket mostra arquivos e pastas", st == 200 and "a.txt" in corpo and "pasta/" in corpo)
st, hd, corpo = req("GET", "/s3/baixar?bucket=dados&chave=a.txt", cookie=cookie)
confere("download sai como anexo genérico", st == 200 and corpo == "abc" and "attachment" in hd["content-disposition"] and hd["content-type"] == "application/octet-stream")
st, _, corpo = req("GET", "/lambda", cookie=cookie)
confere("Lambda abre com formulário de criar", st == 200 and "Criar função" in corpo)
st, _, corpo = req("GET", "/console?servico=dynamodb", cookie=cookie)
confere("console lista operações do serviço", st == 200 and "list_tables" in corpo and "Exemplos para começar" in corpo)

csrf = re.search(r'name="csrf" value="([^"]+)"', corpo).group(1)
st, _, corpo = req("POST", "/console", form(csrf=csrf, servico="dynamodb", operacao="list_tables", parametros="{}"), cookie=cookie)
confere("console executa operação e mostra resultado", st == 200 and "TableNames" in corpo and "clientes" in corpo and "ResponseMetadata" not in corpo)
st, _, corpo = req("POST", "/console", form(csrf=csrf, servico="dynamodb", operacao="apagar_tudo", parametros="{}"), cookie=cookie)
confere("console recusa operação que não existe", st == 200 and "não existe" in corpo)
st, _, corpo = req("POST", "/console", form(csrf=csrf, servico="dynamodb", operacao="list_tables", parametros="[1]"), cookie=cookie)
confere("console exige objeto JSON", "objeto JSON" in corpo)

st, hd, _ = req("POST", "/s3/criar", form(csrf="errado", bucket="novo-bucket"), cookie=cookie)
confere("POST com token CSRF errado não faz nada", st == 303 and not any(c[0] == "create_bucket" for c in CHAMADAS))
st, hd, _ = req("POST", "/s3/criar", form(csrf=csrf, bucket="novo-bucket"), cookie=cookie)
confere("criar bucket chama o emulador", st == 303 and ("create_bucket", {"Bucket": "novo-bucket"}) in CHAMADAS)
st, _, _ = req("POST", "/s3/criar", form(csrf=csrf, bucket="Maiuscula_Inválida"), cookie=cookie)
confere("nome de bucket inválido é recusado", st == 303 and len([c for c in CHAMADAS if c[0] == "create_bucket"]) == 1)

fronteira = "----teste123"
corpo_mp = (f'--{fronteira}\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n{csrf}\r\n'
            f'--{fronteira}\r\nContent-Disposition: form-data; name="bucket"\r\n\r\ndados\r\n'
            f'--{fronteira}\r\nContent-Disposition: form-data; name="prefixo"\r\n\r\npasta/\r\n'
            f'--{fronteira}\r\nContent-Disposition: form-data; name="nome"\r\n\r\n\r\n'
            f'--{fronteira}\r\nContent-Disposition: form-data; name="arquivo"; filename="nota.txt"\r\nContent-Type: text/plain\r\n\r\nolá mundo\r\n'
            f'--{fronteira}--\r\n').encode("utf-8")
st, _, _ = req("POST", "/s3/enviar", corpo_mp, cookie=cookie, tipo=f"multipart/form-data; boundary={fronteira}")
envio = [c for c in CHAMADAS if c[0] == "put_object"]
confere("envio de arquivo grava no S3 com o prefixo", st == 303 and envio and envio[0][1]["Key"] == "pasta/nota.txt" and envio[0][1]["Body"] == "olá mundo".encode("utf-8"), str(envio))

st, _, _ = req("POST", "/lambda/criar", form(csrf=csrf, nome="minha-fn", runtime="python3.12", handler="app.handler", codigo="def handler(e, c):\n    return 1\n"), cookie=cookie)
fn = [c for c in CHAMADAS if c[0] == "create_function"]
ok_zip = False
if fn:
    z = zipfile.ZipFile(io.BytesIO(fn[0][1]["Code"]["ZipFile"]))
    ok_zip = z.namelist() == ["app.py"] and b"def handler" in z.read("app.py")
confere("criar função empacota o código no arquivo do handler", st == 303 and ok_zip)
st, _, _ = req("POST", "/lambda/criar", form(csrf=csrf, nome="../ruim", runtime="python3.12", handler="app.handler", codigo="x"), cookie=cookie)
confere("nome de função inválido é recusado", len([c for c in CHAMADAS if c[0] == "create_function"]) == 1)

st, hd, _ = req("POST", "/sair", form(csrf=csrf), cookie=cookie)
confere("sair apaga o cookie", st == 303 and "Max-Age=0" in hd["set-cookie"])
st, _, _ = req("GET", "/s3", cookie=cookie)
confere("depois de sair a sessão não vale mais", st == 303)

srv.shutdown()
print("\n" + ("Tudo certo." if not falhas else f"{falhas} teste(s) falharam."))
sys.exit(1 if falhas else 0)
