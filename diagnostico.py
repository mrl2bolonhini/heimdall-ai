#!/usr/bin/env python3
"""Diagnóstico de desempenho do Mac (studio doctor): memória, processador, disco, Docker, Ollama e serviços do Heimdall.

Só lê informações do sistema (vm_stat, ps, df, docker stats, ollama ps...). Não mostra linhas de comando nem argumentos de processo,
só o nome do programa ou do script, para nada sensível aparecer. Cada parte falha em silêncio quando o comando não existe.

    python3 diagnostico.py [--memoria] [--cpu] [--disco] [--docker] [--ollama] [--servicos] [--versoes] [--topo N]
Sem opção, faz tudo e termina com uma conclusão em linguagem simples.
"""
import argparse
import heimdall_versoes
import os
import re
import shutil
import subprocess
import sys
import time

GB = 1024 ** 3
SERVICOS = {8000: "MCP busca", 8001: "MCP arquivos", 8002: "Open Terminal", 8003: "agente do Mac", 8004: "MCP banco", 8010: "Lab", 8011: "Notas",
            8012: "News", 8013: "Saúde", 8014: "Jogos", 8019: "Learn", 8020: "Trading", 8021: "Library", 8016: "Finance", 8017: "Controls", 8018: "Account", 8099: "painel", 9000: "LiteLLM", 3000: "Open WebUI", 5678: "n8n", 11434: "Ollama"}


