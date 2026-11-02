import asyncio
import os
import math
import requests
from datetime import datetime
from pathlib import Path
import psutil
import xml.etree.ElementTree as ET

from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

# --- CONSTANTES DO SISTEMA ---
USER_BASE_DIR = Path("/Users/mrl2_bolonhini")

def _resolve_safe_path(relative_or_absolute_path: str) -> Path:
    """Garante que os caminhos sejam resolvidos de forma segura dentro da pasta de usuário."""
    target_path = Path(relative_or_absolute_path).expanduser().resolve()
    if not target_path.is_absolute():
        target_path = (USER_BASE_DIR / relative_or_absolute_path).resolve()
    return target_path

# --- 1. FERRAMENTAS NATIVAS E DE UTILIDADE (HEIMDALL CORE) ---

@tool
def search_searxng(query: str) -> str:
    """Pesquisa por informações recentes, notícias ou dados na web usando o SearXNG local."""
    try:
        url = "http://localhost:8080/search"
        params = {"q": query, "format": "json"}
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        results = []
        for result in data.get("results", [])[:3]:
            results.append(f"- {result.get('title')}: {result.get('content')}")
            
        return "\n".join(results) if results else "Nenhum resultado encontrado."
    except Exception as e:
        return f"Erro ao acessar o SearXNG: {str(e)}"

@tool
def list_directory(path: str = "") -> str:
    """Lista arquivos e subpastas dentro da pasta de usuário no Mac (/Users/mrl2_bolonhini)."""
    try:
        target = _resolve_safe_path(path)
        if not target.exists() or not target.is_dir():
            return f"Erro: Diretório inválido ou inexistente."
        items = os.listdir(target)
        output = [f"Conteúdo de {target}:"]
        for item in sorted(items):
            if item.startswith('.'): continue
            kind = "[DIR] " if (target / item).is_dir() else "[FILE]"
            output.append(f"{kind} {item}")
        return "\n".join(output)
    except Exception as e:
        return f"Falha ao listar diretório: {str(e)}"

@tool
def read_file(file_path: str) -> str:
    """Lê o conteúdo de um arquivo de texto na pasta de usuário no Mac."""
    try:
        target = _resolve_safe_path(file_path)
        if not target.exists() or target.is_dir():
            return f"Erro: Arquivo inválido ou inexistente."
        with open(target, 'r', encoding='utf-8', errors='replace') as f:
            return f"Conteúdo de {target}:\n---\n{f.read()[:6000]}"
    except Exception as e:
        return f"Erro ao ler o documento: {str(e)}"

@tool
def write_file(file_path: str, content: str) -> str:
    """Escreve ou sobrescreve um arquivo de texto na pasta de usuário no Mac."""
    try:
        target = _resolve_safe_path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Sucesso: Arquivo gravado em '{target}'."
    except Exception as e:
        return f"Falha ao escrever o arquivo: {str(e)}"

@tool
def get_system_metrics() -> str:
    """Retorna a utilização de RAM unificada, SWAP e CPU do host macOS (Heimdall Control)."""
    try:
        ram = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu = psutil.cpu_percent(interval=0.5)
        return f"Mac: CPU {cpu}% | RAM {ram.percent}% ({ram.used/(1024**3):.2f}GB) | Swap {swap.used/(1024**3):.2f}GB"
    except Exception as e:
        return f"Erro ao coletar métricas: {str(e)}"

@tool
def calculate_expression(expression: str) -> str:
    """Realiza cálculos matemáticos complexos de forma precisa."""
    try:
        allowed_names = {'sqrt': math.sqrt, 'sin': math.sin, 'cos': math.cos, 'pi': math.pi, 'e': math.e}
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return f"O resultado de {expression} é {result}"
    except Exception as e:
        return f"Erro ao calcular expressão: {str(e)}"

