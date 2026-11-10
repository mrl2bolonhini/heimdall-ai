#!/usr/bin/env python3
"""Move as notas das pastas antigas (soltas) do app Notas para as subpastas novas de Heimdall-ai.

Sem argumentos: só conta o que há em cada pasta antiga (nada é alterado).
Com --executar: move as notas. O app Notas não tem "copiar"; mover mantém o conteúdo e deixa a pasta antiga vazia.
As pastas antigas não são apagadas: apague-as à mão depois de conferir.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heimdall_agente as ag  # noqa: E402

# Reaproveita o trecho do AppleScript que acha ou cria a pasta pelo caminho.
_src = ag.AS_GRAVAR
HANDLER = _src[_src.index("on partes(txt)"):_src.index("end achar_pasta\n") + len("end achar_pasta\n")]

AS_MOVER = "-- heimdall:mover\n" + HANDLER + r'''on run argv
	set oldName to item 1 of argv
	set newPath to item 2 of argv
	set modo to item 3 of argv
	tell application "Notes"
		tell default account
			set oldF to missing value
			repeat with f in (every folder)
				if (name of f) is oldName then
					set vale to true
					try
						set vale to ((class of (container of f)) is account)
					on error
						set vale to true
					end try
					if vale then
						set oldF to contents of f
						exit repeat
					end if
				end if
			end repeat
			if oldF is missing value then return "ausente"
			set n to count of notes of oldF
			if modo is not "mover" then return n as string
			if n is 0 then return "0"
			set newF to my achar_pasta(newPath)
			set lista to every note of oldF
			repeat with x in lista
				move (contents of x) to newF
			end repeat
			return n as string
		end tell
	end tell
end run
'''

RAIZ = ag.RAIZ_NOTAS or "Heimdall-ai"
MAPA = [
    ("Digest", f"{RAIZ}/Digest"),
    ("Monitor de Privacidade", f"{RAIZ}/Monitor de Privacidade"),
    ("Cérebro", f"{RAIZ}/Second Brain"),
    ("Heimdall Cérebro", f"{RAIZ}/Second Brain"),
    ("Heimdall Digest", f"{RAIZ}/Digest"),
    ("Heimdall Privacidade", f"{RAIZ}/Monitor de Privacidade"),
]
for tema in sorted(ag.temas_conhecimento()):
    MAPA.append((tema, f"{RAIZ}/Estudos/{tema}"))


def rodar(antiga, destino, modo):
    return ag.osascript(AS_MOVER, antiga, destino, modo)


def main():
    executar = "--executar" in sys.argv
    print("Modo:", "MOVER" if executar else "só contar (use --executar para mover)")
    total = 0
    for antiga, destino in MAPA:
        try:
            r = rodar(antiga, destino, "mover" if executar else "ver")
        except Exception as e:  # noqa: BLE001
            print(f"  {antiga}: ERRO {str(e)[:150]}")
            continue
        if r == "ausente":
            continue
        n = int(r or 0)
        total += n
        print(f"  {antiga} -> {destino}: {n} nota(s)")
    print(("Movidas: " if executar else "Para mover: ") + str(total))
    if executar:
        print("Confira no Notas e apague à mão as pastas antigas que ficaram vazias.")


if __name__ == "__main__":
    main()
