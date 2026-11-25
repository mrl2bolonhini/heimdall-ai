#!/usr/bin/env python3
"""Versões do que roda no Mac: macOS, Python, Docker, Ollama, LiteLLM, o próprio Heimdall e cada serviço em contêiner.

Usado por `heimdall doctor --versions` (com comparação com a imagem mais nova no registro) e pelo Resumo do Controls (só as versões, sem rede).
Só lê: docker inspect/exec de comandos de versão, sw_vers, git. Cada item falha em silêncio quando o comando não existe.
"""
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

# contêiner -> (nome para o usuário, comandos que dão a versão, na ordem; cada um é (argumentos do docker exec, função que extrai))
def _json_versao(texto: str):
    try:
        v = json.loads(texto).get("version")
        return str(v) if v else None
    except (ValueError, AttributeError):
        return None


def _primeira_versao(texto: str):
    m = re.search(r"\d+\.\d+(?:\.\d+)?(?:[-+.\w]*)?", texto or "")
    return m.group(0) if m else None


CONTEINERES = {
    "open-webui": ("Open WebUI (chat)", [(["cat", "/app/package.json"], _json_versao)]),
    "n8n": ("n8n (automações)", [(["n8n", "--version"], _primeira_versao)]),
    "uptime-kuma": ("Uptime Kuma (status)", [(["cat", "/app/package.json"], _json_versao)]),
    "qdrant": ("Qdrant (base vetorial)", [(["/qdrant/qdrant", "--version"], _primeira_versao)]),
    "searxng": ("SearXNG (busca)", []),
    "dozzle": ("Dozzle (logs)", [(["/dozzle", "--version"], _primeira_versao)]),
    "moto": ("Emulador de AWS (Moto)", [(["python3", "-c", "import moto; print(moto.__version__)"], _primeira_versao)]),
    "localstack": ("Emulador de AWS (LocalStack)", [(["localstack", "--version"], _primeira_versao), (["cat", "/opt/code/localstack/localstack-core/localstack/version.py"], _primeira_versao)]),
    "docling": ("Docling (leitura de documentos)", []),
}


