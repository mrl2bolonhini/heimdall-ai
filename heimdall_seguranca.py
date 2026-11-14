#!/usr/bin/env python3
"""Tarefas de segurança do dolphin3-cyber-8b: o script coleta os dados no Mac e o modelo (só texto, sem ferramentas) analisa.

Três tarefas, chamadas pelo n8n através do agente do Mac (POST /seguranca/executar {"tarefa": "..."}):
    logs       todo dia: logins recusados (401/403 etc.) e erros repetidos nas últimas 24 h (logs/ e contêineres do Docker)
    commits    semanal: segredos, caminhos pessoais, IPs de rede privada e arquivos sensíveis nos commits dos últimos 7 dias
    exposicao  semanal: portas em escuta, contêineres com portas publicadas, Tailscale Funnel e firewall, comparados com a leitura anterior

Como o modelo é tratado (um modelo de 8B inventa achados):
    1. o script faz as verificações que não dependem do modelo e define uma gravidade mínima;
    2. o modelo só é chamado se houver algo a analisar;
    3. cada achado do modelo precisa citar um trecho dos dados; o script confere se o trecho existe e marca o que não existe;
    4. gravidade de média para cima, dita só pelo modelo e sem nenhum achado confirmado, cai para baixa;
    5. segredos são mascarados antes de ir ao modelo e antes de qualquer nota. As notas não trazem os dados brutos.

Uso à mão (na pasta do projeto, com o LiteLLM no ar):
    python3 heimdall_seguranca.py logs|commits|exposicao            roda a tarefa e mostra a nota
    python3 heimdall_seguranca.py logs|commits|exposicao --sem-modelo   só mostra os dados coletados, sem chamar o modelo

No .env (opcionais): HEIMDALL_SEGURANCA_MODELO (padrão dolphin3-cyber-8b), HEIMDALL_LITELLM_URL (padrão http://localhost:9000/v1/chat/completions).
"""
import json
import os
import re
import subprocess
import sys
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
ESTADO = DATA_DIR / "seguranca_estado.json"
MODELO = os.environ.get("HEIMDALL_SEGURANCA_MODELO", "dolphin3-cyber-8b")
LITELLM_URL = os.environ.get("HEIMDALL_LITELLM_URL", "http://localhost:9000/v1/chat/completions")
LIMITE_DADOS = 9000          # caracteres enviados ao modelo (contexto de 8192 tokens, com a resposta incluída)
TEMPO_MODELO = 900           # segundos: o dolphin de 8 GB demora para carregar quando o Mac está ocupado
NIVEIS = ["nenhuma", "baixa", "media", "alta"]
ROTULO = {"nenhuma": "nenhuma", "baixa": "baixa", "media": "média", "alta": "alta"}
EXTRA_PATH = "/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/sbin:/sbin"
LOGS_AUTH_MEDIA = 50         # recusas de login em 24 h que já pedem atenção
LOGS_AUTH_ALTA = 300


# ----------------------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------------------
def _exec(cmd, timeout=30, cwd=None, juntar=False):
    """Roda um comando; devolve (código, saída). Código None se o programa não existe ou estourou o tempo."""
    env = dict(os.environ)
    env["PATH"] = env.get("PATH", "") + ":" + EXTRA_PATH
    try:
        r = subprocess.run(cmd, capture_output=not juntar, stdout=subprocess.PIPE if juntar else None,
                           stderr=subprocess.STDOUT if juntar else None, text=True, errors="replace",
                           timeout=timeout, env=env, cwd=cwd)
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    saida = r.stdout or ""
    if not juntar and not saida:
        saida = r.stderr or ""
    return r.returncode, saida


def _hoje() -> str:
    return datetime.now().strftime("%d/%m/%Y")


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def _maximo(niveis) -> str:
    return max(list(niveis) + ["nenhuma"], key=NIVEIS.index)


