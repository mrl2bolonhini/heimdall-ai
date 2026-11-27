#!/usr/bin/env python3
"""Testa financas_analise.py e studio_perguntar.py: fatos calculados, texto fixo, conferência dos números do modelo e contexto das perguntas.
O modelo é simulado; nada toca a rede. Dados inventados."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

AQUI = RAIZ
sys.path.insert(0, str(AQUI))
import financas_analise as fa  # noqa: E402
import financas_boletos as fb  # noqa: E402
import financas_nucleo as fn  # noqa: E402
import studio_perguntar as hp  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        if detalhe:
            print("     " + str(detalhe)[:600])


con = fn.conectar(Path(tempfile.mkdtemp()) / "a.db")
itens = []
mercado = {"2026-08": 40000, "2026-09": 42000, "2026-10": 45000, "2026-11": 70000}
for m, v in mercado.items():
    itens += [{"data": f"{m}-05", "valor": -150000, "descricao": f"PIX ALUGUEL IMOBILIARIA {m[5:]}", "fitid": ""},
              {"data": f"{m}-12", "valor": -3990, "descricao": "NETFLIX.COM", "fitid": ""},
              {"data": f"{m}-28" if m != "2026-11" else "2026-11-28", "valor": 500000, "descricao": "SALARIO EMPRESA XYZ", "fitid": ""},
              {"data": f"{m}-09", "valor": -v, "descricao": "SUPERMERCADO BOM PRECO", "fitid": ""},
              {"data": f"{m}-14", "valor": -2000, "descricao": "TARIFA BANCARIA", "fitid": ""}]
itens.append({"data": "2026-11-10", "valor": -30000, "descricao": "RESTAURANTE SABOR", "fitid": ""})
itens.append({"data": "2026-10-20", "valor": -12000, "descricao": "LOJA XPTO 03/10", "fitid": ""})
fn.importar_itens(con, [i for i in itens if i["data"] != "2026-11-28"], "ofx", "x.ofx", "Itaú conta")
con.execute("UPDATE transacoes SET categoria='Restaurantes' WHERE desc_norm LIKE 'restaurante%'")
con.execute("UPDATE transacoes SET categoria='Impostos e tarifas' WHERE desc_norm LIKE 'tarifa%'")
con.commit()
fn.definir_orcamento(con, "Mercado", "600,00")
fb.registrar(con, fb.interpretar("34191234546789012345767890123457616560000045090", date(2026, 11, 12)), "PADARIA")
con.execute("UPDATE boletos SET vencimento='2026-11-01'")
con.commit()
hoje = date(2026, 11, 12)

f = fa.fatos(con, "mes", hoje)
s = f["secoes"]
confere("mês: usa o mês mais recente e traz as seis seções", f["mes"] == "2026-11" and list(s) == ["Resumo", "O que subiu", "O que baixou", "Pontos de atenção", "Onde dá para reduzir", "Datas de pagamento"], list(s))
confere("mês: o que subiu cita mercado com percentual e restaurantes como novo", any("Mercado" in x and "56%" in x for x in s["O que subiu"]) and any("Restaurantes" in x and "categoria nova" in x for x in s["O que subiu"]), s["O que subiu"])
confere("mês: pontos de atenção trazem orçamento estourado, boleto vencido e tarifas", any("Mercado estourado" in x for x in s["Pontos de atenção"]) and any("vencido" in x for x in s["Pontos de atenção"]), s["Pontos de atenção"])
confere("mês: projeção do ritmo do mês aparece", any("No ritmo atual" in x for x in s["Resumo"]), s["Resumo"])
confere("mês: reduzir sugere corte de 10% com valor", any("Cortar 10%" in x for x in s["Onde dá para reduzir"]) or any("Assinaturas" in x for x in s["Onde dá para reduzir"]), s["Onde dá para reduzir"])
confere("mês: datas olham o salário", any("dia 28" in x for x in s["Datas de pagamento"]), s["Datas de pagamento"])
w = fa.fatos(con, "semana", hoje)
confere("semana: resumo dos 7 dias", w["tipo"] == "semana" and "7 dias" in w["secoes"]["Resumo"][0], w["secoes"]["Resumo"])
txt = fa.texto_fixo(f)
confere("texto fixo: título, seções e lista numerada", txt.startswith("Análise de novembro de 2026") and "Pontos de atenção:" in txt and "1. " in txt)
confere("texto fixo não tem tabela nem marcação visual", "|" not in txt and "**" not in txt and "#" not in txt)
confere("sem lançamentos: erro claro", "Importe" in (lambda: (_ for _ in ()).throw(AssertionError) if False else str(__import__("subprocess").run([sys.executable, "-c", "import financas_nucleo as fn, financas_analise as fa, tempfile, pathlib\ntry:\n    fa.fatos(fn.conectar(pathlib.Path(tempfile.mkdtemp())/'v.db'))\nexcept fn.ErroFinance as e:\n    print(e)"], capture_output=True, text=True, cwd=str(AQUI)).stdout))())

# modelo simulado
base = fa.texto_fixo(f)
hp.chamar_local = lambda sistema, usuario, modelo="", max_tokens=700, timeout=240: "Consultor: " + base.replace("Análise de", "Visão geral de")
r = fa.com_modelo(f)
confere("modelo que só reusa números dos fatos é aceito", r["origem"] == "modelo local" and not r["avisos"], r["avisos"])
hp.chamar_local = lambda *a, **k: base + "\nAlém disso você gastou R$ 9.999,99 sem motivo."
r = fa.com_modelo(f)
confere("modelo que inventa valor é descartado e volta o texto fixo", r["origem"] == "regras" and r["texto"] == base and r["avisos"], r)


def cai(*a, **k):
    raise OSError("sem modelo")


hp.chamar_local = cai
r = fa.com_modelo(f)
confere("modelo fora do ar: texto fixo com aviso", r["origem"] == "regras" and "não respondeu" in r["avisos"][0], r)

# perguntar
ctx = fa.contexto_pergunta(con, "Quanto gastei com supermercado em outubro?", hoje)
confere("contexto da pergunta: mês pedido, previsto e busca por palavra", "[outubro de 2026]" in ctx and "[Previsto" in ctx and "supermercado" in ctx.lower() and "SUPERMERCADO BOM PRECO" in ctx, ctx[:400])
confere("contexto: boletos em aberto", "[Boletos em aberto]" in ctx and "PADARIA" in ctx)
confere("contexto tem limite de tamanho", len(ctx) <= 9000)
hp.chamar_local = lambda *a, **k: "Em outubro você gastou R$ 450,00 em supermercado."
r = hp.responder(ctx, "Quanto gastei com supermercado em outubro?")
confere("pergunta: resposta com valor dos dados passa sem aviso", r["texto"].startswith("Em outubro") and not r["avisos"], r)
hp.chamar_local = lambda *a, **k: "Foram R$ 777,77."
r = hp.responder(ctx, "x")
confere("pergunta: valor que não está nos dados gera aviso", r["avisos"] and "R$ 777,77" in r["avisos"][0], r)
confere("o módulo tenta a nuvem só quando ligada e volta ao modelo local se ela falhar", "nuvem.ativo()" in (AQUI / "studio_perguntar.py").read_text(encoding="utf-8") and "usando o modelo local" in (AQUI / "studio_perguntar.py").read_text(encoding="utf-8"))

# tarefas em segundo plano
import time  # noqa: E402
t1 = hp.iniciar("dono1", "analise", lambda: {"ok": 1})
for _ in range(50):
    if hp.ultima("dono1")["estado"] != "pensando":
        break
    time.sleep(0.05)
confere("tarefa em segundo plano termina com resultado", hp.ultima("dono1")["estado"] == "pronto" and hp.ultima("dono1")["resultado"] == {"ok": 1})
hp.iniciar("dono2", "x", lambda: 1 / 0)
time.sleep(0.3)
confere("tarefa com erro guarda o erro sem derrubar", hp.ultima("dono2")["estado"] == "erro" and "ZeroDivisionError" in hp.ultima("dono2")["erro"])

print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
