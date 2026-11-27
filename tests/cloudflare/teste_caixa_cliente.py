#!/usr/bin/env python3
"""Teste do cliente da caixa de correio (studio_caixa.py), sem rede e sem token real.

    python3 tests/cloudflare/teste_caixa_cliente.py
"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import io
import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path

sys.path.insert(0, str(RAIZ))
import studio_caixa as cx  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


ENV = {"STUDIO_CAIXA": "1", "STUDIO_CAIXA_TOKEN": "hc_dono", "CLOUDFLARE_API_TOKEN": "cf-teste"}


class Resp:
    def __init__(self, corpo): self._c = json.dumps(corpo).encode()
    def read(self, n=-1): return self._c
    def __enter__(self): return self
    def __exit__(self, *a): return False


def caixa_falsa(entradas, log, falha_apagar=False):
    def abrir(req, timeout=0):
        log.append((req.get_method(), req.full_url.replace(cx.URL_PADRAO, ""), req.headers))
        rota = req.full_url.replace(cx.URL_PADRAO, "")
        if req.get_method() == "GET" and rota == "/v1/entrada":
            return Resp({"itens": entradas})
        if req.get_method() == "DELETE" and falha_apagar:
            raise urllib.error.HTTPError(req.full_url, 500, "x", {}, io.BytesIO(b'{"erro":"boom"}'))
        if req.get_method() == "POST" and rota == "/v1/iniciar":
            return Resp({"token": "hc_novo"})
        if req.get_method() == "POST" and rota == "/v1/tokens":
            return Resp({"usuario": json.loads(req.data)["usuario"], "token": "hc_ana"})
        if req.get_method() == "POST" and rota == "/v1/saida":
            return Resp({"id": "1700000000000-aaaaaaaaaaaa"})
        return Resp({"apagado": True, "revogados": 2})
    return abrir


confere("ligada só com STUDIO_CAIXA=1 e o token", cx.ativa(ENV))
confere("desligada com STUDIO_CAIXA=0", not cx.ativa({**ENV, "STUDIO_CAIXA": "0"}))
confere("desligada sem o token", not cx.ativa({"STUDIO_CAIXA": "1"}))
confere("desligada sem o interruptor", not cx.ativa({"STUDIO_CAIXA_TOKEN": "x"}))

log = []
gravado = {}
t = cx.iniciar(ENV, abrir=caixa_falsa([], log), gravar=gravado.update)
confere("start grava o token novo no .env (função de gravar)", t == "hc_novo" and gravado == {"STUDIO_CAIXA_TOKEN": "hc_novo"})
confere("start prova acesso com a chave da Cloudflare no cabeçalho", any(h.get("X-cf-token") == "cf-teste" for _, _, h in log))
try:
    cx.iniciar({}, abrir=caixa_falsa([], []), gravar=lambda p: None)
    confere("start sem chave da Cloudflare falha", False)
except RuntimeError as e:
    confere("start sem chave da Cloudflare falha com mensagem clara", "studio cloudflare" in str(e))

log = []
confere("add devolve o token da pessoa", cx.criar_pessoa("ana", ENV, abrir=caixa_falsa([], log)) == "hc_ana")
confere("remove devolve a quantidade revogada", cx.revogar_pessoa("ana", ENV, abrir=caixa_falsa([], [])) == 2)
confere("deixar_para devolve o id da saída", cx.deixar_para("ana", "lembrete", {"titulo": "x"}, ENV, abrir=caixa_falsa([], [])).endswith("aaaa"))
try:
    cx.criar_pessoa("ana", {}, abrir=caixa_falsa([], []))
    confere("sem token de dono falha", False)
except RuntimeError as e:
    confere("sem token de dono falha com mensagem clara", "studio mailbox start" in str(e))

with tempfile.TemporaryDirectory() as d:
    itens = [{"id": "1700000000000-aaaaaaaaaaaa", "usuario": "ana", "tipo": "saude", "dados": {"passos": 5}},
             {"id": "1700000000001-bbbbbbbbbbbb", "usuario": "bia", "tipo": "nota", "dados": {"t": "oi"}}]
    log = []
    r = cx.puxar(ENV, abrir=caixa_falsa(itens, log), pasta=d)
    confere("pull recebe e apaga tudo", r == {"recebidos": 2, "apagados": 2, "falhas": 0}, r)
    arq = Path(d) / "ana" / "1700000000000-aaaaaaaaaaaa.json"
    confere("a cópia local existe, com o conteúdo", arq.exists() and json.loads(arq.read_text())["dados"]["passos"] == 5)
    confere("a cópia tem permissão só do dono", (arq.stat().st_mode & 0o777) == 0o600 and (arq.parent.stat().st_mode & 0o777) == 0o700)
    ordem = [m for m, _, _ in log]
    confere("busca antes de apagar", ordem[0] == "GET" and ordem.count("DELETE") == 2)

    # falha ao tratar: o item NÃO é apagado da caixa
    log = []
    def tratar(it): raise RuntimeError("não deu")
    r = cx.puxar(ENV, abrir=caixa_falsa(itens[:1], log), pasta=d, tratar=tratar)
    confere("se o tratamento falha, o item fica na caixa", r["falhas"] == 1 and r["apagados"] == 0 and "DELETE" not in [m for m, _, _ in log], r)

    # falha ao apagar: a cópia local permanece
    log = []
    r = cx.puxar(ENV, abrir=caixa_falsa(itens[:1], log, falha_apagar=True), pasta=d)
    confere("se apagar falha, conta a falha e mantém a cópia local", r["falhas"] == 1 and arq.exists(), r)

chamadas = []
reg = lambda nome, dados, meu: chamadas.append((nome, meu))  # noqa: E731
cx.tratar_padrao({"tipo": "saude", "usuario": "eu", "dados": {"data": {"workouts": []}}}, {}, importar=reg)
confere("saúde do dono ('eu') é importada com o nome do dono", chamadas == [("eu", "eu")])
cx.tratar_padrao({"tipo": "saude", "usuario": "ana", "dados": {}}, {}, importar=reg)
confere("saúde de outra pessoa também é importada, para o banco dela", chamadas[-1] == ("ana", "eu"))
cx.tratar_padrao({"tipo": "nota", "usuario": "eu", "dados": {}}, {}, importar=reg)
confere("outros tipos só ficam na cópia local", len(chamadas) == 2)
cx.tratar_padrao({"tipo": "saude", "usuario": "murillo", "dados": {}}, {"STUDIO_CAIXA_MEU_NOME": "murillo"}, importar=reg)
confere("o nome do dono vem de STUDIO_CAIXA_MEU_NOME", chamadas[-1] == ("murillo", "murillo"))

try:
    cx.pedido("GET", "/v1/entrada", token="x", env=ENV, abrir=lambda *a, **k: (_ for _ in ()).throw(urllib.error.URLError("sem rede")))
    confere("rede fora vira erro claro", False)
except RuntimeError as e:
    confere("rede fora vira erro claro, sem vazar o token", "sem resposta da caixa" in str(e) and "hc_" not in str(e))

print("\nFALHAS: %d" % falhas if falhas else "\nTudo certo.")
sys.exit(1 if falhas else 0)
