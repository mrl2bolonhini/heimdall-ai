#!/usr/bin/env python3
"""Testa a parte do EventKit que não depende do macOS: o texto devolvido, a escolha entre EventKit e AppleScript e o recuo."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys
import time
from pathlib import Path

sys.path.insert(0, str(RAIZ))
import studio_eventkit as ek  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + repr(detalhe)[:300])


# 2. escolha entre EventKit e AppleScript
chamadas = []
ek._registro.clear()
ek.ATIVO = True
ek._falha_ate = 0.0
ek.registrar("SCRIPT_OK", lambda a, b: chamadas.append((a, b)) or "criado")
confere("script registrado: EventKit resolve", ek.tentar("SCRIPT_OK", ("x", "y")) == (True, "criado") and chamadas == [("x", "y")], chamadas)
confere("script não registrado: usa o AppleScript", ek.tentar("OUTRO", ()) == (False, None))


def sem_permissao():
    chamadas.append("tentou")
    raise ek.EKIndisponivel("negado")


ek.registrar("SCRIPT_NEGADO", sem_permissao)
chamadas.clear()
confere("sem permissão: recua para o AppleScript", ek.tentar("SCRIPT_NEGADO", ()) == (False, None))
confere("e não insiste logo em seguida (nem para os outros scripts)", ek.tentar("SCRIPT_NEGADO", ()) == (False, None) and ek.tentar("SCRIPT_OK", ("a", "b")) == (False, None) and chamadas == ["tentou"], chamadas)
ek._falha_ate = time.time() - 1
confere("passado o prazo, tenta de novo", ek.tentar("SCRIPT_OK", ("a", "b")) == (True, "criado"))


def quebrado():
    raise AttributeError("bug")


ek.registrar("SCRIPT_BUG", quebrado)
confere("erro inesperado: recua só desta vez", ek.tentar("SCRIPT_BUG", ()) == (False, None) and ek._falha_ate < time.time())
ek.ATIVO = False
confere("STUDIO_EVENTKIT=0 desliga", ek.tentar("SCRIPT_OK", ("a", "b")) == (False, None))
ek.ATIVO = True

# 3. integração com o agente: com o EventKit resolvendo, o AppleScript não roda e nenhum app é aberto
import studio_agente as ag  # noqa: E402
registrados = [ag.AS_EVENTO, ag.AS_EVENTO_HORARIO, ag.AS_LEMBRETE, ag.AS_PREPARAR_CAL, ag.AS_PREPARAR_LEM]
confere("os 5 scripts de Lembretes e Calendário estão registrados", all(s in ek._registro for s in registrados))
ek._falha_ate = 0.0
abriu = []
ag.subprocess = type("S", (), {"run": staticmethod(lambda *a, **k: abriu.append(a) or (_ for _ in ()).throw(AssertionError("rodou subprocess"))),
                               "TimeoutExpired": Exception})
ek.registrar(ag.AS_LEMBRETE, lambda *a: "criado")
confere("agente: lembrete pelo EventKit não abre app nem roda osascript", ag.osascript(ag.AS_LEMBRETE, "t", "2026", "11", "20", "9", "n", "Heimdall") == "criado" and not abriu, abriu)

print("\nTUDO OK" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)
