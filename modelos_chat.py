#!/usr/bin/env python3
"""Fonte única dos modelos personalizados do chat (Open WebUI) e das funções que cada um pode usar.

Daqui saem o guia guides/modelos_open_webui.txt e a tabela do README (python3 gerar_docs.py). O teste tests/chat/teste_modelos_chat.py confere que
toda função citada existe, que cada prompt só fala das funções do seu modelo e que nenhuma função do servidor de dados ficou sem uso.
Para criar um modelo novo: acrescente-o em MODELOS (e, se precisar de um filtro novo, em CONEXOES), crie o prompt_chat_*.txt e rode gerar_docs.py.
"""
import ast
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent

SAUDE = ["saude_historico", "analise_saude", "frequencia_cardiaca_resumo", "ecg_resumo", "treinos_resumo", "relatorio_saude", "exames_resumo", "exame_historico", "analise_exames", "exames_pendentes", "receitas_encaminhamentos", "banco_consultar", "get_system_timestamp"]
FINANCAS = ["financas_resumo", "financas_transacoes", "financas_orcamentos", "financas_recorrentes", "financas_boletos", "financas_futuros", "get_system_timestamp"]
GERAL = ["banco_resumo", "banco_consultar", "banco_buscar", "saude_historico", "get_system_timestamp"]
INTERNET = ["search_searxng", "calculate_expression", "get_system_timestamp", "get_hackernews_top_stories", "search_reddit_posts", "fetch_rss_feed",
            "get_astronomy_apod", "get_youtube_transcript", "fetch_url"]
WEB_BASICA = ["search_searxng", "fetch_url", "calculate_expression", "get_system_timestamp"]
MEMORIA = ["memory_save", "memory_search", "memory_forget", "rag_temas", "rag_search"]

# Conexões em Configurações do administrador, Integrações, Servidores de ferramentas externos. Várias conexões podem apontar para o mesmo servidor
# com filtros diferentes: é o filtro que limita as funções que cada modelo enxerga (um modelo de 8B escolhe melhor entre 7 funções do que entre 16).
CONEXOES = [
    {"id": "banco-pessoal", "nome": "Meus Dados (banco pessoal)", "descricao": "Banco pessoal em modo leitura: diários oficiais, e-mails, estudos, privacidade, avisos, Second Brain e métricas de saúde simples. Só para o administrador.", "url": "http://host.docker.internal:8004/mcp", "grupo": "DADOS_TOOLS", "acesso": "só do administrador", "funcoes": GERAL},
    {"id": "banco-saude", "nome": "Saúde (banco pessoal)", "descricao": "Saúde em modo leitura: histórico por métrica, análises, coração, ECG, treinos e relatório. Só para o administrador.", "url": "http://host.docker.internal:8004/mcp", "grupo": "DADOS_TOOLS", "acesso": "só do administrador", "funcoes": SAUDE},
    {"id": "banco-financas", "nome": "Finanças (Finance)", "descricao": "Finance em modo leitura: resumo do mês, lançamentos, orçamentos, recorrentes, boletos e pagamentos futuros. Só para o administrador.", "url": "http://host.docker.internal:8004/mcp", "grupo": "DADOS_TOOLS", "acesso": "só do administrador", "funcoes": FINANCAS},
    {"id": "internet", "nome": "Internet e Utilidades", "descricao": "Pesquisa na web, cálculo, notícias, feeds, transcrições e utilidades públicas.", "url": "http://host.docker.internal:8001/mcp", "grupo": "PUBLIC_TOOLS", "acesso": "", "funcoes": INTERNET},
    {"id": "web-basica", "nome": "Web básica (Conversas)", "descricao": "Só pesquisa na web, leitura de página, cálculo e hora: poucas funções para o Conversas gastar pouco com a lista de ferramentas.", "url": "http://host.docker.internal:8001/mcp", "grupo": "PUBLIC_TOOLS", "acesso": "", "funcoes": WEB_BASICA},
    {"id": "mac-admin", "nome": "Mac e Memória (administrador)", "descricao": "Memória persistente e documentos pessoais (RAG). Só para o administrador.", "url": "http://host.docker.internal:8000/mcp", "grupo": "MAC_TOOLS", "acesso": "só do administrador", "funcoes": MEMORIA},
]

