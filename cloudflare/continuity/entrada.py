#!/usr/bin/env python3
"""Ponto de entrada do contêiner de continuidade: restaura a última cópia dos bancos, sobe os sites que não dependem do Mac e responde /health na porta 8080.

Roda dentro da imagem (/app). Os sites sobem em modo de leitura (HEIMDALL_CONTINUIDADE_MODO=1): sem coletores nem vigias que gravariam no banco restaurado.
Se a restauração falhar, sai com erro: o Worker de entrada mostra a página de indisponibilidade em vez de servir dados vazios.
"""
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(os.environ.get("STUDIO_RAIZ") or "/app")   # na imagem o código fica em /app
sys.path.insert(0, str(RAIZ))

# (módulo, variável da porta, porta): as mesmas portas do start_studio.sh
SERVICOS = [
    ("studio_finance.py", "STUDIO_FINANCE_PORT", 8016),
    ("studio_painel_saude.py", "STUDIO_SAUDE_PAINEL_PORT", 8013),
    ("studio_news.py", "STUDIO_NEWS_PORT", 8012),
    ("studio_learn.py", "STUDIO_LEARN_PORT", 8019),
    ("studio_jogos.py", "STUDIO_JOGOS_PORT", 8014),
    ("studio_account.py", "STUDIO_ACCOUNT_PORT", 8018),
]
estado = {"pronto": False, "quando": "", "erro": ""}
FILHOS = {}   # processos dos sites, para quem precisar encerrá-los (testes)


class Saude(BaseHTTPRequestHandler):
    def do_GET(self):
        corpo = (f"ok {estado['quando']}" if estado["pronto"] else f"iniciando {estado['erro']}").encode()
        self.send_response(200 if estado["pronto"] else 503)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("X-Heimdall-Copia", estado["quando"])
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


def _servir_saude() -> None:
    try:
        ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("STUDIO_SAUDE_PORTA", "8080"))), Saude).serve_forever()
    except OSError:   # porta já ocupada (outra instância do /health): segue sem ele
        pass


def subir(modulo: str, var: str, porta: int) -> subprocess.Popen:
    env = dict(os.environ, **{var: str(porta), "HEIMDALL_CONTINUIDADE_MODO": "1"})
    return subprocess.Popen([sys.executable, str(RAIZ / modulo)], cwd=str(RAIZ), env=env)


def main() -> int:
    os.environ["HEIMDALL_CONTINUIDADE_MODO"] = "1"
    threading.Thread(target=_servir_saude, daemon=True).start()
    import studio_continuidade as hc
    try:
        r = hc.restaurar(RAIZ)
    except Exception as ex:  # noqa: BLE001
        estado["erro"] = str(ex)[:200]
        sys.stderr.write(f"Falha ao restaurar a cópia: {ex}\n")
        time.sleep(5)   # dá tempo de o /health mostrar o motivo
        return 1
    estado["quando"] = r["quando"]
    sys.stderr.write(f"Cópia de {r['quando']} restaurada ({len(r['arquivos'])} arquivos).\n")
    filhos = FILHOS
    filhos.update({m: subir(m, v, p) for m, v, p in SERVICOS if (RAIZ / m).exists()})
    estado["pronto"] = True
    reinicios = {m: 0 for m in filhos}
    while True:   # supervisor simples: reinicia um site que cair, no máximo 5 vezes cada
        time.sleep(5)
        for m, v, p in SERVICOS:
            f = filhos.get(m)
            if f is not None and f.poll() is not None and reinicios[m] < 5:
                reinicios[m] += 1
                sys.stderr.write(f"{m} saiu com código {f.returncode}; reiniciando ({reinicios[m]}/5).\n")
                filhos[m] = subir(m, v, p)


if __name__ == "__main__":
    sys.exit(main())
