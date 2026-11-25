#!/usr/bin/env python3
"""Heimdall Trading, motor da mesa de operações em SIMULAÇÃO (sem dinheiro nem mercado reais).

Regras fixas, em código (a IA avisa, quem decide é o usuário, e nenhuma ordem sai sem ele):
  1. Só simulação: caixa virtual, nenhuma corretora, nenhuma ordem real.
  2. Compra e venda a mercado (executa na cotação do momento) ou limitada (fica aberta até a cotação alcançar o preço).
  3. Sem venda a descoberto: só se vende o que está na carteira (descontadas as vendas já abertas).
  4. Limites por ordem (valor), de perda por dia (bloqueia novas compras) e de ordens abertas. Fechar posição e cancelar nunca são bloqueados.
  5. Tudo fica gravado em db/trading.db (por pessoa: banco.pasta_em_uso()); zerar a conta apaga só esse arquivo.
Cotações (HEIMDALL_TRADING_FONTE): "simulada" (padrão, preços artificiais que variam sozinhos, bons para treinar), "manual" (você informa o preço)
ou "brapi" (preços da B3 pela brapi.dev, com HEIMDALL_TRADING_BRAPI_TOKEN no .env).
"""
import contextlib
import json
import math
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import zlib
from datetime import datetime
from pathlib import Path

import heimdall_banco as banco

TICKER = re.compile(r"^[A-Z0-9]{1,10}$")
CAIXA_INICIAL = 100000.0
PADROES = {"caixa_inicial": CAIXA_INICIAL, "caixa": CAIXA_INICIAL, "limite_ordem": 10000.0, "limite_perda_dia": 2000.0, "max_ordens": 20,
           "taxa_pct": 0.0, "fonte": "simulada"}
FONTES = ("simulada", "manual", "brapi")
_lock = threading.RLock()


class ErroTrading(Exception):
    """Erro de regra ou de validação, com mensagem própria para o usuário."""


def caminho() -> Path:
    return banco.pasta_em_uso() / "trading.db"


@contextlib.contextmanager
def conexao():
    caminho().parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(caminho()), timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript("""
CREATE TABLE IF NOT EXISTS config(chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS ordens(id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, lado TEXT, qtd INTEGER, tipo TEXT, preco_limite REAL,
  status TEXT, preco_exec REAL, criada TEXT, executada TEXT, motivo TEXT);
CREATE TABLE IF NOT EXISTS posicoes(ticker TEXT PRIMARY KEY, qtd INTEGER, preco_medio REAL);
CREATE TABLE IF NOT EXISTS fechamentos(id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, qtd INTEGER, preco_medio REAL, preco_saida REAL, lucro REAL, dia TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS precos(ticker TEXT PRIMARY KEY, preco REAL, ts REAL, origem TEXT);
CREATE TABLE IF NOT EXISTS historico(ticker TEXT, ts REAL, preco REAL);
CREATE INDEX IF NOT EXISTS ix_hist ON historico(ticker, ts);
""")
    try:
        yield c
        c.commit()
    finally:
        c.close()


# ---------------------------------------------------------------- configuração
def ler_config(c=None) -> dict:
    def _ler(cx):
        d = dict(PADROES)
        for r in cx.execute("SELECT chave, valor FROM config"):
            if r["chave"] in PADROES:
                try:
                    d[r["chave"]] = type(PADROES[r["chave"]])(r["valor"])
                except (TypeError, ValueError):
                    pass
        return d
    if c is not None:
        return _ler(c)
    with conexao() as cx:
        return _ler(cx)