_MASC_PREFIXOS = re.compile(r"\b(sk-|ghp_|gho_|ghu_|ghs_|github_pat_|xox[baprs]-|AKIA|ASIA)([A-Za-z0-9_\-]{4})[A-Za-z0-9_\-]{6,}")
_MASC_CHAVE = re.compile(r"(?i)((?:api[_-]?key|secret|token|passw(?:or)?d|senha|device_key|authorization)[\"']?\s*[:=]\s*[\"']?)([^\s\"',;]{4})[^\s\"',;]{4,}")
_MASC_BEARER = re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._\-]{4})[A-Za-z0-9._\-]{6,}")


def mascarar(texto: str) -> str:
    """Esconde o miolo de chaves e tokens (mantém 4 caracteres para o dono reconhecer qual é)."""
    t = _MASC_PREFIXOS.sub(lambda m: m.group(1) + m.group(2) + "…[oculto]", str(texto))
    t = _MASC_CHAVE.sub(lambda m: m.group(1) + m.group(2) + "…[oculto]", t)
    return _MASC_BEARER.sub(lambda m: m.group(1) + m.group(2) + "…[oculto]", t)


def _chave_litellm() -> str:
    chave = os.environ.get("LITELLM_MASTER_KEY", "")
    if chave:
        return chave
    try:
        for linha in (PROJECT_DIR / ".env").read_text(encoding="utf-8").splitlines():
            k, sep, v = linha.partition("=")
            if sep and k.strip() == "LITELLM_MASTER_KEY":
                return v.strip().strip("'\"")
    except OSError:
        pass
    return ""


