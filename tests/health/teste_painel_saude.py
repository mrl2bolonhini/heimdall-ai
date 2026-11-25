#!/usr/bin/env python3
"""Testa o painel de saúde: login, páginas, somente leitura, host permitido, escape de HTML e estado dos dados."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import random
import sqlite3
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="painel_saude_"))
os.environ.update({"HEIMDALL_DB_DIR": str(TMP / "banco"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
sys.path.insert(0, str(RAIZ))
import heimdall_banco as banco  # noqa: E402
import heimdall_lab as hc  # noqa: E402
import heimdall_painel_saude as ps  # noqa: E402
import heimdall_saude as hs  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:600])


SENHA, SEGREDO = "senha-de-teste-forte", "JBSWY3DPEHPK3PXP"
hc.SENHA_HASH = hc.hash_senha(SENHA, iteracoes=100_000)
hc.TOTP_SEGREDO = SEGREDO

hs._garantir_banco()
con = sqlite3.connect(banco.DB_PATH)
random.seed(3)
agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
for i in range(120):
    d = (datetime.now() - timedelta(days=i + 1)).strftime("%Y-%m-%d")   # o dado mais novo é de ontem
    s = random.gauss(400, 50)
    for m, v in (("sono_total", s), ("hrv", 30 + (s - 400) * .05 + random.gauss(0, 3)), ("fc_repouso", 64 + random.gauss(0, 2)), ("passos", max(500, random.gauss(6500, 2000))),
                 ("x:apple_exercise_time", max(0, random.gauss(25, 10)))):
        con.execute("INSERT OR REPLACE INTO saude_diaria (dia, metrica, valor, unidade, atualizado) VALUES (?,?,?,?,?)", (d, m, v, "", agora))
con.commit()
con.close()

srv = ThreadingHTTPServer(("127.0.0.1", 0), ps.Painel)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORTA = srv.server_address[1]
BASE = f"http://127.0.0.1:{PORTA}"


class Sem303(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


abre = urllib.request.build_opener(Sem303).open


def pedir(caminho, cookie="", host=None, dados=None, ua=None):
    cab = {}
    if ua:
        cab["User-Agent"] = ua
    if cookie:
        cab["Cookie"] = cookie
    if host:
        cab["Host"] = host
    req = urllib.request.Request(BASE + caminho, data=dados, headers=cab)
    try:
        with abre(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8"), dict(r.headers)
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode("utf-8", "replace"), dict(ex.headers)


st, _, cab = pedir("/")
confere("sem login vai para /entrar", st == 303 and cab.get("Location") == "/entrar", (st, cab))
st, _, _ = pedir("/", host="outro.exemplo.test")
confere("host fora da lista é recusado", st == 421, st)
st, corpo, _ = pedir("/saude")
confere("/saude responde ok sem login", st == 200 and corpo == "ok", (st, corpo))
st, corpo, _ = pedir("/entrar", dados=urllib.parse.urlencode({"senha": "errada", "codigo": "000000"}).encode())
confere("login errado é recusado", st == 401 and "incorretos" in corpo, (st, corpo[:200]))

token, sess = hc.nova_sessao()
ck = f"{ps.COOKIE}={token}"
import heimdall_clinico as _cl
import urllib.parse as _up


def postar(rota, campos, cookie=ck, csrf=None):
    campos = dict(campos, csrf=sess["csrf"] if csrf is None else csrf)
    return pedir(rota, cookie, dados=_up.urlencode(campos).encode())


st, _, cab = pedir("/", ck)
confere("primeiro acesso: a visão geral leva ao Perfil de saúde", st == 303 and cab.get("Location") == "/perfil", (st, cab))
st, corpo, _ = pedir("/perfil", ck)
confere("página Perfil: convite, formulário com rótulos, botões de concluir e de preencher depois",
        st == 200 and "primeiro acesso" in corpo and 'for="texto-perfil"' in corpo and 'for="tipo-perfil"' in corpo and "Preencher depois" in corpo and "Não tenho nada a informar" in corpo
        and "Pular para o conteúdo" in corpo and corpo.count("<h1>") == 1, corpo[:400])
st, _, cab = postar("/perfil/adicionar", {"tipo": "condicao", "texto": "hipoglicemia", "desde": "2020"}, csrf="errado")
confere("perfil: gravar com token errado é recusado", st == 403 and not _cl.perfil_listar(), st)
st, _, cab = postar("/perfil/adicionar", {"tipo": "condicao", "texto": "hipoglicemia", "desde": "2020"})
confere("perfil: adicionar grava e volta ao Perfil", st == 303 and cab.get("Location") == "/perfil" and len(_cl.perfil_listar()) == 1, (st, cab))
st, corpo, _ = pedir("/perfil", ck)
confere("perfil: item na tabela e aviso de confirmação uma vez", "hipoglicemia" in corpo and 'role="status"' in corpo and "Adicionado ao perfil" in corpo and "Adicionado ao perfil" not in pedir("/perfil", ck)[1], corpo[:300])
st, _, cab = postar("/perfil/adicionar", {"tipo": "humor", "texto": "x"})
st, corpo, _ = pedir("/perfil", ck)
confere("perfil: erro de validação vira aviso (alert), não página de erro", st == 200 and 'role="alert"' in corpo and "Tipo inválido" in corpo, corpo[:300])
st, _, cab = pedir("/", ck)
confere("com itens no perfil a visão geral abre normalmente", st == 200, st)
st, _, cab = postar("/perfil/remover", {"id": str(_cl.perfil_listar()[0]["id"])})
confere("perfil: remover", st == 303 and not _cl.perfil_listar(), st)
st, _, cab = postar("/perfil/adiar", {})
st, _, _ = pedir("/", ck)
confere("preencher depois: a visão geral abre por alguns dias", st == 200, st)
_cl.perfil_concluir()
st, _, _ = pedir("/", ck)
confere("concluído: a visão geral abre", st == 200, st)
st, corpo, _ = pedir("/sugestoes", ck)
confere("página Sugestões abre e explica evento e lembrete", st == 200 and "evento no Calendário" in corpo and "lembrete" in corpo and "Procurar novas sugestões" in corpo, corpo[:300])
ex_ = _cl.ex
ex_._escrever(lambda con: con.execute("INSERT INTO sugestoes_saude (chave, tipo, titulo, motivo, quando, compromisso, acao) VALUES ('pontos|1','consulta','Retirada de pontos em 02/12/2099','m','2099-11-29','2099-12-02','retirada de pontos')"))
ex_._escrever(lambda con: con.execute("INSERT INTO sugestoes_saude (chave, tipo, titulo, motivo, quando) VALUES ('p|1','pergunta','Como está a fisioterapia','m','2099-01-01')"))
st, corpo, _ = pedir("/sugestoes", ck)
confere("sugestão com data fixa diz que vira evento; campos de data e hora têm rótulo; pergunta tem resposta",
        "cria um evento no Calendário" in corpo and 'for="data-1"' in corpo and 'for="hora-1"' in corpo and "Guardar resposta" in corpo and 'aria-label="Recusar: Retirada de pontos' in corpo, corpo[:600])
import heimdall_agenda as _ag
_enviados = []
_ag.AGENTE = "http://127.0.0.1:1"
_orig = _ag.enviar
_ag.enviar = lambda tipo, dado, post=None: (_enviados.append((tipo, dado)) or (True, "ok"))
st, _, cab = postar("/sugestoes/acao", {"id": "1", "acao": "aceitar", "data": "", "hora": ""})
confere("aceitar pelo painel cria evento (tipo de agenda de evento) com a data do documento", st == 303 and _enviados and _enviados[0][0] == "sugestao_saude_evento" and _enviados[0][1]["data"] == "2099-12-02", _enviados)
st, corpo, _ = pedir("/sugestoes", ck)
confere("aviso diz que criou o evento", "Evento criado no Calendário para 02/12/2099" in corpo, corpo[:300])
st, _, cab = postar("/sugestoes/acao", {"id": "2", "acao": "responder", "texto": "Fiz 8 sessões."})
confere("responder pelo painel", st == 303 and "Fiz 8 sessões" in _cl.relatorio_sugestoes(todas=True), st)
_ag.enviar = _orig
st, _, cab = postar("/sugestoes/acao", {"id": "999", "acao": "recusar"})
st, corpo, _ = pedir("/sugestoes", ck)
confere("sugestão inexistente vira aviso", 'role="alert"' in corpo, corpo[:200])

# cada pessoa no seu banco: sessão de convidado (escopo saude) lê e grava só no banco dela
_tk, _ss = hc.nova_sessao("saude", "p0123456789ab")
_ck2 = f"{ps.COOKIE}={_tk}"
st, _, cab = pedir("/", _ck2)
confere("convidado: primeiro acesso dele (banco novo) também leva ao Perfil", st == 303 and cab.get("Location") == "/perfil", (st, cab))
_cp = dict(csrf=_ss["csrf"], tipo="alergia", texto="dipirona")
st, _, _ = pedir("/perfil/adicionar", _ck2, dados=_up.urlencode(_cp).encode())
confere("convidado: o perfil dele vai para db/people/<id>/ e não aparece no do dono",
        st == 303 and not [r for r in _cl.perfil_listar() if r["texto"] == "dipirona"] and "dipirona" in pedir("/perfil", _ck2)[1]
        and (ps.banco.pasta_da_pessoa("p0123456789ab") / "heimdall.db").exists(), st)
_cp = dict(csrf=_ss["csrf"], id="1", acao="aceitar")
st, _, _ = pedir("/sugestoes/acao", _ck2, dados=_up.urlencode(_cp).encode())
confere("convidado: não cria evento nem lembrete no Mac do dono", not _enviados[1:], _enviados)
for rota, esperado in (("/", "Como você está agora"), ("/hoje", "Hoje"), ("/semana", "Saúde: semana de"), ("/sono", "noites com dado"), ("/atividade", "Passos"), ("/recuperacao", "Recuperação"), ("/anomalias", "Anomalias"),
                       ("/coracao", "Frequência"), ("/treinos", "Treinos"), ("/eventos", "Sintomas"), ("/diario", "Valores por dia"), ("/dados", "Último dia com dado")):
    st, corpo, cab = pedir(rota, ck)
    confere(f"página {rota}", st == 200 and esperado in corpo and "Pular para o conteúdo" in corpo, (st, corpo[:300]))
st, corpo, cab = pedir("/", ck)
confere("cabeçalhos de segurança e sem cache", "frame-ancestors 'none'" in cab.get("Content-Security-Policy", "") and cab.get("Cache-Control") == "no-store", cab)
confere("datas no padrão brasileiro, sem AAAA-MM-DD", not __import__("re").search(r"\d{4}-\d\d-\d\d", pedir("/diario", ck)[1]), "")
st, corpo, _ = pedir("/diario?dias=7", ck)
confere("período selecionável e tabela com cabeçalhos", "7 dias (selecionado)" in corpo and 'scope="row"' in corpo and 'scope="col"' in corpo, corpo[:400])
st, corpo, _ = pedir("/sono?dias=999%3Cscript%3E", ck)
confere("período inválido volta ao padrão sem quebrar nem refletir", st == 200 and "<script>alert" not in corpo, st)
st, corpo, _ = pedir("/dados", ck)
confere("estado dos dados mostra em dia", "em dia" in corpo and "passos" not in corpo.lower().split("<table")[0], corpo[:500])
st, corpo, _ = pedir("/nao-existe", ck)
confere("página inexistente dá 404", st == 404, st)
st, corpo, _ = pedir("/semana", ck, dados=b"x=1")
confere("POST fora das rotas de gravação é recusado", st == 405, st)
import heimdall_avisos as _av
import heimdall_perguntar as _hp
import time as _tm
st, corpo, cab = pedir("/sono", ck)
import re as _re
_n = _re.search(r"script-src 'nonce-([A-Za-z0-9_-]+)'", cab.get("Content-Security-Policy", ""))
confere("abas no lugar do menu, atalho Option+Shift+número, voltar ao topo e script só com nonce", 'role="tablist"' in corpo and "Atalho: Option Shift 1 a" in corpo and 'aria-selected="true"' in corpo
        and 'id="topo"' in corpo and 'href="#topo"' in corpo and _n and f'<script nonce="{_n.group(1)}">' in corpo and "<nav aria-label=\"Principal\"><ul>" not in corpo, corpo[:200])
confere("campo Perguntar nas telas de dados e não na aba Avisos", 'id="perguntar-t"' in corpo and 'id="perguntar-t"' not in pedir("/avisos", ck)[1])
_hp.chamar_local = lambda sistema, usuario, modelo="", max_tokens=700, timeout=240: "Seu sono ficou estável."
st, _, _ = pedir("/perguntar", ck, dados=b"pergunta=como+foi+meu+sono&volta=%2Fsono&csrf=errado")
confere("Perguntar com CSRF errado é recusado", st == 403, st)
st, _, cab = pedir("/perguntar", ck, dados=("pergunta=como+foi+meu+sono&volta=%2Fsono&csrf=" + sess["csrf"]).encode())
confere("Perguntar volta para a mesma aba", st == 303 and cab.get("Location") == "/sono", (st, cab))
for _ in range(60):
    corpo = pedir("/sono", ck)[1]
    if "Seu sono ficou estável." in corpo:
        break
    _tm.sleep(0.1)
confere("a resposta do modelo local aparece no fim da aba, com a pergunta", "Seu sono ficou estável." in corpo and "como foi meu sono" in corpo, corpo[-400:])
st, _, cab = pedir("/perguntar", ck, dados=("pergunta=x&volta=https%3A%2F%2Foutro.com&csrf=" + sess["csrf"]).encode())
confere("volta para fora do painel cai no início", cab.get("Location") == "/", cab)
_av.do_servico("saude").gravar("Relatório da semana de teste", "- sono bom\n<b>x</b>")
st, corpo, _ = pedir("/avisos", ck)
confere("aba Avisos lista o relatório, sem HTML do texto, com botão de marcar", st == 200 and "Relatório da semana de teste" in corpo and "&lt;b&gt;" in corpo and "Marcar como lido" in corpo and 'aria-current="page"' in corpo, corpo[:300])
st, _, _ = pedir("/avisos/lido", ck, dados=b"id=todos&csrf=errado")
confere("marcar como lido sem CSRF é recusado", st == 403, st)
st, _, cab = pedir("/avisos/lido", ck, dados=("id=todos&csrf=" + sess["csrf"]).encode())
confere("marcar todos como lidos", st == 303 and _av.do_servico("saude").nao_lidos() == 0, (st, cab))
st, corpo, _ = pedir("/sair", ck, dados=b"csrf=errado")
confere("sair sem token CSRF é recusado", st == 403, st)
st, corpo, cab = pedir("/sair", ck, dados=("csrf=" + sess["csrf"]).encode())
confere("sair encerra a sessão", st == 303 and "Max-Age=0" in cab.get("Set-Cookie", "") and pedir("/", ck)[0] == 303, (st, cab))

# botão "Atualizar dados agora": só no iPhone, aponta para o atalho e volta para /dados
import time as _t
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"
token, _ = hc.nova_sessao()
ck2 = f"{ps.COOKIE}={token}"
st, corpo, _ = pedir("/", ck2, ua=IPHONE)
confere("iPhone vê o botão com o atalho e o retorno para /dados", "shortcuts://x-callback-url/run-shortcut?name=Exportar%20dados%20de%20sa%C3%BAde" in corpo
        and "Atualizar dados agora" in corpo and "x-success=http%3A%2F%2F127.0.0.1%3A" in corpo, corpo[:600])
st, corpo, _ = pedir("/", ck2)
confere("fora do iPhone não há botão, só o aviso", "shortcuts://" not in corpo and "abra este painel no iPhone" in corpo, corpo[:300])
st, corpo, _ = pedir("/?_iphone=1&_base=http://malicioso.test", ck2)
confere("parâmetros internos não podem ser forjados pela consulta", "shortcuts://" not in corpo and "malicioso" not in corpo, corpo[:300])
st, corpo, _ = pedir("/", ck2, ua=IPHONE, host="localhost:9<x>")
confere("Host estranho não vira HTML nem endereço de retorno", st in (200, 421) and "<x>" not in corpo, (st, corpo[:200]))
st, corpo, _ = pedir(f"/dados?atualizado={int(_t.time()) - 3600}", ck2)
confere("pedido antigo com gravação mais nova: dados atualizados, sem recarga", "Dados atualizados" in corpo and 'http-equiv="refresh"' not in corpo, corpo[:400])
st, corpo, _ = pedir(f"/dados?atualizado={int(_t.time()) + 30}", ck2)
confere("aguardando: recarga única e link para conferir", "Aguardando os dados" in corpo and 'content="20;url=/dados?atualizado=' in corpo and "v=1" in corpo and "Conferir de novo" in corpo, corpo[:500])
st, corpo, _ = pedir(f"/dados?atualizado={int(_t.time()) + 30}&v=1", ck2)
confere("depois da recarga não recarrega mais", "Aguardando os dados" in corpo and 'http-equiv="refresh"' not in corpo, corpo[:300])
st, corpo, _ = pedir("/dados?atualizado=abc%3Cscript%3E", ck2)
confere("valor inválido de atualizado é ignorado", st == 200 and "<script>" not in corpo and "Aguardando" not in corpo and "Dados atualizados" not in corpo, corpo[:200])
con = sqlite3.connect(banco.DB_PATH)
con.execute("UPDATE saude_diaria SET atualizado = '2020-01-01T00:00:00-03:00'")
con.commit()
con.close()
st, corpo, _ = pedir(f"/dados?atualizado={int(_t.time()) - 300}", ck2)
confere("passou o prazo sem gravação nova: alerta", "nenhum dado novo foi gravado" in corpo and 'role="alert"' in corpo and 'http-equiv="refresh"' not in corpo, corpo[:500])

# estado atrasado: dado mais antigo que 2 dias aparece como alerta
con = sqlite3.connect(banco.DB_PATH)
con.execute("DELETE FROM saude_diaria WHERE metrica = 'passos' AND dia >= ?", ((datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d"),))
con.commit()
con.close()
token, _ = hc.nova_sessao()
st, corpo, _ = pedir("/dados", f"{ps.COOKIE}={token}")
confere("dado parado há dias vira alerta", "dias sem dado novo" in corpo and "Sem dado novo há mais de 2 dias" in corpo and "Passos" in corpo, corpo[:600])

# escape de HTML vindo dos dados
confere("texto das análises é escapado", "&lt;" in ps.texto_html("<img src=x onerror=alert(1)>") and "<img" not in ps.texto_html("<img src=x>"), ps.texto_html("<img>"))
print("Tudo certo." if not falhas else f"{falhas} falha(s).")
sys.exit(1 if falhas else 0)
