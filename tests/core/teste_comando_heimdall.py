#!/usr/bin/env python3
"""Testa o comando heimdall (heimdall.zsh): ajuda por comando, formas curtas de todas as opções documentadas, help --doc e a tradução das opções."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "heimdall_config.py").exists())
_sys.path.insert(0, str(RAIZ))
import re
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = RAIZ
falhas = 0


def confere(nome, ok, detalhe=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome)
    if not ok:
        falhas += 1
        print("     " + str(detalhe)[:500])


def bash(cmd, projeto=None):
    env_dir = projeto or str(AQUI)
    r = subprocess.run(["bash", "-c", f'export HEIMDALL_DIR="{env_dir}"; source "{AQUI}/heimdall.zsh"; {cmd}'], capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr


# --- seções da ajuda: comandos e opções
secoes, atual = [], None
for linha in (AQUI / "guides/heimdall_ajuda.txt").read_text(encoding="utf-8").splitlines():
    if linha.startswith("@ "):
        atual = {"nome": linha[2:].split(" | ")[0].strip(), "opcoes": []}
        secoes.append(atual)
    elif atual is not None and re.match(r"^  -[A-Za-z], --[a-z0-9-]+", linha):
        m = re.match(r"^  (-[A-Za-z]), (--[a-z0-9-]+)", linha)
        atual["opcoes"].append((m.group(1), m.group(2)))
nomes = [s["nome"] for s in secoes]
codigo = (AQUI / "heimdall.zsh").read_text(encoding="utf-8")
no_case = set(re.findall(r"^    ([a-z0-9]+)(?:\||\))", codigo.split("heimdall() {")[1].split("# Completar")[0], re.M))
confere("há seção de ajuda para os 52 comandos", len(nomes) == 52, len(nomes))
confere("todo comando do case tem seção na ajuda e vice-versa", set(nomes) - no_case == set() and (no_case - set(nomes)) <= {"help"}, (set(nomes) - no_case, no_case - set(nomes)))

# --- --help e -h em todos os comandos mostram só aquele comando
for n in nomes:
    for flag in ("--help", "-h"):
        rc, out = bash(f"heimdall {n} {flag}")
        ok = rc == 0 and out.startswith(f"heimdall {n} - ") and "-h, --help" in out and out.count("\nheimdall ") <= 3
        confere(f"heimdall {n} {flag}", ok, out[:200])
rc, out = bash("heimdall help health")
confere("help COMANDO mostra a ajuda do comando", out.startswith("heimdall health - "), out[:100])
rc, out = bash("heimdall help")
confere("help lista todos os comandos", all(f"  {n} " in out for n in nomes), out[:200])
rc, out = bash("heimdall -h")
confere("heimdall -h lista os comandos", "heimdall COMANDO" in out)
rc, out = bash("heimdall help nada")
confere("help de comando desconhecido falha com aviso", rc != 0 and "Sem ajuda" in out, out)

# --- toda opção curta documentada vira a longa
for s in secoes:
    rc, out = bash(f"_heimdall_short {s['nome']}")
    mapa = set(out.split())
    for curta, longa in s["opcoes"]:
        if longa == "--help":
            continue
        confere(f"{s['nome']} {curta} = {longa}", f"{curta}={longa}" in mapa, sorted(mapa))
    confere(f"{s['nome']}: -h=--help", "-h=--help" in mapa)

# --- tradução e execução com programas de mentira
with tempfile.TemporaryDirectory() as d:
    for f in ("subir", "consultar_triagem", "concluir_testes_triagem", "diagnostico_chat", "trocar_senha_webui", "ouvir_estudo", "guardar_no_env", "verificar_mcp_dados",
              "instalar_automacoes_avancadas", "instalar_fluxos_n8n", "instalar_monitor_privacidade", "instalar_email_oficial", "instalar_hook_gitops"):
        alvo = Path(d, f + ".sh") if f == "subir" else Path(d, "scripts", f + ".sh")  # só o subir.sh fica na raiz do projeto
        alvo.parent.mkdir(exist_ok=True)
        alvo.write_text(f'#!/bin/bash\necho "[{f}] $@"\n')
    for f in ("heimdall_saude", "heimdall_banco", "heimdall_backup", "heimdall_email_oficial", "heimdall_acesso", "heimdall_voz", "ingest_docs", "cloudflare_chave",
              "importar_saude_n8n", "limpar_espelhos", "limpar_privadas", "mover_notas_antigas", "gerar_docs", "gerar_marca_png"):
        Path(d, f + ".py").write_text(f'import sys\nprint("[{f}]", *sys.argv[1:])\n')
    casos = [
        ("health -t", "[heimdall_saude] --hoje"), ("health -r 30", "[heimdall_saude] --relatorio 30"), ("health -a 2026-11-10", "[heimdall_saude] --anomalias 2026-11-10"),
        ("health -A", "[heimdall_saude] --atividade"), ("health -R 90", "[heimdall_saude] --recuperacao 90"), ("health -i x.zip", "[heimdall_saude] --importar x.zip"),
        ("health -N", "[importar_saude_n8n]"), ("backup -v", "[heimdall_backup] verificar"), ("backup -R a b", "[heimdall_backup] restaurar a b"),
        ("backup -P", "[heimdall_backup] senha"), ("access -a", "[heimdall_acesso] --tudo"), ("access -v", "[heimdall_acesso] --verificar"),
        ("mail -t", "[heimdall_email_oficial] --testar-login"), ("listen -n 3", "[ouvir_estudo] 3"), ("listen -l", "[ouvir_estudo] --lista"),
        ("env -s X", "[guardar_no_env] X"), ("cloudflare -t", "[cloudflare_chave] --testar"), ("hook -r /r", "[instalar_hook_gitops] --remover /r"),
        ("notes -o -r", "[mover_notas_antigas] --executar"), ("notes -m", "[limpar_espelhos]"), ("chat -d", "[diagnostico_chat]"), ("up -w -t -n -a", "[subir] --webui --terminal --n8n --agente"),
        ("restart -a", "[subir] --reiniciar --agente"), ("logs -s agent", "[subir] --log agente"), ("logs -l", "[subir] --logs"), ("flows -p", "[instalar_monitor_privacidade]"),
        ("flows -b", "[instalar_fluxos_n8n]"), ("docs -b", "[gerar_marca_png]"), ("triage -c", "[concluir_testes_triagem]"), ("db -s SELECT", "[heimdall_banco] --sql SELECT"),
        ("voice -i f.csv", "[heimdall_voz] --importar f.csv"), ("ingest -r", "[ingest_docs] --reset"), ("mcp -v", "[verificar_mcp_dados]"),
        ("health --today", "[heimdall_saude] --hoje"), ("test -r nada", "Teste desconhecido"),
    ]
    for cmd, esperado in casos:
        rc, out = bash(f"heimdall {cmd}", d)
        confere(f"heimdall {cmd}", esperado in out, out[:200])
    rc, out = bash("heimdall help --doc", d)
    confere("help --doc sem o arquivo avisa", rc != 0 and "comando-heimdall.html" in out, out)
    (Path(d) / "docs").mkdir()
    (Path(d) / "docs" / "comando-heimdall.html").write_text("<html></html>")
    rc, out = bash("heimdall help --doc", d)
    confere("help --doc abre o documento por http, não por file://", "http://localhost:8099/comando-heimdall.html" in out and "file://" not in out, out)
    rc, out = bash("heimdall help -d", d)
    confere("help -d abre o documento", "comando-heimdall.html" in out, out)
    rc, out = bash("heimdall --doc", d)
    confere("heimdall --doc abre o documento", "comando-heimdall.html" in out, out)

confere("a página do documento existe no site", (AQUI / "docs" / "comando-heimdall.html").exists())
print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
