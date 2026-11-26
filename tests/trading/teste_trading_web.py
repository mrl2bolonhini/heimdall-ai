#!/usr/bin/env python3
"""Testa o site do Heimdall Trading: login, CSRF, abas, ordens e rejeições, fechar posição, cancelar, lista, Ajustes (limites, fonte, preço manual, zerar), atalhos e Perguntar."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import os
import re
import sys
import tempfile
import threading
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="trading_"))
os.environ.update({"HEIMDALL_TRADING_FONTE": "simulada", "HEIMDALL_DB_DIR": str(TMP / "db"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
import heimdall_lab as hc  # noqa: E402
import heimdall_servico_web as web  # noqa: E402
import heimdall_trading as tr  # noqa: E402
import heimdall_trading_motor as m  # noqa: E402

hc.SENHA_HASH = hc.hash_senha("senha-de-teste-forte", iteracoes=100_000)
hc.TOTP_SEGREDO = "JBSWY3DPEHPK3PXP"
falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:300]})"))
    if not ok:
        falhas += 1


chamadas = []
web.perguntar.iniciar = lambda dono, rotulo, funcao, info="": chamadas.append((dono, info))
srv = ThreadingHTTPServer(("127.0.0.1", 0), web.criar_manipulador(tr.CFG, {"localhost"}))
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORTA = srv.server_address[1]


def req(metodo, rota, a=None, b=None, cookie="", host="localhost"):
    corpo = a if isinstance(a, dict) else None
    cookie = (a if isinstance(a, str) else b if isinstance(b, str) else cookie)
    c = http.client.HTTPConnection("127.0.0.1", PORTA, timeout=30)
    cab = {"Host": host}
    if cookie:
        cab["Cookie"] = f"{hc.COOKIE}={cookie}"
    dados = None
    if corpo is not None:
        dados, cab["Content-Type"] = urllib.parse.urlencode(corpo, doseq=True).encode(), "application/x-www-form-urlencoded"
    c.request(metodo, rota, body=dados, headers=cab)
    r = c.getresponse()
    return r.status, r.read().decode("utf-8", "replace"), r


confere("/saude", req("GET", "/saude")[:2] == (200, "ok"))
confere("host fora da lista: 421", req("GET", "/", host="evil.example")[0] == 421)
confere("sem sessão: entrada", req("GET", "/mesa")[0] == 303)
tk = hc.nova_sessao()[0]
confere("sessão de outro serviço não entra", req("GET", "/mesa", cookie=hc.nova_sessao("memory")[0])[0] == 303)
s, h, r = req("GET", "/mesa?t=ABCD3", tk)
csrf = re.search(r'data-csrf="([^"]+)"', h).group(1)
confere("mesa: design (h1 único, pular, abas, Ajustes, Perguntar, aviso de simulação)", s == 200 and h.count("<h1") == 1 and "Pular para o conteúdo" in h and 'aria-label="Principal"' in h
        and ">Ajustes<" in h and 'id="perguntar-t"' in h and "Simulação: nenhuma ordem é enviada" in h, h[:200])
confere("abas: Mesa, Carteira, Ordens, Análise", all(x in h for x in ("Mesa", "Carteira", "Ordens", "Análise")))
confere("campos com label e botões Comprar e Vender", all(f'for="{c}"' in h for c in ("ticker", "qtd", "tipo", "limite")) and ">Comprar<" in h and ">Vender<" in h)
confere("atalhos no script da Mesa", "KeyB" in h and "KeyQ" in h and "altKey" in h)
confere("atalhos só na Mesa", "KeyB" not in req("GET", "/carteira", cookie=tk)[1])
s, _, r = req("GET", "/", cookie=tk)
confere("raiz leva à Mesa", s == 303 and r.getheader("Location") == "/mesa")
m.definir_fonte("manual")
req("POST", "/ajustes/preco", {"csrf": csrf, "ticker": "ABCD3", "preco": "10,00"}, tk)
confere("preço manual informado", m.cotacao("ABCD3")[0] == 10.0)
s, _, r = req("POST", "/ordem", {"csrf": "errado", "ticker": "ABCD3", "lado": "C", "qtd": "10", "tipo": "mercado", "limite": ""}, tk)
confere("ordem sem CSRF: 403", s == 403)
s, _, r = req("POST", "/ordem", {"csrf": csrf, "ticker": "ABCD3", "lado": "C", "qtd": "100", "tipo": "mercado", "limite": ""}, tk)
confere("compra a mercado", s == 303 and r.getheader("Location") == "/mesa?t=ABCD3" and m.resumo()["posicoes"][0]["qtd"] == 100)
s, h, _ = req("GET", "/mesa?t=ABCD3", tk)
confere("aviso da ordem em role status", "role=\"status\"" in h and "executada" in h.lower(), h[-800:])
s, _, _ = req("POST", "/ordem", {"csrf": csrf, "ticker": "ABCD3", "lado": "C", "qtd": "5000", "tipo": "mercado", "limite": ""}, tk)
s, h, _ = req("GET", "/mesa?t=ABCD3", tk)
confere("rejeitada por limite: aviso de erro em role alert", 'role="alert"' in h and "limite" in h.lower(), h[-800:])
s, _, _ = req("POST", "/ordem", {"csrf": csrf, "ticker": "ABCD3", "lado": "V", "qtd": "10", "tipo": "limite", "limite": "20"}, tk)
s, h, _ = req("GET", "/ordens", tk)
confere("ordem aberta listada com Cancelar", "Cancelar" in h and "<caption>" in h and 'scope="col"' in h and "Limitada" in h)
oid = re.search(r'name="id" value="(\d+)"', h).group(1)
s, h, _ = req("GET", "/historico", tk)
confere("histórico mostra a rejeitada", "rejeitada" in h and "Compra" in h)
s, _, r = req("POST", "/cancelar", {"csrf": csrf, "id": oid}, tk)
confere("cancelar ordem", s == 303 and not m.listar_ordens("abertas"))
s, h, _ = req("GET", "/carteira", tk)
confere("carteira com tabela de posições", "<caption>Posições abertas</caption>" in h and "ABCD3" in h and "Fechar" in h and "Resumo da conta simulada" in h)
s, _, _ = req("POST", "/fechar", {"csrf": csrf, "ticker": "ABCD3"}, tk)
confere("fechar posição", s == 303 and not m.resumo()["posicoes"])
confere("fechar sem posição: 400", req("POST", "/fechar", {"csrf": csrf, "ticker": "ABCD3"}, tk)[0] == 400)
confere("código inválido: 400", req("POST", "/ordem", {"csrf": csrf, "ticker": "<x>", "lado": "C", "qtd": "1", "tipo": "mercado", "limite": ""}, tk)[0] == 400)
s, _, _ = req("POST", "/cancelar-todas", {"csrf": csrf, "ticker": ""}, tk)
confere("cancelar todas", s == 303)
s, _, _ = req("POST", "/lista/acompanhar", {"csrf": csrf, "ticker": "xyz3"}, tk)
s, h, _ = req("GET", "/lista", tk)
confere("lista acompanhada", "XYZ3" in h and "Remover" in h and 'for="novo"' in h)
req("POST", "/ajustes/preco", {"csrf": csrf, "ticker": "XYZ3", "preco": "5"}, tk)
s, h, _ = req("GET", "/analise", tk)
confere("análise sem recomendação", s == 200 and "XYZ3" in h and "compre" not in h.lower() and "venda agora" not in h.lower())
s, _, _ = req("POST", "/lista/remover", {"csrf": csrf, "ticker": "XYZ3"}, tk)
confere("remover da lista", not m.lista_acompanhada())
s, _, r = req("GET", "/ajustes", tk)
confere("/ajustes leva a Limites", s == 303 and r.getheader("Location") == "/ajustes/limites")
s, h, _ = req("GET", "/ajustes/limites", tk)
confere("Ajustes: sem abas de cima, subabas Limites, Cotações, Conta e Ajuda", s == 200 and 'aria-label="Principal"' not in h and all(x in h for x in ("Limites", "Cotações", "Conta", "Ajuda")) and 'for="lo"' in h)
confere("salvar limites", req("POST", "/ajustes/limites", {"csrf": csrf, "limite_ordem": "500", "limite_perda_dia": "100", "max_ordens": "5", "taxa_pct": "0,5"}, tk)[0] == 303 and m.ler_config()["limite_ordem"] == 500.0)
confere("limites inválidos: 400", req("POST", "/ajustes/limites", {"csrf": csrf, "limite_ordem": "x", "limite_perda_dia": "1", "max_ordens": "1", "taxa_pct": "0"}, tk)[0] == 400)
s, h, _ = req("GET", "/ajustes/cotacoes", tk)
confere("cotações: fonte atual e formulário de preço manual", "Fonte atual: Manual" in h and 'for="pp"' in h)
confere("trocar fonte", req("POST", "/ajustes/fonte", {"csrf": csrf, "fonte": "simulada"}, tk)[0] == 303 and m.ler_config()["fonte"] == "simulada")
confere("fonte inválida: 400", req("POST", "/ajustes/fonte", {"csrf": csrf, "fonte": "x"}, tk)[0] == 400)
confere("zerar sem confirmar: 400", req("POST", "/ajustes/zerar", {"csrf": csrf, "caixa": "50000"}, tk)[0] == 400)
confere("zerar confirmado", req("POST", "/ajustes/zerar", {"csrf": csrf, "caixa": "50000", "confirmar": "1"}, tk)[0] == 303 and m.resumo()["patrimonio"] == 50000.0)
confere("Ajuda do serviço", req("GET", "/ajustes/ajuda", cookie=tk)[0] == 200)
s, _, r = req("POST", "/perguntar", {"csrf": csrf, "pergunta": "como está a minha perda do dia?", "volta": "/carteira"}, tk)
confere("Perguntar aceita", s == 303 and r.getheader("Location") == "/carteira" and len(chamadas) == 1)
c = tr.contexto_perguntar(None)
confere("contexto do Perguntar: conta, limites e simulação", "Conta simulada" in c and "Limites:" in c and "R$ 50.000,00" in c)
confere("formato de dinheiro", tr.brl(1234.5) == "R$ 1.234,50" and tr.brl(-5) == "-R$ 5,00")
# convidado: conta simulada própria (regressão: antes o convidado enxergava a conta do dono)
tg = hc.nova_sessao("trading", "p0123456789ab")[0]
sg, hg, _ = req("GET", "/carteira", tg)
confere("convidado abre a própria carteira", sg == 200, sg)
confere("conta do convidado fica na pasta dele, e não na do dono", any((TMP / "db").rglob("p0123456789ab/trading.db")), list((TMP / "db").rglob("*.db")))
confere("rota inexistente: 404", req("GET", "/nada", cookie=tk)[0] == 404)
print("FALHAS:", falhas)
sys.exit(1 if falhas else 0)
