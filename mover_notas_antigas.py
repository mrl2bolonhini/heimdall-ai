#!/usr/bin/env python3
"""Copia as notas das pastas antigas do app Notas (Heimdall-ai e pastas soltas) para a raiz Studio Hub.

Sem argumentos: só conta o que há para copiar (nada é alterado).
Com --executar: COPIA as notas que ainda não existem no destino. Nada é movido nem apagado: as pastas antigas ficam
intactas e só o usuário as apaga, depois de conferir. Pode rodar de novo sem duplicar (notas com o mesmo título são puladas).
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_agente as ag  # noqa: E402

# Reaproveita o trecho do AppleScript que acha ou cria a pasta pelo caminho.
_src = ag.AS_GRAVAR
HANDLER = _src[_src.index("on partes(txt)"):_src.index("end achar_pasta\n") + len("end achar_pasta\n")]

AS_COPIAR = "-- heimdall:copiar\n" + HANDLER + r'''on buscar(caminho)
	tell application "Notes"
		tell default account
			set atual to missing value
			repeat with nm in my partes(caminho)
				set nome to contents of nm
				set achada to missing value
				if atual is missing value then
					set cand to every folder
				else
					set cand to every folder of atual
				end if
				repeat with f in cand
					if (name of f) is nome then
						set vale to true
						if atual is missing value then
							try
								set vale to ((class of (container of f)) is account)
							on error
								set vale to true
							end try
						end if
						if vale then
							set achada to contents of f
							exit repeat
						end if
					end if
				end repeat
				if achada is missing value then return missing value
				set atual to achada
			end repeat
			return atual
		end tell
	end tell
end buscar
on run argv
	set oldPath to item 1 of argv
	set newPath to item 2 of argv
	set modo to item 3 of argv
	tell application "Notes"
		tell default account
			set oldF to my buscar(oldPath)
			if oldF is missing value then return "ausente"
			set lista to every note of oldF
			if modo is not "copiar" then
				set newF to my buscar(newPath)
				if newF is missing value then return (count of lista) as string
				set jaTem to name of every note of newF
			else
				set newF to my achar_pasta(newPath)
				set jaTem to name of every note of newF
			end if
			set feitas to 0
			repeat with x in lista
				set t to name of x
				if jaTem does not contain t then
					if modo is "copiar" then make new note at newF with properties {body:(body of x)}
					set feitas to feitas + 1
				end if
			end repeat
			return feitas as string
		end tell
	end tell
end run
'''

RAIZ = ag.RAIZ_NOTAS or "Studio Hub"
ANTIGA = ag.RAIZ_ANTIGA
MAPA = [
    # (origem no app Notas, destino). Subpastas da raiz antiga e pastas soltas de versões ainda mais antigas.
    (f"{ANTIGA}/Digest", f"{RAIZ}/Digest"),
    (f"{ANTIGA}/Monitor de Privacidade", f"{RAIZ}/Monitor de Privacidade"),
    (f"{ANTIGA}/Second Brain", f"{RAIZ}/Second Brain"),
    (f"{ANTIGA}/Saúde", f"{RAIZ}/Saúde"),
    (f"{ANTIGA}/Segurança", f"{RAIZ}/Segurança"),
    (f"{ANTIGA}/GitOps", f"{RAIZ}/GitOps"),
    ("Digest", f"{RAIZ}/Digest"),
    ("Monitor de Privacidade", f"{RAIZ}/Monitor de Privacidade"),
    ("Cérebro", f"{RAIZ}/Second Brain"),
    ("Heimdall Cérebro", f"{RAIZ}/Second Brain"),
    ("Heimdall Digest", f"{RAIZ}/Digest"),
    ("Heimdall Privacidade", f"{RAIZ}/Monitor de Privacidade"),
    ("Heimdall Finanças", f"{RAIZ}/Studio Finance"),
    ("Heimdall Notas", f"{RAIZ}/Catálogo"),
]
for tema in sorted(ag.temas_conhecimento()):
    MAPA.append((f"{ANTIGA}/Estudos/{tema}", f"{RAIZ}/Estudos/{tema}"))
    MAPA.append((tema, f"{RAIZ}/Estudos/{tema}"))


def rodar(antiga, destino, modo):
    return ag.osascript(AS_COPIAR, antiga, destino, modo)


def main():
    executar = "--executar" in sys.argv
    print("Modo:", "COPIAR" if executar else "só contar (use --executar para copiar)")
    total = 0
    for antiga, destino in MAPA:
        try:
            r = rodar(antiga, destino, "copiar" if executar else "ver")
        except Exception as e:  # noqa: BLE001
            print(f"  {antiga}: ERRO {str(e)[:150]}")
            continue
        if r == "ausente":
            continue
        n = int(r or 0)
        total += n
        print(f"  {antiga} -> {destino}: {n} nota(s)")
    print(("Copiadas: " if executar else "Para copiar: ") + str(total))
    if executar:
        print("As pastas antigas continuam intactas. Confira o Studio Hub no Notas e apague as antigas à mão, quando quiser.")


if __name__ == "__main__":
    main()