# temperatura: valor sugerido no campo Parâmetros avançados. conexao: id da conexão acima (vazio = sem ferramentas).
MODELOS = [
    {"id": "meus-dados", "nome": "Meus Dados", "base": "qwen3-vl-instruct", "prompt": "prompts/prompt_chat_dados.txt", "temperatura": 0.2, "conexao": "banco-pessoal",
     "uso": "diários oficiais, e-mails de serviços públicos, estudos, privacidade, avisos, Second Brain e métricas de saúde simples", "nativa": True},
    {"id": "saude", "nome": "Saúde", "base": "qwen3-vl-instruct", "prompt": "prompts/prompt_chat_saude.txt", "temperatura": 0.2, "conexao": "banco-saude",
     "uso": "sono, pulso, variabilidade, treinos, ECG, anomalias, relatórios de saúde, exames de laboratório, receitas e encaminhamentos", "nativa": True},
    {"id": "financas", "nome": "Finanças", "base": "qwen3-vl-instruct", "prompt": "prompts/prompt_chat_financas.txt", "temperatura": 0.2, "conexao": "banco-financas",
     "uso": "gastos, receitas, categorias, orçamentos, assinaturas, parcelas e boletos do Finance (só leitura)", "nativa": True},
    {"id": "codigo", "nome": "Código", "base": "deepseek-coder-v2:16b", "prompt": "prompts/prompt_chat_codigo.txt", "temperatura": 0.2, "conexao": "",
     "uso": "programação, sem ferramentas", "nativa": False,
     "obs": "nos seus testes esse modelo não suporta ferramentas no Ollama. O contexto dele é de 8192 tokens e ele sai da memória 30 segundos depois do uso."},
    {"id": "curiosidades", "nome": "Curiosidades", "base": "qwen3-vl-instruct", "prompt": "prompts/prompt_chat_curiosidades.txt", "temperatura": 0.4, "conexao": "internet",
     "uso": "web, notícias, cálculo, transcrições e feeds", "nativa": True,
     "obs": "usa o mesmo modelo do Meus Dados, sem trocar de modelo na memória."},
    {"id": "conversas", "nome": "Conversas", "base": "conversas", "prompt": "prompts/prompt_chat_conversas.txt", "temperatura": 0.8, "conexao": "web-basica",
     "uso": "conversa livre, com pesquisa na web quando a pergunta pede", "nativa": True,
     "obs": "na nuvem (HEIMDALL_NUVEM=1) usa o Qwen3 30B; sem a nuvem, o gemma local, que pode não chamar a pesquisa."},
    {"id": "documentos", "nome": "Documentos e Memória", "base": "qwen3-vl-instruct", "prompt": "prompts/prompt_chat_documentos.txt", "temperatura": 0.2, "conexao": "mac-admin",
     "uso": "livros, notas e documentos do estudo e memória pessoal (opcional)", "nativa": True},
]

