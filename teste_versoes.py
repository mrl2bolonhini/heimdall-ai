#!/usr/bin/env python3
"""Teste do heimdall_versoes.py com um 'docker' de mentira: versões, comparação com o registro e falhas em silêncio."""
import sys

import heimdall_versoes as v

falhas = 0


def confere(nome, ok, extra=""):
    global falhas
    print(("ok   " if ok else "FALHOU ") + nome + ("" if ok else f"\n     {extra}"))
    falhas += 0 if ok else 1


def falso(remoto_n8n="sha256:aaa", sem_docker=False):
    def run(cmd, timeout=6):
        c = " ".join(cmd)
        if cmd[0] == "docker" and sem_docker:
            return None
        if c.startswith("sw_vers"): return "15.1"
        if c.startswith("ollama"): return "ollama version is 0.5.1"
        if c.startswith("git"): return "abc1234 2026-11-21" if "log" in c else "develop"
        if c.startswith("docker version"): return "27.3.1"
        if c.startswith("docker ps"): return "open-webui\nn8n\nsearxng\noutro"
        if c.startswith("docker inspect"):
            n = cmd[-1]
            return {"open-webui": "ghcr.io/open-webui/open-webui:main|sha256:i1|main", "n8n": "docker.n8n.io/n8nio/n8n:latest|sha256:i2|",
                    "searxng": "searxng/searxng:latest|sha256:i3|2025.1.1"}[n]
        if c.startswith("docker exec open-webui"): return '{"name":"open-webui","version":"0.6.9"}'
        if c.startswith("docker exec n8n"): return "1.70.2"
        if c.startswith("docker image inspect -f {{.Created}}"): return "2026-11-10T12:00:00Z"
        if c.startswith("docker image inspect -f {{json .RepoDigests}}"):
            return {"sha256:i1": '["ghcr.io/x@sha256:novo"]', "sha256:i2": '["docker.n8n.io/y@sha256:aaa"]', "sha256:i3": "[]"}[cmd[-1]]
        if c.startswith("docker buildx imagetools inspect"):
            return {"ghcr.io/open-webui/open-webui:main": "sha256:maisnovo", "docker.n8n.io/n8nio/n8n:latest": remoto_n8n, "searxng/searxng:latest": "sha256:zzz"}[cmd[4]]
        return None
    return run


it = {i["nome"]: i for i in v.coletar(atualizacoes=True, run=falso())}
confere("macOS, Docker e Ollama lidos", it["macOS"]["versao"] == "15.1" and it["Docker (motor)"]["versao"] == "27.3.1" and it["Ollama"]["versao"] == "0.5.1", str(it))
confere("código do Heimdall com commit e ramo", it["Heimdall-ai (código)"]["versao"].startswith("abc1234") and "develop" in it["Heimdall-ai (código)"]["detalhe"])
confere("Open WebUI: versão do package.json", it["Open WebUI (chat)"]["versao"] == "0.6.9")
confere("n8n: versão do comando", it["n8n (automações)"]["versao"] == "1.70.2")
confere("SearXNG: cai no rótulo da imagem", it["SearXNG (busca)"]["versao"] == "2025.1.1")
confere("só lista contêineres que estão rodando", "Qdrant (base vetorial)" not in it and len(it) >= 6)
confere("compara com o registro: igual = atualizada, diferente = desatualizada, sem digest local = não sabe",
        it["n8n (automações)"]["estado"] == "atualizada" and it["Open WebUI (chat)"]["estado"] == "desatualizada" and it["SearXNG (busca)"]["estado"] == "")
sem = {i["nome"]: i for i in v.coletar(atualizacoes=False, run=falso())}
confere("sem rede não compara", all(i["estado"] == "" for i in sem.values()))
confere("sem Docker não quebra e ainda mostra o resto", {i["nome"] for i in v.coletar(run=falso(sem_docker=True))} >= {"macOS", "Ollama", "Heimdall-ai (código)"})
linhas = "\n".join(v.texto(list(it.values())))
confere("texto: avisa o que tem imagem mais nova", "heimdall restart --update" in linhas and "Open WebUI (chat): 0.6.9" in linhas, linhas)
print("\nFALHAS: %d" % falhas if falhas else "\nTUDO OK")
sys.exit(1 if falhas else 0)
