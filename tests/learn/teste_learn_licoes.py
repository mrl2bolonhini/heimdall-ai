#!/usr/bin/env python3
"""Testa as lições sequenciais do Learn e a voz do aluno: material em ordem, geração com modelo simulado, validação, correção, progresso,
fim do material, gabarito escondido, áudio e transcrição (com programas simulados)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import json
import os
import re
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

TMP = Path(tempfile.mkdtemp())
os.environ["HEIMDALL_DB_DIR"] = str(TMP / "db")
os.environ["HEIMDALL_KNOWLEDGE_DIR"] = str(TMP / "knowledge")
(TMP / "knowledge").mkdir()

import heimdall_lab as nuvem  # noqa: E402
import heimdall_learn as site  # noqa: E402
import heimdall_learn_dados as d  # noqa: E402
import heimdall_learn_licoes as li  # noqa: E402
import heimdall_learn_voz as voz  # noqa: E402
nuvem.SENHA_HASH = nuvem.SENHA_HASH or "teste"
nuvem.TOTP_SEGREDO = nuvem.TOTP_SEGREDO or "JBSWY3DPEHPK3PXP"

falhas = 0


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


par = lambda n: ("Frase %d do material de inglês: the cat sits on the mat while the dog runs in the park. " % n) * 5  # noqa: E731
d.criar_pasta("Inglês", "", "Idiomas", "inglês")
d.criar_pasta("Aleatória", "aleatorio", "Filosofia")
b = TMP / "knowledge" / "ingles"
(b / "02-segunda.md").write_text("\n\n".join(par(i) for i in range(10, 16)), encoding="utf-8")
(b / "01-primeira.md").write_text("\n\n".join(par(i) for i in range(1, 7)), encoding="utf-8")
(b / "10-decima.md").write_text("\n\n".join(par(i) for i in range(20, 24)), encoding="utf-8")

mat = li.material("ingles")
nomes = [Path(x[0]).name for x in mat]
confere("material em ordem natural dos documentos", nomes == sorted(nomes, key=lambda x: int(x[:2])), nomes)
confere("pasta aleatória não tem lições", "sequencial" in (erro(li.nova_licao, "aleatoria") or ""))

BOA = {"titulo": "O verbo to sit", "explicacao": "Explicação em português.\n\nSegundo parágrafo.", "trecho_estudo": "The cat sits. (O gato senta.)",
       "exercicios": [{"tipo": "alternativas", "enunciado": "Como se diz senta?", "opcoes": ["sits", "run", "park"], "correta": 0, "explicacao": "sits é a terceira pessoa."},
                      {"tipo": "texto", "enunciado": "Traduza: o cachorro corre.", "gabarito": "The dog runs.", "explicacao": "verbo na terceira pessoa"},
                      {"tipo": "alternativas", "enunciado": "Qual é o lugar?", "opcoes": ["park", "sits", "the"], "correta": 0}]}
confere("extrai JSON cercado de texto e cercas", li.extrair_json("Claro!\n```json\n" + json.dumps(BOA) + "\n```\nPronto.")["titulo"] == "O verbo to sit")
try:
    li.extrair_json("sem json aqui")
    confere("sem JSON levanta erro", False)
except ValueError:
    confere("sem JSON levanta erro", True)
confere("lição válida é normalizada", len(li.validar(BOA)["exercicios"]) == 3)
ruim = dict(BOA, exercicios=BOA["exercicios"][:2])
try:
    li.validar(ruim)
    confere("menos de 3 exercícios é recusado", False)
except ValueError:
    confere("menos de 3 exercícios é recusado", True)
ruim2 = dict(BOA, exercicios=[dict(e, correta=9) if e["tipo"] == "alternativas" else e for e in BOA["exercicios"]])
try:
    li.validar(ruim2)
    confere("alternativa com gabarito fora da faixa é descartada", False)
except ValueError:
    confere("alternativa com gabarito fora da faixa é descartada", True)

visto = []
def modelo_licao(sistema, usuario, max_tokens=1800):
    visto.append((sistema, usuario))
    return json.dumps(BOA)

i1 = li.nova_licao("ingles")
li.gerar(i1, modelo_licao)
l1 = li.obter(i1)
confere("lição 1 pronta com título e 3 exercícios", l1["estado"] == "pronta" and l1["numero"] == 1 and len(l1["exercicios"]) == 3, l1["erro"])
confere("prompt leva regras do tipo, idioma e a primeira parte do material", "Idiomas" in visto[0][0] and "inglês" in visto[0][0] and "01-primeira.md" in visto[0][1] and "nenhuma (esta é a primeira)" in visto[0][1])
confere("segunda chamada não cria nova lição enquanto a primeira está aberta", li.nova_licao("ingles") == i1)

try:
    li.enviar_respostas(i1, {0: "0", 1: "The dog runs."})
    confere("faltando resposta é recusado", False)
except d.ErroLearn as ex:
    confere("faltando resposta é recusado", "Faltam: 3" in str(ex), str(ex))
confere("nada foi gravado após recusa", li.respostas(i1) == {})
def cor_modelo(sistema, usuario, max_tokens=400):
    return "CERTO. A tradução está correta."
li.enviar_respostas(i1, {0: "0", 1: "The dog runs.", 2: "1"}, {1: "voz"})
r = li.respostas(i1)
confere("alternativas corrigidas na hora", r[0]["correto"] == 1.0 and r[2]["correto"] == 0.0 and "A certa era: park" in r[2]["correcao"])
confere("texto aguarda a IA e guarda a via voz", r[1]["correto"] is None and r[1]["via"] == "voz" and li.obter(i1)["estado"] == "corrigindo")
li.corrigir_pendentes(i1, cor_modelo)
l1 = li.obter(i1)
confere("lição concluída com nota 2/3", l1["estado"] == "concluida" and abs(l1["nota"] - 0.667) < 0.01, (l1["estado"], l1["nota"], l1["erro"]))
confere("progresso", li.resumo_progresso("ingles")["concluidas"] == 1)

def cor_ruim(*a, **k):
    return "talvez"
i2 = li.nova_licao("ingles")
confere("segunda lição tem número 2", li.obter(i2)["numero"] == 2)
li.gerar(i2, modelo_licao)
li.enviar_respostas(i2, {0: "0", 1: "x", 2: "0"})
li.corrigir_pendentes(i2, cor_ruim)
confere("correção sem classificação vira erro_correcao", li.obter(i2)["estado"] == "erro_correcao")
li.corrigir_pendentes(i2, lambda *a, **k: "PARCIAL: faltou o verbo.")
confere("repetir a correção conclui com meia nota", li.obter(i2)["estado"] == "concluida" and abs(li.obter(i2)["nota"] - 0.833) < 0.01, li.obter(i2))

def modelo_lixo(*a, **k):
    return "não sei fazer"
i3 = li.nova_licao("ingles")
li.gerar(i3, modelo_lixo)
confere("modelo sem JSON vira erro registrado", li.obter(i3)["estado"] == "erro" and "JSON" in li.obter(i3)["erro"], li.obter(i3))
li.gerar(i3, modelo_licao)
confere("nova tentativa na mesma lição funciona", li.obter(i3)["estado"] == "pronta")
li.enviar_respostas(i3, {0: "0", 1: "a", 2: "0"})
li.corrigir_pendentes(i3, cor_modelo)
for _ in range(10):
    try:
        n = li.nova_licao("ingles")
    except d.ErroLearn as ex:
        fim = str(ex)
        break
    li.gerar(n, modelo_licao)
    li.enviar_respostas(n, {0: "0", 1: "a", 2: "0"})
    li.corrigir_pendentes(n, cor_modelo)
else:
    fim = ""
confere("no fim do material o Learn avisa em vez de inventar", "fim do material" in fim, fim)
confere("número de lições limitado pelo material", len(li.listar("ingles")) == (len(mat) + 1) // 2, (len(li.listar("ingles")), len(mat)))

# ---- transcrição ----
def conv_falso(origem, destino):
    destino.write_bytes(b"RIFF")
confere("áudio vazio recusado", "vazia" in (erro(voz.transcrever, b"x") or ""))
confere("áudio enorme recusado", "grande" in (erro(voz.transcrever, b"x" * (voz.MAX_AUDIO + 1)) or ""))
visto_cmd = []
def exec_falso(cmd, timeout=300):
    visto_cmd.append(cmd)
    return "[BLANK_AUDIO] The dog runs. "
t = voz.transcrever(b"a" * 500, "auto", executor=exec_falso, conversor=conv_falso)
confere("transcrição limpa marcas entre colchetes", t == "The dog runs.", t)
confere("idioma auto não força língua no comando", "--language" not in visto_cmd[0] and "-l" not in visto_cmd[0])
t = voz.transcrever(b"a" * 500, "inglês", executor=exec_falso, conversor=conv_falso)
confere("idioma da pasta vira código do Whisper", "en" in visto_cmd[1])
confere("transcrição vazia vira erro claro", "Não entendi" in (erro(lambda: voz.transcrever(b"a" * 500, "", executor=lambda c, timeout=300: "  ", conversor=conv_falso)) or ""))
confere("sem transcritor instalado explica como instalar", "brew install" in (erro(voz.transcrever, b"a" * 500, "auto") or "brew install"))
confere("nenhum áudio fica no disco", not list(TMP.rglob("*.audio")) and not list(Path(tempfile.gettempdir()).glob("learn-voz-*")))

# ---- site ----
srv = ThreadingHTTPServer(("127.0.0.1", 0), site.Learn)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
token, _ = nuvem.nova_sessao("*")


def req(metodo, caminho, corpo=None, cab=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
    h = {"Host": "localhost", "Cookie": f"{nuvem.COOKIE}={token}"}
    h.update(cab or {})
    c.request(metodo, caminho, body=corpo, headers=h)
    rr = c.getresponse()
    return rr.status, rr.read().decode("utf-8", "replace"), rr


def post(rota, campos):
    return req("POST", rota, urlencode(campos), {"Content-Type": "application/x-www-form-urlencoded"})


d.criar_pasta("Alemão", "sequencial", "Idiomas", "alemão")
(TMP / "knowledge" / "alemao" / "aula.md").write_text("\n\n".join(par(i) for i in range(1, 6)), encoding="utf-8")
li._modelo = modelo_licao
st, corpo, _ = req("GET", "/licoes?t=alemao")
csrf = re.search(r'name="csrf" value="([^"]+)"', corpo).group(1)
confere("pasta sequencial mostra Próxima lição e progresso", "Próxima lição" in corpo and "lições criadas" in corpo or "lição criada" in corpo)
st, _, r = post("/licao/nova", {"csrf": "x", "c": "alemao"})
confere("criar lição sem csrf é recusado", st == 403)
st, _, r = post("/licao/nova", {"csrf": csrf, "c": "alemao"})
loc = r.getheader("Location")
confere("pedir lição leva à página dela", st == 303 and loc.startswith("/licao?id="), loc)
for _ in range(60):
    _, corpo, _ = req("GET", loc)
    if "Explicação" in corpo or "Não consegui criar" in corpo:
        break
    time.sleep(0.1)
confere("lição aparece com explicação e trecho", "Explicação" in corpo and "Trecho de estudo" in corpo and "O verbo to sit" in corpo)
confere("gabarito não vai para a página", "The dog runs." not in corpo and "A certa era" not in corpo and "terceira pessoa" not in corpo)
confere("alternativas em fieldset com legend e radios", "<fieldset" in corpo and "<legend>" in corpo and 'type="radio"' in corpo)
confere("texto com label e botão de voz acessível", 'for="ex1"' in corpo and 'data-voz="1"' in corpo and 'aria-pressed="false"' in corpo)
confere("script de voz com nonce só nessa página", "MediaRecorder" in corpo and 'nonce="' in corpo)
sid = int(loc.split("=")[1])
st, _, _ = post("/licao/responder", {"csrf": csrf, "id": sid, "ex0": "0", "ex1": "", "ex2": "0"})
_, corpo, _ = req("GET", loc)
confere("resposta incompleta volta com erro e a lição continua aberta", li.obter(sid)["estado"] == "pronta" and "alert" in corpo)
li._modelo = cor_modelo
st, _, _ = post("/licao/responder", {"csrf": csrf, "id": sid, "ex0": "0", "ex1": "The dog runs.", "via1": "voz", "ex2": "0"})
for _ in range(60):
    _, corpo, _ = req("GET", loc)
    if "Nota da lição" in corpo:
        break
    time.sleep(0.1)
confere("resultado com nota e correções, e agora o gabarito aparece", "Nota da lição: 100%" in corpo and "(falada)" in corpo and "A tradução está correta" in corpo, re.sub(r"<[^>]+>", " ", corpo)[-300:])
confere("lição concluída oferece a próxima", "Próxima lição" in corpo)
_, corpo, _ = req("GET", "/licoes?t=ingles")
confere("aba Lições lista com caption e escopo", "<caption>" in corpo and 'scope="row"' in corpo and "O verbo to sit" in corpo)
st, corpo, _ = req("GET", "/licao?id=999")
confere("lição inexistente dá erro amigável", st == 400 and "não encontrada" in corpo)
st, corpo, _ = req("GET", "/licao?id=abc")
confere("id inválido não quebra", st == 400)

# voz via site
st, corpo, _ = req("POST", "/licao/voz", b"x" * 300, {"Content-Type": "audio/mp4"})
confere("voz sem csrf é recusada", st == 403 and "erro" in json.loads(corpo))
voz.transcrever = lambda audio, idioma="", **k: "Der Hund läuft."
st, corpo, _ = req("POST", "/licao/voz", b"x" * 300, {"Content-Type": "audio/mp4", "X-CSRF": csrf})
confere("voz devolve o texto transcrito", st == 200 and json.loads(corpo)["texto"] == "Der Hund läuft.", corpo)
def voz_quebrada(audio, idioma="", **k):
    raise d.ErroLearn("Nenhum transcritor instalado no Mac.")
voz.transcrever = voz_quebrada
st, corpo, _ = req("POST", "/licao/voz", b"x" * 300, {"Content-Type": "audio/mp4", "X-CSRF": csrf})
confere("falha na voz vira mensagem, não erro 500", st == 200 and "Nenhum transcritor" in json.loads(corpo)["erro"])
st, corpo, _ = req("POST", "/licao/voz", b"", {"Content-Type": "audio/mp4", "X-CSRF": csrf})
confere("voz vazia é recusada", st == 413)

# áudio da lição
(d.pasta_dados() / "audio").mkdir(exist_ok=True)
(d.pasta_dados() / "audio" / f"licao-{sid}-trecho.m4a").write_bytes(bytes(range(200)))
st, corpo, r = req("GET", f"/audio-licao?id={sid}&k=trecho", cab={"Range": "bytes=0-9"})
confere("áudio da lição com Range", st == 206 and len(corpo.encode("latin-1")) == 10)
st, _, _ = req("GET", f"/audio-licao?id={sid}&k=../../etc/passwd")
confere("tipo de áudio suspeito é 404", st == 404)
if sys.platform != "darwin":
    st, _, _ = post("/licao/audio", {"csrf": csrf, "id": sid, "k": "explicacao"})
    _, corpo, _ = req("GET", loc)
    confere("gravar áudio fora do Mac explica o motivo", "Mac" in corpo)

print("\n" + ("Tudo certo." if not falhas else f"{falhas} falha(s)."))
sys.exit(1 if falhas else 0)
