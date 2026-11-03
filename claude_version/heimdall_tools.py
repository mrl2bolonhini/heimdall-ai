"""Ferramentas do Heimdall.

Funções simples, sem decoradores, usadas tanto pelo servidor MCP
(heimdall_mcp.py) quanto pelo agente local (agent.py).
Cada função precisa de type hints e docstring: é isso que o modelo enxerga.
"""
import ast
import math
import operator
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import psutil
import requests

USER_BASE_DIR = Path(os.getenv("HEIMDALL_BASE_DIR", "/Users/mrl2_bolonhini")).resolve()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080")
NASA_API_KEY = os.getenv("NASA_API_KEY", "DEMO_KEY")
MAX_READ_CHARS = 6000


# --- Caminho seguro -----------------------------------------------------------

def _resolve_safe_path(path: str) -> Path:
    """Resolve o caminho e garante que ele fica dentro de USER_BASE_DIR."""
    raw = Path(path).expanduser()
    if not raw.is_absolute():
        raw = USER_BASE_DIR / raw
    target = raw.resolve()  # resolve também symlinks
    if not target.is_relative_to(USER_BASE_DIR):
        raise PermissionError(f"Acesso negado: fora de {USER_BASE_DIR}")
    return target


# --- Calculadora segura (sem eval) --------------------------------------------

_BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_UN_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "exp": math.exp,
    "abs": abs, "round": round,
}
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UN_OPS:
        return _UN_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 1000:
            raise ValueError("Expoente grande demais")
        return _BIN_OPS[type(node.op)](left, right)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCS and not node.keywords):
        return _FUNCS[node.func.id](*[_eval_node(a) for a in node.args])
    raise ValueError("Expressão não permitida")


# --- 1. Utilidades ------------------------------------------------------------

def search_searxng(query: str) -> str:
    """Pesquisa informações recentes, notícias ou dados na web usando o SearXNG local."""
    try:
        res = requests.get(
            f"{SEARXNG_URL}/search",
            params={"q": query, "format": "json"},
            timeout=8,
        )
        if res.status_code == 403:
            return "SearXNG recusou o formato JSON. Habilite 'json' em search.formats no settings.yml."
        res.raise_for_status()
        results = [
            f"- {r.get('title')}: {r.get('content')}\n  URL: {r.get('url')}"
            for r in res.json().get("results", [])[:5]
        ]
        return "\n".join(results) if results else "Nenhum resultado encontrado."
    except Exception as e:
        return f"Erro ao acessar o SearXNG: {e}"


def list_directory(path: str = "") -> str:
    """Lista arquivos e subpastas dentro da pasta do usuário no Mac. Sem argumento, lista a pasta raiz do usuário."""
    try:
        target = _resolve_safe_path(path)
        if not target.is_dir():
            return "Erro: diretório inválido ou inexistente."
        lines = [f"Conteúdo de {target}:"]
        for item in sorted(os.listdir(target)):
            if item.startswith("."):
                continue
            kind = "[DIR] " if (target / item).is_dir() else "[FILE]"
            lines.append(f"{kind} {item}")
        return "\n".join(lines)
    except Exception as e:
        return f"Falha ao listar diretório: {e}"


def read_file(file_path: str) -> str:
    """Lê o conteúdo de um arquivo de texto na pasta do usuário no Mac (até 6000 caracteres)."""
    try:
        target = _resolve_safe_path(file_path)
        if not target.is_file():
            return "Erro: arquivo inválido ou inexistente."
        text = target.read_text(encoding="utf-8", errors="replace")
        note = f"\n[...truncado, {len(text)} caracteres no total]" if len(text) > MAX_READ_CHARS else ""
        return f"Conteúdo de {target}:\n---\n{text[:MAX_READ_CHARS]}{note}"
    except Exception as e:
        return f"Erro ao ler o documento: {e}"


def write_file(file_path: str, content: str) -> str:
    """Escreve ou sobrescreve um arquivo de texto na pasta do usuário no Mac. Não grava em pastas ocultas (começam com ponto)."""
    try:
        target = _resolve_safe_path(file_path)
        rel_parts = target.relative_to(USER_BASE_DIR).parts
        if any(part.startswith(".") for part in rel_parts):
            return "Erro: gravação em arquivos ou pastas ocultas não é permitida."
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Sucesso: arquivo gravado em '{target}'."
    except Exception as e:
        return f"Falha ao escrever o arquivo: {e}"


def get_system_metrics() -> str:
    """Retorna o uso atual de RAM, swap e CPU do Mac (host do Heimdall)."""
    try:
        ram = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu = psutil.cpu_percent(interval=0.5)
        return (
            f"Mac: CPU {cpu}% | "
            f"RAM {ram.percent}% ({ram.used / 1024**3:.2f} GB de {ram.total / 1024**3:.2f} GB) | "
            f"Swap {swap.used / 1024**3:.2f} GB"
        )
    except Exception as e:
        return f"Erro ao coletar métricas: {e}"


def get_disk_usage() -> str:
    """Retorna o espaço total, usado e livre do disco principal do Mac."""
    try:
        d = psutil.disk_usage("/")
        return (
            f"Disco: {d.percent}% usado | total {d.total / 1024**3:.2f} GB | "
            f"usado {d.used / 1024**3:.2f} GB | livre {d.free / 1024**3:.2f} GB"
        )
    except Exception as e:
        return f"Erro ao consultar o disco: {e}"


