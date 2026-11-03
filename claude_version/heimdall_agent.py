"""Agente local de teste do Heimdall (LangGraph + Ollama), usando as mesmas
ferramentas do servidor MCP."""
from langchain_core.tools import StructuredTool
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

import tools

# O schema dos argumentos vem dos type hints; a descrição, da docstring.
tools = [StructuredTool.from_function(fn) for fn in tools.ALL_TOOLS]

llm = ChatOllama(
    model="eriktonon/qwen3.8-uncensored:9b",
    temperature=0.3,  # temperature=0 pode causar loops em modelos Qwen
    num_ctx=8192,     # o padrão do Ollama é pequeno e trunca as definições das ferramentas
)

system_prompt = (
    "Você é o Heimdall-ai, assistente de um laboratório pessoal no macOS. "
    "Você pode gerenciar arquivos locais, monitorar o sistema, consultar o Hacker News, "
    "buscar no Reddit, ler feeds RSS, pesquisar na web e ver a astronomia do dia. "
    "Quando precisar de dados do sistema ou de qualquer fonte externa, chame a ferramenta "
    "correspondente. Nunca escreva a chamada da ferramenta como texto. "
    "Responda em português, de forma direta."
)

agent_executor = create_react_agent(llm, tools, prompt=system_prompt)


if __name__ == "__main__":
    print("--- Heimdall Lab inicializado ---")
    print("Digite sua pergunta, '/novo' para limpar a conversa ou 'sair' para encerrar.\n")

    history = []
    while True:
        try:
            user_input = input("Usuário: ").strip()
            if user_input.lower() in ["sair", "exit", "quit"]:
                break
            if not user_input:
                continue
            if user_input == "/novo":
                history = []
                print("Conversa reiniciada.\n")
                continue

            history.append({"role": "user", "content": user_input})
            response = agent_executor.invoke({"messages": history})
            history = response["messages"]

            print(f"\nAssistente:\n{history[-1].content}\n" + "-" * 50 + "\n")

        except KeyboardInterrupt:
            print("\nEncerrando...")
            break
        except Exception as e:
            print(f"\nOcorreu um erro na execução: {e}\n")
