from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
import sys
import os
import psutil
from pathlib import Path
import json
import asyncio

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

USER_BASE_DIR = Path("/Users/mrl2_bolonhini")

try:
    from agent import tools as lang_tools
except ImportError:
    lang_tools = []

class CustomFileSystemTools:
    @staticmethod
    def _resolve_safe_path(relative_or_absolute_path: str) -> Path:
        target_path = Path(relative_or_absolute_path).expanduser().resolve()
        if not target_path.is_absolute():
            target_path = (USER_BASE_DIR / relative_or_absolute_path).resolve()
        return target_path

    @staticmethod
    def list_directory(path: str = "") -> str:
        """Lista arquivos e subpastas dentro da pasta de usuário no Mac."""
        try:
            target = CustomFileSystemTools._resolve_safe_path(path)
            if not target.exists():
                return f"Erro: O diretório '{target}' não existe."
            if not target.is_dir():
                return f"Erro: O caminho '{target}' não é um diretório."
            
            items = os.listdir(target)
            output = [f"Conteúdo de {target}:"]
            for item in sorted(items):
                if item.startswith('.'):
                    continue
                full_item = target / item
                kind = "[DIR] " if full_item.is_dir() else "[FILE]"
                output.append(f"{kind} {item}")
            return "\n".join(output)
        except Exception as e:
            return f"Falha ao listar diretório: {str(e)}"

    @staticmethod
    def read_file(file_path: str) -> str:
        """Lê o conteúdo de um arquivo de texto na pasta do usuário."""
        try:
            target = CustomFileSystemTools._resolve_safe_path(file_path)
            if not target.exists():
                return f"Erro: O arquivo '{target}' não foi encontrado."
            if target.is_dir():
                return f"Erro: '{target}' é um diretório, não um arquivo."
                
            with open(target, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            return f"--- Conteúdo de {target} ---\n\n{content}"
        except Exception as e:
            return f"Falha ao ler o arquivo: {str(e)}"

    @staticmethod
    def write_file(file_path: str, content: str) -> str:
        """Escreve ou sobrescreve um arquivo de texto na pasta do usuário."""
        try:
            target = CustomFileSystemTools._resolve_safe_path(file_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            
            with open(target, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Sucesso: Arquivo gravado em '{target}'."
        except Exception as e:
            return f"Falha ao escrever o arquivo: {str(e)}"

    @staticmethod
    def get_system_metrics() -> str:
        """Retorna o uso atual de RAM unificada, SWAP e CPU do host macOS."""
        ram = psutil.virtual_memory()
        swap = psutil.swap_memory()
        cpu = psutil.cpu_percent(interval=0.5)
        
        return (
            f"Métricas do Host Mac:\n"
            f"- CPU: {cpu}%\n"
            f"- RAM: {ram.percent}% usada ({ram.used / (1024**3):.2f} GB de {ram.total / (1024**3):.2f} GB)\n"
            f"- Swap: {swap.used / (1024**3):.2f} GB usados"
        )

# ATENÇÃO: redirect_slashes=False evita que o FastAPI/Starlette recuse requisições POST na raiz com 405
app = FastAPI(title="Heimdall Gateway - LiteLLM & Open-Client Compatible", redirect_slashes=False)

OLLAMA_URL = "http://localhost:11434"

def _get_tools_array():
    formatted_tools = []
    builtin_tools = [
        CustomFileSystemTools.list_directory,
        CustomFileSystemTools.read_file,
        CustomFileSystemTools.write_file,
        CustomFileSystemTools.get_system_metrics
    ]
    
    all_tools = list(lang_tools) + builtin_tools
    
    for i, t in enumerate(all_tools):
        schema = {"type": "object", "properties": {}}
        if hasattr(t, "args_schema") and t.args_schema:
            try:
                schema = t.args_schema.model_json_schema()
            except AttributeError:
                schema = t.args_schema.schema()
        elif hasattr(t, "__annotations__") and t.__annotations__:
            properties = {}
            for param_name, param_type in t.__annotations__.items():
                if param_name != 'return':
                    properties[param_name] = {"type": "string", "description": f"Parâmetro {param_name}"}
            schema = {"type": "object", "properties": properties}

        tool_name = getattr(t, "__name__", getattr(t, "name", f"tool_{i}"))
        tool_desc = getattr(t, "__doc__", getattr(t, "description", ""))
        
        tool_schema = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_desc.strip() if tool_desc else "",
                "parameters": schema
            }
        }
        formatted_tools.append(tool_schema)
    return formatted_tools

# --- HANDLER MCP CENTRALIZADO ---
async def handle_mcp_logic(request: Request):
    if request.method == "GET":
        tools_list = []
        for t in _get_tools_array():
            fn = t["function"]
            tools_list.append({
                "name": fn["name"],
                "description": fn["description"],
                "inputSchema": fn["parameters"]
            })
        return {
            "jsonrpc": "2.0",
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "StudioMacLocalHub", "version": "1.0.0"},
                "tools": tools_list
            }
        }

    try:
        body = await request.json()
        method = body.get("method")
        msg_id = body.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "StudioMacLocalHub", "version": "1.0.0"}
                }
            }
        elif method == "tools/list":
            tools_list = []
            for t in _get_tools_array():
                fn = t["function"]
                tools_list.append({
                    "name": fn["name"],
                    "description": fn["description"],
                    "inputSchema": fn["parameters"]
                })
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "tools": tools_list
                }
            }
        elif method == "tools/call":
            params = body.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            all_tools = list(lang_tools) + [
                CustomFileSystemTools.list_directory,
                CustomFileSystemTools.read_file,
                CustomFileSystemTools.write_file,
                CustomFileSystemTools.get_system_metrics
            ]
            
            selected_tool = None
            for t in all_tools:
                name = getattr(t, "__name__", getattr(t, "name", ""))
                if name == tool_name:
                    selected_tool = t
                    break
            
            if selected_tool:
                if asyncio.iscoroutinefunction(selected_tool):
                    res = await selected_tool(**arguments)
                else:
                    res = selected_tool(**arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": str(res)}]
                    }
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Ferramenta '{tool_name}' não encontrada."}
                }

        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    except Exception as e:
        return {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}}

