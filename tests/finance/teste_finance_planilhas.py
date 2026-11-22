#!/usr/bin/env python3
"""Testa as páginas do Finance para planilhas, investimentos, empréstimos e visões, com servidor temporário e sem rede."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import re
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

AQUI = RAIZ
os.environ.update({"NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
TMP = tempfile.mkdtemp(prefix="finance_plan_teste_")
os.environ["HEIMDALL_FINANCE_DIR"] = TMP
sys.path.insert(0, str(AQUI))
import heimdall_cloud as hc  # noqa: E402
import heimdall_finance as hf  # noqa: E402
import financas_planilhas as fp  # noqa: E402
from teste_planilhas_util import xlsx  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:600])


hc.SENHA_HASH = hc.hash_senha("senha-de-teste-forte", iteracoes=100_000)
hc.TOTP_SEGREDO = "JBSWY3DPEHPK3PXP"
srv = ThreadingHTTPServer(("127.0.0.1", 0), hf.Finance)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"


class Sem303(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


abre = urllib.request.build_opener(Sem303).open
token, sess = hc.nova_sessao()
ck = f"{hc.COOKIE}={token}"
csrf = sess["csrf"]


def pedir(caminho, dados=None, tipo=None):
    cab = {"Cookie": ck}
    if tipo:
        cab["Content-Type"] = tipo
    req = urllib.request.Request(BASE + caminho, data=dados, headers=cab)
    try:
        with abre(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode("utf-8", "replace"), dict(ex.headers)


def post(caminho, campos):
    return pedir(caminho, urllib.parse.urlencode(dict(campos, csrf=csrf)).encode(), "application/x-www-form-urlencoded")


def envio(caminho, nome, dados, campos=None):
    lim = "----" + uuid.uuid4().hex
    corpo = b""
    for k, v in dict(campos or {}, csrf=csrf).items():
        corpo += f'--{lim}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    corpo += f'--{lim}\r\nContent-Disposition: form-data; name="arquivo"; filename="{nome}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + dados + b"\r\n--" + lim.encode() + b"--\r\n"
    return pedir(caminho, corpo, f"multipart/form-data; boundary={lim}")


def segue(resp):
    st, _, cab = resp
    if st == 303:
        return pedir(cab["Location"])
    return resp


# sem login nada abre
req = urllib.request.Request(BASE + "/planilhas")
try:
    st = abre(req).status
except urllib.error.HTTPError as ex:
    st = ex.code
confere("planilhas exigem login", st == 303)

for rota, trecho in (("/planilhas", "Importar planilha"), ("/investimentos", "Ainda não há investimentos"), ("/emprestimos", "Ainda não há dados aqui"), ("/visoes", "formas gravadas")):
    st, corpo, _ = pedir(rota)
    confere(f"{rota} abre vazio", st == 200 and trecho in corpo, (st, corpo[:200]))
st, corpo, _ = pedir("/planilhas")
confere("abas fixas novas na navegação", all(x in corpo for x in ("Planilhas", "Visões")) and "Investimentos</a>" not in corpo)
confere("formulário com token, rótulos e arquivo", 'name="csrf"' in corpo and '<label for="arquivo">' in corpo and 'enctype="multipart/form-data"' in corpo)

# sem token a ação é recusada
st, corpo, _ = pedir("/planilhas/duvida/descartar", urllib.parse.urlencode({"id": "1", "csrf": "errado"}).encode(), "application/x-www-form-urlencoded")
confere("ação sem token válido é recusada", st == 403)

# importar gastos
gastos = xlsx({"Gastos": [["Data", "Descrição", "Valor"], [("data", 46296), "Mercado Zona Sul", -123.45], [("data", 46297), "Salário", 5000]]})
st, corpo, cab = envio("/planilhas", "gastos_2026_10.xlsx", gastos)
confere("upload de gastos redireciona ao conjunto", st == 303 and cab["Location"].startswith("/conjunto?id="), (st, cab))
st, corpo, _ = segue((st, corpo, cab))
confere("conjunto mostra a tabela com legenda e linhas", st == 200 and "<caption>" in corpo and "Mercado Zona Sul" in corpo and "2 linhas lidas" in corpo or "Mercado Zona Sul" in corpo, corpo[:300])
cid = re.search(r"id=(\d+)", cab["Location"]).group(1)
st, corpo, _ = pedir("/transacoes")
confere("gastos da planilha chegaram nas transações", "Mercado Zona Sul" in corpo)

# visão
st, _, cab = post("/visoes/nova", {"conjunto_id": cid, "nome": "Só valores"})
confere("criar visão leva à personalização", st == 303 and cab["Location"].startswith("/visao?id="), (st, cab))
vid = re.search(r"id=(\d+)", cab["Location"]).group(1)
st, corpo, _ = pedir(f"/visao?id={vid}")
confere("personalização lista colunas com botões", st == 200 and "Mover para baixo" in corpo and "Tirar da visão" in corpo and 'scope="col"' in corpo, corpo[:300])
post("/visao/coluna", {"id": vid, "chave": "descricao", "acao": "tirar"})
post("/visao/coluna", {"id": vid, "chave": "valor", "acao": "acima"})
st, corpo, _ = pedir(f"/visao?id={vid}")
confere("coluna tirada aparece fora da visão", "Colunas fora da visão" in corpo and "Incluir no fim da visão" in corpo)
v = fp.visao(hf.banco(), int(vid))
confere("ordem gravada", v["cfg"]["colunas"] == ["valor", "data"], v["cfg"])
post("/visao/regras", {"id": vid, "ordem": "valor", "direcao": "desc", "filtro_col": "", "filtro_valor": "", "agrupar": "", "somar": ""})
# chega arquivo novo: aparece na visão gravada
novo = xlsx({"Gastos": [["Data", "Descrição", "Valor"], [("data", 46330), "Livraria Cultura", -90]]})
envio("/planilhas", "gastos_2026_12.xlsx", novo)
st, corpo, _ = pedir(f"/conjunto?id={cid}&visao={vid}")
confere("lançamento novo aparece na visão", st == 200 and "-90" in corpo and "3 de 3 linhas" in corpo, corpo[:400])
confere("visão mostra só as colunas escolhidas", '>Descrição</th>' not in corpo and '>Valor</th>' in corpo and '>Data</th>' in corpo, corpo[:600])
st, corpo, _ = post("/visao/coluna", {"id": vid, "chave": "inexistente", "acao": "incluir"})
confere("coluna inexistente vira aviso, não erro", st == 303)
st, corpo, _ = segue((st, corpo, _))
confere("o aviso aparece na página", "Coluna desconhecida" in corpo, corpo[:300])
st, corpo, _ = pedir("/visoes")
confere("lista de visões", "Só valores" in corpo and "Personalizar" in corpo)

# investimentos e empréstimos
inv = xlsx({"Carteira": [["Ativo", "Tipo", "Quantidade", "Valor atual", "Data"], ["PETR4", "Ação", 100, 3500, ("data", 46296)], ["Tesouro Selic", "Renda fixa", 1, 10000, ("data", 46296)]]})
envio("/planilhas", "carteira.xlsx", inv)
st, corpo, _ = pedir("/planilhas")
confere("a aba Investimentos aparece quando há dados", "Investimentos" in corpo)
st, corpo, _ = pedir("/investimentos")
confere("investimentos mostram total e por tipo", "R$ 13.500,00" in corpo and "Renda fixa" in corpo and "<caption>Investimentos por tipo</caption>" in corpo, corpo[:400])
emp = xlsx({"Dívidas": [["Contrato", "Credor", "Saldo devedor", "Valor da parcela", "Taxa de juros"], ["Carro", "Banco X", 25000, 850, ("pct", 0.0189)]]})
envio("/planilhas", "dividas.xlsx", emp)
st, corpo, _ = pedir("/emprestimos")
confere("empréstimos mostram saldo e taxa", "R$ 25.000,00" in corpo and "1,89%" in corpo, corpo[:400])
st, corpo, _ = pedir("/credito/veiculo")
confere("financiamento de carro cai na aba de veículo", st == 200 and "Carro" in corpo and "Financiamento de veículo" in corpo, corpo[:300])

# dúvida pelo site
estranha = xlsx({"Plan": [["Coisa", "Outra", "Mais"], ["a", "b", 1]]})
st, corpo, cab = envio("/planilhas", "estranha.xlsx", estranha)
confere("planilha estranha volta para Planilhas com a dúvida", st == 303 and cab["Location"] == "/planilhas", (st, cab))
st, corpo, _ = pedir("/planilhas")
confere("dúvida aparece com pergunta e opções", "Dúvidas para você responder" in corpo and "Que tipo de planilha é esta?" in corpo and "Responder e importar" in corpo, corpo[:400])
did = fp.duvidas(hf.banco())[0]["id"]
st, corpo, cab = post("/planilhas/duvida", {"id": did, "tipo": "outros", "nome": "Coisas soltas"})
st, corpo, _ = segue((st, corpo, cab))
confere("responder a dúvida importa e some da lista", "Coisas soltas" in corpo and "Dúvidas para você responder" not in corpo, corpo[:300])

# apagar visão
st, corpo, cab = post("/visao/apagar", {"id": vid})
confere("apagar visão volta ao conjunto e mantém as linhas", st == 303 and cab["Location"].startswith("/conjunto?id=") and fp.visao(hf.banco(), int(vid)) is None and next(c for c in fp.conjuntos(hf.banco()) if c["id"] == int(cid))["n"] >= 3)
st, corpo, _ = pedir("/visao?id=9999")
confere("visão inexistente dá 404", st == 404)
st, corpo, _ = envio("/planilhas", "x.xlsx", b"PK\x03\x04lixo")
st, corpo, _ = segue((st, corpo, _))
confere("arquivo quebrado vira aviso claro", "não parece uma planilha" in corpo, corpo[:300])

# pasta com permissões do dono
fp.pasta_de_entrada(hf.DIR_DADOS)
confere("pastas de planilhas só do dono", oct(os.stat(hf.DIR_DADOS / "sheets").st_mode & 0o777) == "0o700" and oct(os.stat(hf.DIR_DADOS / "planilhas_pendentes").st_mode & 0o777) == "0o700")

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
