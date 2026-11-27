#!/usr/bin/env python3
"""Teste das configurações (heimdall_config.py): ler, salvar, remover e o catálogo do código, sempre num .env de mentira."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(RAIZ))
import heimdall_config as c  # noqa: E402

falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f"\n     {detalhe}"))
    falhas += 0 if ok else 1


tmp = Path(tempfile.mkdtemp())
c.ARQUIVO = tmp / ".env"
c.ARQUIVO.write_text("# comentário\nSTUDIO_A=1\nexport STUDIO_B=\"dois\"\nSTUDIO_C='tres'\nSTUDIO_A=repetida\n\nsem igual\n", encoding="utf-8")
lido = {d["nome"]: d["valor"] for d in c.ler()}
confere("ler: tira aspas e export, ignora comentário e linha sem igual", lido == {"STUDIO_B": "dois", "STUDIO_C": "tres", "STUDIO_A": "repetida"}, str(lido))
confere("ler: nome repetido vale pela última linha", [d["nome"] for d in c.ler()][-1] == "STUDIO_A")
confere("salvar: troca o valor e some com as repetições", c.salvar("STUDIO_A", "novo") == "" and c.ARQUIVO.read_text().count("STUDIO_A=") == 1
        and "STUDIO_A='novo'" in c.ARQUIVO.read_text())
confere("salvar: preserva o comentário e as outras linhas", "# comentário" in c.ARQUIVO.read_text() and "STUDIO_C='tres'" in c.ARQUIVO.read_text())
confere("salvar: variável nova entra no fim", c.salvar("STUDIO_NOVA", "x y") == "" and c.ARQUIVO.read_text().rstrip().endswith("STUDIO_NOVA='x y'"))
confere("salvar: o arquivo fica com permissão 600 e há cópia em .env.bak", stat.S_IMODE(c.ARQUIVO.stat().st_mode) == 0o600 and (tmp / ".env.bak").exists())
confere("salvar: recusa aspa simples, quebra de linha e nome inválido", all(c.salvar(n, v) for n, v in (("STUDIO_X", "a'b"), ("STUDIO_X", "a\nb"), ("1X", "a"), ("A B", "a"), ("", "a"))))
confere("salvar: nada foi gravado nas recusas", "STUDIO_X" not in c.ARQUIVO.read_text())
confere("remover: tira a variável e deixa o resto", c.remover("STUDIO_C") == "" and "STUDIO_C" not in c.ARQUIVO.read_text() and "STUDIO_B" in c.ARQUIVO.read_text())
confere("salvar valor com $ e espaço fica entre aspas simples, sem expandir", c.salvar("STUDIO_D", "a $B `x`") == "" and "STUDIO_D='a $B `x`'" in c.ARQUIVO.read_text())
os.remove(c.ARQUIVO)
confere("sem .env: ler devolve lista vazia e salvar cria o arquivo", c.ler() == [] and c.salvar("STUDIO_E", "1") == "" and c.ler()[0]["nome"] == "STUDIO_E")
op = c.opcoes_do_codigo()
confere("catálogo: acha opções do código com e sem valor padrão", "STUDIO_CONTROLS_ATRASO_CURSOR" in op and op["STUDIO_CONTROLS_ATRASO_CURSOR"] == "1800" and len(op) > 30, str(len(op)))
confere("catálogo: só variáveis STUDIO_ (HEIMDALL_ nos nomes da Cloudflare) e SUBIR_", all(n.startswith(("STUDIO_", "HEIMDALL_", "SUBIR_")) for n in op))
confere("grupo pelo nome do serviço", c.grupo("STUDIO_LAB_PORTA") == "LAB" and c.grupo("STUDIO_X") == "GERAL")
c.salvar("STUDIO_LAB_PORT", "9999")
ok, ruins = c.gravar_padroes()
env = {d["nome"]: d["valor"] for d in c.ler()}
confere("gravar padrões: põe os que faltam, não troca os que já existem e nunca grava segredos", "STUDIO_CONTROLS_ATRASO_CURSOR" in ok and env.get("STUDIO_LAB_PORT") == "9999"
        and env.get("STUDIO_CONTROLS_ATRASO_CURSOR") == "1800" and not any("TOKEN" in n or "SENHA" in n for n in env) and not ruins, str(ruins))
ok2, _ = c.gravar_padroes()
confere("gravar padrões de novo não repete nada", ok2 == [])

# ---- o Cloud virou Lab: nomes antigos do .env ----
c.ARQUIVO.write_text("HEIMDALL_CLOUD_PORT='8010'\nHEIMDALL_CLOUD_HOSTS='cloud.heimdall-ai.tech,localhost'\nHEIMDALL_CLOUD_SENHA_HASH='x'\nHEIMDALL_CLOUD_TOTP_SEGREDO='y'\nSTUDIO_LAB_MAX_MB='9'\nHEIMDALL_CLOUD_MAX_MB='50'\n", encoding="utf-8")
trocadas = c.renomear_antigas()
lido = {d["nome"]: d["valor"] for d in c.ler()}
confere("renomear_antigas: troca porta e endereços pelos nomes do Lab", lido.get("STUDIO_LAB_PORT") == "8010" and lido.get("STUDIO_LAB_HOSTS") == "cloud.heimdall-ai.tech,localhost" and "HEIMDALL_CLOUD_PORT" not in lido, str(lido))
confere("renomear_antigas: senha e código continuam com o nome de sempre", lido.get("HEIMDALL_CLOUD_SENHA_HASH") == "x" and lido.get("HEIMDALL_CLOUD_TOTP_SEGREDO") == "y")
confere("renomear_antigas: se o novo já existe, vale o novo e o antigo sai", lido.get("STUDIO_LAB_MAX_MB") == "9" and "HEIMDALL_CLOUD_MAX_MB" not in lido and len(trocadas) == 3, str(trocadas))
confere("renomear_antigas: de novo não muda nada e faz cópia na primeira vez", c.renomear_antigas() == [] and (tmp / ".env.bak").exists())

_op = c.opcoes_do_codigo()
for _n in ("STUDIO_CONTINUIDADE", "HEIMDALL_CONTINUIDADE_SENHA", "HEIMDALL_CF_ALERTA_EMAIL"):
    confere(f"catálogo inclui {_n}", _n in _op)
confere("senha da continuidade é segredo", c.e_segredo("HEIMDALL_CONTINUIDADE_SENHA"))
print("\nTUDO OK" if not falhas else f"\n{falhas} FALHA(S)")

sys.exit(1 if falhas else 0)
