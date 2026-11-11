#!/usr/bin/env python3
"""Testa o banco pessoal (heimdall_banco.py) e as rotas /banco/* do agente. Usa uma pasta temporária; não toca no seu banco.
    python teste_banco.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

tmp = tempfile.mkdtemp(prefix="heimdall-banco-")
os.environ["HEIMDALL_DB_DIR"] = tmp
import heimdall_banco as b  # noqa: E402

falhas = 0


def ok(cond, msg):
    global falhas
    print(("ok   " if cond else "FALHA ") + msg)
    if not cond:
        falhas += 1


b.iniciar()
r = b.gravar("saude_diaria", [{"dia": "2026-11-09", "metrica": "passos", "valor": 5000, "unidade": "count"},
                              {"dia": "2026-11-10", "metrica": "passos", "valor": 8000}, {"dia": "ontem", "metrica": "passos", "valor": 1}, {"dia": "2026-11-10", "metrica": "hrv", "valor": "abc"}])
ok(r == {"gravados": 2, "recusados": 2}, f"grava e recusa dado inválido: {r}")
b.gravar("saude_diaria", [{"dia": "2026-11-10", "metrica": "passos", "valor": 9000}])
c = b.consulta_sql("SELECT valor FROM saude_diaria WHERE dia='2026-11-10' AND metrica='passos'")
ok(c["linhas"] == [[9000.0]], "regravar o mesmo dia atualiza, não duplica")
b.gravar("diarios", [{"id": "justica|1", "fonte": "justica", "data": "2026-11-10", "titulo": "t", "trecho": "x", "url": "u"}])
b.gravar("diarios", [{"id": "justica|1", "fonte": "justica", "data": "2026-11-10", "titulo": "t2", "trecho": "x", "url": "u"}])
ok(b.consulta_sql("SELECT COUNT(*) FROM diarios")["linhas"] == [[1]], "diários não duplicam")
b.gravar("analises", [{"nota_id": "n1", "titulo": "Nota", "tags": ["a", "b"], "conexoes": [{"titulo": "X", "tipo": "complementa", "motivo": "m"}]}])
ok(b.consulta_sql("SELECT json_extract(tags,'$[1]') FROM analises")["linhas"] == [["b"]], "listas viram JSON consultável")
for tab, reg in [("emails", {"id": "<m1@x>", "data": "Mon, 9 Nov 2026", "remetente": "INSS <a@inss.gov.br>", "dominio": "inss.gov.br", "assunto": "A", "classe": "oficial", "urgencia": "alta", "prazo": "2026-11-15"}),
                 ("estudos", {"id": "2026-11-10|13|T|C", "dia": "2026-11-10", "hora": "13", "tema": "T", "conceito": "C", "artigos": [{"titulo": "x", "url": "u"}]}),
                 ("privacidade", {"id": "privacidade|https://a.com", "data": "2026-11-10", "host": "a.com", "url": "https://a.com", "risco": "alto", "dados": ["e-mail"]}),
                 ("avisos", {"id": "manha1|Saúde|1", "quando": "2026-11-10T08:00:00Z", "slot": "manha1", "titulo": "Saúde", "linha": "ok", "urgente": 1})]:
    ok(b.gravar(tab, [reg, reg])["gravados"] == 2 and b.consulta_sql(f"SELECT COUNT(*) FROM {tab}")["linhas"] == [[1]], f"tabela {tab}: grava e não duplica")
ok(b.consulta_sql("SELECT SUM(urgente) FROM avisos")["linhas"] == [[1]], "avisos: urgente vira número")
ok(b.consulta_sql("SELECT json_extract(artigos,'$[0].url') FROM estudos")["linhas"] == [["u"]], "estudos: artigos em JSON")
ok(set(b.resumo()) >= {"emails", "estudos", "privacidade", "avisos"}, "resumo traz as tabelas novas")
for ruim in ["DROP TABLE diarios", "DELETE FROM diarios", "SELECT 1; DROP TABLE diarios", "PRAGMA writable_schema=1",
             "ATTACH DATABASE '/tmp/x.db' AS x", "WITH a AS (SELECT 1) DELETE FROM diarios", "INSERT INTO diarios(id) VALUES ('x')"]:
    try:
        b.consulta_sql(ruim)
        ok(False, f"deveria recusar: {ruim}")
    except (PermissionError, ValueError):
        ok(True, f"recusa: {ruim}")
ok(b.consulta_sql("SELECT COUNT(*) FROM diarios")["linhas"] == [[1]], "a tabela continua intacta")
try:
    b.gravar("sqlite_master", [{"x": 1}])
    ok(False, "deveria recusar tabela desconhecida")
except ValueError:
    ok(True, "recusa tabela desconhecida")
ok(b.resumo()["saude_diaria"]["dias"] == 2, "resumo conta os dias")
ok(any(p.name.startswith("heimdall-") for p in (b.DB_DIR / "copias").glob("*.db")), "cópia diária criada")

# rotas do agente
porta = "18003"
env = dict(os.environ, HEIMDALL_AGENTE_TOKEN="t" * 20, HEIMDALL_AGENTE_PORT=porta, HEIMDALL_VAULT_DIR=tmp + "/cofre")
p = subprocess.Popen([sys.executable, "heimdall_agente.py"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/saude", timeout=1)
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.3)

    def chamar(caminho, corpo=None, token="t" * 20):
        req = urllib.request.Request(f"http://127.0.0.1:{porta}{caminho}", data=None if corpo is None else json.dumps(corpo).encode(),
                                     headers={"X-Heimdall-Token": token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    st, _ = chamar("/banco/resumo", token="errado")
    ok(st == 401, "rota exige token")
    st, d = chamar("/banco/gravar", {"tabela": "saude_diaria", "registros": [{"dia": "2026-11-11", "metrica": "hrv", "valor": 42}]})
    ok(st == 200 and d["gravados"] == 1, "POST /banco/gravar")
    st, d = chamar("/banco/consultar", {"sql": "SELECT metrica, valor FROM saude_diaria WHERE dia='2026-11-11'"})
    ok(st == 200 and d["linhas"] == [["hrv", 42.0]], "POST /banco/consultar")
    st, d = chamar("/banco/consultar", {"sql": "DROP TABLE diarios"})
    ok(st == 403, "consultar recusa escrita com 403")
    st, d = chamar("/banco/resumo")
    ok(st == 200 and d["saude_diaria"]["linhas"] == 3, "GET /banco/resumo")
finally:
    p.terminate()
print("\nTudo certo." if not falhas else f"\n{falhas} falha(s).")
sys.exit(1 if falhas else 0)
