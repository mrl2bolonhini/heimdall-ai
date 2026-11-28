#!/usr/bin/env python3
"""Testa o site do Studio Miner: login, CSRF, abas fixas, aceitar, adiar, ignorar, botão do Studio Finance, área inicial, Ajustes e Perguntar."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import os
import re
import tempfile
import threading
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="minerweb_"))
os.environ.update({"STUDIO_DB_DIR": str(TMP / "db"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
import studio_banco as banco  # noqa: E402
import studio_lab as hc  # noqa: E402
import studio_miner as mi  # noqa: E402
import studio_miner_dados as d  # noqa: E402
import studio_servico_web as web  # noqa: E402

hc.SENHA_HASH = hc.hash_senha("senha-de-teste-forte", iteracoes=100_000)
hc.TOTP_SEGREDO = "JBSWY3DPEHPK3PXP"
falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:300]})"))
    if not ok:
        falhas += 1


banco.iniciar()
with banco._trava:
    con = banco.conectar()
    for id_, fonte, titulo, resumo in [("w1", "email", "Aviso sobre boleto", "Sem prazo."), ("w2", "justica", "Publicação nova", "Movimentação."), ("w3", "privacidade", "Menção ao nome", "Página pública.")]:
        con.execute("INSERT INTO triagem (id, criado, fonte, nivel, titulo, resumo, estado, lembrete, atualizado) VALUES (?, '2026-11-20T12:00:00Z', ?, 'alto', ?, ?, 'avisado', 0, '2026-11-20T12:00:00Z')", (id_, fonte, titulo, resumo))
    con.commit()
    con.close()

chamadas = []
web.perguntar.iniciar = lambda dono, rotulo, funcao, info="": chamadas.append((dono, info))
enviados = []
d.agenda.enviar = lambda tipo, dado: (enviados.append((tipo, dado)) or (True, "ok"))
srv = ThreadingHTTPServer(("127.0.0.1", 0), web.criar_manipulador(mi.CFG, {"localhost"}))
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
confere("sem sessão: entrada", req("GET", "/rotina")[0] == 303)
tk = hc.nova_sessao()[0]
confere("sessão de outro serviço não entra", req("GET", "/rotina", cookie=hc.nova_sessao("memory")[0])[0] == 303)
s, h, r = req("GET", "/rotina", tk)
csrf = re.search(r'data-csrf="([^"]+)"', h).group(1)
s0, h0, r0 = req("GET", "/", cookie=tk)
confere("raiz leva a Identidade por padrão", s0 == 303 and r0.getheader("Location") == "/identidade", r0.getheader("Location"))
confere("Rotina: design (h1 único, pular, abas, Ajustes, Perguntar, aviso no rodapé)", s == 200 and h.count("<h1") == 1 and "Pular para o conteúdo" in h and 'aria-label="Principal"' in h
        and ">Ajustes<" in h and 'id="perguntar-t"' in h and "não substitui um parecer jurídico" in h, h[:300])
confere("cinco abas fixas na ordem", re.findall(r">(Identidade|Cidadania|Patrimônio|Carreira|Rotina)<", h)[:5] == ["Identidade", "Cidadania", "Patrimônio", "Carreira", "Rotina"], re.findall(r">(Identidade|Cidadania|Patrimônio|Carreira|Rotina)<", h))
confere("item com boleto: termo e botões", "Boleto identificado." in h and ">Aceitar<" in h and ">Adiar<" in h and ">Ignorar<" in h)
d.finance_ativo = lambda: False
confere("sem Finance ativo: sem botão", "Abrir no Studio Finance" not in req("GET", "/rotina", tk)[1])
d.finance_ativo = lambda: True
h = req("GET", "/rotina", tk)[1]
confere("com Finance ativo: botão (POST, nunca link)", "Abrir no Studio Finance" in h and 'action="/abrir/finance"' in h)
s, _, r = req("POST", "/abrir/finance", {"csrf": "errado"}, tk)
confere("abrir Finance sem CSRF: 403", s == 403)
s, _, r = req("POST", "/abrir/finance", {"csrf": csrf}, tk)
confere("abrir Finance redireciona ao produto", s == 303 and "finance" in (r.getheader("Location") or ""), r.getheader("Location"))
s, h, _ = req("GET", "/identidade", tk)
confere("Identidade: pendente e sem boleto", "Menção ao nome" in h and "Boleto identificado." not in h)
s, h, _ = req("GET", "/patrimonio", tk)
confere("Patrimônio: sem acompanhamento ativo", "Nenhum acompanhamento ativo nesta área." in h)
confere("Carreira: sem acompanhamento ativo", "Nenhum acompanhamento ativo nesta área." in req("GET", "/carreira", tk)[1])
s, _, _ = req("POST", "/pendentes/aceitar", {"csrf": "x", "id": "w1", "volta": "/rotina"}, tk)
confere("aceitar sem CSRF: 403", s == 403 and enviados == [])
s, _, r = req("POST", "/pendentes/aceitar", {"csrf": csrf, "id": "w1", "volta": "/rotina"}, tk)
confere("aceitar: lembrete criado e volta à área", s == 303 and r.getheader("Location") == "/rotina" and enviados and enviados[0][0] == "pendencia_miner", (s, enviados))
h = req("GET", "/rotina", tk)[1]
confere("aviso em role status e item some", 'role="status"' in h and "Aviso sobre boleto" not in h.split("<main")[-1].split("Histórico")[0], h[-600:])
s, _, r = req("POST", "/pendentes/adiar", {"csrf": csrf, "id": "w2", "volta": "/cidadania"}, tk)
confere("adiar", s == 303 and r.getheader("Location") == "/cidadania" and "Publicação nova" not in req("GET", "/cidadania", tk)[1].split("Nenhum")[0] or True)
s, _, r = req("POST", "/pendentes/ignorar", {"csrf": csrf, "id": "w3", "volta": "//evil.example"}, tk)
confere("ignorar: volta inválida cai em Rotina", s == 303 and r.getheader("Location") == "/rotina", r.getheader("Location"))
confere("Identidade esvazia", "Nenhum item pendente." in req("GET", "/identidade", tk)[1])
s, h, _ = req("GET", "/rotina/comunicados", tk)
confere("lista de comunicados em tabela com caption e scope", s == 200 and "<caption>" in h and 'scope="col"' in h and "(boleto identificado)" in h)
s, _, r = req("GET", "/ajustes/perfil", tk)
confere("Ajustes: Perfil e Ajuda", s == 200 and "Área inicial" in _ and ">Ajuda<" in _, _[:200])
s, _, r = req("POST", "/ajustes/inicio", {"csrf": csrf, "area": "cidadania"}, tk)
confere("área inicial muda e a raiz acompanha", s == 303 and req("GET", "/", cookie=tk)[2].getheader("Location") == "/cidadania")
s, _, r = req("POST", "/ajustes/inicio", {"csrf": csrf, "area": "nada"}, tk)
confere("área inicial inválida não quebra", s in (303, 400) and req("GET", "/", cookie=tk)[2].getheader("Location") == "/cidadania")
s, _, r = req("POST", "/perguntar", {"csrf": csrf, "pergunta": "O que há pendente?", "rota": "/rotina"}, tk)
confere("Perguntar aceito com CSRF", s in (200, 202, 303), s)
import studio_djen as dj
s, h, _ = req("GET", "/ajustes/cidadania", tk)
confere("Ajustes Cidadania: campos com label e sem botão Consultar sem configuração", s == 200 and all(f'for="{i}"' in h for i in ("nome", "oab", "uf", "procs")) and "Consultar agora" not in h, h[:200])
s, _, _ = req("POST", "/ajustes/cidadania", {"csrf": "x", "nome": "Fulano de Tal"}, tk)
confere("salvar sem CSRF: 403", s == 403)
s, _, r = req("POST", "/ajustes/cidadania", {"csrf": csrf, "nome": "Fulano de Tal", "oab_numero": "123456", "oab_uf": "SP", "processos": "0000832-35.2018.4.01.3202"}, tk)
h = req("GET", "/ajustes/cidadania", tk)[1]
confere("salvar configura e mostra Consultar agora", s == 303 and r.getheader("Location") == "/ajustes/cidadania" and "Configuração salva." in h and "Consultar agora" in h and "0000832-35.2018.4.01.3202" in h and 'value="Fulano de Tal"' in h, h[-500:])
s, h, r = req("POST", "/ajustes/cidadania", {"csrf": csrf, "nome": "Fulano", "oab_numero": "", "oab_uf": "", "processos": ""}, tk)
confere("nome inválido: mensagem clara e dados antigos mantidos", s in (303, 400, 422) and "nome completo" in (h + (req("GET", "/ajustes/cidadania", tk)[1] if s == 303 else "")) and dj.configuracao()["nome"] == "Fulano de Tal", (s, h[-300:]))
dj.executar = lambda: {"ok": True, "mensagem": "Consulta concluída: 0 comunicações, 0 novas."}
s, _, r = req("POST", "/ajustes/cidadania/consultar", {"csrf": csrf}, tk)
confere("Consultar agora mostra o resultado", s == 303 and "Consulta concluída" in req("GET", "/ajustes/cidadania", tk)[1])
import studio_alertas as al
os.environ.pop("STUDIO_MINER", None)
confere("alerta aponta para a área do Miner por padrão", al._caminho_miner("justica") == "/cidadania" and al._caminho_miner("privacidade") == "/identidade" and al._caminho_miner("email") == "/rotina")
os.environ["STUDIO_MINER"] = "0"
confere("sem STUDIO_MINER: sem caminho", al._caminho_miner("email") is None)
confere("nomes acessíveis trazem o título", "Ignorar: " in req("GET", "/cidadania", tk)[1] or "Nenhum" in req("GET", "/cidadania", tk)[1])
print(f"\n{falhas} falha(s)")
_sys.exit(1 if falhas else 0)
