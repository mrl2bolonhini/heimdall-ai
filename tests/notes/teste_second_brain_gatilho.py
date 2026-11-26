#!/usr/bin/env python3
"""Testa que o Second Brain só abre o Notas quando há nota nova (gravação do Heimdall ou mudança no banco do Notas)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import sys
import time
from pathlib import Path

sys.path.insert(0, str(RAIZ))
import heimdall_agente as ag  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + repr(detalhe)[:300])


chamadas = []
ag.ids_privados = lambda: set()
ag.osascript = lambda script, *a, **k: (chamadas.append(script[:30]) or "")
mtime = [None]
ag._mtime_notas = lambda: mtime[0]
aberto = [True]
ag._notas_aberto = lambda: aberto[0]


def rodar():
    chamadas.clear()
    ag.notas_alteradas(0.0, 120, 3)
    return len(chamadas)


# 1. banco visível e sem mudança: nada de abrir o Notas
mtime[0] = time.time() - 3600
ag._verificado_mtime = 0.0
confere("primeira verificação consulta o Notas", rodar() > 0)
confere("banco quieto e já verificado: não consulta o Notas", rodar() == 0)
confere("repete sem consultar", rodar() == 0)

# 2. banco mudou: consulta
mtime[0] = time.time() - 3000
confere("banco mudou: consulta o Notas", rodar() > 0)
confere("e depois volta a não consultar", rodar() == 0)

# 3. mudança recente (ainda não 'quieta'): continua consultando até ficar quieta
mtime[0] = time.time() - 10
confere("mudança recente: consulta", rodar() > 0)
confere("ainda recente: consulta de novo (a nota pode ter ficado quieta)", rodar() > 0)

# 4. gravação do Heimdall força a consulta mesmo sem mudança no arquivo
mtime[0] = time.time() - 7200
rodar(); rodar()
ag._gravacao_nova.set()
confere("gravação nova do Heimdall: consulta", rodar() > 0)
confere("sem nova gravação: não consulta", rodar() == 0)

# 5. macOS não deixa ver o banco: só consulta depois de uma gravação (varredura desligada)
mtime[0] = None
ag.VARREDURA_MIN = 0
confere("sem acesso ao banco e sem gravação: não abre o Notas", rodar() == 0)
ag._gravacao_nova.set()
confere("sem acesso ao banco, mas com gravação nova: consulta", rodar() > 0)

# 6. varredura opcional
ag.VARREDURA_MIN = 1
ag._ultima_varredura = 0.0
confere("varredura ligada: consulta de vez em quando", rodar() > 0)
confere("e não de novo logo em seguida", rodar() == 0)

# 7. falha na consulta não marca como verificado
mtime[0] = time.time() - 9000
ag._verificado_mtime = 0.0
def quebra(*a, **k):
    raise RuntimeError("falhou")
ag.osascript = quebra
try:
    ag.notas_alteradas(0.0, 120, 3)
except RuntimeError:
    pass
ag.osascript = lambda script, *a, **k: (chamadas.append(script[:30]) or "")
confere("consulta que falhou é tentada de novo", rodar() > 0)

# 8. app Notas fechado: não abre só para consultar (a menos que o Heimdall tenha acabado de gravar)
aberto[0] = False
ag.SO_COM_NOTAS_ABERTO = True
mtime[0] = time.time() - 500
ag._verificado_mtime = 0.0
ag._gravacao_nova.clear()
confere("Notas fechado e banco mudou: não abre o app", rodar() == 0)
aberto[0] = True
confere("Notas aberto: consulta, pois o banco continua sem verificação", rodar() > 0)
aberto[0] = False
mtime[0] = time.time() - 400
confere("Notas fechado de novo: não consulta", rodar() == 0)
ag._gravacao_nova.set()
confere("gravação do Heimdall com Notas fechado: consulta", rodar() > 0)
aberto[0] = False
ag.SO_COM_NOTAS_ABERTO = False
mtime[0] = time.time() - 300
confere("STUDIO_NOTAS_ABRIR_APP=1 devolve o comportamento antigo", rodar() > 0)

print("\nTUDO OK" if not falhas else f"\nFALHAS: {falhas}")
sys.exit(1 if falhas else 0)
