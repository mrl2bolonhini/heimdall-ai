#!/usr/bin/env python3
"""Testa os nomes do Studio Hub (ex-Memory, 26/11/2026): variáveis STUDIO_HUB_*, serviço no catálogo, endereços, pasta de arquivos antiga renomeada sem perder nada
e convidados liberados para o Hub. Os nomes antigos do .env (HEIMDALL_MEMORY_*, HEIMDALL_LIBRARY_*) são trocados por studio_config.renomear_antigas."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import http.client
import os
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="memory_compat_"))
os.environ.update({"STUDIO_DB_DIR": str(TMP / "db"), "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost"})
for k in [k for k in os.environ if k.startswith("STUDIO_HUB_")]:
    del os.environ[k]
import studio_config as hcf  # noqa: E402
import studio_memory as lib  # noqa: E402
import studio_memory_dados as dados  # noqa: E402
import studio_pastas  # noqa: E402
import studio_servico_web as web  # noqa: E402
import studio_servicos as servicos  # noqa: E402
import studio_usuarios as u  # noqa: E402

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({str(extra)[:300]})"))
    if not ok:
        falhas += 1


# 1. variáveis do .env com o prefixo STUDIO_HUB_
web.PROJECT_DIR = TMP
(TMP / ".env").write_text("STUDIO_HUB_PORT=9111\nSTUDIO_HUB_MAX_MB=9\nSTUDIO_HUB_HOSTS='novo.test,localhost'\nSTUDIO_OUTRA=1\n", encoding="utf-8")
web.carregar_env("STUDIO_HUB_")
confere("porta do Hub lida do .env", os.environ.get("STUDIO_HUB_PORT") == "9111", os.environ.get("STUDIO_HUB_PORT"))
confere("aspas do valor são tiradas", os.environ.get("STUDIO_HUB_HOSTS") == "novo.test,localhost", os.environ.get("STUDIO_HUB_HOSTS"))
confere("variável de outro serviço não entra", "STUDIO_OUTRA" not in os.environ)
confere("o prefixo do Hub é STUDIO_HUB_ (a chave interna continua memory)", lib.CFG.prefixo == "STUDIO_HUB_", lib.CFG.prefixo)
for k in ("STUDIO_HUB_PORT", "STUDIO_HUB_MAX_MB", "STUDIO_HUB_HOSTS"):
    os.environ.pop(k, None)

# 2. catálogo de serviços
sv = next(x for x in servicos.catalogo() if x["id"] == "memory")
confere("catálogo: serviço Hub", sv["nome"] == "Hub" and "hub" in sv.get("apelidos", []) and "library" not in sv.get("apelidos", []) and sv["script"] == ["studio_memory.py"], sv)
confere("catálogo: não sobra serviço library", not any(x["id"] == "library" for x in servicos.catalogo()))
confere("padrão do Hub: endereços hub e memory, sem o library", lib.CFG.hosts.startswith("hub.studiolibre.io") and "library" not in lib.CFG.hosts and "hub.studiolibre.io" in lib.CFG.hosts, lib.CFG.hosts)

# 3. .env antigo: os nomes HEIMDALL_MEMORY_* e HEIMDALL_LIBRARY_* viram STUDIO_HUB_*
hcf.ARQUIVO = TMP / "env_antigo"
hcf.ARQUIVO.write_text("HEIMDALL_MEMORY_PORT=8021\nHEIMDALL_LIBRARY_URL=https://x\nHEIMDALL_R2_BUCKET=b\nHEIMDALL_LAB_PORT=8010\n", encoding="utf-8")
trocadas = hcf.renomear_antigas()
texto = hcf.ARQUIVO.read_text(encoding="utf-8")
confere("renomear_antigas: Memory e Library viram HUB, o Lab vira STUDIO_LAB, nomes da Cloudflare ficam", "STUDIO_HUB_PORT=8021" in texto and "STUDIO_HUB_URL=https://x" in texto and "STUDIO_LAB_PORT=8010" in texto and "HEIMDALL_R2_BUCKET=b" in texto and "HEIMDALL_MEMORY" not in texto and len(trocadas) == 3, texto)
confere("renomear_antigas: segunda vez não muda nada", hcf.renomear_antigas() == [])

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
confere("pessoa: pasta antiga renomeada", studio_pastas.migrar(pessoa, "library", "memory") == pessoa / "memory" and (pessoa / "memory" / "b.txt").exists())
(TMP / "outra" / "library").mkdir(parents=True)
(TMP / "outra" / "memory").mkdir(parents=True)
(TMP / "outra" / "library" / "c.txt").write_text("c", encoding="utf-8")
confere("se as duas existem, nada é mexido", studio_pastas.migrar(TMP / "outra", "library", "memory") == TMP / "outra" / "memory" and (TMP / "outra" / "library" / "c.txt").exists())
confere("o banco mantém o nome histórico library.db", dados.caminho().name == "library.db")

# 5. convidados liberados para o Hub
hcf.ARQUIVO = TMP / "env_usuarios"
hcf.ARQUIVO.write_text("HEIMDALL_CFACCESS_EMAILS='dono@x.com'\nHEIMDALL_CFACCESS_CONVIDADOS='ana@x.com=memory+jogos;beto@x.com=memory'\n", encoding="utf-8")
conv = u.situacao()["convidados"]
confere("convidados do Hub", conv.get("ana@x.com") == ["jogos", "memory"] and conv.get("beto@x.com") == ["memory"], conv)
d = u.desejado()
confere("o Hub libera dono e os dois convidados", d["memory"] == ["ana@x.com", "beto@x.com", "dono@x.com"], d["memory"])
confere("endereço público padrão do Hub", u.host_publico("memory") == "hub.studiolibre.io", u.host_publico("memory"))

print(f"\n{falhas} falha(s)")
_sys.exit(1 if falhas else 0)
