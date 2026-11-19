#!/usr/bin/env python3
"""Fonte única dos modelos personalizados do chat (Open WebUI) e das funções que cada um pode usar.

Daqui saem o guia modelos_open_webui.txt e a tabela do README (python3 gerar_docs.py). O teste teste_modelos_chat.py confere que
toda função citada existe, que cada prompt só fala das funções do seu modelo e que nenhuma função do servidor de dados ficou sem uso.
Para criar um modelo novo: acrescente-o em MODELOS (e, se precisar de um filtro novo, em CONEXOES), crie o prompt_chat_*.txt e rode gerar_docs.py.
"""
import ast
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent

SAUDE = ["saude_historico", "analise_saude", "frequencia_cardiaca_resumo", "ecg_resumo", "treinos_resumo", "relatorio_saude", "banco_consultar", "get_system_timestamp"]
FINANCAS = ["financas_resumo", "financas_transacoes", "financas_orcamentos", "financas_recorrentes", "financas_boletos", "financas_futuros", "get_system_timestamp"]
GERAL = ["banco_resumo", "banco_consultar", "banco_buscar", "saude_historico", "get_system_timestamp"]
INTERNET = ["search_searxng", "calculate_expression", "get_system_timestamp", "get_hackernews_top_stories", "search_reddit_posts", "fetch_rss_feed",
            "get_astronomy_apod", "get_youtube_transcript", "fetch_url"]
MEMORIA = ["memory_save", "memory_search", "memory_forget", "rag_temas", "rag_search"]

# Conexões em Configurações do administrador, Integrações, Servidores de ferramentas externos. Várias conexões podem apontar para o mesmo servidor
# com filtros diferentes: é o filtro que limita as funções que cada modelo enxerga (um modelo de 8B escolhe melhor entre 7 funções do que entre 16).
CONEXOES = [
    {"id": "banco-pessoal", "nome": "Meus Dados (banco pessoal)", "descricao": "Banco pessoal em modo leitura: diários oficiais, e-mails, estudos, privacidade, avisos, Second Brain e métricas de saúde simples. Só para o administrador.", "url": "http://host.docker.internal:8004/mcp", "grupo": "DADOS_TOOLS", "acesso": "só do administrador", "funcoes": GERAL},
    {"id": "banco-saude", "nome": "Saúde (banco pessoal)", "descricao": "Saúde em modo leitura: histórico por métrica, análises, coração, ECG, treinos e relatório. Só para o administrador.", "url": "http://host.docker.internal:8004/mcp", "grupo": "DADOS_TOOLS", "acesso": "só do administrador", "funcoes": SAUDE},
    {"id": "banco-financas", "nome": "Finanças (Finance)", "descricao": "Finance em modo leitura: resumo do mês, lançamentos, orçamentos, recorrentes, boletos e pagamentos futuros. Só para o administrador.", "url": "http://host.docker.internal:8004/mcp", "grupo": "DADOS_TOOLS", "acesso": "só do administrador", "funcoes": FINANCAS},
    {"id": "internet", "nome": "Internet e Utilidades", "descricao": "Pesquisa na web, cálculo, notícias, feeds, transcrições e utilidades públicas.", "url": "http://host.docker.internal:8001/mcp", "grupo": "PUBLIC_TOOLS", "acesso": "", "funcoes": INTERNET},
    {"id": "mac-admin", "nome": "Mac e Memória (administrador)", "descricao": "Memória persistente e documentos pessoais (RAG). Só para o administrador.", "url": "http://host.docker.internal:8000/mcp", "grupo": "MAC_TOOLS", "acesso": "só do administrador", "funcoes": MEMORIA},
]