NOVOS = """OUTROS MODELOS DO LITELLM (não são base de nenhum modelo do chat)
  llama-3.1-8b: aceita ferramentas e respondeu bem em português. É o modelo local padrão do Perguntar (heimdall ask e os sites, quando a nuvem está desligada ou falha). Nenhum modelo do chat o usa. Compare-o com o qwen3-vl-instruct antes de trocar algum modelo do chat; um segundo modelo de 8B alternando faz a memória trocar de modelo a cada mudança de chat.
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


def excluidas(c):
    """Funções do servidor da conexão que ela NÃO deve mostrar: tudo o que o servidor expõe menos as permitidas. Como o servidor é compartilhado,
    a exclusão explícita não depende de o modelo ou do prompt se comportarem. Uma função nova no servidor aparece aqui na próxima geração
    (gerar_docs.py --check avisa) e então o filtro precisa ser colado de novo."""
    grupos, _ = _listas_de_ferramentas()
    return [f for f in grupos.get(c["grupo"], []) if f not in c["funcoes"]]


def filtro_texto(c):
    return ", ".join("!" + f for f in excluidas(c))


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
    com_filtro = [c["id"] for c in CONEXOES if excluidas(c)]
    sem_filtro = [c["id"] for c in CONEXOES if not excluidas(c)]
    L = ["MODELOS PERSONALIZADOS DO OPEN WEBUI (Workspace, Modelos): GUIA DA PRIMEIRA CONFIGURAÇÃO", "",
         "Este arquivo é gerado por python3 gerar_docs.py a partir de modelos_chat.py. Não edite aqui; edite lá.", "",
         "Serve para quem ainda não importou nada. Todos os arquivos estão em ~/heimdall-ai/openwebui/. Tudo leva uns 15 minutos. Os passos são de teclado e de terminal, pensados para o VoiceOver.", "",
         "ANTES DE COMEÇAR",
         "  1. Atualize o Heimdall e reinicie: heimdall update --restart. Isso sobe o LiteLLM, que é de onde o Open WebUI tira a lista de modelos.",
         "  2. Para o chat responder pela nuvem (rápido), ligue o interruptor e reinicie: heimdall env --set HEIMDALL_NUVEM 1, depois heimdall restart. Confira com heimdall cloudai. Sem a nuvem, o chat usa os modelos locais do Ollama e fica lento. Para voltar ao local: heimdall env --set HEIMDALL_NUVEM 0 e heimdall restart.",
         "  3. Abra o Open WebUI (porta 3000, ou o endereço do seu acesso) e entre como administrador. Em Workspace, Modelos, a lista deve mostrar os modelos do LiteLLM (qwen3-vl-instruct, conversas, deepseek-coder-v2:16b e os outros). Se estiver vazia, o LiteLLM não subiu: rode heimdall status.", "",
         "PASSO 1: AS CONEXÕES DE FERRAMENTAS (%d arquivos)" % len(CONEXOES),
         "  1. Abra Configurações do administrador, Integrações, Servidores de ferramentas externos.",
         "  2. Use Importar, uma vez para cada arquivo da pasta openwebui/ferramentas/: " + ", ".join(c["id"] + ".json" for c in CONEXOES) + ". Um arquivo por conexão, porque o Open WebUI importa só a primeira conexão de cada arquivo. Se o Open WebUI já tiver uma conexão com o mesmo ID (por exemplo internet), apague a antiga antes de importar, para não duplicar; se o convidado usava essa conexão, reaplique o acesso dele depois.",
         "  3. O filtro de funções NÃO vem na importação (o Open WebUI não o exporta nem o importa). Ele é o que impede cada modelo de enxergar funções que não são do seu assunto. Nas conexões " + ", ".join(com_filtro) + ", abra a edição e cole a lista no campo Lista de filtros de nomes de funções. Para copiar sem digitar, no Terminal: pbcopy < ~/heimdall-ai/openwebui/filtro_ID.txt (troque ID pelo nome da conexão) e depois Command+V no campo. Sem filtro (usa todas as funções do servidor): " + ", ".join(sem_filtro) + ".",
         "  4. Salve cada conexão e use o botão de verificar conexão. As que usam o servidor de dados (porta 8004) e o do Mac (porta 8000) só respondem com o Heimdall ligado.", "",
         "PASSO 2: OS MODELOS (%d)" % len(MODELOS),
         "  0. Atalho: crie uma chave em Configurações, Conta, Chaves de API (conta administradora) e rode heimdall chat --models; ele cria ou atualiza os 7 modelos com os prompts padrão, sem importar arquivo. A chave pode ficar em HEIMDALL_WEBUI_API_KEY no .env ou ser digitada na hora.",
         "  1. Ou abra Workspace, Modelos, Importar, e escolha openwebui/modelos_importar.json (todos de uma vez). Se só o primeiro entrar, importe um por um os arquivos de openwebui/modelos/ (" + ", ".join(m["id"] + ".json" for m in MODELOS) + ").",
         "  2. Os modelos entram só para o administrador, de propósito: eles mexem em saúde, finanças e dados pessoais. Para o convidado usar algum, dê o acesso modelo a modelo, e só aos que não tocam dados pessoais (Curiosidades, Conversas, Código).",
         "  3. Cada modelo já chega com o prompt, a temperatura, a conexão de ferramentas e a chamada de função Nativa. Confira uma vez abrindo o modelo para editar. Se a importação recusar o arquivo, diga a mensagem de erro e eu ajusto o formato.", "",
         "PASSO 3: TESTE COM UMA PERGUNTA REAL EM CADA MODELO",
         "  1. Conversas: \"Quem ganhou o jogo do Corinthians ontem?\" (deve pesquisar na web e dizer de onde veio).",
         "  2. Curiosidades: uma notícia do dia. Meus Dados, Saúde e Finanças: uma pergunta simples sobre os seus dados (ex.: como foi o meu sono na semana).",
         "  3. Se um modelo ignorar as ferramentas, confira se a chamada de função está em Nativa e se a conexão do modelo está ligada em Ferramentas.",
         "  4. Na nuvem, o primeiro uso do dia pode demorar alguns segundos; se a nuvem falhar ou o limite de gasto cortar, o LiteLLM usa sozinho o modelo local (o chat só fica mais lento).", "",
         "O QUE VAI PARA A NUVEM COM HEIMDALL_NUVEM=1",
         "  Meus Dados, Saúde, Finanças, Curiosidades, Documentos e Memória e Código: gpt-oss-120b (gateway \"heimdall\", teto de gasto). Conversas: Qwen3 30B (HEIMDALL_NUVEM_CONVERSAS_MODELO troca). Os modelos locais ficam como volta. Lembrete: o contexto das conversas, incluindo saúde e finanças nos modelos desses assuntos, passa pela Cloudflare (decisão de 21/11/2026).", "",
         "CAMINHO MANUAL (para conferir ou criar à mão). Abaixo, o que cada arquivo contém.", "",
         "Servidores de ferramentas (Configurações do administrador, Integrações, Servidores de ferramentas externos).",
         "Cada conexão tem um filtro que EXCLUI as funções do servidor que não são do seu assunto (formato !funcao1, !funcao2). Como o servidor é compartilhado, assim a função fica bloqueada de verdade e não depende do modelo se comportar.",
         "As conexões de dados apontam para o mesmo servidor (porta 8004) e só mudam o filtro; Internet e Web básica também dividem o servidor público (porta 8001).", ""]
    for k, c in enumerate(CONEXOES):
        letra = "Conexão %d" % (k + 1)
        L.append("%s: ID %s, nome \"%s\", %s%s" % (letra, c["id"], c["nome"], c["url"], (", acesso " + c["acesso"]) if c["acesso"] else ""))
        L.append("  Funções permitidas: " + ", ".join(c["funcoes"]))
        L.append("  Filtro a colar (exclui o resto do servidor): " + (filtro_texto(c) or "nenhum, esta conexão usa todas as funções do servidor"))
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
    L.append("  Nos que têm ferramentas, deixe a chamada de função em Nativa. O contexto (8192 nos modelos locais) e o tempo na memória já vêm do litellm_config.yaml; na nuvem o Conversas usa o contexto de 32 mil tokens do Qwen3.")
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
    formato: ele é digitado à mão em cada conexão (veja filtro_<id>.txt)."""
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
    """Todos os arquivos gerados em openwebui/, por caminho relativo. O Open WebUI importa só a primeira conexão de cada arquivo de ferramentas,
    então há um arquivo por conexão; para os modelos há um arquivo com todos e um por modelo, caso a importação em lote ignore algum."""
    import json

    def js(lista):
        return json.dumps(lista, ensure_ascii=False, indent=1) + "\n"
    saida = {"filtro_%s.txt" % c["id"]: filtro_texto(c) + "\n" for c in CONEXOES if excluidas(c)}
    for c in exportar_conexoes():
        saida["ferramentas/%s.json" % c["info"]["id"]] = js([c])
    modelos = exportar_modelos()
    saida["modelos_importar.json"] = js(modelos)
    for m in modelos:
        saida["modelos/%s.json" % m["id"]] = js([m])
    return saida


if __name__ == "__main__":
    erros = problemas()
    for e in erros:
        print("PROBLEMA:", e)
    if "--escrever" in sys.argv and not erros:
        (AQUI / "guides/modelos_open_webui.txt").write_text(texto_guia(), encoding="utf-8")
        PASTA_IMPORTAR.mkdir(exist_ok=True)
        for nome, conteudo in json_importar().items():
            (PASTA_IMPORTAR / nome).parent.mkdir(parents=True, exist_ok=True)
            (PASTA_IMPORTAR / nome).write_text(conteudo, encoding="utf-8")
        print("guides/modelos_open_webui.txt e openwebui/*.json escritos.")
    elif "--guia" in sys.argv:
        print(texto_guia())
    sys.exit(1 if erros else 0)