def _gravar(c, chave: str, valor) -> None:
    c.execute("INSERT INTO config(chave, valor) VALUES(?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, str(valor)))


def definir_limites(limite_ordem, limite_perda_dia, max_ordens, taxa_pct) -> None:
    """Valida e grava os limites. Valores inválidos levantam ErroTrading e nada é gravado."""
    try:
        lo, lp, mo, tx = float(str(limite_ordem).replace(",", ".")), float(str(limite_perda_dia).replace(",", ".")), int(max_ordens), float(str(taxa_pct).replace(",", "."))
    except (TypeError, ValueError):
        raise ErroTrading("Use só números nos limites.") from None
    if not (0 < lo <= 10_000_000 and 0 < lp <= 10_000_000 and 1 <= mo <= 200 and 0 <= tx <= 5):
        raise ErroTrading("Limite por ordem e de perda por dia entre 0,01 e 10.000.000; ordens abertas de 1 a 200; taxa de 0 a 5%.")
    with _lock, conexao() as c:
        for k, v in (("limite_ordem", lo), ("limite_perda_dia", lp), ("max_ordens", mo), ("taxa_pct", tx)):
            _gravar(c, k, v)


def definir_fonte(fonte: str) -> None:
    if fonte not in FONTES:
        raise ErroTrading("Fonte de cotações desconhecida.")
    with _lock, conexao() as c:
        _gravar(c, "fonte", fonte)


def zerar_conta(caixa=CAIXA_INICIAL) -> None:
    """Apaga ordens, posições, histórico e config: volta ao caixa inicial. Só mexe no trading.db desta pessoa."""
    try:
        cx = float(str(caixa).replace(",", "."))
    except ValueError:
        raise ErroTrading("Informe o caixa inicial em número.") from None
    if not 1000 <= cx <= 100_000_000:
        raise ErroTrading("O caixa inicial vai de 1.000 a 100.000.000.")
    with _lock, conexao() as c:
        for t in ("ordens", "posicoes", "fechamentos", "precos", "historico", "config"):
            c.execute(f"DELETE FROM {t}")  # noqa: S608 (nomes fixos)
        _gravar(c, "caixa_inicial", cx)
        _gravar(c, "caixa", cx)


# ---------------------------------------------------------------- cotações
def _preco_simulado(ticker: str, t: float) -> float:
    base = 10 + (zlib.crc32(ticker.encode()) % 9000) / 100.0        # 10,00 a 99,99
    f1 = (zlib.crc32(b"a" + ticker.encode()) % 628) / 100.0
    f2 = (zlib.crc32(b"b" + ticker.encode()) % 628) / 100.0
    ruido = ((zlib.crc32(f"{ticker}:{int(t // 5)}".encode()) % 2001) - 1000) / 1000.0   # -1 a 1, muda a cada 5 s
    return round(base * (1 + 0.035 * math.sin(t / 900 + f1) + 0.015 * math.sin(t / 110 + f2) + 0.0015 * ruido), 2)


_cache_brapi = {}


def _preco_brapi(ticker: str, agora: float) -> float:
    ant = _cache_brapi.get(ticker)
    if ant and agora - ant[0] < 15:
        return ant[1]
    token = os.environ.get("HEIMDALL_TRADING_BRAPI_TOKEN", "")
    url = f"https://brapi.dev/api/quote/{ticker}" + (f"?token={token}" if token else "")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Heimdall-Trading"}), timeout=8) as r:
            preco = float(json.loads(r.read(200_000))["results"][0]["regularMarketPrice"])
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError):
        raise ErroTrading(f"Não consegui a cotação de {ticker} na brapi. Tente de novo ou mude a fonte em Ajustes.") from None
    _cache_brapi[ticker] = (agora, preco)
    return preco


def _gravar_preco(c, ticker: str, preco: float, origem: str, agora: float) -> None:
    c.execute("INSERT INTO precos(ticker, preco, ts, origem) VALUES(?,?,?,?) ON CONFLICT(ticker) DO UPDATE SET preco=excluded.preco, ts=excluded.ts, origem=excluded.origem",
              (ticker, preco, agora, origem))
    ult = c.execute("SELECT ts FROM historico WHERE ticker=? ORDER BY ts DESC LIMIT 1", (ticker,)).fetchone()
    if not ult or agora - ult["ts"] >= 10:
        c.execute("INSERT INTO historico(ticker, ts, preco) VALUES(?,?,?)", (ticker, agora, preco))
        c.execute("DELETE FROM historico WHERE ticker=? AND ts<?", (ticker, agora - 7 * 86400))


def validar_ticker(t: str) -> str:
    t = (t or "").strip().upper()
    if not TICKER.match(t):
        raise ErroTrading("Informe o código do ativo com letras e números, até 10 caracteres (por exemplo, ABCD3).")
    return t


def cotacao(ticker: str, agora: float = None, c=None) -> tuple:
    """(preço, origem) do ativo. Na fonte manual, é o último preço informado."""
    ticker = validar_ticker(ticker)
    agora = time.time() if agora is None else agora
    if c is None:
        with _lock, conexao() as cx:
            return cotacao(ticker, agora, cx)
    fonte = ler_config(c)["fonte"]
    if fonte == "manual":
        r = c.execute("SELECT preco FROM precos WHERE ticker=?", (ticker,)).fetchone()
        if not r:
            raise ErroTrading(f"Sem cotação de {ticker}. Na fonte manual, informe o preço primeiro.")
        return r["preco"], "manual"
    preco = _preco_simulado(ticker, agora) if fonte == "simulada" else _preco_brapi(ticker, agora)
    _gravar_preco(c, ticker, preco, fonte, agora)
    return preco, fonte


