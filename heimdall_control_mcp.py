from fastmcp import FastMCP
import psutil
import httpx

mcp = FastMCP("HeimdallControl")

@mcp.tool()
def get_system_metrics() -> str:
    """Retorna o uso atual de RAM unificada, SWAP e CPU do host macOS."""
    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()
    cpu = psutil.cpu_percent(interval=1)
    
    return (
        f"Métricas do Host Mac:\n"
        f"- CPU: {cpu}%\n"
        f"- RAM: {ram.percent}% usada ({ram.used / (1024**3):.2f} GB de {ram.total / (1024**3):.2f} GB)\n"
        f"- Swap: {swap.used / (1024**3):.2f} GB usados"
    )

@mcp.tool()
async def check_ollama_models() -> str:
    """Lista os modelos atualmente carregados na memória pelo Ollama local."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:11434/api/ps")
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                if not models:
                    return "Nenhum modelo carregado na VRAM no momento."
                
                result = "Modelos Ativos no Ollama:\n"
                for m in models:
                    size_gb = m.get('size', 0) / (1024**3)
                    result += f"- {m.get('name')} ({size_gb:.2f} GB)\n"
                return result
            return "Erro ao consultar o Ollama local."
    except Exception as e:
        return f"Falha de conexão com o Ollama: {str(e)}"

if __name__ == "__main__":
    mcp.run()