# temperatura: valor sugerido no campo Parâmetros avançados. conexao: id da conexão acima (vazio = sem ferramentas).
MODELOS = [
    {"id": "meus-dados", "nome": "Meus Dados", "base": "qwen3-vl-instruct", "prompt": "prompt_chat_dados.txt", "temperatura": 0.2, "conexao": "banco-pessoal",
     "uso": "diários oficiais, e-mails de serviços públicos, estudos, privacidade, avisos, Second Brain e métricas de saúde simples", "nativa": True},
    {"id": "saude", "nome": "Saúde", "base": "qwen3-vl-instruct", "prompt": "prompt_chat_saude.txt", "temperatura": 0.2, "conexao": "banco-saude",
     "uso": "sono, pulso, variabilidade, treinos, ECG, anomalias e relatórios de saúde", "nativa": True},
    {"id": "financas", "nome": "Finanças", "base": "qwen3-vl-instruct", "prompt": "prompt_chat_financas.txt", "temperatura": 0.2, "conexao": "banco-financas",
     "uso": "gastos, receitas, categorias, orçamentos, assinaturas, parcelas e boletos do Finance (só leitura)", "nativa": True},
    {"id": "codigo", "nome": "Código", "base": "deepseek-coder-v2:16b", "prompt": "prompt_chat_codigo.txt", "temperatura": 0.2, "conexao": "",
     "uso": "programação, sem ferramentas", "nativa": False,
     "obs": "nos seus testes esse modelo não suporta ferramentas no Ollama. O contexto dele é de 8192 tokens e ele sai da memória 30 segundos depois do uso."},
    {"id": "curiosidades", "nome": "Curiosidades", "base": "qwen3-vl-instruct", "prompt": "prompt_chat_curiosidades.txt", "temperatura": 0.4, "conexao": "internet",
     "uso": "web, notícias, cálculo, transcrições e feeds", "nativa": True,
     "obs": "usa o mesmo modelo do Meus Dados, sem trocar de modelo na memória."},
    {"id": "conversas", "nome": "Conversas", "base": "gemma-4-uncensored", "prompt": "prompt_chat_conversas.txt", "temperatura": 0.8, "conexao": "",
     "uso": "conversa livre, sem ferramentas", "nativa": False},
    {"id": "documentos", "nome": "Documentos e Memória", "base": "qwen3-vl-instruct", "prompt": "prompt_chat_documentos.txt", "temperatura": 0.2, "conexao": "mac-admin",
     "uso": "livros, notas e documentos do estudo e memória pessoal (opcional)", "nativa": True},
]

NOVOS = """MODELOS NOVOS QUE AINDA NÃO TÊM PAPEL NO CHAT
  llama-3.1-8b: aceita ferramentas e respondeu bem em português. É candidato a substituir o qwen3-vl-instruct no Curiosidades ou no Meus Dados, se ele errar menos ao escolher ferramentas. Compare as mesmas 3 perguntas nos dois antes de trocar. Atenção: usar um segundo modelo de 8B alternando com o qwen3-vl-instruct faz a memória de 16 GB trocar de modelo a cada mudança de chat.
  dolphin3-cyber-8b: só texto (sem ferramentas). Já trabalha nas tarefas programadas de segurança; no chat só faria sentido para analisar um texto colado.
  gemma3-4b: usado nos resumos do News; é pequeno e rápido, serve para conversas curtas sem tirar o qwen3-vl-instruct da memória.
"""


# Coleção de conhecimento do Open WebUI usada pelo modelo Documentos e Memória (a que já existe no seu Open WebUI).
CONHECIMENTO = {"id": "42999e43-33d7-4a5e-bef7-0f2bd58184d7", "name": "heimdall_docs", "type": "collection", "description": "Meus documentos"}
PASTA_IMPORTAR = AQUI / "openwebui"


def _listas_de_ferramentas():
    """Lê heimdall_tools.py sem importá-lo: devolve {grupo: [funções]} e o conjunto de todas as funções definidas."""
    arvore = ast.parse((AQUI / "heimdall_tools.py").read_text(encoding="utf-8"))
    funcs = {n.name for n in arvore.body if isinstance(n, ast.FunctionDef)}
    grupos = {}
    for n in arvore.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.List):
            for t in n.targets:
                if getattr(t, "id", "") in ("PUBLIC_TOOLS", "MAC_TOOLS", "DADOS_TOOLS"):
                    grupos[t.id] = [e.id for e in n.value.elts if isinstance(e, ast.Name)]
    return grupos, funcs


def conexao(cid):
    return next((c for c in CONEXOES if c["id"] == cid), None)


def funcoes_do_modelo(m):
    c = conexao(m["conexao"]) if m["conexao"] else None
    return list(c["funcoes"]) if c else []