def _ler_estado() -> dict:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar_estado(dado: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")


# ----------------------------------------------------------------------------------------
# Modelo
# ----------------------------------------------------------------------------------------
COMUM = (
    "Você é um analista de segurança de um laboratório pessoal de IA que roda em um MacBook, com serviços acessados pelo iPhone "
    "pelo Tailscale e por subdomínios da Cloudflare. Responda em português do Brasil, só com base nos DADOS recebidos; nunca invente. "
    "Formato obrigatório, sem nada antes nem depois:\n"
    "GRAVIDADE: nenhuma, baixa, media ou alta\n"
    "RESUMO: uma frase\n"
    "ACHADO: o que é e por que importa || EVIDENCIA: trecho copiado exatamente dos dados || ACAO: o que fazer\n"
    "Escreva uma linha ACHADO por problema, no máximo 6, cada uma em uma única linha. Se não houver nada preocupante, escreva "
    "GRAVIDADE: nenhuma e nenhuma linha ACHADO."
)
ORIENTACAO = {
    "exposicao": "Tarefa: revisar a exposição do Mac à rede. Foque no que mudou desde a leitura anterior, em escutas fora do próprio Mac, "
                 "no Tailscale Funnel (expõe à internet pública) e no firewall. Os serviços do Heimdall escutam em todas as interfaces de "
                 "propósito, para o acesso pelo Tailscale: só aponte um deles se a mudança for inesperada.",
    "logs": "Tarefa: revisar os logs das últimas 24 horas. Cada linha dos dados traz quantas vezes ocorreu (Nx) e um exemplo. Procure "
            "tentativas de login recusadas, padrões de varredura ou força bruta, e erros que se repetem sem motivo. Ignore ruído comum.",
    "commits": "Tarefa: revisar candidatos a vazamento nos commits da semana de um repositório PÚBLICO no GitHub. Cada linha traz o tipo, o "
               "commit, o arquivo e o trecho. Diga quais são problemas reais (segredo, caminho pessoal, IP de rede privada, e-mail pessoal, "
               "arquivo sensível) e quais parecem exemplos ou falsos alarmes.",
}


def _pedir_ao_modelo(tarefa: str, dados: str) -> str:
    chave = _chave_litellm()
    if not chave:
        raise RuntimeError("LITELLM_MASTER_KEY não está no ambiente nem no .env")
    if len(dados) > LIMITE_DADOS:
        dados = dados[:LIMITE_DADOS] + "\n[dados cortados por tamanho]"
    corpo = {"model": MODELO, "temperature": 0.2, "max_tokens": 800, "stream": False,
             "messages": [{"role": "system", "content": COMUM + "\n" + ORIENTACAO[tarefa]},
                          {"role": "user", "content": "DADOS:\n" + dados}]}
    req = urllib.request.Request(LITELLM_URL, data=json.dumps(corpo).encode("utf-8"), method="POST",
                                 headers={"Authorization": "Bearer " + chave, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TEMPO_MODELO) as r:
        resposta = json.loads(r.read().decode("utf-8"))
    return str(resposta["choices"][0]["message"]["content"] or "")


def interpretar(texto: str, dados: str) -> dict:
    """Lê a resposta do modelo e confere se cada evidência citada existe nos dados enviados."""
    base = _norm(dados)
    grav, formato_ok = "baixa", False
    m = re.search(r"GRAVIDADE\s*:\s*([A-Za-zÀ-ÿ]+)", texto, re.I)
    if m:
        g = _sem_acento(m.group(1).lower())
        if g in NIVEIS:
            grav, formato_ok = g, True
    r = re.search(r"RESUMO\s*:\s*(.+)", texto, re.I)
    resumo = r.group(1).strip() if r else ""
    achados = []
    for linha in texto.splitlines():
        if not re.match(r"^\W*ACHADO\s*:", linha, re.I):
            continue
        corpo = re.sub(r"^\W*ACHADO\s*:\s*", "", linha, flags=re.I)
        partes = [p.strip() for p in re.split(r"\s*\|\|\s*", corpo)]
        achado = {"texto": partes[0], "evidencia": "", "acao": ""}
        for p in partes[1:]:
            mm = re.match(r"(?i)(evid[eê]ncia|a[cç][aã]o)\s*:\s*(.*)", p)
            if mm:
                achado["evidencia" if mm.group(1).lower().startswith("evid") else "acao"] = mm.group(2).strip()
        ev = _norm(achado["evidencia"]).strip("`'\"“”")
        achado["confirmada"] = len(ev) >= 4 and ev in base
        if achado["texto"]:
            achados.append(achado)
    return {"gravidade": grav, "resumo": resumo, "achados": achados[:6], "formato_ok": formato_ok or bool(achados)}


def combinar(piso: str, modelo: str, achados: list) -> str:
    """Gravidade final: a maior entre as verificações do script e a do modelo; o modelo sozinho não passa de baixa sem evidência."""
    if modelo in ("media", "alta") and not any(a.get("confirmada") for a in achados):
        modelo = "baixa"
    return _maximo([piso, modelo])


# ----------------------------------------------------------------------------------------
# Coleta: exposição
# ----------------------------------------------------------------------------------------
_LSOF = re.compile(r"^(\S+)\s+\d+\s+\S+.*?(\*|\[[^\]]+\]|[\d.]+):(\d+) \(LISTEN\)")


def _escutas():
    rc, saida = _exec(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"])
    if rc is None:
        return None
    melhor = {}
    for linha in saida.splitlines()[1:]:
        m = _LSOF.match(linha)
        if not m:
            continue
        proc, addr, porta = m.group(1).replace("\\x20", " "), m.group(2), int(m.group(3))
        if addr in ("127.0.0.1", "[::1]"):
            nivel, txt = 0, "só neste Mac"
        elif addr in ("*", "[::]", "0.0.0.0"):
            nivel, txt = 2, "TODAS as interfaces"
        else:
            nivel, txt = 1, "interface " + addr
        if (proc, porta) not in melhor or nivel > melhor[(proc, porta)][0]:
            melhor[(proc, porta)] = (nivel, txt)
    return sorted(f"{proc} escutando na porta {porta} ({txt})" for (proc, porta), (_, txt) in melhor.items())


def _conteineres():
    rc, saida = _exec(["docker", "ps", "--format", "{{.Names}} {{.Ports}}"])
    if rc != 0:
        return None
    return sorted(l.strip() for l in saida.splitlines() if l.strip())


def _tailscale():
    for exe in ("tailscale", "/Applications/Tailscale.app/Contents/MacOS/Tailscale"):
        rc, saida = _exec([exe, "serve", "status"], timeout=15)
        if rc == 0:
            texto = saida.strip()
            return texto, "funnel on" in texto.lower()
    return None, False


def _firewall():
    rc, saida = _exec(["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"], timeout=10)
    if rc is None:
        return None
    s = saida.lower()
    return False if "disabled" in s else True if "enabled" in s else None


def _env_info():
    try:
        modo = (PROJECT_DIR / ".env").stat().st_mode & 0o777
    except OSError:
        return None, None
    rc, _ = _exec(["git", "check-ignore", "-q", ".env"], cwd=PROJECT_DIR)
    return modo, (rc == 0) if rc is not None else None


def coletar_exposicao(anterior: dict) -> dict:
    escutas, conteineres = _escutas(), _conteineres()
    ts_texto, funnel = _tailscale()
    fw = _firewall()
    modo, ignorado = _env_info()
    atual = sorted(set((escutas or []) + ["contêiner " + c for c in (conteineres or [])]))
    antes = anterior.get("itens")
    primeira = antes is None
    novos = [] if primeira else [i for i in atual if i not in antes]
    sumiram = [] if primeira else [i for i in antes if i not in atual]
    ver = []
    for n in novos:
        if "TODAS as interfaces" in n or "interface " in n or "0.0.0.0:" in n:
            ver.append(("media", "Nova escuta fora do próprio Mac: " + n))
    if funnel and (primeira or not anterior.get("funnel")):
        ver.append(("media", "O Tailscale Funnel está ligado: ele expõe um serviço à internet pública."))
    elif funnel:
        ver.append(("baixa", "O Tailscale Funnel continua ligado."))
    if fw is False:
        ver.append(("baixa", "O firewall do macOS está desligado."))
    if ignorado is False:
        ver.append(("alta", "O arquivo .env NÃO está no .gitignore: as chaves podem ir para o GitHub."))
    if modo is not None and modo & 0o077:
        ver.append(("baixa", f".env com permissão {modo:o}: outros usuários do Mac podem ler (o ideal é 600)."))
    linhas = ["ESCUTAS E CONTÊINERES AGORA:"] + (atual or ["(não consegui listar: lsof ou docker indisponível)"])
    linhas += ["", "TAILSCALE (serve/funnel): " + (ts_texto if ts_texto else "indisponível ou sem nada publicado"),
               "FIREWALL DO MACOS: " + {True: "ligado", False: "DESLIGADO", None: "não consegui ler"}[fw]]
    linhas += ["", "MUDANÇAS DESDE A LEITURA ANTERIOR: " + ("primeira leitura, sem comparação" if primeira else f"{len(novos)} nova(s), {len(sumiram)} removida(s)")]
    linhas += ["NOVAS: " + n for n in novos] + ["REMOVIDAS: " + s for s in sumiram]
    return {"dados": mascarar("\n".join(linhas)), "verificacoes": ver, "primeira": primeira,
            "precisa_modelo": primeira or bool(novos or sumiram or ver),
            "estado": {"itens": atual, "funnel": funnel, "em": datetime.now().isoformat(timespec="seconds")}}


# ----------------------------------------------------------------------------------------
# Coleta: logs
# ----------------------------------------------------------------------------------------
_AUTH = re.compile(r"(?i)\b(?:401|403)\b|unauthori[sz]ed|forbidden|invalid (?:token|password|credentials|api key)|token inv[aá]lido|"
                   r"senha (?:incorreta|inv[aá]lida)|login (?:failed|falhou)|authentication failed|access denied|permission denied|"
                   r"recusad|too many (?:requests|attempts)|brute")
_RUIDO = re.compile(r"Killed: 9")   # o start_heimdall.sh encerra os processos antigos a cada reinício
_ERRO = re.compile(r"(?i)traceback|exception|\berror\b|\berro\b|fatal|panic|out of memory|killed")


def agrupar_logs(fontes) -> list:
    """fontes: lista de (origem, linhas). Junta linhas parecidas (números viram N) e conta."""
    grupos = {}
    for origem, linhas in fontes:
        for l in linhas:
            l = l.rstrip()
            if _RUIDO.search(l):
                continue
            tipo = "auth" if _AUTH.search(l) else "erro" if _ERRO.search(l) else None
            if not tipo:
                continue
            chave = (tipo, re.sub(r"\d+", "N", l)[:140])
            if chave not in grupos:
                grupos[chave] = {"tipo": tipo, "n": 0, "exemplo": mascarar(l.strip())[:220], "origem": origem}
            grupos[chave]["n"] += 1
    return sorted(grupos.values(), key=lambda g: (g["tipo"] != "auth", -g["n"]))


def _linhas_arquivo(caminho: Path, max_bytes=2_000_000):
    try:
        with open(caminho, "rb") as f:
            f.seek(0, 2)
            tam = f.tell()
            f.seek(max(0, tam - max_bytes))
            return f.read().decode("utf-8", errors="replace").splitlines()[-4000:]
    except OSError:
        return []


def coletar_logs() -> dict:
    limite = datetime.now().timestamp() - 86400
    fontes = []
    for p in sorted((PROJECT_DIR / "logs").glob("*.log")):
        try:
            if p.stat().st_mtime >= limite:
                fontes.append((p.name, _linhas_arquivo(p)))
        except OSError:
            continue
    rc, nomes = _exec(["docker", "ps", "--format", "{{.Names}}"])
    if rc == 0:
        for nome in nomes.split():
            rc2, saida = _exec(["docker", "logs", "--since", "24h", "--tail", "4000", nome], timeout=45, juntar=True)
            if rc2 == 0:
                fontes.append(("contêiner " + nome, saida.splitlines()))
    grupos = agrupar_logs(fontes)
    auth = [g for g in grupos if g["tipo"] == "auth"]
    erros = [g for g in grupos if g["tipo"] == "erro" and g["n"] >= 5]
    total_auth = sum(g["n"] for g in auth)
    ver = []
    if total_auth >= LOGS_AUTH_ALTA:
        ver.append(("alta", f"{total_auth} linhas de acesso recusado nas últimas 24 h."))
    elif total_auth >= LOGS_AUTH_MEDIA:
        ver.append(("media", f"{total_auth} linhas de acesso recusado nas últimas 24 h."))
    elif total_auth:
        ver.append(("baixa", f"{total_auth} linha(s) de acesso recusado nas últimas 24 h."))
    linhas = [f"ACESSOS RECUSADOS (total {total_auth} linhas):"]
    linhas += [f"{g['n']}x [{g['origem']}] {g['exemplo']}" for g in auth[:8]] or ["(nenhum)"]
    linhas += ["", "ERROS QUE SE REPETEM (5 ou mais vezes):"]
    linhas += [f"{g['n']}x [{g['origem']}] {g['exemplo']}" for g in erros[:10]] or ["(nenhum)"]
    return {"dados": "\n".join(linhas), "verificacoes": ver, "primeira": False, "precisa_modelo": total_auth >= 5 or bool(erros), "estado": None}


# ----------------------------------------------------------------------------------------
# Coleta: commits
# ----------------------------------------------------------------------------------------
_HOME = re.escape(Path.home().name)
PADROES_COMMIT = [
    ("segredo", "alta", re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{12,}|"
                                    r"xox[baprs]-[A-Za-z0-9\-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")),
    ("segredo", "alta", re.compile(r"(?i)(?:api[_-]?key|secret|token|passw(?:or)?d|senha|device_key)[\"']?\s*[:=]\s*[\"'][^\"'\s]{12,}[\"']")),
    ("caminho pessoal", "media", re.compile(r"/Users/" + _HOME)),
    ("rede privada", "media", re.compile(r"\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
                                          r"100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}|[\w-]+\.ts\.net)\b")),
    ("e-mail", "media", re.compile(r"[\w.+-]{2,}@(?!heimdall-ai\.tech)[\w-]+\.[\w.]+")),
]
_ARQ_SENSIVEL = re.compile(r"(^|/)(\.env(\.[a-z]+)?|[^/]*\.(pem|p12|pfx|key|db|sqlite3?)|id_rsa[^/]*|[^/]*credentials[^/]*|(backups|banco)/[^/]+)$")


def _placeholder(valor: str) -> bool:
    v = valor.lower()
    if re.search(r"\$[A-Za-z_{(]", v):    # variável de shell: o valor vem de fora
        return True
    return any(s in v for s in ("__", "environ", "getenv", "${", "$(", "{{", "<", "xxx", "exemplo", "example", "changeme",
                                "seu_", "sua_", "seu-", "sua-", "****", "…", "..."))


def candidatos_commits(texto: str) -> list:
    """texto: saída de git log -p --unified=0 com a linha "@@COMMIT <hash> <assunto>" antes de cada commit."""
    achados, vistos = [], set()
    commit = arquivo = ""

    def adicionar(tipo, nivel, trecho):
        trecho = mascarar(trecho.strip())[:200]
        chave = (tipo, arquivo, trecho)
        if chave not in vistos and len(achados) < 40:
            vistos.add(chave)
            achados.append({"tipo": tipo, "nivel": nivel, "commit": commit, "arquivo": arquivo, "trecho": trecho})

    for linha in texto.splitlines():
        if linha.startswith("@@COMMIT "):
            commit, arquivo = linha[9:].split(" ", 1)[0], ""
            continue
        if linha.startswith("+++ b/"):
            arquivo = linha[6:]
            if _ARQ_SENSIVEL.search(arquivo) and not re.search(r"\.(example|exemplo)", arquivo):
                adicionar("arquivo sensível", "alta", "arquivo versionado: " + arquivo)
            continue
        if linha.startswith(("+++", "---")) or not linha.startswith("+"):
            continue
        corpo = linha[1:501]
        eh_teste = Path(arquivo).name.startswith(("teste_", "test_"))   # testes usam valores de mentira de propósito
        for i, (tipo, nivel, rx) in enumerate(PADROES_COMMIT):
            if eh_teste and i > 0:
                continue                                              # em testes só vale chave com formato real (sk-, ghp_...)
            m = rx.search(corpo)
            if not m or (tipo == "segredo" and _placeholder(m.group(0))):
                continue
            if tipo == "e-mail" and re.search(r"\.gov\.br$|example\.|@x\.|@x$", m.group(0)):
                continue                                              # endereços de exemplo
            adicionar(tipo, nivel, corpo)
    return achados


def coletar_commits(dias: int = 7) -> dict:
    rc, saida = _exec(["git", "log", f"--since={dias} days ago", "--no-merges", "-p", "--unified=0", "--no-color",
                       "--format=@@COMMIT %h %s"], timeout=60, cwd=PROJECT_DIR)
    achados = candidatos_commits(saida) if rc == 0 else []
    ver = []
    for tipo in sorted({a["tipo"] for a in achados}):
        n = sum(1 for a in achados if a["tipo"] == tipo)
        ver.append((_maximo(a["nivel"] for a in achados if a["tipo"] == tipo), f"{n} candidato(s) de {tipo} nos commits dos últimos {dias} dias."))
    linhas = [f"[{a['tipo']}] commit {a['commit']} arquivo {a['arquivo']}: {a['trecho']}" for a in achados] or ["(nenhum candidato)"]
    return {"dados": "\n".join(linhas), "verificacoes": ver, "primeira": False, "precisa_modelo": bool(achados), "estado": None}


# ----------------------------------------------------------------------------------------
# Execução
# ----------------------------------------------------------------------------------------
TITULOS = {"exposicao": "Exposição do Mac", "logs": "Logs de segurança", "commits": "Revisão de commits"}


def _markdown(titulo, final, resumo, achados, ver, modelo_erro, formato_ok):
    m = [f"# {titulo}", "",
         f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} pelo modelo {MODELO}. É uma revisão automática: confira cada achado antes de agir.",
         "", f"Gravidade: {ROTULO[final]}"]
    if resumo:
        m.append("Resumo: " + resumo)
    if modelo_erro:
        m.append("Atenção: o modelo não respondeu (" + modelo_erro + "). Valem só as verificações do script abaixo.")
    elif not formato_ok:
        m.append("Atenção: a resposta do modelo veio fora do formato; a gravidade dele foi tratada como baixa.")
    if achados:
        m += ["", "## Achados do modelo"]
        for i, a in enumerate(achados, 1):
            m.append(f"{i}. {a['texto']}")
            m.append("   - Evidência: " + (a["evidencia"] or "não citada") + (" (confirmada nos dados)" if a["confirmada"] else " (NÃO encontrada nos dados: pode ser invenção do modelo)"))
            if a["acao"]:
                m.append("   - O que fazer: " + a["acao"])
    if ver:
        m += ["", "## Verificações do script (sem o modelo)"] + [f"- [{ROTULO[n]}] {t}" for n, t in ver]
    return "\n".join(m)


def executar(tarefa: str, usar_modelo: bool = True) -> dict:
    if tarefa not in TITULOS:
        raise ValueError("tarefa desconhecida: use logs, commits ou exposicao")
    anterior = _ler_estado()
    coleta = {"exposicao": lambda: coletar_exposicao(anterior.get("exposicao", {})),
              "logs": coletar_logs, "commits": coletar_commits}[tarefa]()
    ver = coleta["verificacoes"]
    piso = _maximo(n for n, _ in ver)
    resultado = {"gravidade": "nenhuma", "resumo": "", "achados": [], "formato_ok": True}
    modelo_erro = ""
    if usar_modelo and coleta["precisa_modelo"]:
        try:
            resultado = interpretar(_pedir_ao_modelo(tarefa, coleta["dados"]), coleta["dados"])
        except Exception as e:  # noqa: BLE001 - modelo fora do ar: as verificações do script continuam valendo
            modelo_erro = (type(e).__name__ + ": " + str(e))[:160]
    modelo_grav = resultado["gravidade"] if resultado["formato_ok"] else "baixa"
    final = combinar(piso, modelo_grav, resultado["achados"])
    resumo = resultado["resumo"] or (ver[0][1] if ver else "")
    if tarefa == "exposicao" and usar_modelo and coleta["estado"] is not None and not modelo_erro:
        anterior["exposicao"] = coleta["estado"]
        _gravar_estado(anterior)
    titulo = f"{TITULOS[tarefa]} {_hoje()}"
    gravar = final in ("media", "alta") or coleta["primeira"] or (final == "baixa" and any(a["confirmada"] for a in resultado["achados"]))
    linha = (ROTULO[final].capitalize() + ": " + (resumo or "nada de preocupante")) if final != "nenhuma" else "Nada de preocupante."
    if modelo_erro:
        linha = "(sem o modelo) " + linha
    return {"ok": True, "tarefa": tarefa, "gravidade": final, "titulo": titulo, "linha": linha[:400], "gravar": gravar,
            "achados": len(resultado["achados"]), "modelo_usado": bool(usar_modelo and coleta["precisa_modelo"] and not modelo_erro),
            "modelo_erro": modelo_erro, "dados": coleta["dados"],
            "markdown": _markdown(titulo, final, resumo, resultado["achados"], ver, modelo_erro, resultado["formato_ok"])}


def main(argv) -> int:
    if len(argv) < 2 or argv[1] not in TITULOS:
        print(__doc__)
        return 2
    r = executar(argv[1], usar_modelo="--sem-modelo" not in argv)
    if "--sem-modelo" in argv:
        print(r["dados"])
        print("\nVerificações do script: gravidade mínima =", r["gravidade"])
    else:
        print(r["markdown"])
        print(f"\n[{'seria gravada' if r['gravar'] else 'não seria gravada'} no app Notas; aviso: {r['linha']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
