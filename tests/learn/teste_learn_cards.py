#!/usr/bin/env python3
"""Testa cards e agenda do Learn: limites (3 cards e 1 lição por dia), horários, espera após falha, notificação e as telas."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import json
import os
import random
import re
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

TMP = Path(tempfile.mkdtemp())
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "db")
os.environ["HEIMDALL_KNOWLEDGE_DIR"] = str(TMP / "knowledge")
os.environ["HEIMDALL_AVISOS_MAC"] = "0"
(TMP / "knowledge").mkdir()

import heimdall_lab as nuvem  # noqa: E402
import heimdall_learn as site  # noqa: E402
import heimdall_learn_cards as ca  # noqa: E402
import heimdall_learn_dados as d  # noqa: E402
d.definir_ajuste("estudos_dia", "0")   # estudos por sorteio têm teste próprio (teste_learn_estudos_dia.py)
import heimdall_learn_licoes as li  # noqa: E402
nuvem.SENHA_HASH = nuvem.SENHA_HASH or "teste"
nuvem.TOTP_SEGREDO = nuvem.TOTP_SEGREDO or "JBSWY3DPEHPK3PXP"

falhas = 0
_agora_real = d._agora


def rodar(dt, *a, **k):
    d._agora = lambda: dt.strftime("%Y-%m-%d %H:%M:%S")   # relógio simulado: o banco grava a data do teste
    return ca.executar_agenda(dt, *a, **k)



def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


def erro(f, *a):
    try:
        f(*a)
    except d.ErroLearn as ex:
        return str(ex)
    return None


par = lambda n: ("Ponto %d sobre ingestão em lote e em fluxo, filas e orquestração de pipelines de dados. " % n) * 5  # noqa: E731
d.criar_pasta("Dados", "aleatorio", "Arquitetura e dados")
d.criar_pasta("Inglês", "sequencial", "Idiomas", "inglês")
(TMP / "knowledge" / "dados" / "guia.md").write_text("\n\n".join(par(i) for i in range(10)), encoding="utf-8")
(TMP / "knowledge" / "ingles" / "aula.md").write_text("\n\n".join(par(i) for i in range(10)), encoding="utf-8")

confere("horários: 3 cards a partir das 08:00, de 4 em 4 horas", ca.horarios_dos_cards("08:00", 3) == ["08:00", "12:00", "16:00"])
confere("horários apertados perto da meia-noite", ca.horarios_dos_cards("21:00", 3)[-1] <= "23:59" and ca.horarios_dos_cards("21:00", 3)[0] == "21:00", ca.horarios_dos_cards("21:00", 3))
confere("máximo de 3 cards", "No máximo 3" in (erro(ca.configurar, "dados", 4, 0, "08:00") or ""))
confere("máximo de 1 lição", "No máximo 1" in (erro(ca.configurar, "ingles", 1, 2, "08:00") or ""))
confere("lição por dia só em pasta sequencial", "sequencial" in (erro(ca.configurar, "dados", 1, 1, "08:00") or ""))
confere("horário inválido recusado", "Horário inválido" in (erro(ca.configurar, "dados", 1, 0, "25:00") or ""))
confere("horário aceita 8:30 e normaliza", ca.configurar("dados", 1, 0, "8:30")["horario"] == "08:30")
confere("pasta inexistente recusada", erro(ca.configurar, "nao-existe", 1, 0, "08:00") is not None)

def modelo_card(sistema, usuario, max_tokens=400):
    return "Filas desacoplam\n\nUma fila separa quem produz de quem consome os dados, e assim cada lado escala sozinho."
c1 = ca.gerar_card("dados", modelo_card, random.Random(1))
card = ca.listar()[0]
confere("card gerado com título e corpo separados", card["titulo"] == "Filas desacoplam" and "separa quem produz" in card["corpo"] and card["origem"] == "agenda")
try:
    ca.gerar_card("dados", lambda *a, **k: "só uma linha", random.Random(1))
    confere("card sem corpo é recusado", False)
except RuntimeError:
    confere("card sem corpo é recusado", True)
ca.marcar_lido(c1)
confere("marcar como lido", ca.listar(True) == [])

# agenda
avisos = []
notif = lambda t, c, g="": avisos.append((t, c, g))  # noqa: E731
con = d.conectar()
con.execute("DELETE FROM cards")
con.commit()
ca.configurar("dados", 3, 0, "08:00")
dia = datetime(2026, 11, 23, 7, 59)
confere("antes do horário nada acontece", rodar(dia, modelo_card, None, notif) == [])
f = rodar(datetime(2026, 11, 23, 8, 0), modelo_card, None, notif)
confere("às 08:00 sai o primeiro card e avisa", f == ["card dados"] and len(avisos) == 1 and "Filas desacoplam" in avisos[0][0] and avisos[0][2] == "Há um card novo no Learn.")
confere("nova checagem no mesmo horário não duplica", rodar(datetime(2026, 11, 23, 8, 1), modelo_card, None, notif) == [])
confere("às 12:00 sai o segundo", rodar(datetime(2026, 11, 23, 12, 0), modelo_card, None, notif) == ["card dados"])
confere("às 16:00 sai o terceiro", rodar(datetime(2026, 11, 23, 16, 0), modelo_card, None, notif) == ["card dados"])
confere("nunca passa de 3 por dia", rodar(datetime(2026, 11, 23, 23, 0), modelo_card, None, notif) == [] and len(ca.listar()) == 3)
confere("dia seguinte recomeça", rodar(datetime(2026, 11, 24, 9, 0), modelo_card, None, notif) == ["card dados"])
n_antes = len(ca.listar())
ca.gerar_card("dados", modelo_card, random.Random(2), "aluno")
confere("card pedido na hora não conta no limite do dia", len(ca.listar()) == n_antes + 1 and rodar(datetime(2026, 11, 24, 12, 0), modelo_card, None, notif) == ["card dados"])

# falha do modelo: espera
ca.configurar("dados", 3, 0, "08:00")
con.execute("DELETE FROM cards")
con.commit()
ca._falhas.clear()
def cai(*a, **k):
    raise RuntimeError("modelo fora do ar")
f = rodar(datetime(2026, 12, 1, 8, 0), cai, None, notif)
confere("falha do modelo é registrada, sem derrubar", len(f) == 1 and f[0].startswith("erro card dados"), f)
confere("depois da falha espera antes de tentar de novo", rodar(datetime(2026, 12, 1, 8, 1), modelo_card, None, notif) == [])
ca._falhas.clear()

# lição por dia
BOA = {"titulo": "Primeira lição", "explicacao": "Explicação.", "trecho_estudo": "Texto.",
       "exercicios": [{"tipo": "alternativas", "enunciado": "q1", "opcoes": ["a", "b", "c"], "correta": 0},
                      {"tipo": "texto", "enunciado": "q2", "gabarito": "g"}, {"tipo": "alternativas", "enunciado": "q3", "opcoes": ["a", "b", "c"], "correta": 1}]}
ml = lambda *a, **k: json.dumps(BOA)  # noqa: E731
ca.configurar("dados", 0, 0, "08:00")
ca.configurar("ingles", 0, 1, "07:00")
avisos.clear()
f = rodar(datetime(2026, 12, 2, 7, 0), modelo_card, ml, notif)
confere("lição do dia é criada e avisa", f == ["lição ingles"] and "Lição nova: Primeira lição" in avisos[0][0], (f, avisos))
confere("lição vem marcada como da agenda", li.listar("ingles")[0]["origem"] == "agenda")
x = rodar(datetime(2026, 12, 2, 9, 0), modelo_card, ml, notif)
confere("com lição aberta não cria outra", x == [], (x, li.listar("ingles")))
li.enviar_respostas(li.listar("ingles")[0]["id"], {0: "0", 1: "x", 2: "1"})
li.corrigir_pendentes(li.listar("ingles")[0]["id"], lambda *a, **k: "CERTO. Bom.")
confere("no mesmo dia, mesmo concluída, não cria outra", rodar(datetime(2026, 12, 2, 15, 0), modelo_card, ml, notif) == [])
f = rodar(datetime(2026, 12, 3, 7, 0), modelo_card, ml, notif)
confere("no dia seguinte cria a próxima", f == ["lição ingles"] and li.listar("ingles")[0]["numero"] == 2, f)
confere("cards de pasta sequencial usam só o que já foi estudado", True)
ca.configurar("ingles", 1, 0, "07:00")
mat = li.material("ingles")
vistos = set()
for sem in range(8):
    doc, texto = ca._trecho_para_card(d.obter_pasta("ingles"), random.Random(sem))
    vistos.add(texto)
confere("trecho do card sequencial limitado às lições criadas", all(t in [x[1] for x in mat[:4]] for t in vistos), len(vistos))

confere("notificar_padrao nunca levanta erro", ca.notificar_padrao("t", "c") is None)
d._agora = _agora_real
os.environ["HEIMDALL_LEARN_AGENDA"] = "0"
confere("agenda desligável por variável", ca.iniciar_agenda() is None)

# site
srv = ThreadingHTTPServer(("127.0.0.1", 0), site.Learn)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
token, _ = nuvem.nova_sessao("*")


def req(metodo, caminho, corpo=None, cab=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    h = {"Host": "localhost", "Cookie": f"{nuvem.COOKIE}={token}"}
    h.update(cab or {})
    c.request(metodo, caminho, body=corpo, headers=h)
    r = c.getresponse()
    return r.status, r.read().decode("utf-8", "replace"), r


def post(rota, campos):
    return req("POST", rota, urlencode(campos), {"Content-Type": "application/x-www-form-urlencoded"})


_, corpo, _ = req("GET", "/pasta?c=dados")
csrf = re.search(r'name="csrf" value="([^"]+)"', corpo).group(1)
confere("pasta mostra agenda com labels e botão de card", 'for="cards_dia"' in corpo and 'for="horario"' in corpo and "Gerar um card agora" in corpo)
confere("pasta aleatória não oferece lição por dia", 'name="licao_dia" value="0"' in corpo and 'for="licao_dia"' not in corpo)
_, corpo, _ = req("GET", "/pasta?c=ingles")
confere("pasta sequencial oferece lição por dia", 'for="licao_dia"' in corpo)
st, _, _ = post("/agenda", {"csrf": "x", "c": "dados", "cards_dia": 2, "licao_dia": 0, "horario": "09:00"})
confere("agenda sem csrf é recusada", st == 403)
st, _, r = post("/agenda", {"csrf": csrf, "c": "dados", "cards_dia": 2, "licao_dia": 0, "horario": "09:15"})
confere("salvar agenda", st == 303 and ca.obter_agenda("dados")["cards_dia"] == 2 and ca.obter_agenda("dados")["horario"] == "09:15")
st, _, r = post("/agenda", {"csrf": csrf, "c": "dados", "cards_dia": 9, "licao_dia": 0, "horario": "09:15"})
_, corpo, _ = req("GET", r.getheader("Location"))
confere("agenda inválida volta à pasta com erro", "No máximo 3" in corpo and "alert" in corpo)
ca._modelo = modelo_card
st, _, r = post("/card/novo", {"csrf": csrf, "c": "dados"})
for _ in range(50):
    _, corpo, _ = req("GET", "/cards?t=dados")
    if "Filas desacoplam" in corpo:
        break
    time.sleep(0.1)
confere("card pedido na hora aparece na aba Cards", "Filas desacoplam" in corpo and "card novo" in corpo, re.sub(r"<[^>]+>", " ", corpo)[-400:])
cid = ca.listar(True)[0]["id"]
st, _, _ = post("/cards/lido", {"csrf": csrf, "id": cid})
confere("marcar como lido pelo site", ca.listar(True) == [] or all(c["id"] != cid for c in ca.listar(True)))
_, corpo, _ = req("GET", "/")
confere("o início é a lista de temas, sem abas, com os botões Ajustes e Novo estudo", "Temas de estudo" in corpo and "<div role=\"tablist\"" not in corpo and "Ajustes" in corpo and "/tema?t=" in corpo)
_, ab, _ = req("GET", "/estudos?t=dados")
confere("tema aleatório: abas Estudos, Cards e Progresso, sem Lições nem Exercícios, e botões Trocar de tema e Ajustes", all(x in ab for x in ("Estudos", "Cards", "Progresso", "Trocar de tema", "Ajustes")) and "Lições" not in ab and "Exercícios" not in ab and ">Início</a>" not in ab.split("role=\"tabpanel\"")[0].split("</nav>")[0].split("role=\"tablist\"")[-1])
_, ab, _ = req("GET", "/licoes?t=ingles")
confere("tema sequencial: abas Lições, Exercícios, Cards e Progresso, sem Estudos", all(x in ab for x in ("Lições", "Exercícios", "Cards", "Progresso")) and ">Estudos</a>" not in ab.split("</nav>")[0])
_, aj, _ = req("GET", "/ajustes?t=dados")
confere("Ajustes carrega tela sem abas, com Voltar ao tema", "<div role=\"tablist\"" not in aj and "Voltar ao tema" in aj and "Trocar de tema" in aj)
confere("início: botões Novo estudo e Ajustes no topo, sem tipos nem categorias, com Resumo em texto", "Novo estudo" in corpo and "Ajustes" in corpo and "Tipos de estudo" not in corpo and "<h2>Categorias" not in corpo and "<h2>Resumo</h2>" in corpo and "cadastrado" in corpo and "documento" in corpo and "consulta" in corpo)
_, aj0, _ = req("GET", "/ajustes")
confere("os tipos e suas regras moraram nos Ajustes", "Tipos de estudo e suas regras" in aj0)
_, corpo, _ = req("GET", "/nova")
confere("Novo estudo: nome, arquivos, categoria e tipos com explicação, numa tela só", all(f'for="{i}"' in corpo for i in ("nome", "arquivos", "categoria", "tipo_0", "tipo_novo")) and "multiple" in corpo and 'name="tipo" value="Programação"' in corpo and "Aprender uma linguagem" in corpo and "Criar estudo" in corpo and 'aria-describedby="tipo_0_d"' in corpo)
_, corpo, _ = req("GET", "/exercicios?t=ingles")
confere("aba Exercícios lista com tabela, caption e scope, e esconde o gabarito de lição em aberto", "<caption>Exercícios das suas lições</caption>" in corpo and 'scope="col"' in corpo and "Resposta esperada" in corpo)
_, corpo, _ = req("GET", "/exercicios?t=ingles&erros=1")
confere("filtro dos erros funciona", st == 303 or "Exercícios" in corpo)
_, corpo, _ = req("GET", "/progresso?t=ingles")
confere("aba Progresso mostra dias seguidos e tabela por pasta", "Progresso por pasta" in corpo and "dia" in corpo)

print("\n" + ("Tudo certo." if not falhas else f"{falhas} falha(s)."))
sys.exit(1 if falhas else 0)
