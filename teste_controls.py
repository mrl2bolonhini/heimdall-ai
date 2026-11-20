#!/usr/bin/env python3
"""Testa o Heimdall Controls: login só do dono, CSRF, terminal persistente, cópia das últimas saídas, auditoria e acessibilidade da página."""
import http.client
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.parse
from http.server import ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="controls_"))
os.environ.update({"HEIMDALL_CONTROLS_SHELL": "/bin/bash", "HEIMDALL_CONTROLS_RC": "0", "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
sys.path.insert(0, str(Path(__file__).resolve().parent))
import heimdall_cloud as hc  # noqa: E402
import heimdall_controls as hcx  # noqa: E402

hcx.AUDITORIA = TMP / "logs" / "controls_audit.log"
falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:700])


SENHA, SEGREDO = "senha-de-teste-forte", "JBSWY3DPEHPK3PXP"
hc.SENHA_HASH = hc.hash_senha(SENHA, iteracoes=100_000)
hc.TOTP_SEGREDO = SEGREDO

srv = ThreadingHTTPServer(("127.0.0.1", 0), hcx.Painel)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORTA = srv.server_address[1]


def req(metodo, rota, corpo=None, cookie="", host="localhost", extra=None):
    c = http.client.HTTPConnection("127.0.0.1", PORTA, timeout=30)
    cab = {"Host": host}
    if cookie:
        cab["Cookie"] = f"{hc.COOKIE}={cookie}"
    cab.update(extra or {})
    dados = None
    if corpo is not None:
        dados = urllib.parse.urlencode(corpo).encode()
        cab["Content-Type"] = "application/x-www-form-urlencoded"
    c.request(metodo, rota, body=dados, headers=cab)
    r = c.getresponse()
    return r.status, r.read().decode("utf-8", "replace"), r


# --- host, login
confere("/saude responde sem login", req("GET", "/saude")[:2] == (200, "ok"))
confere("host fora da lista: 421", req("GET", "/", host="evil.example")[0] == 421)
s, _, r = req("GET", "/terminal")
confere("sem sessão vai para a entrada", s == 303 and r.getheader("Location") == "/entrar")
s, corpo, _ = req("GET", "/entrar")
confere("entrada: campos com label", s == 200 and 'for="senha"' in corpo and 'for="codigo"' in corpo and corpo.count("<h1") == 1)
s, corpo, _ = req("POST", "/entrar", {"senha": "errada", "codigo": "000000"})
confere("senha errada: 401", s == 401)
token = hc.nova_sessao()[0]
sess = hc.sessao_valida(token, "controls")
CSRF = sess["csrf"]

# --- só o dono
convidado = hc.nova_sessao("controls")[0]
s, _, r = req("GET", "/terminal", cookie=convidado)
confere("sessão de convidado (escopo controls) é recusada", s == 303 and r.getheader("Location") == "/entrar")
s, _, _ = req("POST", "/terminal/executar", {"comando": "echo oi", "csrf": "x"}, cookie=convidado, extra={"X-Heimdall-Ajax": "1"})
confere("convidado não executa comando", s == 401)

# --- páginas
s, corpo, r = req("GET", "/terminal", cookie=token)
csp = r.getheader("Content-Security-Policy") or ""
nonce = re.search(r"nonce-([\w-]+)", csp)
confere("terminal: um só h1, campo único com rótulo, região de aviso", s == 200 and corpo.count("<h1") == 1 and 'for="terminal"' in corpo and '<textarea class="terminal" id="terminal"' in corpo and 'role="alert"' in corpo, corpo[:300])
confere("terminal: sem campo separado de resposta; lista de atalhos presente", "Resposta ao programa" not in corpo and 'id="h-atalhos"' in corpo and "Option+Shift+C" in corpo and "Ctrl+C" in corpo and "Ctrl+L" in corpo)
confere("terminal: script só com nonce, sem manipulador inline", bool(nonce) and f'<script nonce="{nonce.group(1)}">' in corpo and " onclick=" not in corpo and "javascript:" not in corpo)
confere("terminal: botões de copiar a última e as últimas N", "Copiar a última saída" in corpo and 'id="qtd"' in corpo and 'for="qtd"' in corpo and "Copiar as últimas saídas" in corpo)
confere("terminal: pular para o conteúdo e lang pt-BR", 'href="#principal"' in corpo and 'lang="pt-BR"' in corpo)