def check_ollama_models() -> str:
    """Lista os modelos carregados agora na memória pelo Ollama local."""
    try:
        res = requests.get(f"{OLLAMA_URL}/api/ps", timeout=5)
        res.raise_for_status()
        models = res.json().get("models", [])
        if not models:
            return "Nenhum modelo carregado na memória no momento."
        return "Modelos ativos no Ollama:\n" + "\n".join(
            f"- {m.get('name')} ({m.get('size', 0) / 1024**3:.2f} GB)" for m in models
        )
    except Exception as e:
        return f"Falha de conexão com o Ollama: {e}"


def calculate_expression(expression: str) -> str:
    """Calcula uma expressão matemática. Aceita + - * / // % ** ^, parênteses, pi, e e as funções sqrt, sin, cos, tan, log, log10, exp, abs, round."""
    try:
        tree = ast.parse(expression.replace("^", "**").strip(), mode="eval")
        return f"O resultado de {expression} é {_eval_node(tree)}"
    except Exception as e:
        return f"Erro ao calcular expressão: {e}"


def get_system_timestamp() -> str:
    """Retorna a data e a hora atuais do sistema."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")


# --- 2. Comunidade: Hacker News, Reddit, RSS, astronomia ----------------------

def get_hackernews_top_stories() -> str:
    """Busca as 5 principais histórias em alta no Hacker News."""
    try:
        ids = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json", timeout=5
        ).json()[:5]
        stories = []
        for sid in ids:
            item = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=5
            ).json()
            if item and "title" in item:
                url = item.get("url", f"https://news.ycombinator.com/item?id={sid}")
                stories.append(f"- [{item.get('score', 0)} pts] {item['title']}\n  Link: {url}")
        return "Top histórias do Hacker News:\n\n" + "\n".join(stories) if stories else "Nenhuma história encontrada."
    except Exception as e:
        return f"Erro ao acessar o Hacker News: {e}"


def search_reddit_posts(subreddit: str, query: str = "") -> str:
    """Busca posts em um subreddit (ex: Python, MachineLearning). Com query, pesquisa; sem query, lista os posts em alta."""
    try:
        sub = subreddit.replace("r/", "").strip("/ ")
        if query:
            url = f"https://www.reddit.com/r/{sub}/search.json"
            params = {"q": query, "restrict_sr": "on", "limit": 5, "sort": "new"}
        else:
            url = f"https://www.reddit.com/r/{sub}/hot.json"
            params = {"limit": 5}
        res = requests.get(url, params=params, headers={"User-Agent": "HeimdallLab/1.0"}, timeout=8)
        if res.status_code != 200:
            return f"Erro ao acessar o Reddit (status {res.status_code}). O Reddit costuma bloquear acessos sem autenticação."
        posts = []
        for child in res.json().get("data", {}).get("children", [])[:5]:
            p = child.get("data", {})
            posts.append(f"- [{p.get('score', 0)} upvotes] {p.get('title')}\n  URL: https://reddit.com{p.get('permalink')}")
        return f"Resultados em r/{sub}:\n\n" + "\n".join(posts) if posts else "Nenhum post encontrado."
    except Exception as e:
        return f"Erro ao consultar o Reddit: {e}"


def fetch_rss_feed(feed_url: str) -> str:
    """Lê as últimas notícias de um feed RSS ou Atom a partir da URL do feed."""
    try:
        res = requests.get(feed_url, timeout=8)
        if res.status_code != 200:
            return f"Erro ao carregar o feed (status {res.status_code})."
        root = ET.fromstring(res.content)
        items = []
        for item in root.findall(".//item")[:5]:
            title, link = item.find("title"), item.find("link")
            items.append(f"- {title.text if title is not None else 'Sem título'}\n  Link: {link.text if link is not None else '#'}")
        if not items:
            ns = "{http://www.w3.org/2005/Atom}"
            for entry in root.findall(f"{ns}entry")[:5]:
                title, link = entry.find(f"{ns}title"), entry.find(f"{ns}link")
                href = link.attrib.get("href", "#") if link is not None else "#"
                items.append(f"- {title.text if title is not None else 'Sem título'}\n  Link: {href}")
        return "Últimas atualizações do feed:\n\n" + "\n".join(items) if items else "Nenhum item encontrado no feed."
    except Exception as e:
        return f"Erro ao processar o feed: {e}"


def get_astronomy_apod() -> str:
    """Retorna a Astronomia do Dia da NASA (APOD): título, explicação e link da mídia."""
    try:
        res = requests.get(
            "https://api.nasa.gov/planetary/apod", params={"api_key": NASA_API_KEY}, timeout=8
        )
        if res.status_code != 200:
            return f"Não foi possível recuperar os dados astronômicos (status {res.status_code})."
        d = res.json()
        return (
            f"Astronomia do Dia (NASA, {d.get('date')}):\n"
            f"Título: {d.get('title')}\n\n"
            f"Explicação: {d.get('explanation')}\n\n"
            f"Mídia: {d.get('url')}"
        )
    except Exception as e:
        return f"Erro ao buscar dados de astronomia: {e}"


# Lista única: o MCP e o agent.py registram exatamente estas funções.
ALL_TOOLS = [
    search_searxng,
    list_directory,
    read_file,
    write_file,
    get_system_metrics,
    get_disk_usage,
    check_ollama_models,
    calculate_expression,
    get_system_timestamp,
    get_hackernews_top_stories,
    search_reddit_posts,
    fetch_rss_feed,
    get_astronomy_apod,
]