def informar_preco(ticker: str, preco, agora: float = None) -> float:
    """Fonte manual: grava o preço do ativo e processa as ordens limitadas que ele alcança."""
    ticker = validar_ticker(ticker)
    try:
        p = round(float(str(preco).replace(",", ".")), 2)
    except ValueError:
        raise ErroTrading("Informe o preço em número, por exemplo 12,34.") from None
    if not 0 < p <= 1_000_000:
        raise ErroTrading("O preço precisa ser maior que zero.")
    agora = time.time() if agora is None else agora
    with _lock, conexao() as c:
        _gravar_preco(c, ticker, p, "manual", agora)
        _processar(c, agora)
    return p


# ---------------------------------------------------------------- carteira e resultado
def _posicoes(c) -> list:
    return [dict(r) for r in c.execute("SELECT ticker, qtd, preco_medio FROM posicoes WHERE qtd>0 ORDER BY ticker")]


def _valor_posicoes(c, agora: float) -> float:
    total = 0.0
    for p in _posicoes(c):
        try:
            total += p["qtd"] * cotacao(p["ticker"], agora, c)[0]
        except ErroTrading:
            total += p["qtd"] * p["preco_medio"]
    return total


def _reservado(c) -> float:
    r = c.execute("SELECT COALESCE(SUM(qtd*preco_limite),0) AS t FROM ordens WHERE status='aberta' AND lado='C'").fetchone()
    return float(r["t"])


def _patrimonio(c, agora: float) -> float:
    return ler_config(c)["caixa"] + _valor_posicoes(c, agora)


def _dia(agora: float) -> str:
    return datetime.fromtimestamp(agora).strftime("%Y-%m-%d")


def _abertura(c, agora: float) -> float:
    chave = "abertura:" + _dia(agora)
    r = c.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
    if r:
        return float(r["valor"])
    pat = _patrimonio(c, agora)
    c.execute("DELETE FROM config WHERE chave LIKE 'abertura:%'")
    c.execute("INSERT INTO config(chave, valor) VALUES(?,?)", (chave, str(pat)))
    return pat


def resumo(agora: float = None) -> dict:
    agora = time.time() if agora is None else agora
    with _lock, conexao() as c:
        _processar(c, agora)
        cfg = ler_config(c)
        pos = []
        for p in _posicoes(c):
            try:
                preco = cotacao(p["ticker"], agora, c)[0]
            except ErroTrading:
                preco = p["preco_medio"]
            pos.append({**p, "preco": preco, "valor": round(p["qtd"] * preco, 2), "resultado": round((preco - p["preco_medio"]) * p["qtd"], 2),
                        "pct": round((preco / p["preco_medio"] - 1) * 100, 2) if p["preco_medio"] else 0.0})
        valor = sum(p["valor"] for p in pos)
        pat = cfg["caixa"] + valor
        dia = round(pat - _abertura(c, agora), 2)
        realizado_hoje = c.execute("SELECT COALESCE(SUM(lucro),0) AS t FROM fechamentos WHERE dia=?", (_dia(agora),)).fetchone()["t"]
        return {"caixa": round(cfg["caixa"], 2), "reservado": round(_reservado(c), 2), "livre": round(cfg["caixa"] - _reservado(c), 2), "valor_posicoes": round(valor, 2),
                "patrimonio": round(pat, 2), "resultado_dia": dia, "realizado_hoje": round(realizado_hoje, 2), "resultado_total": round(pat - cfg["caixa_inicial"], 2),
                "limite_perda_dia": cfg["limite_perda_dia"], "bloqueado": dia <= -cfg["limite_perda_dia"], "posicoes": pos}


