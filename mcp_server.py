from mcp.server.mcpserver import MCPServer
import requests
import os
from pypdf import PdfReader

mcp = MCPServer("StudioMacLocalHub")

@mcp.tool()
def search_searxng(query: str) -> str:
    """Pesquisa por informações recentes ou dados na web usando o SearXNG local."""
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

@mcp.tool()
def read_local_document(file_path: str) -> str:
    """Lê e analisa o conteúdo de um arquivo de texto local no Mac."""
    try:
        expanded_path = os.path.expanduser(file_path)
        if not os.path.exists(expanded_path):
            return f"Erro: O arquivo '{file_path}' não foi encontrado."
        
        with open(expanded_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return f"Conteúdo do arquivo:\n---\n{content[:4000]}"
    except Exception as e:
        return f"Erro ao ler o documento: {str(e)}"

@mcp.tool()
def extract_pdf_text(file_path: str) -> str:
    """Extrai texto de um documento PDF local no Mac para análise."""
    try:
        expanded_path = os.path.expanduser(file_path)
        if not os.path.exists(expanded_path):
            return f"Erro: O arquivo PDF '{file_path}' não foi encontrado."
        
        reader = PdfReader(expanded_path)
        text = ""
        for page in reader.pages[:10]:
            text += page.extract_text() + "\n"
            
        return f"Conteúdo do PDF:\n---\n{text[:4000]}"
    except Exception as e:
        return f"Erro ao extrair texto do PDF: {str(e)}"

if __name__ == "__main__":
    # Garante que o transporte SSE escute na porta 8000 com o path /sse esperado pelo LiteLLM
    mcp.run(transport="sse", port=8000)