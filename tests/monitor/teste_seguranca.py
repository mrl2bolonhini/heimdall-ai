#!/usr/bin/env python3
"""Testes das tarefas de segurança (heimdall_seguranca.py), sem rede e sem o modelo: o modelo e os comandos do sistema são simulados.
Uso: python3 tests/monitor/teste_seguranca.py"""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys
import tempfile
from pathlib import Path

import heimdall_seguranca as S

falhas = []


def ok(cond, msg):
    print(("ok   " if cond else "FALHA ") + msg)
    if not cond:
        falhas.append(msg)


# --- máscara de segredos ---
m = S.mascarar('token = "sk-abcdefghijklmnopqrstuvwxyz1234" e Authorization: Bearer abcd1234efgh5678ijkl')
ok("abcdefghijkl" not in m and "…[oculto]" in m, "segredos são mascarados e sobram só 4 caracteres")
ok(S.mascarar("porta 8000 aberta") == "porta 8000 aberta", "texto comum não é alterado")

# --- interpretação da resposta do modelo e conferência da evidência ---
dados = "python3 escutando na porta 9000 (TODAS as interfaces)\nNOVAS: node escutando na porta 3333 (TODAS as interfaces)"
resp = ("GRAVIDADE: média\nRESUMO: Apareceu uma porta nova aberta.\n"
        "ACHADO: Porta 3333 nova em todas as interfaces || EVIDENCIA: node escutando na porta 3333 || ACAO: confirme se foi você\n"
        "ACHADO: Há invasão em andamento || EVIDENCIA: log mostra root remoto || ACAO: desligue o Mac")
r = S.interpretar(resp, dados)
ok(r["gravidade"] == "media" and r["formato_ok"], "gravidade com acento é entendida (média -> media)")
ok(len(r["achados"]) == 2, "duas linhas ACHADO lidas")
ok(r["achados"][0]["confirmada"] is True, "evidência que existe nos dados é confirmada")
ok(r["achados"][1]["confirmada"] is False, "evidência inventada é marcada como não confirmada")
ok(S.interpretar("não sei responder", dados)["formato_ok"] is False, "resposta fora do formato é detectada")

# modelo que escreve ACHADO/EVIDENCIA/ACAO sem usar "||"
r5 = S.interpretar("GRAVIDADE: baixa\nRESUMO: x\nACHADO: Porta nova. EVIDENCIA: node escutando na porta 3333 ACAO: confirme", dados)
ok(len(r5["achados"]) == 1 and r5["achados"][0]["confirmada"] and r5["achados"][0]["acao"] == "confirme", "separa evidência e ação mesmo sem '||'")

# --- gravidade final ---
ok(S.combinar("nenhuma", "alta", [{"confirmada": False}]) == "baixa", "modelo diz alta sem evidência confirmada: cai para baixa")
ok(S.combinar("nenhuma", "alta", [{"confirmada": True}]) == "alta", "modelo diz alta com evidência confirmada: mantém alta")
ok(S.combinar("alta", "nenhuma", []) == "alta", "o piso do script vale mesmo se o modelo disser nenhuma")

# --- logs ---
fontes = [("a.log", ["10:01 GET /x 401 Unauthorized ip 1.2.3.4", "10:02 GET /x 401 Unauthorized ip 5.6.7.8", "tudo bem", "Traceback (most recent call last)"] * 3)]
g = S.agrupar_logs(fontes)
auth = [x for x in g if x["tipo"] == "auth"]
ok(len(auth) == 1 and auth[0]["n"] == 6, "linhas parecidas (só números diferentes) viram um grupo contado")
ok(g[0]["tipo"] == "auth", "acessos recusados vêm antes dos erros")