# ---------------------------------------------------------------- ordens
def _executar(c, o: dict, preco: float, agora: float) -> None:
    cfg = ler_config(c)
    valor = round(o["qtd"] * preco, 2)
    taxa = round(valor * cfg["taxa_pct"] / 100, 2)
    ts = datetime.fromtimestamp(agora).isoformat(timespec="seconds")
    if o["lado"] == "C":
        _gravar(c, "caixa", cfg["caixa"] - valor - taxa)
        p = c.execute("SELECT qtd, preco_medio FROM posicoes WHERE ticker=?", (o["ticker"],)).fetchone()
        q0, m0 = (p["qtd"], p["preco_medio"]) if p else (0, 0.0)
        q1 = q0 + o["qtd"]
        m1 = (q0 * m0 + o["qtd"] * preco + taxa) / q1
        c.execute("INSERT INTO posicoes(ticker, qtd, preco_medio) VALUES(?,?,?) ON CONFLICT(ticker) DO UPDATE SET qtd=excluded.qtd, preco_medio=excluded.preco_medio",
                  (o["ticker"], q1, round(m1, 4)))
    else:
        p = c.execute("SELECT qtd, preco_medio FROM posicoes WHERE ticker=?", (o["ticker"],)).fetchone()
        _gravar(c, "caixa", cfg["caixa"] + valor - taxa)
        lucro = round((preco - p["preco_medio"]) * o["qtd"] - taxa, 2)
        c.execute("UPDATE posicoes SET qtd=qtd-? WHERE ticker=?", (o["qtd"], o["ticker"]))
        c.execute("INSERT INTO fechamentos(ticker, qtd, preco_medio, preco_saida, lucro, dia, ts) VALUES(?,?,?,?,?,?,?)",
                  (o["ticker"], o["qtd"], p["preco_medio"], preco, lucro, _dia(agora), ts))
    c.execute("UPDATE ordens SET status='executada', preco_exec=?, executada=? WHERE id=?", (preco, ts, o["id"]))


def _processar(c, agora: float) -> int:
    """Executa as ordens limitadas que a cotação já alcançou. Devolve quantas executou."""
    n = 0
    for o in [dict(r) for r in c.execute("SELECT * FROM ordens WHERE status='aberta' ORDER BY id")]:
        try:
            preco = cotacao(o["ticker"], agora, c)[0]
        except ErroTrading:
            continue
        if (o["lado"] == "C" and preco <= o["preco_limite"]) or (o["lado"] == "V" and preco >= o["preco_limite"]):
            _executar(c, o, preco, agora)
            n += 1
    return n


def _rejeitar(c, ticker, lado, qtd, tipo, limite, motivo, agora) -> None:
    c.execute("INSERT INTO ordens(ticker, lado, qtd, tipo, preco_limite, status, criada, motivo) VALUES(?,?,?,?,?,'rejeitada',?,?)",
              (ticker, lado, qtd, tipo, limite, datetime.fromtimestamp(agora).isoformat(timespec="seconds"), motivo))