def problemas():
    """Lista de problemas de consistência; vazia quando tudo confere."""
    erros = []
    grupos, funcs = _listas_de_ferramentas()
    ids = [c["id"] for c in CONEXOES]
    if len(ids) != len(set(ids)):
        erros.append("há conexões com o mesmo id")
    nomes = [m["nome"] for m in MODELOS]
    if len(nomes) != len(set(nomes)):
        erros.append("há modelos com o mesmo nome")
    todas = set()
    for c in CONEXOES:
        no_grupo = grupos.get(c["grupo"], [])
        for f in c["funcoes"]:
            todas.add(f)
            if f not in funcs:
                erros.append("conexão %s: a função %s não existe em heimdall_tools.py" % (c["id"], f))
            elif f not in no_grupo:
                erros.append("conexão %s: a função %s não faz parte do servidor %s" % (c["id"], f, c["grupo"]))
    for g in ("DADOS_TOOLS",):
        usadas = {f for c in CONEXOES if c["grupo"] == g for f in c["funcoes"]}
        for f in grupos.get(g, []):
            if f not in usadas:
                erros.append("a função %s do servidor de dados não está em nenhum modelo" % f)
    for m in MODELOS:
        if m["conexao"] and not conexao(m["conexao"]):
            erros.append("modelo %s: conexão %s não existe" % (m["nome"], m["conexao"]))
        arq = AQUI / m["prompt"]
        if not arq.exists():
            erros.append("modelo %s: falta %s" % (m["nome"], m["prompt"]))
            continue
        texto = arq.read_text(encoding="utf-8")
        permitidas = set(funcoes_do_modelo(m))
        citadas = {f for f in funcs if re.search(r"(?<![\w])" + re.escape(f) + r"(?![\w])", texto)}
        for f in sorted(citadas - permitidas):
            erros.append("modelo %s: o prompt cita %s, que o modelo não pode usar" % (m["nome"], f))
        if m["conexao"]:
            for f in sorted(permitidas - citadas - {"get_system_timestamp"}):
                erros.append("modelo %s: o prompt não ensina a usar %s" % (m["nome"], f))
        elif citadas:
            erros.append("modelo %s: não tem ferramentas, mas o prompt cita %s" % (m["nome"], ", ".join(sorted(citadas))))
    return erros


def texto_guia():
    L = ["MODELOS PERSONALIZADOS DO OPEN WEBUI (Workspace, Modelos)", "",
         "Este arquivo é gerado por python3 gerar_docs.py a partir de modelos_chat.py. Não edite aqui; edite lá.", "",
         "IMPORTAR TUDO DE UMA VEZ (recomendado). Os arquivos estão em ~/heimdall-ai/openwebui/:",
         "  1. ferramentas_importar.json: em Configurações do administrador, Integrações, Servidores de ferramentas, use Importar. Antes, apague as conexões antigas internet, mac-admin e banco-pessoal, para não duplicar. Depois reaplique o acesso do convidado ao internet, se ele usava.",
         "     O filtro de funções permitidas NÃO vem na importação (o Open WebUI não o exporta nem o importa). Em cada conexão, abra a edição e cole a lista no campo Lista de filtros de nomes de funções (formato func1, func2; um nome com ! na frente seria uma exclusão, e aqui só usamos permissões): copie com pbcopy < ~/heimdall-ai/openwebui/funcoes_ID.txt (troque ID por banco-pessoal, banco-saude, banco-financas, internet ou mac-admin) e cole com Command+V.",
         "  2. modelos_importar.json: em Workspace, Modelos, use Importar. Os modelos entram só para o administrador. Os modelos antigos não são apagados: apague à mão só os que não quiser mais.",
         "  3. Confira cada conexão e cada modelo uma vez, com uma pergunta real. Se a importação recusar o arquivo, diga a mensagem de erro e eu ajusto o formato.",
         "Abaixo, o que cada arquivo contém, para conferir ou para criar à mão.", "",
         "Servidores de ferramentas (Configurações do administrador, Integrações, Servidores de ferramentas externos).",
         "Cada conexão tem um filtro com a lista de funções permitidas: é ele que deixa cada modelo enxergar só as funções do seu assunto.",
         "As três primeiras apontam para o mesmo servidor, o de dados, e só mudam o filtro.", ""]
    for k, c in enumerate(CONEXOES):
        letra = "Conexão %d" % (k + 1)
        L.append("%s: ID %s, nome \"%s\", %s%s" % (letra, c["id"], c["nome"], c["url"], (", acesso " + c["acesso"]) if c["acesso"] else ""))
        L.append("  Funções permitidas (filtro): " + ", ".join(c["funcoes"]))
    L.append("")
    for k, m in enumerate(MODELOS, 1):
        L.append("%d. %s" % (k, m["nome"]))
        L.append("   Para: " + m["uso"])
        L.append("   Base: " + m["base"])
        L.append("   Prompt: " + m["prompt"])
        c = conexao(m["conexao"]) if m["conexao"] else None
        if c:
            L.append("   Ferramentas: conexão %s (%d funções: %s)" % (c["id"], len(c["funcoes"]), ", ".join(c["funcoes"])))
            if m["nativa"]:
                L.append("   Chamada de função: Nativa")
        else:
            L.append("   Ferramentas: nenhuma")
        L.append("   Temperatura: " + str(m["temperatura"]).replace(".", ","))
        if m.get("obs"):
            L.append("   Observação: " + m["obs"])
        L.append("")
    L += ["Para copiar um prompt sem digitar: pbcopy < ~/heimdall-ai/NOME_DO_ARQUIVO.txt e colar com Command+V no campo de instrução de sistema.", "",
          "AJUSTES EM CADA MODELO (campo Parâmetros avançados, ao editar o modelo)"]
    for m in MODELOS:
        L.append("  %s: temperatura %s." % (m["nome"], str(m["temperatura"]).replace(".", ",")))
    L.append("  Nos que têm ferramentas, deixe a chamada de função em Nativa. O contexto (8192, o mesmo no Código) e o tempo na memória já vêm do litellm_config.yaml.")
    L.append("")
    L.append(NOVOS.rstrip("\n"))
    return "\n".join(L) + "\n"