# --- commits ---
git = """@@COMMIT abc1234 teste
diff --git a/x.py b/x.py
+++ b/x.py
+KEY = "sk-abcdefghijklmnopqrstuvwxyz123456"
+caminho = "/Users/%s/heimdall-ai"
+ip = "192.168.0.15"
+token = os.environ.get("TOKEN_DA_API_AQUI_12345")
+contato = "suporte@heimdall-ai.tech"
+pessoal = "alguem@gmail.com"
@@COMMIT def5678 env
+++ b/.env
+SEGREDO=1
@@COMMIT 999aaaa ok
+++ b/.env.example
+TOKEN=
""" % Path.home().name
c = S.candidatos_commits(git)
tipos = sorted(x["tipo"] for x in c)
ok("segredo" in tipos and "caminho pessoal" in tipos and "rede privada" in tipos and "e-mail" in tipos, "segredo, caminho, IP privado e e-mail são encontrados")
ok(sum(1 for x in c if x["tipo"] == "segredo") == 1, "variável de ambiente não conta como segredo")
ok(sum(1 for x in c if x["tipo"] == "e-mail") == 1, "o e-mail do próprio projeto não conta")
ok(any(x["tipo"] == "arquivo sensível" and x["arquivo"] == ".env" for x in c), ".env versionado é encontrado")
ok(not any(x["arquivo"] == ".env.example" and x["tipo"] == "arquivo sensível" for x in c), ".env.example é permitido")
ok(all("abcdefghijklmnopqrstuvwxyz123456" not in x["trecho"] for x in c), "o segredo não aparece inteiro nos achados")

# --- tarefa completa, com comandos e modelo simulados ---
tmp = Path(tempfile.mkdtemp(prefix="hd_seg_"))
S.ESTADO = tmp / "estado.json"
S.DATA_DIR = tmp
LSOF = ("COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\n"
        "python3 100 u 5u IPv4 0x1 0t0 TCP *:9000 (LISTEN)\n"
        "node 200 u 6u IPv4 0x2 0t0 TCP 127.0.0.1:5678 (LISTEN)\n")
estado_lsof = {"texto": LSOF}


def falso_exec(cmd, timeout=30, cwd=None, juntar=False):
    if cmd[0] == "lsof":
        return 0, estado_lsof["texto"]
    if cmd[0] == "docker":
        return 0, "n8n 0.0.0.0:5678->5678/tcp\n"
    if cmd[0] == "git":
        return 0, ""
    return None, ""


chamadas = []


def falso_modelo(tarefa, dados):
    chamadas.append(tarefa)
    return "GRAVIDADE: media\nRESUMO: Porta nova.\nACHADO: Nova porta || EVIDENCIA: ruby escutando na porta 4444 || ACAO: confirme"


S._exec = falso_exec
S._pedir_ao_modelo = falso_modelo
r1 = S.executar("exposicao")
ok(r1["gravar"] and len(chamadas) == 1, "primeira leitura chama o modelo e grava a nota (base de comparação)")
r2 = S.executar("exposicao")
ok(len(chamadas) == 1 and not r2["gravar"] and r2["gravidade"] == "nenhuma", "sem mudanças: não chama o modelo, não grava nota")
estado_lsof["texto"] = LSOF + "ruby 300 u 7u IPv4 0x3 0t0 TCP *:4444 (LISTEN)\n"
r3 = S.executar("exposicao")
ok(len(chamadas) == 2 and r3["gravidade"] == "media", "porta nova em todas as interfaces: média (piso do script)")
ok("confirmada nos dados" in r3["markdown"], "a nota mostra que a evidência foi confirmada")
ok("TODAS as interfaces" not in r3["markdown"] or "Dados" not in r3["markdown"], "a nota não traz os dados brutos")


def modelo_quebrado(tarefa, dados):
    raise RuntimeError("LiteLLM fora do ar")


S._pedir_ao_modelo = modelo_quebrado
estado_lsof["texto"] = LSOF + "ruby 300 u 7u IPv4 0x3 0t0 TCP *:4444 (LISTEN)\nsshd 400 u 8u IPv4 0x4 0t0 TCP *:22 (LISTEN)\n"
r4 = S.executar("exposicao")
ok(r4["modelo_erro"] and r4["gravidade"] == "media", "modelo fora do ar: o piso do script continua valendo e o erro é informado")
ok(S.executar("exposicao", usar_modelo=False)["modelo_usado"] is False, "--sem-modelo não chama o modelo")
try:
    S.executar("outra")
    ok(False, "tarefa desconhecida deve falhar")
except ValueError:
    ok(True, "tarefa desconhecida é recusada")

print()
if falhas:
    print(f"{len(falhas)} falha(s).")
    sys.exit(1)
print("Tudo certo.")