# --- CSRF e origem
s, corpo, _ = req("POST", "/terminal/executar", {"comando": "echo oi", "csrf": "errado"}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
confere("CSRF errado: 403 e nada executa", s == 403 and "recusado" in corpo)
s, _, _ = req("POST", "/terminal/executar", {"comando": "echo oi", "csrf": CSRF}, cookie=token, extra={"X-Heimdall-Ajax": "1", "Origin": "https://evil.example"})
confere("Origin de outro site: 403", s == 403)


def exec_(cmd, espera=15):
    s, corpo, _ = req("POST", "/terminal/executar", {"comando": cmd, "csrf": CSRF}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
    n = json.loads(corpo).get("n") if s == 200 else None
    fim = time.time() + espera
    while time.time() < fim:
        st = json.loads(req("GET", "/terminal/estado?desde=0", cookie=token, extra={"X-Heimdall-Ajax": "1"})[1])
        if not st["rodando"]:
            return n, st
        time.sleep(0.2)
    return n, st


# --- terminal persistente
n1, st = exec_("cd /usr && export HD_TESTE=42 && pwd")
b1 = next(b for b in st["blocos"] if b["n"] == n1)
confere("executa e mostra a saída", b1["estado"] == "concluido" and b1["codigo"] == 0 and "/usr" in b1["saida"])
n2, st = exec_("echo $HD_TESTE; pwd")
b2 = next(b for b in st["blocos"] if b["n"] == n2)
confere("pasta e variável continuam entre comandos", "42" in b2["saida"] and "/usr" in b2["saida"] and st["pasta"] == "/usr", b2["saida"])
n3, st = exec_("echo errado; exit_code_test() { return 3; }; exit_code_test")
b3 = next(b for b in st["blocos"] if b["n"] == n3)
confere("código de saída aparece no campo, no aviso e no JSON", b3["codigo"] == 3 and "[código 3, em" in st["texto"] and "Código 3" in b3["aviso"], st["texto"][-200:])
n4, st = exec_("printf '\\033[31mverm\\033[0m <script>alert(1)</script>\\n'")
b4 = next(b for b in st["blocos"] if b["n"] == n4)
s_, pag, _ = req("GET", "/terminal", cookie=token)
confere("sem códigos de cor; HTML escapado na página", "\x1b" not in b4["saida"] and "verm" in b4["saida"] and "&lt;script&gt;alert(1)" in pag and "<script>alert(1)" not in pag, b4["saida"])
confere("campo: só o último comando, com prompt, saída e situação", st["texto"].startswith("usr% printf") and "% cd /usr" not in st["texto"] and "% echo $HD_TESTE" not in st["texto"] and st["prompt"] == "usr%" and st["texto"].endswith("\n\n") and st["texto"][st["inicio_ultima"]:].startswith("verm"), st["texto"])
confere("histórico à parte traz os comandos anteriores ao último, do mais antigo ao mais novo", st["historico"].index("% cd /usr") < st["historico"].index("usr% echo $HD_TESTE") and "printf" not in st["historico"] and st["n_hist"] == 3, st["historico"][-300:])
st_h = json.loads(req("GET", f"/terminal/estado?desde=0&h={st['n_hist']}", cookie=token, extra={"X-Heimdall-Ajax": "1"})[1])
confere("histórico só vai quando mudou (h igual: não manda de novo)", st_h["historico"] is None and st_h["n_hist"] == st["n_hist"])
confere("a página traz o histórico ACIMA do terminal, sem verificação de ortografia e com foco automático no terminal",
        pag.index('id="historico"') < pag.index('id="terminal"') and 'id="historico" aria-readonly="true"' in pag and '<label for="historico">Histórico</label>' in pag and '<label for="terminal">Terminal</label>' in pag and "readonly" not in pag.split('id="historico"')[1].split(">")[0].replace("aria-readonly", "") and 'spellcheck="false" autofocus' in pag, pag[pag.index('id="historico"') - 60:pag.index('id="historico"') + 200])
confere("aviso curto traz a saída; histórico de comandos no JSON", "Saída: verm" in b4["aviso"] and any("printf" in c for c in st["comandos"]), b4["aviso"])

# --- completar com Tab
import tempfile as _tf  # noqa: E402
dc = Path(_tf.mkdtemp(prefix="comp_"))
(dc / "sub dir").mkdir()
(dc / "pasta").mkdir()
for nome in ("alfa.txt", "alfabeto.txt", "beta.txt", ".oculto"):
    (dc / nome).write_text("")
r1 = hcx.completar(str(dc), "cat be")
confere("Tab: um só arquivo completa com espaço", r1["palavra_nova"] == "beta.txt " and r1["inicio"] == 4, r1)
r2 = hcx.completar(str(dc), "cat alf")
confere("Tab: vários completam o prefixo comum e listam as opções", r2["palavra_nova"] == "alfa" and r2["opcoes"] == ["alfa.txt", "alfabeto.txt"], r2)
r3 = hcx.completar(str(dc), "ls pa")
confere("Tab: pasta completa com barra, sem espaço", r3["palavra_nova"] == "pasta/", r3)
r4 = hcx.completar(str(dc), "ls sub")
confere("Tab: espaço no nome é escapado", r4["palavra_nova"] == "sub\\ dir/", r4)
confere("Tab: arquivo oculto só aparece se a palavra começar com ponto", ".oculto" not in hcx.completar(str(dc), "cat ")["opcoes"] and ".oculto" in hcx.completar(str(dc), "cat .")["opcoes"])
r5 = hcx.completar(str(dc), "ec")
confere("Tab: primeira palavra completa comando", r5["palavra_nova"] == "echo " and r5["inicio"] == 0, r5)
_h = Path(_tf.mkdtemp(prefix="home_")); (_h / "heimdall-ai").mkdir(); (_h / "heimfile").write_text("x")
_ant = os.environ.get("HOME"); os.environ["HOME"] = str(_h)
rcd = hcx.completar(str(dc), "cd heim")
confere("Tab: cd heim (sem pasta parecida na atual) completa pela pasta pessoal, só pastas", rcd["palavra_nova"] == "~/heimdall-ai/" and rcd["inicio"] == 3 and rcd["opcoes"] == ["heimdall-ai/"], rcd)
confere("Tab: cd só oferece pastas", hcx.completar(str(dc), "cd sub")["palavra_nova"] == "sub\\ dir/" and "beta.txt" not in hcx.completar(str(dc), "cd ")["opcoes"])
if _ant is None: os.environ.pop("HOME")
else: os.environ["HOME"] = _ant
confere("duração: número colado no s, sem fração quando zero", [hcx.duracao(x) for x in (0, 0.004, 0.3, 12.3, 37.21, 65.4)] == ["0s", "0s", "0,3s", "12,3s", "37,21s", "1min e 5,4s"], [hcx.duracao(x) for x in (0, 0.004, 0.3, 12.3, 37.21, 65.4)])
import heimdall_shell as _hs  # noqa: E402
confere("eco da linha digitada sai da saída; saída parecida fica", _hs._sem_eco("cd ../", "cd ../\nok") == "ok" and _hs._sem_eco("ls", "a\nls") == "a\nls" and _hs._sem_eco("echo oi", "oi") == "oi")
confere("histórico sem linha em branco no fim", not st["historico"].endswith("\n"), repr(st["historico"][-20:]))
confere("Tab: nada que combine devolve lista vazia", hcx.completar(str(dc), "cat zzz")["opcoes"] == [])
confere("Tab: depois de ; volta a completar comando", hcx.completar(str(dc), "ls; ech")["palavra_nova"] == "echo ")
s_, corpo_, _ = req("GET", "/terminal/completar?linha=" + urllib.parse.quote("ls /us"), cookie=token, extra={"X-Heimdall-Ajax": "1"})
confere("Tab pelo servidor: exige sessão e responde JSON", s_ == 200 and "/usr/" in json.loads(corpo_)["palavra_nova"] and req("GET", "/terminal/completar?linha=ls", extra={"X-Heimdall-Ajax": "1"})[0] == 401, corpo_)

# --- cópia
s, t, _ = req("GET", "/terminal/texto?ultimos=1", cookie=token)
confere("copiar a última saída: comando e saída", s == 200 and t.startswith("$ printf") and "verm" in t and "alert(1)" in t, t)
s, t, _ = req("GET", "/terminal/texto?ultimos=2&comando=0", cookie=token)
confere("copiar as últimas 2 sem o comando", "$ " not in t and "verm" in t and "[concluido, código 3]" in t, t)
s, t, _ = req("GET", f"/terminal/texto?bloco={n2}", cookie=token)
confere("copiar um bloco específico", "$ echo $HD_TESTE" in t and "42" in t and "verm" not in t, t)
s, t, _ = req("GET", "/terminal/texto?ultimos=999", cookie=token)
confere("pedido grande de saídas é limitado, não quebra", s == 200 and "/usr" in t)

n_longo, st_l = exec_("seq 1 40")
bl = next(b for b in st_l["blocos"] if b["n"] == n_longo)
confere("aviso de saída longa traz a saída inteira", "Saída: 1\n2\n3" in bl["aviso"] and bl["aviso"].rstrip().endswith("40"), bl["aviso"][-60:])

# --- programa que pergunta, e interrupção
s, corpo, _ = req("POST", "/terminal/executar", {"comando": 'read -p "nome? " x; echo ola $x', "csrf": CSRF}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
n5 = json.loads(corpo)["n"]
time.sleep(0.6)
s, corpo, _ = req("POST", "/terminal/entrada", {"texto": "Ana", "csrf": CSRF}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
confere("resposta a um programa em execução", s == 200)
fim = time.time() + 10
while time.time() < fim and hcx.obter_shell().rodando():
    time.sleep(0.2)
confere("o programa recebeu a resposta", "ola Ana" in hcx.obter_shell().bloco(n5).saida, hcx.obter_shell().bloco(n5).saida)
s, corpo, _ = req("POST", "/terminal/executar", {"comando": "sleep 60", "csrf": CSRF}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
n6 = json.loads(corpo)["n"]
s, corpo, _ = req("POST", "/terminal/executar", {"comando": "echo outro", "csrf": CSRF}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
confere("não aceita segundo comando enquanto um roda", s == 409 and "em execução" in corpo, corpo)
time.sleep(0.3)
s, corpo, _ = req("POST", "/terminal/interromper", {"csrf": CSRF}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
hcx.obter_shell().esperar(10)
confere("interromper (Ctrl+C)", json.loads(corpo)["ok"] and hcx.obter_shell().bloco(n6).estado == "interrompido")

# --- serviços (rádios) e manutenção (ações)
import heimdall_servicos as hsv  # noqa: E402
import heimdall_kuma as hku  # noqa: E402
hku.monitores = lambda: ([{"id": 7, "nome": "Cloud (8010)", "status": "no ar"}], "")
chamadas = []
hsv.aplicar = lambda sid, lig: (chamadas.append((sid, lig)) or (True, f"{sid} ok"))
hku.pausar_ou_retomar = lambda mid, pausar: ""
estado_falso = {"cloud": True, "news": False}
hsv.no_ar = lambda sv: estado_falso.get(sv["id"], True)
s, corpo, _ = req("GET", "/servicos", cookie=token)
confere("serviços: uma chave (role=switch) por serviço, com estado e sem botão Aplicar", s == 200 and corpo.count('role="switch"') == len(hsv.catalogo())
        and 'aria-checked="true"' in corpo and 'aria-checked="false"' in corpo and "Kuma: no ar" in corpo and "Aplicar" not in corpo and corpo.count("<h1") == 1 and 'role="status"' in corpo)
confere("serviços: o próprio Controls não é desligável", "Controls" not in "".join(x["nome"] for x in hsv.catalogo()))
confere("abas: tablist, tab com aria-selected, painel e atalho",
        'role="tablist"' in corpo and corpo.count('role="tab"') == 5 and 'aria-selected="true"' in corpo and 'role="tabpanel"' in corpo and "Atalho: Option Shift 3" in corpo and "Alt+Shift" not in corpo)
confere("abas: o Terminal carrega a página inteira (data-completa)", corpo.count(" data-completa>") == 1)
confere("abas e chaves: os scripts vão com nonce", "ArrowRight" in corpo and "/servicos/alternar" in corpo and "nonce=" in corpo)
s, corpo, _ = req("POST", "/servicos/alternar", {"csrf": CSRF, "id": "cloud", "estado": "off"}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
d = json.loads(corpo)
confere("alternar: liga ou desliga o serviço escolhido e devolve o estado", s == 200 and chamadas == [("cloud", False)] and d["ok"] and "Monitor do Kuma pausado" in d["mensagem"] and "situacao" in d, corpo)
s, corpo, _ = req("POST", "/servicos/alternar", {"csrf": CSRF, "id": "inventado", "estado": "on"}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
confere("alternar: serviço desconhecido é recusado", s == 409, corpo)
s, corpo, _ = req("POST", "/servicos/alternar", {"csrf": "errado", "id": "cloud", "estado": "off"}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
confere("alternar sem o token de segurança é recusado, com o motivo", s == 403 and "token" in corpo, corpo)
import heimdall_config as hcf  # noqa: E402
import tempfile as _tf  # noqa: E402
hcf.ARQUIVO = Path(_tf.mkdtemp()) / ".env"
hcf.ARQUIVO.write_text("HEIMDALL_TESTE='um'\n", encoding="utf-8")
s, corpo, _ = req("GET", "/configuracoes", cookie=token)
confere("configurações: lista o que está no .env, com o valor inteiro, e as opções do código", s == 200 and "HEIMDALL_TESTE" in corpo and 'value="um"' in corpo
        and "<details" in corpo and "No .env" in corpo and "Opções ainda sem valor" in corpo and "Controls: " in corpo and corpo.count("<h1") == 1 and 'type="search"' in corpo, corpo[:200])
import re as _re
_tit = _re.findall(r"<summary>([^<]*)</summary>", corpo)
_nom = [t.split(":")[0] for t in _tit]
confere("configurações: nenhum grupo repetido e opções com explicação ligada ao campo", len(_nom) == len(set(_nom)) and 'aria-describedby="desc-' in corpo and "Porta em que o serviço escuta" in corpo, str(_nom))
confere("configurações: cada campo tem label", corpo.count("<label") >= corpo.count('type="text"') - 1)
s, corpo, _ = req("POST", "/configuracoes/salvar", {"csrf": CSRF, "nome": "HEIMDALL_TESTE", "valor": "dois", "acao": "salvar"}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
confere("salvar grava no .env e diz que vale depois de reiniciar", s == 200 and json.loads(corpo)["ok"] and "HEIMDALL_TESTE='dois'" in hcf.ARQUIVO.read_text() and "reiniciado" in corpo, corpo)
s, corpo, _ = req("POST", "/configuracoes/salvar", {"csrf": CSRF, "nome": "HEIMDALL_TESTE", "valor": "a'b", "acao": "salvar"}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
confere("valor com aspa simples é recusado com o motivo", not json.loads(corpo)["ok"] and "aspa" in corpo and "'a" not in hcf.ARQUIVO.read_text())
s, corpo, _ = req("POST", "/configuracoes/salvar", {"csrf": "errado", "nome": "HEIMDALL_TESTE", "valor": "x"}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
confere("salvar sem o token de segurança é recusado", s == 403 and "dois" in hcf.ARQUIVO.read_text())
s, corpo, _ = req("POST", "/configuracoes/salvar", {"csrf": CSRF, "nome": "HEIMDALL_TESTE", "acao": "remover"}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
confere("remover tira do .env", json.loads(corpo)["ok"] and "HEIMDALL_TESTE" not in hcf.ARQUIVO.read_text())
# Origin "null" (formulário comum com no-referrer), origem de fora e Sec-Fetch-Site
s, _, _ = req("POST", "/manutencao/acao", {"acao": "inventada", "csrf": CSRF}, cookie=token, extra={"Origin": "null"})
confere("formulário comum com Origin null passa (o token continua valendo)", s == 303)
s, _, _ = req("POST", "/manutencao/acao", {"acao": "inventada", "csrf": CSRF}, cookie=token, extra={"Origin": "https://mal.example"})
confere("Origin de outro site é recusado", s == 403)
s, _, _ = req("POST", "/manutencao/acao", {"acao": "inventada", "csrf": CSRF}, cookie=token, extra={"Origin": "null", "Sec-Fetch-Site": "cross-site"})
confere("Origin null vindo de outro site (Sec-Fetch-Site) é recusado", s == 403)
s, corpo, _ = req("POST", "/manutencao/acao", {"acao": "inventada", "csrf": "errado"}, cookie=token, extra={"Origin": "null"})
confere("Origin null com token errado continua recusado", s == 403)
s, corpo, _ = req("GET", "/", cookie=token)
confere("menu Conta mostra o nome de quem entrou e tem o Sair", "<summary>Conta: Dono</summary>" in corpo and 'action="/sair"' in corpo and "senha e código" in corpo)
tk2, _ = hc.nova_sessao("*")
csrf2 = hc.sessao_valida(tk2, hcx.SERVICO)["csrf"]
s, _, r = req("POST", "/sair", {"csrf": csrf2}, cookie=tk2, extra={"Origin": "null"})
confere("Sair com Origin null encerra a sessão e volta ao login", s == 303 and r.getheader("Location") == "/entrar", str((s, r.getheader("Location"))))
s, _, _ = req("GET", "/", cookie=tk2)
confere("depois do Sair a sessão não vale mais", s in (303, 401))
s, corpo, _ = req("GET", "/", cookie=token)
confere("páginas marcadas para o Cloudflare não trocar e-mails por link (email_off)", "<!--email_off-->" in corpo and "<!--/email_off-->" in corpo)
s, corpo, _ = req("GET", "/manutencao", cookie=token)
confere("manutenção: botões de ação e um só h1", s == 200 and "Update e restart" in corpo and ">Start<" in corpo and ">Stop<" in corpo and "Exibir log" in corpo and corpo.count("<h1") == 1)
hsv.parar_tudo = lambda: [("Cloud", True, "parado"), ("News", True, "parado")]
hsv.iniciar_tudo = lambda: (True, "subida iniciada")
s, _, r = req("POST", "/manutencao/acao", {"acao": "stop", "csrf": CSRF}, cookie=token)
s2, corpo, _ = req("GET", "/manutencao", cookie=token)
confere("Stop para tudo menos o painel e avisa", s == 303 and "Tudo parado, menos este painel" in corpo, corpo[:200])
s, _, r = req("POST", "/manutencao/acao", {"acao": "start", "csrf": CSRF}, cookie=token)
s2, corpo, _ = req("GET", "/manutencao", cookie=token)
confere("Start sobe o Heimdall e avisa", s == 303 and "Subida iniciada" in corpo, corpo[:200])
confere("nomes dos serviços em inglês, sem mistura", not any(x in "".join(sv["nome"] for sv in hsv.catalogo()) for x in ("Notas", "Saúde", "Jogos", "Agente", "(")))
s, _, r = req("POST", "/manutencao/acao", {"acao": "inventada", "csrf": CSRF}, cookie=token)
confere("ação desconhecida não executa nada", s == 303)
s, _, r = req("POST", "/manutencao/acao", {"acao": "log", "servico": "mcp; rm -rf /", "csrf": CSRF}, cookie=token)
confere("serviço do log fora da lista é recusado", s == 303)
confere("a lista de ações não aceita comando livre", all(v[1].startswith(("heimdall ", "./subir.sh")) for v in hcx.ACOES.values()))

# --- limpar e reiniciar
s, _, _ = req("POST", "/terminal/limpar", {"csrf": CSRF}, cookie=token, extra={"X-Heimdall-Ajax": "1"})
confere("limpar a lista de saídas", s == 200 and not hcx.obter_shell().blocos)
s, _, _ = req("POST", "/terminal/reiniciar", {"csrf": CSRF}, cookie=token)
n7, st = exec_("echo ${HD_TESTE:-vazio}")
b7 = next(b for b in st["blocos"] if b["n"] == n7)
confere("reiniciar o shell abre um novo e limpo", "vazio" in b7["saida"], b7["saida"])

# --- Access exigido em endereço público
hcx.HOSTS_OK.add("controls.heimdall-ai.tech")
import heimdall_cfaccess as cfa  # noqa: E402
orig_ativo = cfa.ativo
cfa.ativo = lambda: True
s, corpo, _ = req("GET", "/terminal", cookie=token, host="controls.heimdall-ai.tech")
confere("endereço público com Access ligado e sem token do Access: 403", s == 403)
cfa.ativo = orig_ativo

# --- auditoria
log = hcx.AUDITORIA.read_text(encoding="utf-8")
confere("auditoria guarda o comando e não a saída", "HD_TESTE=42" in log and "ola Ana" not in log and "(texto não gravado)" in log and "verm" in log.replace("printf", "") , log[-400:])
confere("arquivo de auditoria só do dono", oct(hcx.AUDITORIA.stat().st_mode)[-3:] == "600")

# --- sair
s, _, r = req("POST", "/sair", {"csrf": CSRF}, cookie=token)
confere("sair encerra a sessão", s == 303 and "Max-Age=0" in (r.getheader("Set-Cookie") or ""))
hcx.obter_shell().encerrar()
print("\n" + ("TUDO OK" if not falhas else f"{falhas} FALHA(S)"))
sys.exit(1 if falhas else 0)