def enviar_ordem(ticker: str, lado: str, qtd, tipo: str = "mercado", preco_limite=None, agora: float = None, forcar_saida: bool = False) -> dict:
    """Valida contra os limites e executa (mercado) ou deixa aberta (limitada). Devolve {"status", "mensagem", "id"}.
    Rejeitada por regra não é erro de programa: volta status "rejeitada" com o motivo e fica no histórico."""
    ticker = validar_ticker(ticker)
    lado = {"C": "C", "COMPRAR": "C", "V": "V", "VENDER": "V"}.get((lado or "").upper())
    if lado is None:
        raise ErroTrading("Escolha comprar ou vender.")
    try:
        qtd = int(str(qtd).strip())
    except ValueError:
        raise ErroTrading("Informe a quantidade em número inteiro.") from None
    if not 1 <= qtd <= 1_000_000:
        raise ErroTrading("A quantidade vai de 1 a 1.000.000.")
    if tipo not in ("mercado", "limite"):
        raise ErroTrading("Tipo de ordem inválido.")
    limite = None
    if tipo == "limite":
        try:
            limite = round(float(str(preco_limite).replace(",", ".")), 2)
        except (TypeError, ValueError):
            raise ErroTrading("Informe o preço limite em número, por exemplo 12,34.") from None
        if not 0 < limite <= 1_000_000:
            raise ErroTrading("O preço limite precisa ser maior que zero.")
    agora = time.time() if agora is None else agora
    with _lock, conexao() as c:
        _processar(c, agora)
        cfg = ler_config(c)
        preco, _ = cotacao(ticker, agora, c)
        ref = limite if limite else preco
        nome = "compra" if lado == "C" else "venda"

        def rejeita(motivo):
            _rejeitar(c, ticker, lado, qtd, tipo, limite, motivo, agora)
            return {"status": "rejeitada", "mensagem": f"Ordem de {nome} rejeitada: {motivo}", "id": None}

        if not forcar_saida:
            if c.execute("SELECT COUNT(*) AS n FROM ordens WHERE status='aberta'").fetchone()["n"] >= cfg["max_ordens"] and tipo == "limite":
                return rejeita(f"o limite de {cfg['max_ordens']} ordens abertas foi atingido.")
            if lado == "C":
                if qtd * ref > cfg["limite_ordem"]:
                    return rejeita(f"o valor da ordem (R$ {qtd * ref:,.2f}) passa do limite por ordem (R$ {cfg['limite_ordem']:,.2f}).")
                dia = _patrimonio(c, agora) - _abertura(c, agora)
                if dia <= -cfg["limite_perda_dia"]:
                    return rejeita("o limite de perda do dia foi atingido; novas compras ficam bloqueadas até amanhã. Vender e fechar posição continuam liberados.")
                if qtd * ref * (1 + cfg["taxa_pct"] / 100) > cfg["caixa"] - _reservado(c):
                    return rejeita("não há caixa livre suficiente.")
        if lado == "V":
            p = c.execute("SELECT qtd FROM posicoes WHERE ticker=?", (ticker,)).fetchone()
            vendida = c.execute("SELECT COALESCE(SUM(qtd),0) AS t FROM ordens WHERE status='aberta' AND lado='V' AND ticker=?", (ticker,)).fetchone()["t"]
            if (p["qtd"] if p else 0) - vendida < qtd:
                return rejeita("você só pode vender o que tem na carteira (vendas abertas já contam).")
        cur = c.execute("INSERT INTO ordens(ticker, lado, qtd, tipo, preco_limite, status, criada) VALUES(?,?,?,?,?,'aberta',?)",
                        (ticker, lado, qtd, tipo, limite, datetime.fromtimestamp(agora).isoformat(timespec="seconds")))
        oid = cur.lastrowid
        o = {"id": oid, "ticker": ticker, "lado": lado, "qtd": qtd}
        if tipo == "mercado":
            _executar(c, o, preco, agora)
            return {"status": "executada", "mensagem": f"{'Compra' if lado == 'C' else 'Venda'} de {qtd} {ticker} a R$ {preco:,.2f} executada.", "id": oid}
        if (lado == "C" and preco <= limite) or (lado == "V" and preco >= limite):
            _executar(c, o, preco, agora)
            return {"status": "executada", "mensagem": f"{'Compra' if lado == 'C' else 'Venda'} de {qtd} {ticker} a R$ {preco:,.2f} executada.", "id": oid}
        return {"status": "aberta", "mensagem": f"Ordem limitada de {nome} de {qtd} {ticker} a R$ {limite:,.2f} aberta. Cotação agora: R$ {preco:,.2f}.", "id": oid}


def cancelar(oid, agora: float = None) -> str:
    try:
        oid = int(oid)
    except (TypeError, ValueError):
        raise ErroTrading("Ordem inválida.") from None
    with _lock, conexao() as c:
        r = c.execute("UPDATE ordens SET status='cancelada', executada=? WHERE id=? AND status='aberta'",
                      (datetime.fromtimestamp(time.time() if agora is None else agora).isoformat(timespec="seconds"), oid))
        if r.rowcount == 0:
            raise ErroTrading("Essa ordem não está aberta.")
    return f"Ordem {oid} cancelada."


def cancelar_todas(ticker: str = "", agora: float = None) -> str:
    ts = datetime.fromtimestamp(time.time() if agora is None else agora).isoformat(timespec="seconds")
    with _lock, conexao() as c:
        if ticker:
            r = c.execute("UPDATE ordens SET status='cancelada', executada=? WHERE status='aberta' AND ticker=?", (ts, validar_ticker(ticker)))
        else:
            r = c.execute("UPDATE ordens SET status='cancelada', executada=? WHERE status='aberta'", (ts,))
    return f"{r.rowcount} ordem(ns) aberta(s) cancelada(s)." if r.rowcount else "Não havia ordens abertas."


def fechar_posicao(ticker: str, agora: float = None) -> dict:
    """Cancela as vendas abertas do ativo e vende tudo a mercado. Nunca é bloqueado pelos limites."""
    ticker = validar_ticker(ticker)
    agora = time.time() if agora is None else agora
    with _lock, conexao() as c:
        p = c.execute("SELECT qtd FROM posicoes WHERE ticker=?", (ticker,)).fetchone()
        qtd = p["qtd"] if p else 0
        if qtd <= 0:
            raise ErroTrading(f"Você não tem posição em {ticker}.")
        c.execute("UPDATE ordens SET status='cancelada' WHERE status='aberta' AND lado='V' AND ticker=?", (ticker,))
    return enviar_ordem(ticker, "V", qtd, "mercado", None, agora, forcar_saida=True)