def run(cmd: list, timeout: int = 15):
    """Saída de texto do comando, ou None se não existir, demorar demais ou falhar."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def gb(n: float) -> str:
    return f"{n / GB:.1f}".replace(".", ",") + " GB"


def mb(n: float) -> str:
    return f"{n / 1024 ** 2:.0f} MB"


# ---------------------------------------------------------------- análise de textos do sistema (testáveis)
def parse_vm_stat(texto: str) -> dict:
    """Páginas por categoria, em bytes. Devolve {} se não reconhecer."""
    m = re.search(r"page size of (\d+) bytes", texto)
    if not m:
        return {}
    pag = int(m.group(1))
    v = {}
    for linha in texto.splitlines():
        k = re.match(r"\s*\"?([A-Za-z -]+?)\"?:\s+(\d+)\.", linha)
        if k:
            v[k.group(1).strip().lower()] = int(k.group(2)) * pag
    return v


def parse_swap(texto: str) -> dict:
    """'total = 3072.00M  used = 2012.50M  free = 1059.50M' -> bytes."""
    r = {}
    for k, n, u in re.findall(r"(total|used|free)\s*=\s*([\d.,]+)\s*([KMG])", texto or ""):
        r[k] = float(n.replace(",", ".")) * {"K": 1024, "M": 1024 ** 2, "G": GB}[u]
    return r


def nome_do_processo(comm: str, comando: str = "") -> str:
    """Nome amigável sem argumentos: o aplicativo (.app), o script Python ou o nome do programa."""
    m = re.search(r"/([^/]+)\.app/", comm)
    if m:
        return m.group(1)
    base = os.path.basename(comm.strip())
    if base.lower().startswith("python"):
        for tok in comando.split():
            if tok.endswith(".py"):
                return os.path.basename(tok)
        return "python"
    return base or comm


def parse_ps(texto: str, comandos: dict = None) -> list:
    """Linhas 'pid rss(KB) %cpu comm' -> lista de dicts agregada por nome (memória em bytes)."""
    comandos = comandos or {}
    agreg = {}
    for linha in (texto or "").splitlines():
        p = linha.split(None, 3)
        if len(p) < 4 or not p[0].isdigit():
            continue
        try:
            rss, cpu = int(p[1]) * 1024, float(p[2].replace(",", "."))
        except ValueError:
            continue
        nome = nome_do_processo(p[3], comandos.get(int(p[0]), ""))
        a = agreg.setdefault(nome, {"nome": nome, "mem": 0, "cpu": 0.0, "n": 0})
        a["mem"] += rss
        a["cpu"] += cpu
        a["n"] += 1
    return list(agreg.values())


def parse_boottime(texto: str, agora: float = None):
    """'{ sec = 1731000000, usec = 0 } ...' -> dias ligado, ou None."""
    m = re.search(r"sec\s*=\s*(\d+)", texto or "")
    if not m:
        return None
    return ((agora if agora is not None else time.time()) - int(m.group(1))) / 86400


def parse_ollama_ps(texto: str) -> list:
    linhas = [l for l in (texto or "").splitlines() if l.strip()]
    return [re.sub(r"\s{2,}", " | ", l.strip()) for l in linhas[1:]]


def parse_docker_stats(texto: str) -> list:
    r = []
    for linha in (texto or "").splitlines():
        p = linha.split("|")
        if len(p) == 3:
            r.append({"nome": p[0], "cpu": p[1], "mem": p[2].split("/")[0].strip()})
    return r


def _mem_texto_para_bytes(t: str) -> float:
    m = re.match(r"([\d.,]+)\s*([KMG]i?B)", t)
    if not m:
        return 0
    return float(m.group(1).replace(",", ".")) * {"K": 1024, "M": 1024 ** 2, "G": GB}[m.group(2)[0]]


# ---------------------------------------------------------------- coleta
def _processos() -> list:
    ps = run(["ps", "-axo", "pid=,rss=,pcpu=,comm="])
    cmd_py = {}
    cm = run(["ps", "-axo", "pid=,command="])
    if cm:
        for linha in cm.splitlines():
            p = linha.strip().split(None, 1)
            if len(p) == 2 and p[0].isdigit() and "python" in p[1].lower().split()[0].lower():
                cmd_py[int(p[0])] = p[1]
    return parse_ps(ps, cmd_py)


def memoria(topo: int, procs: list, achados: list) -> list:
    out = ["Memória"]
    total = run(["sysctl", "-n", "hw.memsize"])
    vm = parse_vm_stat(run(["vm_stat"]) or "")
    swap = parse_swap(run(["sysctl", "-n", "vm.swapusage"]) or "")
    livre_pct = None
    mp = run(["memory_pressure", "-Q"])
    if mp:
        m = re.search(r"free percentage:\s*(\d+)%", mp)
        livre_pct = int(m.group(1)) if m else None
    dias = parse_boottime(run(["sysctl", "-n", "kern.boottime"]) or "")
    if dias is not None:
        out.append(f"Ligado há {dias:.0f} dias sem reiniciar." if dias >= 1 else "Ligado há menos de um dia.")
        if dias > 14:
            achados.append(f"O Mac está ligado há {dias:.0f} dias sem reiniciar; reiniciar libera memória e troca acumuladas.")
    if total and vm:
        t = int(total.strip())
        fixa, comp = vm.get("pages wired down", 0), vm.get("pages occupied by compressor", 0)
        ativa = vm.get("pages active", 0)
        out.append(f"Total instalado: {gb(t)}. Fixa do sistema: {gb(fixa)}. Em uso por aplicativos: {gb(ativa)}. Comprimida: {gb(comp)}.")
    elif total:
        out.append(f"Total instalado: {gb(int(total.strip()))}.")
    if livre_pct is not None:
        out.append(f"Memória livre segundo o sistema: {livre_pct}%.")
        if livre_pct < 20:
            achados.append(f"A memória está apertada (só {livre_pct}% livre).")
    if swap:
        out.append(f"Troca em disco (swap): {gb(swap.get('used', 0))} usados de {gb(swap.get('total', 0))}. Troca alta deixa o Mac lento.")
        if swap.get("used", 0) > 2 * GB:
            if livre_pct is not None and livre_pct >= 50:
                achados.append(f"A troca em disco está em {gb(swap['used'])}, mas hoje há memória sobrando ({livre_pct}% livre): é resíduo de um momento em que a memória apertou (por exemplo, um modelo grande no Ollama) e o macOS não devolve a troca sozinho. Para zerar: reinicie o Mac.")
            else:
                achados.append(f"O Mac está usando {gb(swap['used'])} de troca em disco, sinal de falta de memória: feche programas pesados ou descarregue modelos do Ollama (ollama stop NOME).")
    grandes = sorted(procs, key=lambda a: a["mem"], reverse=True)[:topo]
    if grandes:
        out.append(f"Os {len(grandes)} que mais usam memória:")
        out += [f"  {i}. {a['nome']}: {gb(a['mem'])}" + (f" ({a['n']} processos)" if a["n"] > 1 else "") for i, a in enumerate(grandes, 1)]
    return out


def cpu(topo: int, procs: list, achados: list) -> list:
    out = ["Processador"]
    n = os.cpu_count() or 1
    try:
        c1, c5, c15 = os.getloadavg()
        d = lambda x: f"{x:.1f}".replace(".", ",")  # noqa: E731
        out.append(f"Carga média (1, 5 e 15 minutos): {d(c1)}, {d(c5)} e {d(c15)}, para {n} núcleos. Acima do número de núcleos significa fila de trabalho.")
        if c5 > n and c1 < n / 2:
            achados.append(f"Houve um pico de processador nos últimos minutos (carga de {d(c5)} em 5 minutos para {n} núcleos), mas agora já baixou (carga {d(c1)}): costuma ser tarefa de manutenção do sistema depois de reiniciar ou atualizar o Mac.")
        elif c5 > n:
            achados.append(f"O processador está saturado (carga {d(c5)} para {n} núcleos).")
    except OSError:
        pass
    term = run(["pmset", "-g", "therm"])
    if term:
        m = re.search(r"CPU_Speed_Limit\s*=\s*(\d+)", term)
        if m:
            lim = int(m.group(1))
            out.append(f"Limite de velocidade por temperatura: {lim}%." + (" O Mac está reduzindo a velocidade por calor." if lim < 100 else ""))
            if lim < 100:
                achados.append("O Mac está reduzindo a velocidade por calor.")
    tm = run(["tmutil", "status"])
    if tm and re.search(r"Running\s*=\s*1", tm):
        out.append("Um backup do Time Machine está em andamento agora.")
        achados.append("O Time Machine está fazendo backup agora, o que deixa o Mac lento até terminar.")
    ativos = [a for a in sorted(procs, key=lambda a: a["cpu"], reverse=True)[:topo] if a["cpu"] >= 1]
    if ativos:
        out.append(f"Os {len(ativos)} que mais usam processador agora (100 = um núcleo inteiro):")
        out += [f"  {i}. {a['nome']}: {a['cpu']:.0f}%" for i, a in enumerate(ativos, 1)]
        for a in ativos:
            if a["nome"] in ("mds_stores", "mds", "mdworker", "mdworker_shared", "photolibraryd", "photoanalysisd", "corespotlightd") and a["cpu"] > 50:
                achados.append(f"{a['nome']} (indexação do sistema) está usando bastante processador; costuma passar sozinho depois de alguns minutos.")
            if a["nome"] in ("ANECompilerService", "ANEServices", "siriknowledged", "intelligenceplatformd") and a["cpu"] > 50:
                achados.append(f"{a['nome']} (preparação de recursos de inteligência do sistema, como Siri e ditado) está usando bastante processador; é normal logo depois de atualizar o macOS e costuma terminar em minutos ou poucas horas. Se passar de umas 3 horas, rode o doctor de novo e me avise.")
    else:
        out.append("Nenhum programa usando mais de 1% de um núcleo agora.")
    return out


def disco(achados: list) -> list:
    out = ["Disco"]
    raiz = "/System/Volumes/Data" if os.path.isdir("/System/Volumes/Data") else "/"
    try:
        u = shutil.disk_usage(raiz)
        livre = u.free
        out.append(f"Livre: {gb(livre)} de {gb(u.total)} ({100 * livre / u.total:.0f}% livre).")
        if livre < 15 * GB or livre / u.total < 0.10:
            achados.append(f"O disco está quase cheio (só {gb(livre)} livres); com pouco espaço o Mac fica lento.")
    except OSError:
        out.append("Não consegui ler o espaço do disco.")
    ol = os.path.expanduser("~/.ollama")
    if os.path.isdir(ol):
        du = run(["du", "-sk", ol], 30)
        if du:
            out.append(f"Modelos do Ollama ocupam {gb(int(du.split()[0]) * 1024)}.")
    ds = run(["docker", "system", "df", "--format", "{{.Type}}: {{.Size}} ({{.Reclaimable}} recuperável)"], 20)
    if ds:
        out += ["Docker:"] + [f"  {l}" for l in ds.strip().splitlines()]
    return out


def docker(achados: list) -> list:
    out = ["Docker"]
    st = run(["docker", "stats", "--no-stream", "--format", "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}"], 25)
    if st is None:
        return out + ["O Docker não respondeu (parado ou não instalado)."]
    cont = parse_docker_stats(st)
    if not cont:
        return out + ["Nenhum contêiner rodando."]
    total = sum(_mem_texto_para_bytes(c["mem"]) for c in cont)
    out.append(f"{len(cont)} contêineres usando {gb(total)} de memória ao todo:")
    out += [f"  {i}. {c['nome']}: memória {c['mem']}, processador {c['cpu']}" for i, c in enumerate(sorted(cont, key=lambda c: _mem_texto_para_bytes(c["mem"]), reverse=True), 1)]
    if total > 4 * GB:
        achados.append(f"Os contêineres do Docker usam {gb(total)} de memória; veja se todos são necessários (studio containers).")
    return out


def ollama(achados: list) -> list:
    out = ["Ollama (modelos carregados na memória)"]
    r = run(["ollama", "ps"])
    if r is None:
        return out + ["O Ollama não respondeu (parado ou não instalado)."]
    mod = parse_ollama_ps(r)
    if not mod:
        return out + ["Nenhum modelo carregado agora."]
    out += [f"  {i}. {m}" for i, m in enumerate(mod, 1)]
    achados.append("Há modelo do Ollama carregado na memória; para liberar: ollama stop NOME-DO-MODELO.")
    return out


def servicos(procs_por_porta: dict = None) -> list:
    out = ["Serviços do Heimdall (porta, nome e memória)"]
    achou = False
    for porta in sorted(SERVICOS):
        pid = run(["lsof", "-nP", f"-iTCP:{porta}", "-sTCP:LISTEN", "-t"], 5)
        if not pid or not pid.split():
            continue
        p = pid.split()[0]
        rss = run(["ps", "-o", "rss=", "-p", p], 5)
        mem = mb(int(rss.strip()) * 1024) if rss and rss.strip().isdigit() else "?"
        out.append(f"  {SERVICOS[porta]} (porta {porta}): {mem}")
        achou = True
    if not achou:
        out.append("  Nenhum serviço do Heimdall escutando agora (ou o lsof não está disponível).")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Diagnóstico de desempenho do Mac")
    for o in ("memoria", "cpu", "disco", "docker", "ollama", "servicos", "versoes"):
        ap.add_argument("--" + o, action="store_true")
    ap.add_argument("--topo", type=int, default=8)
    a = ap.parse_args(argv)
    tudo = not any((a.memoria, a.cpu, a.disco, a.docker, a.ollama, a.servicos, a.versoes))
    achados, blocos = [], []
    procs = _processos() if (tudo or a.memoria or a.cpu) else []
    if tudo or a.memoria:
        blocos.append(memoria(a.topo, procs, achados))
    if tudo or a.cpu:
        blocos.append(cpu(a.topo, procs, achados))
    if tudo or a.disco:
        blocos.append(disco(achados))
    if tudo or a.docker:
        blocos.append(docker(achados))
    if tudo or a.ollama:
        blocos.append(ollama(achados))
    if tudo or a.servicos:
        blocos.append(servicos())
    avisos_versoes = []
    if a.versoes:  # só quando pedida: compara com o registro e usa a rede
        itens = heimdall_versoes.coletar(atualizacoes=True)
        blocos.append(heimdall_versoes.texto(itens))
        avisos_versoes = heimdall_versoes.avisos(itens)
    so_versoes = a.versoes and not any((a.memoria, a.cpu, a.disco, a.docker, a.ollama, a.servicos))
    for b in blocos:
        print("\n".join(b))
        print()
    if so_versoes:  # sem "Nada fora do normal": só fala se houver o que atualizar ou corrigir
        for n, x in enumerate(avisos_versoes, 1):
            print(f"Atenção {n}: {x}")
        return 0
    print("Conclusão")
    achados = achados + avisos_versoes
    if achados:
        for i, x in enumerate(achados, 1):
            print(f"  {i}. {x}")
    else:
        print("  Nada fora do normal nos itens conferidos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
