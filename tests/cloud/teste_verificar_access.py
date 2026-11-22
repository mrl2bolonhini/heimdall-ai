#!/usr/bin/env python3
"""Teste do verificar_access.py com servidores locais que imitam o Access, um site aberto e um endereço sem resposta."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import verificar_access as v

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f"\n     {extra}"))
    falhas += 0 if ok else 1


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/access":
            self.send_response(302)
            self.send_header("Location", "https://exemplo.cloudflareaccess.com/cdn-cgi/access/login/x")
        elif self.path == "/aberto":
            self.send_response(200)
        elif self.path == "/outro":
            self.send_response(302)
            self.send_header("Location", "https://login.exemplo.test/")
        else:
            self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"
confere("redireciona para o Access: protegido", v.verificar(base + "/access")[0] == 0)
confere("responde 200 sem pedir entrada: aberto", v.verificar(base + "/aberto")[0] == 1)
confere("redireciona para outro login que não é o Access: aberto", v.verificar(base + "/outro")[0] == 1)
confere("404 de um servidor qualquer: aberto", v.verificar(base + "/nada")[0] == 1)
confere("sem resposta: 2", v.verificar("http://127.0.0.1:9/", 2)[0] == 2)
srv.shutdown()
print("\n" + ("TUDO OK" if not falhas else f"{falhas} FALHA(S)"))
sys.exit(1 if falhas else 0)
