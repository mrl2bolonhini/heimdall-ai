#!/usr/bin/env python3
"""Testa migrar_avisos.py: traz as notas antigas de saúde e finanças para os avisos, confere e só então apaga (cofre e app Notas de mentira)."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="heimdall-migrar-"))
os.environ.update({"STUDIO_DB_DIR": str(TMP / "banco"), "STUDIO_FINANCE_DIR": str(TMP / "fin"), "STUDIO_VAULT_DIR": str(TMP / "cofre")})
sys.path.insert(0, str(RAIZ))
import heimdall_avisos as av  # noqa: E402
import migrar_avisos as mg  # noqa: E402

falhas = 0


def confere(nome, cond, detalhe=""):
    global falhas
    print(("ok   " if cond else "FALHOU ") + nome + ("" if cond else f"  -> {detalhe}"))
    falhas += 0 if cond else 1


cofre = TMP / "cofre"
(cofre / "saude" / "audio").mkdir(parents=True)
(cofre / "heimdall-financas").mkdir(parents=True)
(cofre / "heimdall-digest").mkdir(parents=True)
(cofre / "saude" / "saude-semana.md").write_text("---\ntags: [a]\n---\n# Saúde: semana de 10/11\n\n- sono 6h\n", encoding="utf-8")
(cofre / "saude" / "audio" / "saude-semana.m4a").write_bytes(b"audio")
(cofre / "heimdall-financas" / "analise-de-marco.md").write_text("# Análise de março\n\ngastei 500\n", encoding="utf-8")
(cofre / "heimdall-digest" / "digest.md").write_text("# Digest\n", encoding="utf-8")

NOTAS = {"x-coredata://1": ("Saúde", "Saúde: semana de 10/11", "texto da nota 1"), "x-coredata://2": ("Saúde", "Resumo antigo sem cofre", "texto do resumo"),
         "x-coredata://3": ("Heimdall Finanças", "Análise de março", "gastei 500")}
apagadas, chamadas = [], []


def osa(script, *args):
    chamadas.append((script.split("\n")[0], args))
    if "listar-pasta" in script:
        pasta, raiz = args
        return "".join(f"{i}\t{t}\n" for i, (p, t, _) in NOTAS.items() if p == pasta)
    if "heimdall:ler" in script:
        p, t, corpo = NOTAS[args[0]]
        return f"{t}\n<<<CORPO>>>\n{corpo}"
    if "apagar-nota" in script:
        apagadas.append(args[0])
        return "ok"
    raise RuntimeError("script inesperado")


seco = mg.migrar(cofre, osa, "StudioLibre", simular=True, log=lambda *_: None)
confere("simular não grava nem apaga nada", av.do_servico("saude").listar() == [] and (cofre / "saude" / "saude-semana.md").exists() and not apagadas, seco)
r = mg.migrar(cofre, osa, "StudioLibre", log=lambda *_: None)
sa, fi = av.do_servico("saude").listar(), av.do_servico("financas").listar()
confere("saúde: importa a cópia do cofre e a nota sem cofre; sem duplicar a que está nos dois", len(sa) == 2 and {a["titulo"] for a in sa} == {"Saúde: semana de 10/11", "Resumo antigo sem cofre"}, sa)
confere("finanças: importa a análise", len(fi) == 1 and fi[0]["titulo"] == "Análise de março" and "gastei 500" in fi[0]["texto"], fi)
confere("o frontmatter do cofre não vai para o aviso", all("tags:" not in a["texto"] for a in sa))
confere("as 3 notas do app Notas foram apagadas depois da conferência", sorted(apagadas) == sorted(NOTAS) and r["apagados_notas"] == 3, (apagadas, r))
confere("cofre: md e áudio de saúde e finanças apagados; outras pastas intactas", not (cofre / "saude" / "saude-semana.md").exists() and not (cofre / "saude" / "audio" / "saude-semana.m4a").exists()
        and not (cofre / "heimdall-financas" / "analise-de-marco.md").exists() and (cofre / "heimdall-digest" / "digest.md").exists(), r)
confere("sem erros e sem a lista de saúde dentro da raiz tocada fora de StudioLibre", r["erros"] == [] and all(a[1] == ("Saúde", "StudioLibre") for a in chamadas if "listar-pasta" in a[0] and a[1][0] == "Saúde"), chamadas)
apagadas.clear()
r2 = mg.migrar(cofre, osa, "StudioLibre", log=lambda *_: None)
confere("rodar de novo não duplica", len(av.do_servico("saude").listar()) == 2 and len(av.do_servico("financas").listar()) == 1 and r2["importados"] == 0, r2)

# falha ao apagar no app Notas: o cofre fica para tentar de novo
(cofre / "saude" / "novo.md").write_text("# Novo\n\ntexto\n", encoding="utf-8")


def osa_falha(script, *args):
    if "apagar-nota" in script:
        raise RuntimeError("sem permissão")
    return osa(script, *args)


r3 = mg.migrar(cofre, osa_falha, "StudioLibre", log=lambda *_: None)
confere("erro ao apagar nota: mantém o arquivo do cofre e avisa", (cofre / "saude" / "novo.md").exists() and any("mantive" in e for e in r3["erros"]), r3)

# importação com falha: nada é apagado
(cofre / "saude" / "x.md").write_text("# X\n", encoding="utf-8")
orig = av.Avisos.gravar
av.Avisos.gravar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disco cheio"))
r4 = mg.migrar(cofre, None, log=lambda *_: None)
av.Avisos.gravar = orig
confere("importação com erro: nada é apagado", (cofre / "saude" / "x.md").exists() and r4["apagados_arquivos"] == 0 and r4["erros"], r4)
print("TUDO OK" if not falhas else f"{falhas} falha(s)")
sys.exit(1 if falhas else 0)
