#!/usr/bin/env python3
"""Dicionário de pronúncia do Heimdall: troca palavras por uma grafia que a voz do macOS lê do jeito certo
(por exemplo, "Heimdall" por "Háimdal"). Vale para o anúncio falado do subir.sh e para o áudio das notas.

Os dicionários são arquivos de texto, uma entrada por linha no formato  palavra = como falar  (linhas com # são comentário):
  pronuncias.txt        entradas que vêm com o projeto (o git reset pode sobrescrever)
  pronuncias.local.txt  as suas (não vai para o GitHub; ganha da outra quando a palavra se repete)
A busca ignora maiúsculas e só pega palavras inteiras. Sem dependências além do Python.

Para trazer o que você já tem no VoiceOver: python3 heimdall_voz.py --importar arquivo.csv (grava em pronuncias.local.txt).
Uso na linha de comando:  python3 heimdall_voz.py "Heimdall no ar"  ->  Háimdal no ar
"""
import csv
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ARQUIVOS = ("pronuncias.txt", "pronuncias.local.txt")


def carregar(raiz: Path = RAIZ) -> dict:
    d = {}
    for nome in ARQUIVOS:
        try:
            linhas = (raiz / nome).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for linha in linhas:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            de, para = (x.strip() for x in linha.split("=", 1))
            if de and para:
                d[de.lower()] = (de, para)   # o arquivo local vem depois e ganha
    return d


def aplicar(texto: str, raiz: Path = RAIZ) -> str:
    d = carregar(raiz)
    if not d:
        return texto
    chaves = sorted((v[0] for v in d.values()), key=len, reverse=True)   # "Heimdall-ai" antes de "Heimdall"
    padrao = re.compile(r"(?<![\w-])(" + "|".join(re.escape(c) for c in chaves) + r")(?![\w-]|\.\w)", re.I)
    return padrao.sub(lambda m: d[m.group(1).lower()][1], texto)


def importar_csv(arquivo: str) -> list:
    """Lê o arquivo de pronúncias exportado do VoiceOver (CSV) e devolve linhas 'palavra = como falar'.
    Pula o que não serve para texto corrido: números romanos e outras entradas que diferenciam maiúsculas, símbolos (aspas, reticências),
    substituições vazias e linhas que parecem dados pessoais (CPF, 'uso exclusivo')."""
    saida = []
    with open(arquivo, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            de, para = (r.get("Original Text") or "").strip(), (r.get("Replacement Text") or "").strip()
            if not de or not para or "=" in de or "=" in para or "\n" in de or "\n" in para:
                continue
            if (r.get("Ignore Case") or "").strip().upper() != "TRUE" or not re.search(r"[A-Za-zÀ-ÿ]", de):
                continue
            if re.search(r"\d{6,}|uso exclusivo|cpf", de + " " + para, re.I):
                continue
            saida.append(f"{de} = {para}")
    return saida


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--importar":
        novas = importar_csv(sys.argv[2])
        alvo = RAIZ / "pronuncias.local.txt"
        antigas = set(carregar(RAIZ))
        novas = [l for l in novas if l.split("=", 1)[0].strip().lower() not in antigas]
        with open(alvo, "a", encoding="utf-8") as f:
            f.write("\n".join(["# importado do VoiceOver"] + novas) + "\n")
        print(f"{len(novas)} entradas novas gravadas em {alvo.name}.")
    else:
        print(aplicar(" ".join(sys.argv[1:])))
