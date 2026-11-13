#!/usr/bin/env python3
"""Dicionário de pronúncia do Heimdall: troca palavras por uma grafia que a voz do macOS lê do jeito certo
(por exemplo, "Heimdall" por "Háimdal"). Vale para o anúncio falado do subir.sh e para o áudio das notas.

Os dicionários são arquivos de texto, uma entrada por linha no formato  palavra = como falar  (linhas com # são comentário):
  pronuncias.txt        entradas que vêm com o projeto (o git reset pode sobrescrever)
  pronuncias.local.txt  as suas (não vai para o GitHub; ganha da outra quando a palavra se repete)
A busca ignora maiúsculas e só pega palavras inteiras. Sem dependências além do Python.

Uso na linha de comando:  python3 heimdall_voz.py "Heimdall no ar"  ->  Háimdal no ar
"""
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


if __name__ == "__main__":
    print(aplicar(" ".join(sys.argv[1:])))
