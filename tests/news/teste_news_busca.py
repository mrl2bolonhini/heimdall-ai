#!/usr/bin/env python3
"""Teste da busca em camadas do Perguntar do News (30 dias: categorias, títulos, leitura)."""
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
import studio_news_busca as b  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("OK   " if ok else "FALHA ") + nome + ("" if ok else f"  {extra}"))
    falhas += 0 if ok else 1


AGORA = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
con = sqlite3.connect(":memory:")
con.row_factory = sqlite3.Row
con.execute("CREATE TABLE noticias (id INTEGER PRIMARY KEY, titulo TEXT, fonte TEXT, categoria TEXT, publicado TEXT, resumo TEXT, trecho TEXT)")


def add(i, titulo, cat, dias, resumo="", trecho=""):
    con.execute("INSERT INTO noticias VALUES (?,?,?,?,?,?,?)", (i, titulo, "Fonte X", cat, b._iso(AGORA - timedelta(days=dias)), resumo, trecho))


add(1, "Banco Central mantém a Selic em 15%", "Economia", 2, "Copom decidiu manter os juros.")
add(2, "Dólar fecha em alta", "Economia", 20, "Moeda subiu com cenário externo.")
add(3, "Time vence clássico no domingo", "Esportes", 1, "Jogo terminou 2 a 1.")
add(4, "Nova vacina é aprovada", "Saúde", 40, "Fora da janela.")
add(5, "Chuva forte alaga ruas", "Brasil", 0, "", "Trecho longo sobre a chuva em São Paulo.")

cats = b.categorias(con, b._iso(AGORA - timedelta(days=30)))
confere("categorias contam só os 30 dias", dict(cats) == {"Economia": 2, "Esportes": 1, "Brasil": 1}, cats)
confere("palavras tiram acento e palavras comuns", b.palavras("Qual foi a decisão da Selic hoje?") == ["decisao", "selic"], b.palavras("Qual foi a decisão da Selic hoje?"))

chamadas = []


def llm_ok(sistema, usuario, n):
    chamadas.append(sistema[:20])
    if "CATEGORIAS" in usuario:
        return 'Claro: {"categorias": ["economia", "Inexistente"], "dias": 7, "palavras": ["juros"]}'
    return '{"escolhidas": [1]}'


ctx = b.montar_contexto("o que decidiram sobre a Selic?", "", llm_ok, con, AGORA)
confere("contexto traz a notícia escolhida com a data", "Selic em 15%" in ctx and "21/11" in ctx, ctx)
confere("não lê o que ficou fora das categorias e dos dias", "Dólar" not in ctx and "clássico" not in ctx and "vacina" not in ctx, ctx)
confere("fez as duas etapas do modelo", len(chamadas) == 2, chamadas)

ctx = b.montar_contexto("e o dólar?", "", llm_ok, con, AGORA)
confere("janela de 7 dias escolhida pelo modelo exclui notícia de 20 dias", "Dólar" not in ctx, ctx)


def llm_quebrado(sistema, usuario, n):
    raise RuntimeError("fora do ar")


ctx = b.montar_contexto("dólar", "", llm_quebrado, con, AGORA)
confere("modelo falhou: o código segue sozinho por palavras", "Dólar fecha em alta" in ctx, ctx)

ctx = b.montar_contexto("chuva", "Economia", llm_quebrado, con, AGORA)
confere("categoria da página aberta manda", "Chuva" not in ctx and "Economia" in ctx, ctx)


def llm_nenhuma(sistema, usuario, n):
    return '{"categorias": [], "dias": 30, "palavras": []}' if "CATEGORIAS" in usuario else '{"escolhidas": []}'


ctx = b.montar_contexto("selic", "", llm_nenhuma, con, AGORA)
confere("nenhuma lida: avisa e mostra títulos próximos", "Nenhuma notícia lida" in ctx and "Títulos mais próximos" in ctx, ctx)

con2 = sqlite3.connect(":memory:")
con2.row_factory = sqlite3.Row
con2.execute("CREATE TABLE noticias (id INTEGER PRIMARY KEY, titulo TEXT, fonte TEXT, categoria TEXT, publicado TEXT, resumo TEXT, trecho TEXT)")
confere("banco vazio avisa", "não tem notícias" in b.montar_contexto("x", "", llm_ok, con2, AGORA))

print("\n" + ("Tudo certo." if not falhas else f"{falhas} falha(s)."))
sys.exit(1 if falhas else 0)