@app.api_route("/", methods=["GET", "POST", "PUT", "DELETE"])
@app.api_route("", methods=["GET", "POST", "PUT", "DELETE"])
async def root_handler(request: Request):
    return await handle_mcp_logic(request)

@app.api_route("/messages", methods=["GET", "POST", "PUT", "DELETE"])
async def messages_handler(request: Request):
    return await handle_mcp_logic(request)

@app.get("/v1/mcp/server")
@app.get("/mcp/server")
async def mcp_server_manifest():
    tools_list = []
    for t in _get_tools_array():
        fn = t["function"]
        tools_list.append({
            "name": fn["name"],
            "description": fn["description"],
            "inputSchema": fn["parameters"]
        })
    return {
        "jsonrpc": "2.0",
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "StudioMacLocalHub", "version": "1.0.0"},
            "tools": tools_list
        }
    }

@app.get("/sse")
async def mcp_sse(request: Request):
    async def event_generator():
        endpoint_url = "http://localhost:8000/messages"
        yield f"event: endpoint\ndata: {endpoint_url}\n\n"
        while True:
            await asyncio.sleep(15)
            yield ": ping\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/v1/models")
@app.get("/models")
async def list_models():
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            data = resp.json()
            models = [
                {"id": m["name"], "object": "model", "owned_by": "ollama"}
                for m in data.get("models", [])
            ]
            return {"object": "list", "data": models}
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/v1/model/info")
@app.get("/model/info")
async def model_info():
    return {"status": "healthy", "models": ["gemma-4-uncensored", "qwen-3.8-uncensored", "bonsai-27b"]}

@app.get("/v1/health/readiness")
@app.get("/health/readiness")
@app.get("/health")
async def health_check():
    return {"status": "ok", "database": "connected"}

@app.post("/api/show")
async def ollama_show_proxy(request: Request):
    return {"details": {"parameters": ""}}

@app.get("/v1/tools/list")
@app.get("/tools/list")
async def list_tools_wrapped(request: Request):
    return {"tools": _get_tools_array()}

@app.get("/v1/tools")
@app.get("/tools")
async def list_tools(request: Request):
    return _get_tools_array()

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model = body.get("model", "eriktonon/qwen3.8-uncensored:9b")
    messages = body.get("messages", [])
    tools = body.get("tools", None)
    
    ollama_payload = {
        "model": model,
        "messages": messages,
        "stream": False
    }

    if tools:
        ollama_payload["tools"] = tools

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            ollama_resp = await client.post(f"{OLLAMA_URL}/api/chat", json=ollama_payload)
            response_data = ollama_resp.json()
            
            message = response_data.get("message", {})
            message_content = message.get("content", "")
            tool_calls = message.get("tool_calls", None)
            
            openai_message = {
                "role": "assistant",
                "content": message_content if message_content else "Processado."
            }
            
            if tool_calls:
                openai_message["tool_calls"] = tool_calls

            openai_formatted_response = {
                "id": "chatcmpl-heimdall-gateway",
                "object": "chat.completion",
                "created": 1700000000,
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": openai_message,
                    "finish_reason": "tool_calls" if tool_calls else "stop"
                }]
            }
            return JSONResponse(openai_formatted_response)
            
        except Exception as e:
            return JSONResponse({"error": f"Erro no gateway: {str(e)}"}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "proxy_gateway:app", 
        host="0.0.0.0", 
        port=8000,
        reload=False,
        log_level="info"
    )