@tool
def get_system_timestamp() -> str:
    """Retorna a data e hora atual exata do sistema."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")


# --- 2. FERRAMENTAS NATIVAS DA COMUNIDADE (HACKER NEWS, REDDIT, RSS, ASTRONOMIA) ---

@tool
def get_hackernews_top_stories() -> str:
    """Busca as principais histórias em alta no Hacker News utilizando a API oficial pública."""
    try:
        top_ids_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
        response = requests.get(top_ids_url, timeout=5)
        story_ids = response.json()[:5]  # Pega os top 5
        
        stories = []
        for sid in story_ids:
            item_url = f"https://hacker-news.firebaseio.com/v0/item/{sid}.json"
            item_res = requests.get(item_url, timeout=3)
            item_data = item_res.json()
            if item_data and "title" in item_data:
                title = item_data.get("title")
                url = item_data.get("url", f"https://news.ycombinator.com/item?id={sid}")
                score = item_data.get("score", 0)
                stories.append(f"- [{score} pts] {title}\n  Link: {url}")
                
        return "Top Histórias do Hacker News:\n\n" + "\n".join(stories) if stories else "Nenhuma história encontrada."
    except Exception as e:
        return f"Erro ao acessar Hacker News: {str(e)}"

@tool
def search_reddit_posts(subreddit: str, query: str = "") -> str:
    """Busca posts em um subreddit específico do Reddit (ex: r/Python, r/MachineLearning)."""
    try:
        sub = subreddit.replace("r/", "").strip()
        url = f"https://www.reddit.com/r/{sub}/search.json"
        params = {"q": query, "restrict_sr": "on", "limit": 3, "sort": "new"} if query else f"https://www.reddit.com/r/{sub}/hot.json"
        
        headers = {"User-Agent": "HeimdallLab/1.0"}
        res = requests.get(url if not query else url, params=params if query else {"limit": 3}, headers=headers, timeout=5)
        
        if res.status_code != 200:
            return f"Erro ao acessar o Reddit (Status: {res.status_code})."
            
        data = res.json()
        posts = []
        for child in data.get("data", {}).get("children", [])[:3]:
            p_data = child.get("data", {})
            title = p_data.get("title")
            permalink = f"https://reddit.com{p_data.get('permalink')}"
            score = p_data.get("score", 0)
            posts.append(f"- [{score} upvotes] {title}\n  URL: {permalink}")
            
        return f"Resultados em r/{sub}:\n\n" + "\n".join(posts) if posts else "Nenhum post encontrado."
    except Exception as e:
        return f"Erro ao consultar o Reddit: {str(e)}"

@tool
def fetch_rss_feed(feed_url: str) -> str:
    """Lê e extrai as últimas notícias de um link RSS ou Atom Feed fornecido."""
    try:
        res = requests.get(feed_url, timeout=6)
        if res.status_code != 200:
            return f"Erro ao carregar RSS (Status: {res.status_code})."
            
        root = ET.fromstring(res.content)
        items = []
        
        # Tenta formato RSS padrão (<item>)
        for item in root.findall(".//item")[:4]:
            title = item.find("title")
            link = item.find("link")
            t_text = title.text if title is not None else "Sem título"
            l_text = link.text if link is not None else "#"
            items.append(f"- {t_text}\n  Link: {l_text}")
            
        # Se não achar, tenta formato Atom (<entry>)
        if not items:
            for entry in root.findall("{http://www.w3.org/2005/Atom}entry")[:4]:
                title = entry.find("{http://www.w3.org/2005/Atom}title")
                link = entry.find("{http://www.w3.org/2005/Atom}link")
                t_text = title.text if title is not None else "Sem título"
                l_text = link.attrib.get("href", "#") if link is not None else "#"
                items.append(f"- {t_text}\n  Link: {l_text}")

        return "Últimas atualizações do Feed:\n\n" + "\n".join(items) if items else "Nenhum item encontrado no feed."
    except Exception as e:
        return f"Erro ao processar RSS: {str(e)}"

@tool
def get_astronomy_apod() -> str:
    """Retorna informações sobre a Astronomia do dia (APOD - Astronomy Picture of the Day da NASA)."""
    try:
        url = "https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY"
        res = requests.get(url, timeout=5)
        if res.status_code != 200:
            return "Não foi possível recuperar os dados astronômicos no momento."
            
        data = res.json()
        title = data.get("title")
        date = data.get("date")
        explanation = data.get("explanation")
        media_url = data.get("url")
        
        return (
            f"🌌 Astronomia do Dia (NASA - {date}):\n"
            f"Título: {title}\n\n"
            f"Explicação: {explanation}\n\n"
            f"Mídia: {media_url}"
        )
    except Exception as e:
        return f"Erro ao buscar dados de astronomia: {str(e)}"


# --- 3. CONSOLIDAÇÃO DO TOOLBOX E AGENTE ---

tools = [
    search_searxng,
    list_directory,
    read_file,
    write_file,
    get_system_metrics,
    calculate_expression,
    get_system_timestamp,
    get_hackernews_top_stories,
    search_reddit_posts,
    fetch_rss_feed,
    get_astronomy_apod
]

# Configuração do modelo no Ollama
llm = ChatOllama(model="eriktonon/qwen3.8-uncensored:9b", temperature=0)

system_prompt = (
    "Você é o assistente autônomo Heimdall em um laboratório pessoal no macOS. "
    "Você tem total autonomia para gerenciar arquivos locais, monitorar o sistema, "
    "consultar o Hacker News, buscar tópicos no Reddit, ler RSS feeds e explorar astronomia. "
    "Use as ferramentas adequadas de forma prestativa e direta."
)

agent_executor = create_react_agent(llm, tools, prompt=system_prompt)


# --- 4. INTERFACE DE EXECUÇÃO ---
if __name__ == "__main__":
    print("--- Heimdall Lab (Modo Nativo Robusto) Inicializado ---")
    print("Digite sua pergunta ou 'sair' para encerrar.\n")
    
    while True:
        try:
            user_input = input("Usuário: ")
            if user_input.lower() in ["sair", "exit", "quit"]:
                break
            if not user_input.strip():
                continue
                
            messages = [{"role": "user", "content": user_input}]
            response = agent_executor.invoke({"messages": messages})
            
            final_output = response["messages"][-1].content
            print(f"\nAssistente:\n{final_output}\n" + "-"*50 + "\n")
            
        except KeyboardInterrupt:
            print("\nEncerrando...")
            break
        except Exception as e:
            print(f"\nOcorreu um erro na execução: {str(e)}\n")