#!/usr/bin/env python3
"""Testa o comando studio (studio.zsh): ajuda por comando, formas curtas de todas as opções documentadas, help --doc e a tradução das opções."""
import sys as _sys
from pathlib import Path as _Path
RAIZ = next(p for p in _Path(__file__).resolve().parents if (p / "studio_config.py").exists())
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


# `open` de mentira: sem isto o teste abriria o navegador de verdade no Mac a cada comando que abre um endereço
_FALSOS = Path(tempfile.mkdtemp())
for _n in ("open", "xdg-open"):
    (_FALSOS / _n).write_text("#!/bin/bash\nexit 0\n")
    (_FALSOS / _n).chmod(0o755)


def bash(cmd, projeto=None):
    env_dir = projeto or str(AQUI)
    r = subprocess.run(["bash", "-c", f'export PATH="{_FALSOS}:$PATH"; export STUDIO_DIR="{env_dir}"; source "{AQUI}/studio.zsh"; {cmd}'], capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout + r.stderr


# --- seções da ajuda: comandos e opções
secoes, atual = [], None
for linha in (AQUI / "guides/studio_ajuda.txt").read_text(encoding="utf-8").splitlines():
    if linha.startswith("@ "):
        atual = {"nome": linha[2:].split(" | ")[0].strip(), "opcoes": []}
        secoes.append(atual)
    elif atual is not None and re.match(r"^  -[A-Za-z], --[a-z0-9-]+", linha):
        m = re.match(r"^  (-[A-Za-z]), (--[a-z0-9-]+)", linha)
        atual["opcoes"].append((m.group(1), m.group(2)))
nomes = [s["nome"] for s in secoes]
codigo = (AQUI / "studio.zsh").read_text(encoding="utf-8")
no_case = {x for g in re.findall(r"^    ([a-z0-9|]+)\)", codigo.split("studio() {")[1].split("# Completar")[0], re.M) for x in g.split("|")}
confere("há seção de ajuda para os 51 comandos", len(nomes) == 51, len(nomes))
confere("todo comando do case tem seção na ajuda e vice-versa", set(nomes) - no_case == set() and (no_case - set(nomes)) <= {"help"}, (set(nomes) - no_case, no_case - set(nomes)))

# --- --help e -h em todos os comandos mostram só aquele comando
for n in nomes:
    for flag in ("--help", "-h"):
        rc, out = bash(f"studio {n} {flag}")
        ok = rc == 0 and out.startswith(f"studio {n} - ") and "-h, --help" in out and out.count("\nstudio ") <= 3
        confere(f"studio {n} {flag}", ok, out[:200])
# pasta padrão: STUDIO_DIR, senão ~/StudioApps
_h = Path(tempfile.mkdtemp())
def _dir(prep):
    r = subprocess.run(["bash", "-c", f'export HOME="{_h}"; unset STUDIO_DIR STUDIO_DIR; {prep}; source "{AQUI}/studio.zsh"; echo "$STUDIO_DIR"'], capture_output=True, text=True, timeout=60)
    return r.stdout.strip()
confere("pasta padrão: ~/StudioApps", _dir("true") == f"{_h}/StudioApps")
confere("STUDIO_DIR manda sobre a padrão", _dir("export STUDIO_DIR=/tmp/outra") == "/tmp/outra")
rc, out = bash("studio help health")
confere("studio help mostra a ajuda do comando", rc == 0 and out.startswith("studio health - "), out[:100])
rc, out = bash("type heimdall")
confere("o comando antigo heimdall não existe mais", rc != 0, out[:100])
rc, out = bash("studio help health")
confere("help COMANDO mostra a ajuda do comando", out.startswith("studio health - "), out[:100])
rc, out = bash("studio help")
confere("help lista todos os comandos", all(f"  {n} " in out for n in nomes), out[:200])
rc, out = bash("studio -h")
confere("studio -h lista os comandos", "studio COMANDO" in out)
rc, out = bash("studio help nada")
confere("help de comando desconhecido falha com aviso", rc != 0 and "Sem ajuda" in out, out)

# --- toda opção curta documentada vira a longa
for s in secoes:
    rc, out = bash(f"_studio_short {s['nome']}")
    mapa = set(out.split())
    for curta, longa in s["opcoes"]:
        if longa == "--help":
            continue
        confere(f"{s['nome']} {curta} = {longa}", f"{curta}={longa}" in mapa, sorted(mapa))
    confere(f"{s['nome']}: -h=--help", "-h=--help" in mapa)

# --- tradução e execução com programas de mentira
with tempfile.TemporaryDirectory() as d:
    for f in ("subir", "diagnostico_chat", "trocar_senha_webui", "ouvir_estudo", "guardar_no_env", "verificar_mcp_dados",
              "instalar_automacoes_avancadas", "instalar_fluxos_n8n", "instalar_monitor_privacidade", "instalar_email_oficial", "instalar_hook_gitops"):
        alvo = Path(d, f + ".sh") if f == "subir" else Path(d, "scripts", f + ".sh")  # só o subir.sh fica na raiz do projeto
        alvo.parent.mkdir(exist_ok=True)
        alvo.write_text(f'#!/bin/bash\necho "[{f}] $@"\n')
    for f in ("studio_saude", "studio_banco", "studio_backup", "studio_email_oficial", "studio_acesso", "studio_voz", "ingest_docs", "cloudflare_chave",
              "importar_saude_n8n", "limpar_espelhos", "limpar_privadas", "mover_notas_antigas", "gerar_docs", "gerar_marca_png"):
        Path(d, f + ".py").write_text(f'import sys\nprint("[{f}]", *sys.argv[1:])\n')
    Path(d, "rodar_testes.sh").write_text('#!/bin/bash\necho "[rodar_testes] $@"\n')  # fica na raiz do projeto
    casos = [
        ("health -t", "[studio_saude] --hoje"), ("health -r 30", "[studio_saude] --relatorio 30"), ("health -a 2026-11-10", "[studio_saude] --anomalias 2026-11-10"),
        ("health -A", "[studio_saude] --atividade"), ("health -R 90", "[studio_saude] --recuperacao 90"), ("health -i x.zip", "[studio_saude] --importar x.zip"),
        ("health -N", "[importar_saude_n8n]"), ("backup -v", "[studio_backup] verificar"), ("backup -R a b", "[studio_backup] restaurar a b"),
        ("backup -P", "[studio_backup] senha"), ("access -a", "[studio_acesso] --tudo"), ("access -v", "[studio_acesso] --verificar"),
        ("mail -t", "[studio_email_oficial] --testar-login"), ("listen -n 3", "[ouvir_estudo] 3"), ("listen -l", "[ouvir_estudo] --lista"),
        ("env -s X", "[guardar_no_env] X"), ("cloudflare -t", "[cloudflare_chave] --testar"), ("hook -r /r", "[instalar_hook_gitops] --remover /r"),
        ("hub -o -r", "[mover_notas_antigas] --executar"), ("hub -m", "[limpar_espelhos]"), ("chat -d", "[diagnostico_chat]"), ("up -w -t -n -a", "[subir] --webui --terminal --n8n --agente"),
        ("restart -a", "[subir] --reiniciar --agente"), ("logs -s agent", "[subir] --log agente"), ("logs -l", "[subir] --logs"), ("flows -p", "[instalar_monitor_privacidade]"),
        ("flows -b", "[instalar_fluxos_n8n]"), ("docs -b", "[gerar_marca_png]"), ("db -s SELECT", "[studio_banco] --sql SELECT"),
        ("voice -i f.csv", "[studio_voz] --importar f.csv"), ("ingest -r", "[ingest_docs] --reset"), ("mcp -v", "[verificar_mcp_dados]"),
        ("health --today", "[studio_saude] --hoje"), ("tests -x -q core", "[rodar_testes] --stop --quiet core"), ("tests -L", "[rodar_testes] --live"), ("tests -H", "[rodar_testes] --here"), ("tests -n 5 -v", "[rodar_testes] --lines 5 --verbose"),
    ]
    for cmd, esperado in casos:
        rc, out = bash(f"studio {cmd}", d)
        confere(f"studio {cmd}", esperado in out, out[:200])
    rc, out = bash("studio help --doc", d)
    confere("help --doc sem o arquivo avisa", rc != 0 and "catalogo_comandos.html" in out, out)
    (Path(d) / "guides").mkdir()
    (Path(d) / "guides" / "catalogo_comandos.html").write_text("<html></html>")
    # nc, curl e python3 de mentira: o teste nunca sobe um servidor de verdade (um servidor preso numa pasta apagada responderia 404 na porta 8099)
    bin_ = Path(d, "falsos"); bin_.mkdir()
    for nome, corpo in (("nc", "exit 1"), ("curl", "exit 0"), ("python3", "exit 0")):
        (bin_ / nome).write_text("#!/bin/bash\n" + corpo + "\n"); (bin_ / nome).chmod(0o755)
    rc, out = bash(f'export PATH="{bin_}:$PATH"; studio help --doc', d)
    confere("help --doc abre o documento por http, não por file://", "http://localhost:8099/catalogo_comandos.html" in out and "file://" not in out, out)
    rc, out = bash(f'export PATH="{bin_}:$PATH"; studio help -d', d)
    confere("help -d abre o documento", "catalogo_comandos.html" in out, out)
    rc, out = bash(f'export PATH="{bin_}:$PATH"; studio --doc', d)
    confere("studio --doc abre o documento", "catalogo_comandos.html" in out, out)

# --- catálogo do dono (guides/catalogo_comandos.html): completo, atual, acessível e fora do site público
import gerar_catalogo  # noqa: E402
cat = (AQUI / "guides" / "catalogo_comandos.html").read_text(encoding="utf-8") if (AQUI / "guides" / "catalogo_comandos.html").exists() else ""
confere("catálogo: está atualizado em relação ao guides/studio_ajuda.txt", gerar_catalogo.main(True))
confere("catálogo: todo comando do studio.zsh aparece", all(f'id="c-{n}"' in cat for n in no_case if n not in ("*",)), [n for n in no_case if f'id="c-{n}"' not in cat])
confere("catálogo: lang pt-BR, um só h1, pular para o conteúdo, busca com rótulo", 'lang="pt-BR"' in cat and cat.count("<h1") == 1 and 'class="skip"' in cat and 'for="busca"' in cat)
confere("catálogo: tabelas com caption e scope", cat.count("<caption>") >= 40 and 'scope="col"' in cat and 'scope="row"' in cat)
confere("catálogo: sem o nome antigo nos comandos", "heimdall " not in cat.replace("HEIMDALL_", ""))
confere("catálogo: não vai para o site público", not (AQUI / "docs" / "comando-studio.html").exists() and "comando-studio" not in (AQUI / "docs_tema.py").read_text(encoding="utf-8"))
print("\nFALHAS:", falhas)
sys.exit(1 if falhas else 0)
