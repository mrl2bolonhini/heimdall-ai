#!/usr/bin/env python3
"""Testa a troca de nome do Library para Memory (26/11/2026): o .env antigo continua valendo, o endereço antigo redireciona (301) só quando o novo está configurado,
a pasta de arquivos antiga é renomeada sem perder nada e convidados liberados com a chave antiga entram no Memory."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import os
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="memory_compat_"))
os.environ.update({"HEIMDALL_DB_DIR": str(TMP / "db"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
for k in [k for k in os.environ if k.startswith(("HEIMDALL_MEMORY_", "HEIMDALL_LIBRARY_"))]:
    del os.environ[k]
import heimdall_config as hcf  # noqa: E402
import heimdall_memory as lib  # noqa: E402
import heimdall_memory_dados as dados  # noqa: E402
import heimdall_pastas  # noqa: E402
import heimdall_servico_web as web  # noqa: E402
import heimdall_servicos as servicos  # noqa: E402
import heimdall_usuarios as u  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:300]})"))
    if not ok:
        falhas += 1


# 1. variáveis do .env: o prefixo antigo vale como o novo; se as duas existirem, a nova manda
web.PROJECT_DIR = TMP
(TMP / ".env").write_text("HEIMDALL_LIBRARY_PORT=9111\nHEIMDALL_LIBRARY_MAX_MB=7\nHEIMDALL_MEMORY_MAX_MB=9\nHEIMDALL_LIBRARY_HOSTS='velho.test,localhost'\nHEIMDALL_OUTRA=1\n", encoding="utf-8")
web.carregar_env("HEIMDALL_MEMORY_", legado="HEIMDALL_LIBRARY_")
confere("variável antiga vira a nova (porta)", os.environ.get("HEIMDALL_MEMORY_PORT") == "9111", os.environ.get("HEIMDALL_MEMORY_PORT"))
confere("quando as duas existem, a nova manda", os.environ.get("HEIMDALL_MEMORY_MAX_MB") == "9", os.environ.get("HEIMDALL_MEMORY_MAX_MB"))
confere("aspas do valor antigo são tiradas", os.environ.get("HEIMDALL_MEMORY_HOSTS") == "velho.test,localhost", os.environ.get("HEIMDALL_MEMORY_HOSTS"))
confere("variável de outro serviço não entra", "HEIMDALL_OUTRA" not in os.environ)
for k in ("HEIMDALL_MEMORY_PORT", "HEIMDALL_MEMORY_MAX_MB", "HEIMDALL_MEMORY_HOSTS"):
    os.environ.pop(k, None)

# 2. catálogo de serviços: id novo, nome novo, apelido antigo e porta antiga como reserva
sv = next(x for x in servicos.catalogo() if x["id"] == "memory")
confere("catálogo: Memory com apelido library", sv["nome"] == "Memory" and "library" in sv.get("apelidos", []) and sv["script"] == ["heimdall_memory.py"], sv)
confere("catálogo: não sobra serviço library", not any(x["id"] == "library" for x in servicos.catalogo()))

# 3. endereço antigo: responde; com HEIMDALL_MEMORY_URL, redireciona (301) para o novo
confere("padrão do Memory: endereço novo e antigo", lib.CFG.hosts.startswith("memory.heimdall-ai.tech") and lib.CFG.hosts_legados == {"library.heimdall-ai.tech"}, (lib.CFG.hosts, lib.CFG.hosts_legados))
hosts_ok = {"memory.heimdall-ai.tech", "localhost"} | set(lib.CFG.hosts_legados)
srv = ThreadingHTTPServer(("127.0.0.1", 0), web.criar_manipulador(lib.CFG, hosts_ok))
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORTA = srv.server_address[1]


def req(metodo, rota, host):
    c = http.client.HTTPConnection("127.0.0.1", PORTA, timeout=30)
    c.request(metodo, rota, headers={"Host": host})
    r = c.getresponse()
    return r.status, r.getheader("Location") or "", r.read()


os.environ.pop("HEIMDALL_MEMORY_URL", None)
st, loc, _ = req("GET", "/pesquisar?q=a", "library.heimdall-ai.tech")
confere("sem URL nova configurada, o endereço antigo segue servindo (pede entrada)", st == 303 and loc == "/entrar", (st, loc))
os.environ["HEIMDALL_MEMORY_URL"] = "https://memory.heimdall-ai.tech"
st, loc, _ = req("GET", "/pesquisar?q=a", "library.heimdall-ai.tech")
confere("com a URL nova, o endereço antigo redireciona 301 mantendo caminho e parâmetros", st == 301 and loc == "https://memory.heimdall-ai.tech/pesquisar?q=a", (st, loc))
st, loc, _ = req("GET", "/pesquisar", "memory.heimdall-ai.tech")
confere("o endereço novo não redireciona", st == 303 and loc == "/entrar", (st, loc))
st, _, corpo = req("GET", "/saude", "library.heimdall-ai.tech")
confere("a checagem de saúde responde no endereço antigo", st == 200 and corpo == b"ok", st)
st, _, _ = req("GET", "/pesquisar", "outro.test")
confere("endereço desconhecido segue recusado (421)", st == 421, st)
os.environ["HEIMDALL_MEMORY_URL"] = "https://library.heimdall-ai.tech"
st, loc, _ = req("GET", "/pesquisar", "library.heimdall-ai.tech")
confere("URL configurada igual ao endereço antigo não cria laço", st == 303, (st, loc))
os.environ.pop("HEIMDALL_MEMORY_URL", None)

# 4. pasta de arquivos: library/ vira memory/ sem copiar nem apagar (dono e pessoa)
(TMP / "library" / "files").mkdir(parents=True)
(TMP / "library" / "files" / "a.txt").write_text("conteudo", encoding="utf-8")
dados.PROJECT_DIR = TMP
base = dados.pasta_base()
confere("dono: pasta antiga renomeada para memory/", base == TMP / "memory" and not (TMP / "library").exists() and (TMP / "memory" / "files" / "a.txt").read_text() == "conteudo", base)
confere("depois de migrar, a chamada seguinte devolve a mesma pasta", dados.pasta_base() == TMP / "memory")
pessoa = TMP / "pessoa"
(pessoa / "library").mkdir(parents=True)
(pessoa / "library" / "b.txt").write_text("x", encoding="utf-8")
confere("pessoa: pasta antiga renomeada", heimdall_pastas.migrar(pessoa, "library", "memory") == pessoa / "memory" and (pessoa / "memory" / "b.txt").exists())
(TMP / "outra" / "library").mkdir(parents=True)
(TMP / "outra" / "memory").mkdir(parents=True)
(TMP / "outra" / "library" / "c.txt").write_text("c", encoding="utf-8")
confere("se as duas existem, nada é mexido", heimdall_pastas.migrar(TMP / "outra", "library", "memory") == TMP / "outra" / "memory" and (TMP / "outra" / "library" / "c.txt").exists())
confere("o banco mantém o nome histórico library.db", dados.caminho().name == "library.db")

# 5. convidados liberados com a chave antiga (library) entram no Memory
hcf.ARQUIVO = TMP / "env_usuarios"
hcf.ARQUIVO.write_text("HEIMDALL_CFACCESS_EMAILS='dono@x.com'\nHEIMDALL_CFACCESS_CONVIDADOS='ana@x.com=library+jogos;beto@x.com=memory'\n", encoding="utf-8")
conv = u.situacao()["convidados"]
confere("chave antiga library vira memory", conv.get("ana@x.com") == ["jogos", "memory"], conv)
confere("chave nova memory continua valendo", conv.get("beto@x.com") == ["memory"], conv)
d = u.desejado()
confere("o Memory libera dono e os dois convidados", d["memory"] == ["ana@x.com", "beto@x.com", "dono@x.com"], d["memory"])
confere("endereço público padrão do Memory", u.host_publico("memory") == "memory.heimdall-ai.tech", u.host_publico("memory"))

print(f"\n{falhas} falha(s)")
_sys.exit(1 if falhas else 0)
