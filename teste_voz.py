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

# --- áudio pelo atalho do app Atalhos (shortcuts e afconvert de mentira) ---
import os
import stat
with tempfile.TemporaryDirectory() as t3:
    b = Path(t3) / "bin"
    b.mkdir()
    (b / "shortcuts").write_text("#!/bin/bash\n# shortcuts run NOME -i ENTRADA -o SAIDA\n[ \"$2\" = Quebrado ] && { echo 'não achei' >&2; exit 1; }\n"
                                 "[ \"$2\" = Mudo ] && { : > \"$6\"; exit 0; }\ncp \"$4\" \"$6\"; python3 -c \"open('$6','ab').write(b'x'*3000)\"\n", encoding="utf-8")
    (b / "afconvert").write_text("#!/bin/bash\n# afconvert -f m4af -d aac ENTRADA SAIDA\ncp \"$5\" \"$6\"\n", encoding="utf-8")
    for x in b.iterdir():
        x.chmod(x.stat().st_mode | stat.S_IEXEC)
    os.environ["PATH"] = str(b) + os.pathsep + os.environ["PATH"]
    os.environ["HEIMDALL_VOZ_ATALHO"] = "Narrator"
    os.environ["HEIMDALL_DB_DIR"] = t3
    import heimdall_agente as ag
    ag.sys.platform = "darwin"
    pasta = Path(t3) / "cofre"
    caminho, motivo = ag.fazer_audio("Nota de teste", "O Heimdall subiu. Veja https://exemplo.com agora.", pasta)
    confere("atalho gera o m4a", caminho is not None and caminho.name == "nota-de-teste.m4a" and caminho.stat().st_size > 2000 and motivo == "")
    confere("o texto vai com a pronúncia e sem links", b"Raimdall subiu" in caminho.read_bytes() and b"exemplo.com" not in caminho.read_bytes())
    confere("sem sobras do atalho", not list((pasta / "audio").glob("*.atalho")) and not list((pasta / "audio").glob("*.aiff")))
    ag.ATALHO = "Quebrado"
    confere("atalho quebrado dá motivo", "falhou" in ag.audio_por_atalho(str(Path(t3) / "x.txt"), pasta / "audio" / "y"))
    ag.ATALHO = "Mudo"
    confere("atalho sem áudio dá motivo", "não devolveu áudio" in ag.audio_por_atalho(str(Path(t3) / "x.txt"), pasta / "audio" / "z"))
print("Tudo certo." if not falhas else f"{falhas} falha(s).")
sys.exit(1 if falhas else 0)
