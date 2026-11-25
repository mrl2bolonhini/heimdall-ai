#!/usr/bin/env python3
"""Testa o motor do Heimdall Trading: ordens a mercado e limitadas, limites, venda sem posição, perda do dia, cotações e sinais."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp())
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "db")

import heimdall_trading_motor as m  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


def erro(fn, *a, **k):
    try:
        fn(*a, **k)
    except m.ErroTrading as ex:
        return str(ex)
    return None


T0 = 1_800_000_000.0
confere("o banco da mesa é separado (trading.db)", m.caminho() == TMP / "db" / "trading.db")
confere("cotação simulada é estável no mesmo instante e muda ao longo do tempo",
        m.cotacao("ABCD3", T0)[0] == m.cotacao("ABCD3", T0)[0] and len({m.cotacao("ABCD3", T0 + i * 600)[0] for i in range(6)}) > 1)
confere("código de ativo inválido é recusado", erro(m.cotacao, "ab cd") is not None and erro(m.validar_ticker, "") is not None)

# manual
m.definir_fonte("manual")
confere("fonte manual sem preço informado dá erro claro", "Sem cotação" in (erro(m.cotacao, "XYZ1", T0) or ""))
m.informar_preco("XYZ1", "10,00", T0)
r = m.enviar_ordem("XYZ1", "comprar", 100, "mercado", None, T0)
confere("compra a mercado executa na cotação e baixa o caixa", r["status"] == "executada" and m.resumo(T0)["caixa"] == 99000.0, r)
s = m.resumo(T0)
confere("posição criada com preço médio", s["posicoes"][0]["qtd"] == 100 and s["posicoes"][0]["preco_medio"] == 10.0, s)
m.informar_preco("XYZ1", "12,00", T0 + 5)
confere("resultado não realizado e patrimônio", m.resumo(T0 + 5)["posicoes"][0]["resultado"] == 200.0 and m.resumo(T0 + 5)["patrimonio"] == 100200.0)

# sem venda a descoberto
r = m.enviar_ordem("XYZ1", "vender", 150, "mercado", None, T0 + 5)
confere("venda acima da carteira é rejeitada e fica no histórico", r["status"] == "rejeitada" and m.listar_ordens()[0]["status"] == "rejeitada", r)
r = m.enviar_ordem("XYZ1", "vender", 40, "limite", 15, T0 + 5)
confere("venda limitada fica aberta", r["status"] == "aberta")
r = m.enviar_ordem("XYZ1", "vender", 70, "mercado", None, T0 + 5)
confere("vendas abertas contam: não dá para vender além do que sobra", r["status"] == "rejeitada", r)
m.informar_preco("XYZ1", "15,50", T0 + 10)
confere("ordem limitada executa quando a cotação alcança", [o["status"] for o in m.listar_ordens() if o["qtd"] == 40] == ["executada"], m.listar_ordens())
confere("lucro realizado gravado", m.resumo(T0 + 10)["realizado_hoje"] == 220.0, m.resumo(T0 + 10))

# fechar posição e cancelar
m.enviar_ordem("XYZ1", "vender", 10, "limite", 99, T0 + 11)
r = m.fechar_posicao("XYZ1", T0 + 12)
confere("fechar posição cancela as vendas abertas e vende tudo", r["status"] == "executada" and not m.resumo(T0 + 12)["posicoes"], r)
confere("fechar sem posição dá erro claro", "não tem posição" in (erro(m.fechar_posicao, "XYZ1", T0 + 13) or ""))
confere("cancelar todas sem ordens avisa", "Não havia" in m.cancelar_todas(agora=T0 + 13))

# limites
m.definir_limites(1000, 2000, 2, 0)
r = m.enviar_ordem("XYZ1", "comprar", 100, "mercado", None, T0 + 20)
confere("ordem acima do limite por ordem é rejeitada", r["status"] == "rejeitada" and "limite por ordem" in r["mensagem"], r)
confere("limites inválidos não são gravados", erro(m.definir_limites, "x", 1, 1, 0) is not None and erro(m.definir_limites, 0, 1, 1, 0) is not None)
m.definir_limites(1000000, 2000, 2, 0)
m.enviar_ordem("XYZ1", "comprar", 1, "limite", 1, T0 + 20)
m.enviar_ordem("XYZ1", "comprar", 1, "limite", 1, T0 + 20)
r = m.enviar_ordem("XYZ1", "comprar", 1, "limite", 1, T0 + 20)
confere("limite de ordens abertas", r["status"] == "rejeitada" and "ordens abertas" in r["mensagem"], r)
m.cancelar_todas(agora=T0 + 21)

# perda do dia bloqueia compras, mas não vendas
D = 86400
m.definir_limites(1000000, 500, 20, 0)
m.informar_preco("XYZ1", "15,00", T0 + D)
m.resumo(T0 + D)
m.enviar_ordem("XYZ1", "comprar", 1000, "mercado", None, T0 + D)
m.informar_preco("XYZ1", "14,00", T0 + D + 31)
a = m.alertas(T0 + D + 31)
confere("alerta de perda do dia e bloqueio", m.resumo(T0 + D + 31)["bloqueado"] and any("bloqueadas" in x for x in a), a)
r = m.enviar_ordem("XYZ1", "comprar", 1, "mercado", None, T0 + D + 31)
confere("compra bloqueada pelo limite de perda do dia", r["status"] == "rejeitada" and "perda do dia" in r["mensagem"], r)
r = m.fechar_posicao("XYZ1", T0 + D + 32)
confere("fechar posição continua liberado com o limite atingido", r["status"] == "executada", r)

# taxa e caixa livre
m.zerar_conta(10000)
confere("zerar conta volta ao caixa inicial", m.resumo(T0 + 40)["caixa"] == 10000.0 and not m.listar_ordens())
m.definir_fonte("manual")
m.definir_limites(100000, 5000, 20, 1)
m.informar_preco("ABC1", "10", T0 + 40)
r = m.enviar_ordem("ABC1", "comprar", 1000, "mercado", None, T0 + 40)
confere("compra sem caixa para o valor mais a taxa é rejeitada", r["status"] == "rejeitada" and "caixa" in r["mensagem"], r)
r = m.enviar_ordem("ABC1", "comprar", 900, "mercado", None, T0 + 40)
confere("taxa é cobrada e entra no preço médio", r["status"] == "executada" and m.resumo(T0 + 40)["caixa"] == 910.0 and m.resumo(T0 + 40)["posicoes"][0]["preco_medio"] == 10.1, m.resumo(T0 + 40))

# fonte simulada: série e sinal
m.definir_fonte("simulada")
sn = m.sinal("ABCD3", T0)
confere("sinal descreve o movimento sem recomendar", "tendência" in sn["texto"] and "compre" not in sn["texto"].lower() and "venda" not in sn["texto"].lower(), sn)
m.acompanhar("ABCD3")
m.acompanhar("zzz9")
confere("lista acompanhada", m.lista_acompanhada() == ["ABCD3", "ZZZ9"])
m.acompanhar("zzz9", remover=True)
confere("remover da lista", m.lista_acompanhada() == ["ABCD3"])
confere("cancelar ordem inexistente dá erro", erro(m.cancelar, 999) is not None)
sys.exit(1 if falhas else 0)
