#!/usr/bin/env python3
"""Testa os avisos de saúde e finanças: ficam na aba Avisos de cada serviço, nunca no app Notas, e o Bark leva só texto genérico."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="heimdall-avisos-"))
os.environ.update({"STUDIO_DB_DIR": str(TMP / "banco"), "STUDIO_FINANCE_DIR": str(TMP / "fin"), "STUDIO_VAULT_DIR": str(TMP / "cofre"),
                   "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
sys.path.insert(0, str(RAIZ))
import heimdall_agente as ag  # noqa: E402
import heimdall_avisos as av  # noqa: E402
import heimdall_banco as banco  # noqa: E402

falhas = 0


def confere(nome, cond, detalhe=""):
    global falhas
    print(("ok   " if cond else "FALHOU ") + nome + ("" if cond else f"  -> {detalhe}"))
    falhas += 0 if cond else 1


# módulo
a = av.Avisos(TMP / "x.db")
confere("sem arquivo: lista vazia e zero não lidos", a.listar() == [] and a.nao_lidos() == 0)
i = a.gravar("Relatório da semana", "# Título\n- item um\n<script>alert(1)</script>")
confere("grava, conta não lidos e marca como lido", a.nao_lidos() == 1 and a.marcar(i) and a.nao_lidos() == 0 and not a.marcar(999))
try:
    a.gravar("   ", "x")
    confere("título vazio é recusado", False)
except ValueError:
    confere("título vazio é recusado", True)
html = av.pagina(a.listar(), "tok")
confere("a página não interpreta HTML do texto", "<script>" not in html and "&lt;script&gt;" in html and "<li>item um</li>" in html, html)
a.gravar("Outro", "texto")
confere("não lidos vêm primeiro; botão com nome acessível", html.count("Marcar como lido") == 0 and av.pagina(a.listar(), "tok").find("Outro") < av.pagina(a.listar(), "tok").find("Relatório"))
for n in range(av.MAX_AVISOS + 5):
    a.gravar(f"t{n}", "")
confere("guarda no máximo os mais recentes", len(a.listar(10000)) == av.MAX_AVISOS)
b = av.texto_bark("saude", 1)
confere("Bark genérico: só o nome do serviço e a aba, sem conteúdo", b["title"] == "Studio Health: aviso novo" and "Avisos" in b["body"] and "ECG" not in json.dumps(b))
confere("do_servico separa saúde e finanças", av.do_servico("saude").caminho != av.do_servico("financas").caminho and "fin" in str(av.do_servico("financas").caminho))

# agente
TOKEN = "token-do-agente-123456"
ag.TOKEN = TOKEN
barks = []
ag.bark.enviar_bark = lambda payload: barks.append(payload) or True
banco.iniciar()
srv = ag.ThreadingHTTPServer(("127.0.0.1", 0), ag.Handler)
porta = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()


def post(caminho, dado):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=20)
    corpo = json.dumps(dado).encode()
    c.request("POST", caminho, body=corpo, headers={"Content-Length": str(len(corpo)), "X-Heimdall-Token": TOKEN, "Content-Type": "application/json"})
    r = c.getresponse()
    d = json.loads(r.read() or b"{}")
    c.close()
    return r.status, d


st, d = post("/avisos/gravar", {"servico": "saude", "titulo": "Resumo das 5h50", "markdown": "sono 6h", "bark": True})
confere("/avisos/gravar de saúde grava na aba Avisos e manda Bark genérico", st == 200 and d["ok"] and av.do_servico("saude").nao_lidos() == 1 and barks and "sono" not in json.dumps(barks[-1]), (st, d, barks))
confere("/avisos/gravar recusa serviço desconhecido e título vazio", post("/avisos/gravar", {"servico": "notas", "titulo": "x"})[0] == 400 and post("/avisos/gravar", {"servico": "saude", "titulo": ""})[0] == 400)
st, d = post("/notas/gravar", {"pasta": "Saúde", "titulo": "Nota antiga de saúde", "markdown": "pressão 12 por 8"})
confere("/notas/gravar com pasta Saúde vira aviso e não escreve no Notas", st == 200 and d.get("destino") == "avisos" and av.do_servico("saude").nao_lidos() == 2, (st, d))
st, d = post("/notas/gravar", {"pasta": "Heimdall Finanças", "titulo": "Análise de março", "markdown": "gastei 500"})
confere("/notas/gravar com pasta de finanças vira aviso de finanças", st == 200 and d.get("destino") == "avisos" and av.do_servico("financas").nao_lidos() == 1, (st, d))
print("TUDO OK" if not falhas else f"{falhas} falha(s)")
sys.exit(1 if falhas else 0)
