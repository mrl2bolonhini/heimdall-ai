#!/usr/bin/env python3
"""Testa heimdall_pessoas.py e a pessoa dentro da sessão: id estável, caminhos, contexto, tarefas em segundo plano e tokens de convidado."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import sys
import tempfile
import threading
from pathlib import Path

os.environ.pop("HEIMDALL_PESSOAS", None)
import heimdall_cloud as nuvem  # noqa: E402
import heimdall_pessoas as pe  # noqa: E402
nuvem.SENHA_HASH = nuvem.SENHA_HASH or "teste"
nuvem.TOTP_SEGREDO = nuvem.TOTP_SEGREDO or "JBSWY3DPEHPK3PXP"

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f" ({extra})"))
    if not ok:
        falhas += 1


base = Path(tempfile.mkdtemp()) / "db"
ana, beto = pe.id_da("ana@x.com"), pe.id_da("Beto@Y.com ")
confere("id é estável, ignora maiúsculas e espaços, e não mostra o e-mail", pe.id_da("ANA@x.com") == ana and pe.id_da("beto@y.com") == beto and ana != beto and "ana" not in ana and pe.valido(ana))
for ruim in ("", "sem-arroba", None):
    try:
        pe.id_da(ruim)
        confere(f"e-mail inválido {ruim!r} é recusado", False)
    except pe.ErroPessoa:
        confere(f"e-mail inválido {ruim!r} é recusado", True)
confere("ids forjados não valem", not pe.valido("../x") and not pe.valido("p123") and not pe.valido("P" + "0" * 12) and pe.valido("dono"))
confere("sem nada definido, é o dono, com o caminho de sempre", pe.atual() == "dono" and pe.raiz(base) == base)
with pe.definir(ana):
    confere("com a pessoa definida, o caminho é o dela (db/pessoas/<id>)", pe.atual() == ana and pe.raiz(base) == base / "pessoas" / ana and (base / "pessoas" / ana).is_dir())
    confere("permissão só do dono do Mac", oct((base / "pessoas" / ana).stat().st_mode & 0o777) == "0o700")
    with pe.definir(beto):
        confere("blocos aninhados trocam e voltam", pe.atual() == beto and pe.raiz(base) == base / "pessoas" / beto)
    confere("volta para a anterior", pe.atual() == ana)
confere("fora do bloco volta ao dono", pe.atual() == "dono")
try:
    with pe.definir("../../etc"):
        pass
    confere("pessoa forjada no contexto é recusada", False)
except pe.ErroPessoa:
    confere("pessoa forjada no contexto é recusada", True)
try:
    pe.raiz(base, "../../etc")
    confere("raiz recusa id forjado", False)
except pe.ErroPessoa:
    confere("raiz recusa id forjado", True)

# segundo plano
visto = []
with pe.definir(ana):
    f = pe.vincular(lambda: visto.append(pe.atual()))
t = threading.Thread(target=f)
t.start()
t.join()
sem = []
t = threading.Thread(target=lambda: sem.append(pe.atual()))
t.start()
t.join()
confere("tarefa vinculada leva a pessoa para outra thread", visto == [ana])
confere("thread sem vínculo cai no dono (nunca em outra pessoa)", sem == ["dono"])

# listar
confere("existentes: dono e as pastas válidas", pe.existentes(base) == ["dono", *sorted([ana, beto])] or pe.existentes(base) == ["dono", ana])
(base / "pessoas" / "lixo").mkdir()
confere("pasta com nome fora do padrão é ignorada", "lixo" not in pe.existentes(base))

# desligado
os.environ["HEIMDALL_PESSOAS"] = "0"
with pe.definir(ana):
    confere("HEIMDALL_PESSOAS=0 usa sempre os dados do dono", pe.raiz(base) == base and pe.e_dono())
    confere("existentes com o recurso desligado: só o dono", pe.existentes(base) == ["dono"])
os.environ.pop("HEIMDALL_PESSOAS")

# tokens
tk, s = nuvem.nova_sessao("*")
confere("sessão do dono tem pessoa dono", s["pessoa"] == "dono")
tk, s = nuvem.nova_sessao("learn", ana)
confere("sessão de convidado carrega a pessoa, vale só no serviço dela", s["pessoa"] == ana and nuvem.sessao_valida(tk, "learn")["pessoa"] == ana and nuvem.sessao_valida(tk, "notas") is None)
partes = tk.split(".")
forjado = ".".join(partes[:2] + [partes[2].replace(ana, beto)] + partes[3:])
confere("trocar a pessoa dentro do token invalida a assinatura", nuvem.sessao_valida(forjado, "learn") is None)
dono_forjado = ".".join(partes[:2] + [partes[2].replace("~" + ana, "")] + partes[3:])
confere("tirar a pessoa do token também invalida a assinatura (não vira dono)", nuvem.sessao_valida(dono_forjado, "learn") is None)
tk_antigo, s = nuvem.nova_sessao("learn")
confere("sessão de convidado sem pessoa fica com pessoa vazia (o Learn a recusa)", s["pessoa"] == "" and not pe.valido(s["pessoa"]))
for ruim in ("dono", "../x", "p12"):
    try:
        nuvem.nova_sessao("learn", ruim)
        confere(f"token com pessoa {ruim!r} é recusado", False)
    except ValueError:
        confere(f"token com pessoa {ruim!r} é recusado", True)
try:
    nuvem.nova_sessao("*", ana)
    confere("sessão do dono não aceita pessoa", False)
except ValueError:
    confere("sessão do dono não aceita pessoa", True)
nuvem.encerrar_sessao(tk)
confere("encerrar a sessão do convidado funciona", nuvem.sessao_valida(tk, "learn") is None)

print("\n" + ("Tudo certo." if not falhas else f"{falhas} falha(s)."))
sys.exit(1 if falhas else 0)