def listar_ordens(status: str = "", limite: int = 50) -> list:
    with _lock, conexao() as c:
        _processar(c, time.time())
        if status == "abertas":
            q, a = "SELECT * FROM ordens WHERE status='aberta' ORDER BY id DESC LIMIT ?", (limite,)
        else:
            q, a = "SELECT * FROM ordens ORDER BY id DESC LIMIT ?", (limite,)
        return [dict(r) for r in c.execute(q, a)]


# ---------------------------------------------------------------- lista de acompanhamento e sinais
def lista_acompanhada() -> list:
    with conexao() as c:
        r = c.execute("SELECT valor FROM config WHERE chave='lista'").fetchone()
        try:
            return [t for t in json.loads(r["valor"]) if TICKER.match(t)] if r else []
        except (ValueError, TypeError):
            return []


def acompanhar(ticker: str, remover: bool = False) -> None:
    ticker = validar_ticker(ticker)
    lista = [t for t in lista_acompanhada() if t != ticker]
    if not remover:
        if len(lista) >= 30:
            raise ErroTrading("A lista acompanha até 30 ativos.")
        lista.append(ticker)
    with _lock, conexao() as c:
        _gravar(c, "lista", json.dumps(sorted(lista)))


def serie(ticker: str, minutos: int, passos: int = 12, agora: float = None) -> list:
    """Preços do ativo nos últimos `minutos`, em `passos` pontos (do mais antigo ao mais novo)."""
    ticker = validar_ticker(ticker)
    agora = time.time() if agora is None else agora
    with _lock, conexao() as c:
        fonte = ler_config(c)["fonte"]
        if fonte == "simulada":
            return [_preco_simulado(ticker, agora - minutos * 60 * (1 - i / (passos - 1))) for i in range(passos)]
        linhas = [r["preco"] for r in c.execute("SELECT preco FROM historico WHERE ticker=? AND ts>=? ORDER BY ts", (ticker, agora - minutos * 60))]
        return linhas


def sinal(ticker: str, agora: float = None) -> dict:
    """Descrição objetiva do movimento recente (média curta contra longa e variação). Não recomenda comprar nem vender."""
    ticker = validar_ticker(ticker)
    agora = time.time() if agora is None else agora
    preco, origem = cotacao(ticker, agora)
    s = serie(ticker, 60, 13, agora)
    if len(s) < 4:
        return {"ticker": ticker, "preco": preco, "texto": f"{ticker}: R$ {preco:,.2f}. Ainda há poucos registros para descrever a tendência.", "alerta": False}
    var = (s[-1] / s[0] - 1) * 100
    curta, longa = sum(s[-3:]) / 3, sum(s) / len(s)
    tend = "em alta" if curta > longa * 1.002 else "em queda" if curta < longa * 0.998 else "lateral"
    alerta = abs(var) >= 2.0
    txt = (f"{ticker}: R$ {preco:,.2f}, {var:+.2f}% na última hora, tendência {tend} (média dos últimos minutos "
           f"{'acima' if curta > longa else 'abaixo' if curta < longa else 'igual à'} da média da hora).")
    if alerta:
        txt += " Movimento forte: confira o limite de perda e as ordens abertas."
    return {"ticker": ticker, "preco": preco, "variacao": round(var, 2), "tendencia": tend, "texto": txt, "alerta": alerta, "origem": origem}


def alertas(agora: float = None) -> list:
    """Avisos objetivos: limite de perda, ordens abertas e movimentos fortes nos ativos da carteira e da lista."""
    agora = time.time() if agora is None else agora
    r = resumo(agora)
    out = []
    if r["bloqueado"]:
        out.append(f"O limite de perda do dia (R$ {r['limite_perda_dia']:,.2f}) foi atingido: novas compras estão bloqueadas.")
    elif r["limite_perda_dia"] and r["resultado_dia"] < 0 and -r["resultado_dia"] >= 0.7 * r["limite_perda_dia"]:
        out.append(f"A perda do dia (R$ {-r['resultado_dia']:,.2f}) passou de 70% do limite (R$ {r['limite_perda_dia']:,.2f}).")
    for t in sorted({p["ticker"] for p in r["posicoes"]} | set(lista_acompanhada())):
        try:
            s = sinal(t, agora)
        except ErroTrading:
            continue
        if s["alerta"]:
            out.append(s["texto"])
    return out
