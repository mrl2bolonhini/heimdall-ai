#!/usr/bin/env python3
"""Testes do dicionário de pronúncia (heimdall_voz.py)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heimdall_voz as v

falhas = 0


def confere(nome, cond):
    global falhas
    print(("ok   " if cond else "FALHOU ") + nome)
    falhas += 0 if cond else 1


with tempfile.TemporaryDirectory() as t:
    r = Path(t)
    (r / "pronuncias.txt").write_text("# c\nHeimdall-ai = raimdall-ei-ai\nHeimdall = Raimdall\nn8n = ene oito ene\nruim sem igual\n", encoding="utf-8")
    confere("troca a palavra", v.aplicar("Heimdall no ar", r) == "Raimdall no ar")
    confere("ignora maiúsculas", v.aplicar("o HEIMDALL subiu", r) == "o Raimdall subiu")
    confere("a entrada mais longa ganha", v.aplicar("Heimdall-ai pronto", r) == "raimdall-ei-ai pronto")
    confere("só palavra inteira", v.aplicar("Heimdallx e xHeimdall", r) == "Heimdallx e xHeimdall")
    confere("n8n", v.aplicar("rode o n8n agora", r) == "rode o ene oito ene agora")
    confere("sem dicionário devolve igual", v.aplicar("Heimdall", r / "nada") == "Heimdall")
    (r / "pronuncias.local.txt").write_text("Heimdall = Raimdal\n", encoding="utf-8")
    confere("o arquivo local ganha", v.aplicar("Heimdall", r) == "Raimdal")
    confere("linha ruim ignorada", "ruim" not in v.carregar(r))
confere("o dicionário do projeto fala Raimdall", v.aplicar("Heimdall-ai e Heimdall") == "raimdall-ei-ai e Raimdall")
confere("pronuncias.txt tem as entradas do VoiceOver", v.aplicar("abra o GitHub e o Whatsapp") == "abra o Guitirrâb e o Uatzap")
with tempfile.TemporaryDirectory() as t2:
    c = Path(t2) / "p.csv"
    c.write_text("Original Text,Replacement Text,Phonemes,Languages,Voice IDs,Active,Ignore Case,App Bundle IDs\nWhatsapp,Uatzap,,pt-BR,,FALSE,TRUE,\nII,2,,pt-BR,,FALSE,FALSE,\n\"\"\"\",Aspas,,pt-BR,,FALSE,TRUE,\nUso exclusivo de X - CPF: 12345678901,x,,pt-BR,,FALSE,TRUE,\nVazio, ,,pt-BR,,FALSE,TRUE,\n", encoding="utf-8")
    confere("importar do VoiceOver pula numerais, símbolos, vazios e CPF", v.importar_csv(str(c)) == ["Whatsapp = Uatzap"])
print("Tudo certo." if not falhas else f"{falhas} falha(s).")
sys.exit(1 if falhas else 0)