def tabela_md():
    linhas = ["| Modelo | Base | Ferramentas (conexão) | Funções | Temperatura |", "|---|---|---|---|---|"]
    for m in MODELOS:
        c = conexao(m["conexao"]) if m["conexao"] else None
        linhas.append("| %s | `%s` | %s | %s | %s |" % (m["nome"], m["base"], ("`%s`" % c["id"]) if c else "nenhuma",
                                                       (", ".join("`%s`" % f for f in c["funcoes"])) if c else "", str(m["temperatura"]).replace(".", ",")))
    return "\n".join(linhas)


def exportar_conexoes():
    """Servidores de ferramentas (MCP) no formato de importação do Open WebUI (o mesmo que ele exporta). O filtro de funções NÃO viaja nesse
    formato: ele é digitado à mão em cada conexão (veja funcoes_<id>.txt)."""
    saida = []
    for c in CONEXOES:
        saida.append({"type": "mcp", "url": c["url"], "spec_type": "url", "spec": "", "path": "openapi.json", "auth_type": "none", "key": "",
                      "info": {"id": c["id"], "name": c["nome"], "description": c["descricao"]}})
    return saida


def exportar_modelos():
    """Modelos no formato de importação do Open WebUI (Workspace, Modelos, Importar). Sem acesso para ninguém além do administrador:
    quem já tinha acesso aos modelos antigos (por exemplo o convidado) não ganha acesso a estes, que mexem em dados pessoais."""
    saida = []
    for m in MODELOS:
        com_ferr = bool(m["conexao"])
        meta = {"profile_image_url": None, "background_image_url": None, "description": m["uso"][:1].upper() + m["uso"][1:] + ".",
                "capabilities": {"file_context": m["nome"] == "Documentos e Memória", "vision": False, "file_upload": False, "web_search": False,
                                 "image_generation": False, "code_interpreter": False, "terminal": False, "citations": True, "status_updates": True,
                                 "memory": False, "builtin_tools": False},
                "knowledge": [CONHECIMENTO] if m["nome"] == "Documentos e Memória" else [], "defaultFeatureIds": []}
        if com_ferr:
            meta["toolIds"] = ["server:mcp:" + m["conexao"]]
        params = {"system": (AQUI / m["prompt"]).read_text(encoding="utf-8").strip(), "temperature": m["temperatura"]}
        if com_ferr and m["nativa"]:
            params["function_calling"] = "native"
        saida.append({"id": m["id"], "base_model_id": m["base"], "name": m["nome"], "params": params, "meta": meta, "access_grants": [], "is_active": True})
    return saida


def json_importar():
    import json
    funcoes = {"funcoes_%s.txt" % c["id"]: ", ".join(c["funcoes"]) + "\n" for c in CONEXOES}
    return {**funcoes, "modelos_importar.json": json.dumps(exportar_modelos(), ensure_ascii=False, indent=1) + "\n",
            "ferramentas_importar.json": json.dumps(exportar_conexoes(), ensure_ascii=False, indent=1) + "\n"}


if __name__ == "__main__":
    erros = problemas()
    for e in erros:
        print("PROBLEMA:", e)
    if "--escrever" in sys.argv and not erros:
        (AQUI / "modelos_open_webui.txt").write_text(texto_guia(), encoding="utf-8")
        PASTA_IMPORTAR.mkdir(exist_ok=True)
        for nome, conteudo in json_importar().items():
            (PASTA_IMPORTAR / nome).write_text(conteudo, encoding="utf-8")
        print("modelos_open_webui.txt e openwebui/*.json escritos.")
    elif "--guia" in sys.argv:
        print(texto_guia())
    sys.exit(1 if erros else 0)
