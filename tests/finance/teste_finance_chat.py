#!/usr/bin/env python3
"""Testa as ferramentas do Finance no chat (heimdall_tools.financas_*): leitura, filtros, somente leitura, desligar e banco ausente. Dados inventados."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import sqlite3
import sys
import tempfile
from datetime import date
from pathlib import Path

AQUI = RAIZ
sys.path.insert(0, str(AQUI))
tmp = Path(tempfile.mkdtemp())
os.environ["HEIMDALL_FINANCE_DIR"] = str(tmp / "dados")
os.environ.pop("HEIMDALL_FINANCE_CHAT", None)
import financas_boletos as fb  # noqa: E402
import financas_nucleo as fn  # noqa: E402
import heimdall_tools as ht  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        if detalhe:
            print("     " + str(detalhe)[:500])


confere("sem banco: mensagem clara e sem erro", "importe um extrato" in ht.financas_resumo(), ht.financas_resumo())

(tmp / "dados").mkdir()
con = fn.conectar(tmp / "dados" / "financas.db")
itens = []
for m in ("2026-08", "2026-09", "2026-10"):
    itens += [{"data": f"{m}-05", "valor": -150000, "descricao": f"PIX ALUGUEL IMOBILIARIA {m[5:]}", "fitid": ""},
              {"data": f"{m}-12", "valor": -3990, "descricao": "NETFLIX.COM", "fitid": ""},
              {"data": f"{m}-28", "valor": 500000, "descricao": "SALARIO EMPRESA XYZ", "fitid": ""},
              {"data": f"{m}-15", "valor": -45000, "descricao": "SUPERMERCADO BOM PRECO", "fitid": ""}]
fn.importar_itens(con, itens, "ofx", "c.ofx", "Itaú conta")
fn.definir_orcamento(con, "Mercado", "300,00")
fb.registrar(con, fb.interpretar("34191234546789012345767890123457616560000045090"), "PADARIA DOIS IRMAOS")
con.close()

r = ht.financas_resumo("2026-10")
confere("resumo traz receitas, despesas e categorias do mês", "receitas R$ 5.000,00" in r and "Moradia e contas: R$ 1.500,00" in r and "Mercado: R$ 450,00" in r, r)
confere("resumo sem mês usa o mais recente", "outubro de 2026" in ht.financas_resumo(), ht.financas_resumo()[:200])
confere("resumo de mês sem dados lista os meses que existem", "2026-10" in ht.financas_resumo("2020-01") and "não há lançamentos" in ht.financas_resumo("2020-01"))
confere("mês mal escrito é recusado sem erro", "Finance:" in ht.financas_resumo("outubro"))
t = ht.financas_transacoes("supermercado", "", "", 10)
confere("transações: busca sem acento e maiúsculas", "SUPERMERCADO BOM PRECO" in t and t.count("SUPERMERCADO") == 3, t)
confere("transações: filtro por mês e categoria", "NETFLIX" not in ht.financas_transacoes("", "2026-09", "Mercado", 10))
confere("transações: nada achado", "Nenhum lançamento" in ht.financas_transacoes("zzzz"))
confere("transações: limite máximo 50", "mostrando" in ht.financas_transacoes("", "", "", 9999))
o = ht.financas_orcamentos("2026-10")
confere("orçamentos: limite, gasto e situação", "Mercado: limite R$ 300,00, gasto R$ 450,00" in o and "estourado" in o, o)
rec = ht.financas_recorrentes()
confere("recorrentes: acha aluguel e salário", "ALUGUEL" in rec.upper() and "SALARIO" in rec.upper(), rec)
fu = ht.financas_futuros(3)
confere("futuros: devolve meses com totais", "saídas previstas" in fu, fu)
b = ht.financas_boletos()
confere("boletos: lista o boleto e não paga nada", "PADARIA DOIS IRMAOS: R$ 450,90" in b, b)

# somente leitura: a conexão das ferramentas não consegue gravar
con2, _ = ht._financas_ro()
try:
    con2.execute("DELETE FROM transacoes")
    confere("a conexão do chat é somente leitura", False)
except sqlite3.OperationalError:
    confere("a conexão do chat é somente leitura", True)
con2.close()
confere("nada mudou no banco depois das consultas", fn.conectar(tmp / "dados" / "financas.db").execute("SELECT COUNT(*) FROM transacoes").fetchone()[0] == 12)

os.environ["HEIMDALL_FINANCE_CHAT"] = "0"
confere("HEIMDALL_FINANCE_CHAT=0 desliga todas as ferramentas", all("desligadas" in f() for f in (ht.financas_resumo, ht.financas_recorrentes, ht.financas_boletos, ht.financas_orcamentos, ht.financas_transacoes)))
os.environ.pop("HEIMDALL_FINANCE_CHAT")
confere("as ferramentas estão no grupo de dados do chat", {"financas_resumo", "financas_transacoes", "financas_orcamentos", "financas_recorrentes", "financas_boletos"} <= {f.__name__ for f in ht.DADOS_TOOLS})
confere("e não estão no grupo público dos convidados", not ({f.__name__ for f in ht.PUBLIC_TOOLS} & {"financas_resumo", "financas_transacoes", "financas_orcamentos", "financas_recorrentes", "financas_boletos"}))

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