def run(cmd: list, timeout: int = 6):
    """Saída de texto do comando, ou None se não existir, demorar ou falhar."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _digest_local(imagem_id: str, run=run):
    """Digests do registro que a imagem local já tem (RepoDigests)."""
    saida = run(["docker", "image", "inspect", "-f", "{{json .RepoDigests}}", imagem_id])
    try:
        return {d.split("@", 1)[1] for d in json.loads(saida or "[]") if "@" in d}
    except ValueError:
        return set()


def _estado(imagem: str, imagem_id: str, run=run) -> str:
    """'atualizada', 'desatualizada' ou '' se não deu para comparar (sem rede, sem buildx, imagem local)."""
    remoto = run(["docker", "buildx", "imagetools", "inspect", imagem, "--format", "{{.Manifest.Digest}}"], 15)
    local = _digest_local(imagem_id, run)
    if not remoto or not local or not remoto.startswith("sha256:"):
        return ""
    return "atualizada" if remoto in local else "desatualizada"


def _conteiner(nome: str, atualizacoes: bool, run=run) -> dict:
    rotulo, comandos = CONTEINERES[nome]
    info = run(["docker", "inspect", "-f", '{{.Config.Image}}|{{.Image}}|{{index .Config.Labels "org.opencontainers.image.version"}}', nome])
    if not info or "|" not in info:
        return {}
    imagem, imagem_id, rotulo_ver = (info.split("|") + ["", "", ""])[:3]
    versao = None
    for args, extrai in comandos:
        versao = extrai(run(["docker", "exec", nome] + args) or "")
        if versao:
            break
    if not versao and rotulo_ver and rotulo_ver not in ("<no value>", "main", "latest"):
        versao = rotulo_ver
    atual = run(["docker", "image", "inspect", "-f", "{{.Id}}", imagem])
    aviso = (f"{rotulo} está rodando numa imagem antiga: já existe uma mais nova baixada no Mac. Reinicie com heimdall restart para usá-la."
             if atual and atual != imagem_id else "")
    criada = run(["docker", "image", "inspect", "-f", "{{.Created}}", imagem_id]) or ""
    detalhe = f"imagem {imagem}" + (f", criada em {criada[:10]}" if criada else "")
    return {"nome": rotulo, "versao": versao or "versão não informada pelo serviço", "detalhe": detalhe,
            "estado": _estado(imagem, imagem_id, run) if atualizacoes else "", "aviso": aviso}


def _do_mac(run=run) -> list:
    itens = []
    v = run(["sw_vers", "-productVersion"])
    if v:
        itens.append({"nome": "macOS", "versao": v, "detalhe": "", "estado": ""})
    itens.append({"nome": "Python do Heimdall", "versao": sys.version.split()[0], "detalhe": "", "estado": ""})
    d = run(["docker", "version", "--format", "{{.Server.Version}}"])
    if d:
        itens.append({"nome": "Docker (motor)", "versao": d, "detalhe": "", "estado": ""})
    o = run(["ollama", "--version"])
    if o and _primeira_versao(o):
        todas = set(re.findall(r"\d+\.\d+\.\d+", o))
        aviso = (f"O Ollama (cliente e servidor) está com versões diferentes ({', '.join(sorted(todas))}). Atualize o aplicativo e reinicie o Ollama."
                 if len(todas) > 1 else "")
        itens.append({"nome": "Ollama", "versao": _primeira_versao(o), "detalhe": "", "estado": "", "aviso": aviso})
    try:
        from importlib.metadata import version
        itens.append({"nome": "LiteLLM (modelos)", "versao": version("litellm"), "detalhe": "", "estado": ""})
    except Exception:
        pass
    commit = run(["git", "-C", str(PROJECT_DIR), "log", "-1", "--format=%h %cs"])
    ramo = run(["git", "-C", str(PROJECT_DIR), "rev-parse", "--abbrev-ref", "HEAD"])
    if commit:
        itens.append({"nome": "Heimdall-ai (código)", "versao": commit, "detalhe": f"ramo {ramo}" if ramo else "", "estado": ""})
    return itens


def coletar(atualizacoes: bool = False, run=run) -> list:
    """Lista de {nome, versao, detalhe, estado}. Com atualizacoes=True compara com a imagem mais nova no registro (usa a rede)."""
    itens = _do_mac(run)
    ativos = (run(["docker", "ps", "--format", "{{.Names}}"]) or "").split()
    nomes = [n for n in CONTEINERES if n in ativos]
    with ThreadPoolExecutor(max_workers=6) as ex:
        achados = list(ex.map(lambda n: _conteiner(n, atualizacoes, run), nomes))
    return itens + [a for a in achados if a]


def avisos(itens: list) -> list:
    """O que merece atenção: imagem mais nova no registro, contêiner em imagem antiga, versão que o serviço não informou, cliente e servidor diferentes.
    Não há tabela de incompatibilidades entre programas: só entra aqui o que dá para conferir de verdade."""
    out = []
    for i in itens:
        if i.get("estado") == "desatualizada":
            out.append(f"{i['nome']} tem imagem mais nova no registro. Atualize com heimdall restart --update.")
        if i.get("aviso"):
            out.append(i["aviso"])
        if i["versao"].startswith("versão não informada"):
            out.append(f"{i['nome']} não informou a versão, então não dá para conferir se está atual.")
    return out


def texto(itens: list) -> list:
    """Linhas para o terminal."""
    out = ["Versões instaladas"]
    for i in itens:
        extra = " ".join(x for x in (f"({i['detalhe']})" if i["detalhe"] else "", {"atualizada": "[na versão mais nova]", "desatualizada": "[há imagem mais nova: heimdall restart --update]"}.get(i["estado"], "")) if x)
        out.append(f"  {i['nome']}: {i['versao']}" + (f" {extra}" if extra else ""))
    return out


if __name__ == "__main__":
    it = coletar(atualizacoes="--sem-rede" not in sys.argv)
    print("\n".join(texto(it)))
    for n, a in enumerate(avisos(it), 1):
        print(f"  Atenção {n}: {a}")
