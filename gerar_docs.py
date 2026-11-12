#!/usr/bin/env python3
"""Gera as páginas do GitHub Pages (docs/) e as tabelas automáticas do README.md a partir do código do projeto.

Uso, na pasta do projeto:
    python3 gerar_docs.py            gera docs/*.html e atualiza as tabelas do README.md
    python3 gerar_docs.py --check    só confere se docs/ e README estão em dia (sai com 1 se não estiverem)

O que sai do código (sempre em dia): ferramentas (heimdall_tools.py), modelos e servidores MCP (litellm_config.yaml),
fluxos do n8n (n8n_flows*/), opções do start_heimdall.sh e as novidades (CHANGELOG.md).
O que é texto escrito à mão: os textos explicativos deste arquivo. Ao criar um recurso novo, siga a lista de
"Como manter" do README: CHANGELOG.md, texto aqui se preciso, e rode este script.
Só usa a biblioteca padrão (PyYAML é usado se existir; senão, uma leitura simples do YAML).
"""
import ast
import glob
import html
import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DOCS = AQUI / "docs"
DOMINIO = "heimdall-ai.tech"
AUTOR = "Murillo Bolonhini Cita"
GH_USUARIO = "mrl2bolonhini"
H = lambda s: html.escape(str(s), quote=True)

# ---------------------------------------------------------------------------------------------------------
# Dados lidos do projeto
# ---------------------------------------------------------------------------------------------------------


def ler_ferramentas():
    arvore = ast.parse((AQUI / "heimdall_tools.py").read_text(encoding="utf-8"))
    funcs = {n.name: n for n in arvore.body if isinstance(n, ast.FunctionDef)}
    grupos = {}
    for n in arvore.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.List):
            for t in n.targets:
                if getattr(t, "id", "") in ("PUBLIC_TOOLS", "MAC_TOOLS"):
                    grupos[t.id] = [e.id for e in n.value.elts if isinstance(e, ast.Name)]
    saida = []
    for grupo, rotulo in (("PUBLIC_TOOLS", "público"), ("MAC_TOOLS", "mac")):
        for nome in grupos.get(grupo, []):
            f = funcs.get(nome)
            if not f:
                continue
            doc = " ".join((ast.get_docstring(f) or "").split())
            params = []
            padroes = [None] * (len(f.args.args) - len(f.args.defaults)) + list(f.args.defaults)
            for a, d in zip(f.args.args, padroes):
                params.append(a.arg + ("=" + ast.unparse(d) if d is not None else ""))
            saida.append({"nome": nome, "grupo": rotulo, "params": params, "doc": doc})
    return saida


def ler_yaml_simples(texto):
    """Lê só o que precisamos do litellm_config.yaml (model_list e mcp_servers) sem depender do PyYAML."""
    try:
        import yaml  # type: ignore
        return yaml.safe_load(texto)
    except Exception:
        pass
    modelos, mcp, atual, bloco = [], {}, None, None
    for linha in texto.splitlines():
        s = linha.split("#")[0].rstrip()
        if re.match(r"^model_list:", s):
            bloco = "m"; continue
        if re.match(r"^mcp_servers:", s):
            bloco = "s"; continue
        if re.match(r"^\S", s):
            bloco = None
        if bloco == "m":
            m = re.match(r"^\s+- model_name:\s*(.+)$", s)
            if m:
                atual = {"model_name": m.group(1).strip(), "litellm_params": {}, "model_info": {}}; modelos.append(atual); continue
            m = re.match(r"^\s+model:\s*(.+)$", s)
            if m and atual: atual["litellm_params"]["model"] = m.group(1).strip()
            m = re.match(r"^\s+(supports_\w+):\s*(\w+)$", s)
            if m and atual: atual["model_info"][m.group(1)] = m.group(2) == "true"
        if bloco == "s":
            m = re.match(r"^  (\w+):\s*$", s)
            if m:
                atual = {}; mcp[m.group(1)] = atual; continue
            m = re.match(r"^\s{4}(url|transport|command):\s*(.+)$", s)
            if m and atual is not None: atual[m.group(1)] = m.group(2).strip()
    return {"model_list": modelos, "mcp_servers": mcp}


def ler_config():
    cfg = ler_yaml_simples((AQUI / "litellm_config.yaml").read_text(encoding="utf-8")) or {}
    return cfg.get("model_list", []), cfg.get("mcp_servers", {})


def agenda_do_gatilho(n):
    p = n.get("parameters", {})
    if "errorTrigger" in n["type"]:
        return "quando outro fluxo falha"
    if "webhook" in n["type"]:
        return "a cada git push (webhook)"
    for it in (p.get("rule", {}) or {}).get("interval", []):
        campo = it.get("field")
        if campo == "cronExpression":
            return "cron " + it.get("expression", "")
        if campo == "hours":
            return "a cada %s hora(s)" % it.get("hoursInterval", 1)
        if campo == "minutes":
            return "a cada %s minutos" % it.get("minutesInterval", 1)
        if campo == "days":
            return "todo dia às %sh%02d" % (it.get("triggerAtHour", 0), it.get("triggerAtMinute", 0))
        if campo == "weeks":
            return "toda semana (segunda às %sh)" % it.get("triggerAtHour", 0)
    return "agendado"


def ler_fluxos():
    vistos, saida = set(), []
    for f in sorted(glob.glob(str(AQUI / "n8n_flows*" / "*.json")), key=lambda x: (int(re.match(r"(\d+)", Path(x).name).group(1)), x)):
        w = json.loads(Path(f).read_text(encoding="utf-8"))
        if w["id"] in vistos:
            continue
        vistos.add(w["id"])
        gat = next((n for n in w["nodes"] if re.search(r"scheduleTrigger|webhook|errorTrigger", n["type"])), None)
        etapas = [n["name"] for n in w["nodes"] if "manualTrigger" not in n["type"] and n is not gat]
        saida.append({"id": w["id"], "nome": re.sub(r"^Heimdall:\s*", "", w["name"]), "arquivo": str(Path(f).relative_to(AQUI)),
                      "quando": agenda_do_gatilho(gat) if gat else "manual", "etapas": etapas, "num": Path(f).name.split("-")[0]})
    return saida


def ler_opcoes_start():
    linhas = []
    for l in (AQUI / "start_heimdall.sh").read_text(encoding="utf-8").splitlines()[1:30]:
        if not l.startswith("#"):
            break
        linhas.append(l.lstrip("# ").rstrip())
    return linhas


def ler_changelog():
    arq = AQUI / "CHANGELOG.md"
    if not arq.exists():
        return []
    blocos, atual = [], None
    for l in arq.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^##\s+(\d{4}-\d{2}-\d{2}|Anteriores)\s*(?:[-—:]\s*)?(.*)$", l)
        if m:
            atual = {"data": m.group(1), "titulo": m.group(2).strip(), "itens": []}; blocos.append(atual); continue
        m = re.match(r"^\s*[-*]\s+(.*)$", l)
        if m and atual:
            atual["itens"].append(m.group(1).strip())
    return blocos


def ler_roadmap():
    """ROADMAP.md: '## Etapa', uma linha de texto livre (a nota da etapa) e itens '- Título: descrição'."""
    arq = AQUI / "ROADMAP.md"
    if not arq.exists():
        return [], ""
    etapas, atual, intro = [], None, ""
    for l in arq.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^##\s+(.+)$", l)
        if m:
            atual = {"nome": m.group(1).strip(), "nota": "", "itens": []}; etapas.append(atual); continue
        m = re.match(r"^\s*[-*]\s+(.*)$", l)
        if m and atual:
            t, _, d = m.group(1).partition(": ")
            atual["itens"].append((t.strip(), d.strip()))
        elif l.strip() and not l.startswith(("#", "<!--")):
            if atual:
                atual["nota"] = (atual["nota"] + " " + l.strip()).strip()
            else:
                intro = (intro + " " + l.strip()).strip()
    return etapas, intro


# ---------------------------------------------------------------------------------------------------------
# Textos escritos à mão
# ---------------------------------------------------------------------------------------------------------
SERVICOS = [
    # nome, função, porta, como sobe
    ("Ollama", "Executa os modelos de linguagem no Mac.", "11434", "start_heimdall.sh (inicia se não estiver rodando)"),
    ("LiteLLM Proxy", "Ponto único de acesso (API compatível com a da OpenAI) aos modelos; também expõe os servidores MCP.", "9000", "start_heimdall.sh"),
    ("Servidor MCP do Mac (admin)", "Ferramentas que mexem no Mac: arquivos, métricas, memória e documentos.", "8000", "start_heimdall.sh"),
    ("Servidor MCP público", "Ferramentas seguras para convidados: web, cálculo, feeds, transcrições.", "8001", "start_heimdall.sh"),
    ("Servidor MCP de dados", "Só as ferramentas do banco pessoal (saúde, diários, e-mails, estudos, Second Brain), para o Open WebUI. Escuta só em 127.0.0.1.", "8004", "start_heimdall.sh"),
    ("SearXNG", "Mecanismo de busca na web que não rastreia quem pesquisa.", "8080", "start_heimdall.sh (Docker)"),
    ("Qdrant", "Base vetorial: busca por significado nos documentos e nas notas.", "6333", "start_heimdall.sh (Docker)"),
    ("Open WebUI", "Interface de chat usada pelos convidados e pelo dono.", "3000", "--webui ou HEIMDALL_WEBUI=1"),
    ("Open Terminal", "Terminal acessível pelo Open WebUI.", "8002", "--terminal"),
    ("n8n", "Automações e tarefas agendadas.", "5678", "--n8n ou HEIMDALL_N8N=1"),
    ("Agente do Mac", "Ponte entre o n8n (no Docker) e o app Notas, o Calendário, os Lembretes e a voz do macOS.", "8003", "--agente (sobe sozinho com HEIMDALL_AGENTE_TOKEN)"),
    ("Docling", "Extração de texto de PDFs, com OCR.", "5001", "--docling ou HEIMDALL_DOCLING=1"),
    ("Uptime Kuma", "Painel de disponibilidade dos serviços.", "3001", "start_heimdall.sh (HEIMDALL_MONITORING=0 desliga)"),
    ("Dozzle", "Leitor de logs dos contêineres.", "8081", "start_heimdall.sh (HEIMDALL_MONITORING=0 desliga)"),
    ("Emulador de AWS (Moto ou LocalStack)", "Para testar código de AWS sem custo.", "4566", "start_heimdall.sh (HEIMDALL_AWS_EMULATOR)"),
    ("Heimdall Notas", "Site para ler as notas de estudo e ouvir os áudios (velocidade, voltar e avançar 15 segundos, busca, documentos de knowledge/). Mesmo login do Heimdall Cloud. Escuta só em 127.0.0.1.", "8011", "sobe sozinho com HEIMDALL_CLOUD_SENHA_HASH e HEIMDALL_CLOUD_TOTP_SEGREDO no .env"),
    ("Heimdall Cloud", "Painel web do emulador de AWS (S3, Lambda, Glue, Athena e console geral), com senha e código de 6 dígitos. Escuta só em 127.0.0.1; o acesso público é pelo túnel Cloudflare.", "8010", "sobe sozinho com HEIMDALL_CLOUD_SENHA_HASH e HEIMDALL_CLOUD_TOTP_SEGREDO no .env"),
]

TECNOLOGIAS = [
    ("Ollama", "https://ollama.com", "Executa os modelos de linguagem no computador."),
    ("LiteLLM", "https://www.litellm.ai", "Reúne os modelos em um único ponto de acesso e expõe os servidores MCP."),
    ("Open WebUI", "https://openwebui.com", "Interface de chat."),
    ("Model Context Protocol (MCP)", "https://modelcontextprotocol.io", "Padrão que liga o assistente a ferramentas externas."),
    ("FastMCP", "https://gofastmcp.com", "Biblioteca Python que implementa os servidores MCP do projeto."),
    ("Qdrant", "https://qdrant.tech", "Base vetorial para a busca por significado."),
    ("SearXNG", "https://docs.searxng.org", "Busca na web sem rastreamento."),
    ("n8n", "https://n8n.io", "Automações e agendamentos."),
    ("Bark", "https://github.com/Finb/Bark", "Aplicativo de notificações para o iPhone."),
    ("Docker", "https://www.docker.com", "Contêineres dos serviços auxiliares."),
    ("LocalStack e Moto", "https://www.localstack.cloud", "Emulam a AWS no computador (S3, Lambda, Glue, Athena e outros), para estudar e testar código sem custo."),
    ("boto3", "https://boto3.amazonaws.com/v1/documentation/api/latest/index.html", "Biblioteca da AWS em Python, usada pelo painel Heimdall Cloud para falar com o emulador."),
    ("Tailscale", "https://tailscale.com", "Rede privada que liga o celular ao computador."),
    ("Cloudflare", "https://www.cloudflare.com", "Domínio, DNS e túnel de acesso ao chat."),
    ("GitHub e GitHub Pages", "https://pages.github.com", "Código e esta documentação."),
    ("Python 3.12", "https://www.python.org", "Servidores MCP, agente do Mac, indexação e testes."),
    ("AppleScript e macOS", "https://developer.apple.com/library/archive/documentation/AppleScript/", "Integração com Notas, Calendário, Lembretes e voz."),
]

MODELOS_NOTAS = {
    "qwen-3.8-uncensored": ("Uso geral", "Confira a chamada de ferramentas com test_models_tools.py."),
    "gemma-4-uncensored": ("Uso geral", "Confira a chamada de ferramentas com test_models_tools.py."),
    "dolphin3-cyber-8b": ("Segurança e conversa livre", "Confira a chamada de ferramentas com test_models_tools.py."),
    "deepseek-coder-v2:16b": ("Código (usado pelo GitOps)", "O GitOps usa este modelo na etapa de análise de código."),
    "qwen3-vl-instruct": ("Modelo padrão dos fluxos; entende imagens", "Declara suporte a imagens no LiteLLM."),
    "bonsai-27b": ("Modelo grande, respostas mais elaboradas", "Confira a chamada de ferramentas com test_models_tools.py."),
}

FLUXO_DESCRICAO = {
    "hdAwsDiario0001": "Lê o feed de novidades da AWS, filtra os serviços de dados (Glue, Redshift, Athena, S3, Kinesis e outros), resume em português e avisa no iPhone.",
    "hdVersoesSem0001": "Consulta os lançamentos dos projetos que o Heimdall usa, avalia se vale atualizar e avisa no iPhone.",
    "hdSaudeMac00001": "Lê as métricas do Mac pelo MCP e avisa quando RAM, swap ou disco passam dos limites configurados.",
    "hdDisponib000001": "Lê a página de status do Uptime Kuma, monta o relatório de disponibilidade do dia e avisa no iPhone.",
    "hdEstudoDiario01": "Para cada tema da base de conhecimento (subpastas de knowledge/), sorteia um trecho, monta uma leitura, cria pergunta e resposta, busca de 1 a 3 artigos na web e grava a nota no app Notas, na pasta com o nome do tema, com áudio narrado.",
    "hdGitOps00000001": "A cada git push, divide o código alterado em trechos de até 5 mil caracteres, analisa os trechos tocados pelo commit com o modelo de código (um de cada vez, para poupar memória), que responde com edições pontuais validadas uma a uma, e abre um Pull Request em rascunho com as refatorações sugeridas. Se o GitHub recusar o PR, apaga a branch para não deixar lixo e avisa com o motivo e o resumo dos achados. Sempre avisa o resultado, inclusive quando não há nada a refatorar.",
    "hdDigest00000001": "Lê feeds de notícias, filtra pelo que interessa, cruza com as notas e os livros e grava um resumo personalizado no app Notas.",
    "hdSecondBrain001": "Observa as notas alteradas do app Notas (nunca as de pastas privadas), cria embeddings, encontra conexões e lacunas e grava a análise na pasta Cérebro.",
    "hdFalhaAviso0001": "Quando qualquer fluxo falha, avisa no iPhone qual fluxo, em que etapa e por quê. Fluxos nunca falham em silêncio.",
    "hdMonitor00000001": "Pesquisa na web os identificadores pessoais configurados pelo dono (nome, e-mails, usuários) em busca de menções, comentários, vazamentos e imagens, separa homônimos, analisa o risco e grava o relatório. Tem memória: só avisa o que é novo.",
    "hdDiario00000001": "Procura o nome do dono nos diários oficiais do município de São Paulo, da União e do Estado de SP e, se a OAB estiver configurada, as comunicações dela no Diário da Justiça Eletrônico Nacional (CNJ). Avisa só o que for novo. Se uma fonte externa falhar, repete a consulta dela a cada 2 horas (até 72 h), avisa na hora quando voltar e, depois de cerca de 24 h fora do ar, manda um único aviso de indisponibilidade. Nunca finge que não há nada.",
    "hdResumo00000001": "Junta os avisos de rotina em três notificações por dia (6h, 8h e 10h), em vez de uma por fluxo. Avisos urgentes e os de situação (falhas, GitOps, alerta do Mac) continuam na hora.",
    "hdSaude000000001": "Recebe os dados do app Saúde (iPhone e Apple Watch) e escreve às 5h50 um resumo de sono, pulso, variabilidade, respiração e atividade contra a média de 30 dias. As regras decidem o que é relevante, o modelo só redige e uma verificação barra texto com sentido trocado.",
    "hdTriagem0000001": "A cada 15 minutos chama o agente do Mac, que lê a lista \"Heimdall: Triagem\" do app Lembretes, registra o que você concluiu, reclassificou ou adiou e insiste pelo Bark nos itens pendentes: a cada 2 horas das 7h às 21h, a cada 8 horas se você marcar prioridade baixa, e furando o modo silencioso nos itens críticos. Menções do Diário da Justiça viram críticas depois de 24 horas sem ação.",
    "hdBackup00000001": "Todo dia às 3h30 pede ao agente do Mac uma cópia do banco pessoal, criptografada com senha, enviada a uma pasta (iCloud Drive) e ao Cloudflare R2 quando configurado, mantendo as 14 mais recentes e uma por mês. Aos domingos, às 4h, baixa a cópia mais recente, decifra e confere a integridade. Qualquer falha aciona o aviso de falha pelo Bark.",
    "hdLembrete0000001": "Lembrete mensal para conferir, nos aplicativos oficiais, serviços que exigem login (INSS, FGTS, Carteira de Trabalho, Registrato e Serasa).",
}

SCRIPTS = [
    ("heimdall_agente.py", "Agente do Mac (porta 8003). Recebe pedidos do n8n com um token e grava notas no app Notas, cria eventos no Calendário e lembretes no app Lembretes, narra textos com a voz do macOS e busca em dois sites públicos permitidos. Só escreve nas pastas do próprio Heimdall e nunca lê notas de pastas privadas."),
    ("heimdall_triagem.py", "Triagem obrigatória de avisos importantes. Cria lembretes na lista \"Heimdall: Triagem\" do app Lembretes (menções do Diário da Justiça, alertas de saúde, e-mails suspeitos ou urgentes e achados de privacidade de risco médio ou alto) e insiste pelo Bark até você concluir, reclassificar ou adiar. Roda dentro do agente do Mac."),
    ("heimdall_email_oficial.py", "Vigia o Gmail a cada hora, só lendo. Confere se e-mails de serviços públicos (INSS, gov.br, FGTS, Receita, Serasa e outros) são autênticos, resume os verdadeiros, alerta sobre imitações e cria evento e lembrete quando há prazo. Nunca segue links."),
    ("heimdall_biblioteca.py", "Heimdall Notas (porta 8011): site para ler as notas de estudo do cofre e ouvir os áudios, com velocidade, voltar e avançar 15 segundos, busca e os documentos de knowledge/. Mesmo login do Heimdall Cloud; mostra o cofre inteiro, menos o Digest."),
    ("heimdall_cloud.py", "Painel web do emulador de AWS (porta 8010): S3, Lambda, Glue (bancos, tabelas, crawlers e jobs), Athena (consultas SQL) e um console geral que chama qualquer operação de qualquer serviço. Entrada com senha (hash PBKDF2) e código de 6 dígitos, limite de tentativas, sessão com validade e proteção contra CSRF. Escuta só em 127.0.0.1 e nunca expõe a porta do emulador."),
    ("ingest_docs.py", "Indexa os documentos de knowledge/ no Qdrant, de forma incremental. Cada subpasta vira um tema."),
    ("limpar_privadas.py", "Apaga do Second Brain o que veio de notas que depois foram para uma pasta privada."),
    ("limpar_espelhos.py", "Remove espelhos duplicados do Cérebro."),
    ("ouvir_estudo.sh", "Toca no Mac o áudio de estudo mais recente."),
    ("teste_triagem.py", "Testa as regras da triagem com uma simulação do app Lembretes e do Bark. Com --mac, confere os scripts de verdade no Mac."),
    ("test_mcp.py", "Testa os servidores MCP direto e pelo LiteLLM."),
    ("test_models_tools.py", "Testa a chamada de ferramentas de cada modelo."),
]

COMANDOS = [
    ("Subir e parar", [
        ("Subir tudo em segundo plano, com Open WebUI e Open Terminal", "nohup bash start_heimdall.sh --webui --terminal > heimdall.log 2>&1 &"),
        ("Subir com n8n e agente do Mac", "nohup bash start_heimdall.sh --webui --terminal --n8n --agente > heimdall.log 2>&1 &"),
        ("Subir e indexar os documentos novos antes", "nohup bash start_heimdall.sh --ingest > heimdall.log 2>&1 &"),
        ("Atualizar as imagens Docker (com backup) ao subir", "nohup bash start_heimdall.sh --update > heimdall.log 2>&1 &"),
        ("Reiniciar só o agente do Mac", "pkill -f heimdall_agente.py   # depois suba o sistema como de costume"),
        ("Definir senha e código de 6 dígitos do painel do emulador de AWS", "python3 heimdall_cloud.py --definir-senha"),
        ("Gerar só um novo código de 6 dígitos do painel", "python3 heimdall_cloud.py --novo-codigo"),
        ("Reiniciar só o painel do emulador de AWS", "pkill -f heimdall_cloud.py   # depois suba o sistema como de costume"),
        ("Ver o final do log", "tail -30 heimdall.log"),
    ]),
    ("Conferir se está no ar", [
        ("Agente do Mac (deve responder ok)", "curl -s http://localhost:8003/saude"),
        ("Contêineres rodando", "docker ps --format '{{.Names}}: {{.Status}}'"),
        ("Modelos carregados no Ollama", "ollama ps"),
        ("Servidores MCP, direto e pelo LiteLLM", "venv/bin/python test_mcp.py"),
        ("Chamada de ferramentas de cada modelo", "venv/bin/python test_models_tools.py --only qwen"),
        ("Acesso ao app Notas, Calendário e Lembretes", "python3 heimdall_agente.py --teste"),
        ("Voz e velocidade do áudio de estudo", "python3 heimdall_agente.py --voz"),
        ("Painel do emulador de AWS (deve responder ok)", "curl -s http://localhost:8010/saude"),
        ("Heimdall Notas (deve responder ok)", "curl -s http://localhost:8011/saude"),
        ("Reiniciar só o Heimdall Notas", "pkill -f heimdall_biblioteca.py   # depois suba o sistema como de costume"),
        ("Teste do painel do emulador de AWS (sem rede)", "python3 teste_cloud.py"),
        ("Teste do Heimdall Notas (sem rede)", "python3 teste_biblioteca.py"),
        ("Teste dos trechos de livros do estudo (sem rede, precisa do Node)", "python3 teste_trechos.py"),
        ("Login e simulação do vigia de e-mail", "bash instalar_email_oficial.sh --testar"),
    ]),
    ("Documentos e conhecimento", [
        ("Indexar knowledge/ (incremental)", "python3 ingest_docs.py"),
        ("Recriar a base do zero (troca de modelo de embedding)", "python3 ingest_docs.py --reset"),
        ("Ouvir o áudio de estudo mais recente", "bash ouvir_estudo.sh"),
        ("Listar o que o Second Brain guardou de pastas privadas, sem apagar", "python3 limpar_privadas.py --so-listar"),
    ]),
    ("Instalar e atualizar as automações", [
        ("Fluxos básicos (AWS, versões, saúde do Mac, disponibilidade)", "bash instalar_fluxos_n8n.sh"),
        ("Fluxos avançados (GitOps, digest, Second Brain, estudo)", "bash instalar_automacoes_avancadas.sh"),
        ("Monitor de privacidade e diários oficiais", "bash instalar_monitor_privacidade.sh"),
        ("Mudar o que o monitor procura", "bash instalar_monitor_privacidade.sh --reconfigurar"),
        ("Vigia de e-mail de serviços públicos", "bash instalar_email_oficial.sh"),
        ("Conferir Querido Diário e Diário da Justiça", "python3 teste_diario_justica.py"),
        ("Testar as regras da triagem de avisos", "python3 teste_triagem.py"),
        ("Conferir a triagem de verdade no Mac (cria um lembrete de teste)", "python3 teste_triagem.py --mac"),
        ("Ver os itens pendentes da triagem", "python3 heimdall_banco.py --sql \"SELECT titulo, nivel, estado, avisos FROM triagem WHERE estado='pendente'\""),
        ("Ligar um repositório ao GitOps", "bash instalar_hook_gitops.sh /caminho/do/repositorio"),
    ]),
    ("Rodar um fluxo agora", [
        ("Estudo dos livros", "docker exec -e N8N_RUNNERS_BROKER_PORT=5680 n8n n8n execute --id=hdEstudoDiario01 2>&1 | tail -20"),
        ("Monitor de privacidade", "docker exec -e N8N_RUNNERS_BROKER_PORT=5680 n8n n8n execute --id=hdMonitor00000001 2>&1 | tail -20"),
        ("Diários oficiais", "docker exec -e N8N_RUNNERS_BROKER_PORT=5680 n8n n8n execute --id=hdDiario00000001 2>&1 | tail -20"),
    ]),
    ("Manter esta documentação", [
        ("Regerar as páginas e as tabelas do README", "python3 gerar_docs.py"),
        ("Conferir se estão em dia (usado no CI)", "python3 gerar_docs.py --check"),
    ]),
]

PROBLEMAS = [
    ("O comando de subir falha ou o terminal mostra 'command not found' depois dele",
     "Confira se digitou dois hifens nas opções (--terminal, não ---terminal) e se não colou texto extra no fim da linha. Digite o comando em vez de colar."),
    ("O Bark avisa 'não consegui gravar a nota'",
     "O aviso traz o motivo entre parênteses. Veja também: grep -E \"recusado|erro em|inválido\" heimdall.log | tail -5. Depois de atualizar o heimdall_agente.py, reinicie o agente."),
    ("Erro 'ascii codec can't encode' na busca do Gmail",
     "Corrigido: a consulta ao Gmail sai sem acentos. Atualize heimdall_email_oficial.py."),
    ("Falha de conexão TLS (SSL handshake failure) ao consultar o Querido Diário",
     "O servidor recusa a conexão de alguns ambientes. O aviso do Bark diz que a fonte não pôde ser consultada, sem fingir que não há nada. Teste de outra rede (por exemplo, o roteador do celular)."),
    ("Texto extraído de PDF derruba a gravação da nota ('embedded null byte')",
     "Corrigido: o agente remove caracteres de controle antes de gravar."),
    ("Sistema operacional pergunta permissão ao criar evento, lembrete ou nota",
     "Autorize o Terminal em Ajustes do Sistema, Privacidade e Segurança, Automação (Notas, Calendário e Lembretes). python3 heimdall_agente.py --teste confere tudo."),
]

from docs_tema import (CSS, JS, PAGINAS, REPO, ACESSOS, pagina, comando, tabela, corpo_inicio, corpo_marca, diagrama, favicon_svg,
                        logo_arquivo, simbolo_arquivo, simbolo_mono)

# ---------------------------------------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------------------------------------


def gerar_paginas(ferr, modelos, mcp, fluxos):
    out = {}
    n_pub = sum(1 for f in ferr if f["grupo"] == "público")
    n_mac = len(ferr) - n_pub
    out["index.html"] = pagina("index.html", "Heimdall-ai", "Heimdall-ai: assistente de Inteligência Artificial que roda no próprio computador, com ferramentas, documentos e automações. Documentação do projeto.",
                               corpo_inicio(len(modelos), len(ferr), n_pub, n_mac, len(mcp), len(fluxos)), home=True)
    out["marca.html"] = pagina("marca.html", "Marca", "Logotipo, cores e tipografia do Heimdall-ai.", corpo_marca())

    # ---- arquitetura
    linhas = [(H(n), H(f), "<code>%s</code>" % p, H(c)) for n, f, p, c in SERVICOS]
    out["arquitetura.html"] = pagina("arquitetura.html", "Arquitetura", "Como as peças do Heimdall-ai se ligam: modelos, LiteLLM, MCP, Qdrant, n8n, agente do Mac e serviços.", f"""
<h1>Arquitetura</h1>
<section aria-labelledby="mapa"><h2 id="mapa">Mapa</h2>
{diagrama()}</section>
<section aria-labelledby="camadas"><h2 id="camadas">Visão geral</h2>
<p>O Heimdall-ai tem quatro camadas, da base para o topo.</p>
<ol>
<li><strong>Modelos.</strong> O Ollama executa os modelos de linguagem no Mac (chip Apple, 16 GB de memória).</li>
<li><strong>Acesso único.</strong> O LiteLLM Proxy (porta 9000) expõe todos os modelos em uma API compatível com a da OpenAI e repassa os servidores MCP. Clientes como o Open WebUI e aplicativos de iPhone falam só com ele.</li>
<li><strong>Ferramentas.</strong> Três servidores MCP em Python (portas 8000, 8001 e 8004, este só com o banco pessoal e só nesta máquina) e o servidor de documentação da AWS dão ao modelo ferramentas: busca na web, leitura de páginas, arquivos, memória, documentos pessoais.</li>
<li><strong>Automações.</strong> O n8n agenda fluxos que usam os modelos e as ferramentas. O agente do Mac (porta 8003) liga o n8n, que roda em Docker, aos aplicativos do macOS. O Bark entrega os avisos no iPhone.</li>
</ol></section>
<section aria-labelledby="caminho"><h2 id="caminho">O caminho de uma pergunta no chat</h2>
<ol><li>A pessoa escreve no Open WebUI (pelo navegador ou pelo celular, pela rede privada Tailscale).</li>
<li>O Open WebUI envia ao LiteLLM, que encaminha ao Ollama o modelo escolhido.</li>
<li>Se o modelo decide usar uma ferramenta, devolve uma chamada estruturada; o LiteLLM a executa no servidor MCP correspondente e devolve o resultado ao modelo.</li>
<li>O modelo escreve a resposta final com o que a ferramenta trouxe.</li></ol></section>
<section aria-labelledby="auto"><h2 id="auto">O caminho de uma automação</h2>
<ol><li>O n8n dispara um fluxo no horário (ou por um evento, como um git push).</li>
<li>O fluxo busca dados (feeds, SearXNG, Qdrant, notas) e pede análises ao modelo pelo LiteLLM.</li>
<li>O resultado vai para o app Notas, o Calendário ou os Lembretes, pelo agente do Mac, e um resumo chega ao iPhone pelo Bark.</li>
<li>Se qualquer etapa falha, o fluxo de aviso de falha notifica; nenhuma automação falha em silêncio.</li></ol></section>
<section aria-labelledby="servicos"><h2 id="servicos">Serviços e portas</h2>
{tabela("Serviços do Heimdall-ai", ["Serviço", "Função", "Porta", "Como sobe"], linhas)}
<p class="muted">Os serviços de Docker escutam só no próprio computador. O acesso de fora passa pela rede privada Tailscale ou por túnel da Cloudflare com autenticação.</p></section>
<section aria-labelledby="seg"><h2 id="seg">Princípios de privacidade e segurança</h2>
<ul>
<li><strong>Dados pessoais ficam no Mac.</strong> Chaves e identificadores ficam no arquivo <code>.env</code>, com permissão restrita, e nunca no repositório.</li>
<li><strong>Pastas privadas são intocáveis.</strong> Notas de pastas marcadas como privadas nunca são lidas, indexadas nem analisadas. Se a verificação falhar, nenhuma nota é entregue.</li>
<li><strong>O agente só escreve onde deve.</strong> Grava apenas nas pastas do próprio Heimdall e nas pastas de temas de estudo.</li>
<li><strong>Autenticidade antes de confiança.</strong> O vigia de e-mail só trata como oficial o remetente que o Gmail confirmou, e nunca segue links.</li>
<li><strong>Falha externa não vira falso &quot;nada novo&quot;.</strong> Quando uma fonte de fora não responde, o fluxo tenta de novo a cada 2 horas, avisa assim que ela volta e, se ela passar de cerca de 24 horas fora do ar, manda um único aviso de indisponibilidade. Nunca finge que não há novidade.</li>
<li><strong>Entradas externas são dados, não ordens.</strong> Textos de páginas, e-mails e documentos passados ao modelo são tratados como conteúdo não confiável.</li></ul></section>
""")

    # ---- tecnologias
    tl = "".join('<li><a href="%s">%s</a>: %s</li>' % (H(u), H(n), H(d)) for n, u, d in TECNOLOGIAS)
    out["tecnologias.html"] = pagina("tecnologias.html", "Tecnologias", "Tecnologias usadas no Heimdall-ai e para que serve cada uma.", f"""
<h1>Tecnologias</h1>
<section aria-labelledby="stack"><h2 id="stack">O que foi usado</h2><ul>{tl}</ul></section>
<section aria-labelledby="req"><h2 id="req">Requisitos</h2>
<ul><li>Mac com chip Apple e 16 GB de memória ou mais (o projeto roda em um MacBook M2 Pro de 16 GB).</li>
<li>Docker Desktop, Ollama, Python 3.12 e, para o servidor de documentação da AWS, o <code>uv</code>.</li>
<li>Para os avisos: o aplicativo Bark no iPhone. Para o acesso remoto: Tailscale.</li>
<li>Pacotes Python no <code>venv</code>: fastmcp, litellm (com proxy), feedparser, psutil, pypdf, requests, starlette, pyyaml e youtube-transcript-api.</li>
<li>Para o modelo de embeddings: <code>ollama pull nomic-embed-text</code>.</li></ul></section>
""")

    # ---- LLMs
    ml = []
    for m in modelos:
        nome = m["model_name"]
        info = m.get("model_info", {}) or {}
        recs = [r for r, ok in (("ferramentas", info.get("supports_function_calling")), ("imagens", info.get("supports_vision"))) if ok]
        uso, obs = MODELOS_NOTAS.get(nome, ("(descrever em gerar_docs.py)", ""))
        ml.append(("<code>%s</code>" % H(nome), "<code>%s</code>" % H((m.get("litellm_params") or {}).get("model", "")), H(uso), H(", ".join(recs) or "texto"), H(obs)))
    out["llms.html"] = pagina("llms.html", "Modelos (LLMs)", "Modelos de linguagem do Heimdall-ai: quais são, para que servem e como foram testados.", f"""
<h1>Modelos de linguagem (LLMs)</h1>
<section aria-labelledby="lista"><h2 id="lista">Modelos configurados</h2>
{tabela("Modelos no LiteLLM", ["Nome no LiteLLM", "Modelo no Ollama", "Uso", "Declara suporte a", "Observações"], ml)}
<p class="muted">A coluna "Declara suporte a" vem do <code>litellm_config.yaml</code>; é o que o LiteLLM anuncia, não o resultado do teste. O resultado real de cada modelo se confere com <code>venv/bin/python test_models_tools.py</code>.</p></section>
<section aria-labelledby="como"><h2 id="como">Como funciona</h2>
<ul><li>Todos usam o prefixo <code>ollama_chat/</code>, que chama o endpoint de chat do Ollama e suporta chamada de ferramentas. O prefixo <code>ollama/</code> não suporta.</li>
<li>O modelo só chama ferramentas se o template dele no Ollama tiver suporte a ferramentas; o LiteLLM apenas declara. Quem decide é o teste (<code>test_models_tools.py</code>).</li>
<li>O contexto é de 8192 tokens (<code>num_ctx</code>) para todos.</li>
<li>Modelo padrão dos fluxos do n8n: <code>qwen3-vl-instruct</code> (muda com <code>HEIMDALL_FLOW_MODEL</code> no <code>.env</code>). O GitOps usa o <code>deepseek-coder-v2:16b</code>.</li>
<li>Embeddings: <code>nomic-embed-text</code>, para a base vetorial.</li></ul></section>
<section aria-labelledby="teste"><h2 id="teste">Como testar um modelo</h2>
{comando("venv/bin/python test_models_tools.py", "Testa todos os modelos")}
{comando("venv/bin/python test_models_tools.py --only qwen", "Testa só os que têm 'qwen' no nome")}
<p>O teste faz duas etapas: a chamada (o modelo devolve uma chamada estruturada à ferramenta certa) e o ciclo (a ferramenta executa e a resposta final usa o resultado real). Chamada escrita como texto é reprovada.</p></section>
""")

    # ---- MCP
    srv = []
    nomes_srv = {"heimdall": "Ferramentas do Mac (admin)", "heimdall_public": "Ferramentas públicas (convidados)", "aws_docs": "Documentação oficial da AWS"}
    for k, v in mcp.items():
        srv.append(("<code>%s</code>" % H(k), H(nomes_srv.get(k, "")), H(v.get("url") or ("%s %s" % (v.get("command", ""), "(stdio)"))), H(v.get("transport", ""))))
    blocos = ""
    for grupo, titulo_g, desc in (("público", "Ferramentas públicas", "Seguras para convidados. Servidas na porta 8001."), ("mac", "Ferramentas do Mac (administrador)", "Acessam arquivos, métricas e memória do computador. Servidas na porta 8000; só para o dono.")):
        blocos += '<section aria-labelledby="g-%s"><h2 id="g-%s">%s</h2><p>%s</p>' % (grupo, grupo, H(titulo_g), H(desc))
        for f in [x for x in ferr if x["grupo"] == grupo]:
            blocos += '<h3><code>%s</code></h3><p><code>%s(%s)</code></p><p>%s</p>' % (H(f["nome"]), H(f["nome"]), H(", ".join(f["params"])), H(f["doc"]))
        blocos += "</section>"
    out["mcp.html"] = pagina("mcp.html", "MCP e ferramentas", "Servidores MCP do Heimdall-ai e a documentação de cada ferramenta que o modelo pode chamar.", f"""
<h1>MCP e ferramentas</h1>
<section aria-labelledby="mcp"><h2 id="mcp">O que é o MCP</h2>
<p>O Model Context Protocol é o padrão que permite ao modelo chamar ferramentas externas. No Heimdall-ai, os servidores são escritos em Python com a biblioteca FastMCP e o LiteLLM os expõe em <code>http://&lt;host&gt;:9000/mcp</code> para os clientes.</p>
{tabela("Servidores MCP", ["Nome", "Função", "Endereço", "Transporte"], srv)}
<p>Os grupos de ferramentas são separados de propósito: o Open WebUI dos convidados se conecta só ao grupo público (porta 8001), e o grupo do Mac fica restrito ao administrador. O Open WebUI do administrador se conecta ao grupo de dados (porta 8004), que só tem as ferramentas do banco pessoal e escuta apenas em 127.0.0.1.</p></section>
{blocos}
<section aria-labelledby="teste"><h2 id="teste">Como testar</h2>
{comando("venv/bin/python test_mcp.py", "Testa os dois grupos direto e pelo LiteLLM")}
{comando("venv/bin/python test_mcp.py <IP-do-Tailscale>", "Testa pelo IP do Tailscale")}
<h3>Como criar uma ferramenta nova</h3>
<ol><li>Escreva a função em <code>heimdall_tools.py</code>, com anotação de tipos e um docstring claro (é o que o modelo lê para decidir quando usar).</li>
<li>Acrescente-a a <code>PUBLIC_TOOLS</code> (segura para convidados) ou <code>MAC_TOOLS</code> (acessa o Mac).</li>
<li>Reinicie o sistema e rode <code>test_mcp.py</code>.</li>
<li>Rode <code>python3 gerar_docs.py</code>: esta página se atualiza sozinha.</li></ol></section>
""")

    # ---- fluxos
    fl = ""
    for f in fluxos:
        desc = FLUXO_DESCRICAO.get(f["id"], "(descrição pendente: acrescente em gerar_docs.py)")
        fl += '<h3>%s<span class="tag">%s</span></h3><p>%s</p><details><summary>Etapas (%d)</summary><ol class="etapas">%s</ol></details><p class="muted">Arquivo: <code>%s</code> · id: <code>%s</code></p>' % (
            H(f["nome"]), H(f["quando"]), H(desc), len(f["etapas"]), "".join("<li>%s</li>" % H(e) for e in f["etapas"]), H(f["arquivo"]), H(f["id"]))
    sc = "".join("<li><code>%s</code>: %s</li>" % (H(n), H(d)) for n, d in SCRIPTS)
    out["fluxos.html"] = pagina("fluxos.html", "Fluxos e automações", "Fluxos do n8n e scripts do Heimdall-ai: o que cada um faz, quando roda e como funciona.", f"""
<h1>Fluxos e automações</h1>
<section aria-labelledby="n8n"><h2 id="n8n">Fluxos do n8n</h2>
<p>Cada fluxo é um arquivo JSON importável, gerado por script e instalado com os instaladores da página de comandos. As chaves (Bark, LiteLLM, token do agente) são aplicadas na instalação e nunca ficam no repositório. Todos os avisos chegam pelo Bark.</p>
{fl}</section>
<section aria-labelledby="scripts"><h2 id="scripts">Scripts e serviços de apoio</h2><ul>{sc}</ul></section>
<section aria-labelledby="regras"><h2 id="regras">Regras comuns a todos os fluxos</h2>
<ul><li>Falha nunca é silenciosa: o fluxo de aviso de falha notifica qual fluxo, em qual etapa e por quê.</li>
<li>Resultado vazio por falha de uma fonte nunca é descrito como "nada novo".</li>
<li>Fluxos com memória guardam o que já foi visto e só avisam o novo. A memória só persiste em execuções agendadas, não nas manuais.</li>
<li>Textos de fontes externas vão ao modelo como dados não confiáveis.</li></ul></section>
""")

    # ---- comandos
    cm = ""
    for titulo_c, itens in COMANDOS:
        cm += '<section aria-labelledby="c%d"><h2 id="c%d">%s</h2>' % (len(cm), len(cm), H(titulo_c))
        cm += "".join(comando(c, r) for r, c in itens) + "</section>"
    op = "".join("<li>%s</li>" % H(l) for l in ler_opcoes_start())
    pr = "".join("<h3>%s</h3><p>%s</p>" % (H(a), H(b)) for a, b in PROBLEMAS)
    out["comandos.html"] = pagina("comandos.html", "Comandos", "Comandos para subir, testar, instalar e manter o Heimdall-ai.", f"""
<h1>Comandos</h1>
<p>Todos os comandos são executados no Terminal, na pasta do projeto (<code>~/heimdall-ai</code>). Em cada um há um botão para copiar. Se for colar, confira que nada além do comando entrou na linha.</p>
{cm}
<section aria-labelledby="opcoes"><h2 id="opcoes">Opções do start_heimdall.sh</h2><details><summary>Texto de ajuda do script</summary><ul>{op}</ul></details></section>
<section aria-labelledby="prob"><h2 id="prob">Problemas conhecidos</h2>{pr}</section>
""")

    # ---- novidades
    cl = ler_changelog()
    nv = "".join('<section aria-labelledby="d%s"><h2 id="d%s">%s%s</h2><ul>%s</ul></section>' % (b["data"], b["data"], H(b["data"] if b["data"]=="Anteriores" else b["data"][8:10] + "/" + b["data"][5:7] + "/" + b["data"][:4]), (" · " + H(b["titulo"])) if b["titulo"] else "", "".join("<li>%s</li>" % H(i) for i in b["itens"])) for b in cl) or "<p>Sem registros ainda.</p>"
    out["novidades.html"] = pagina("novidades.html", "Novidades", "Histórico de recursos do Heimdall-ai, do mais recente ao mais antigo.", f"<h1>Novidades</h1><p class=\"muted\">Gerado do arquivo CHANGELOG.md.</p>{nv}")
    etapas, intro_rm = ler_roadmap()
    rm = "".join('<section aria-labelledby="r%d"><h2 id="r%d">%s</h2>%s<ul>%s</ul></section>' % (
        k, k, H(e["nome"]), ('<p class="muted">%s</p>' % H(e["nota"])) if e["nota"] else "",
        "".join("<li><strong>%s</strong>%s</li>" % (H(t), (": " + H(d)) if d else "") for t, d in e["itens"])) for k, e in enumerate(etapas)) or "<p>Sem itens ainda.</p>"
    out["roadmap.html"] = pagina("roadmap.html", "Roadmap", "Próximos recursos do Heimdall-ai: o que está em andamento, o que vem em seguida e as ideias em avaliação.",
                                 f"<h1>Roadmap</h1><p>{H(intro_rm)}</p>{rm}<p>O que já foi entregue está em <a href=\"novidades.html\">Novidades</a>.</p>")
    out["cloud.html"] = pagina("cloud.html", "Cloud", "Heimdall Cloud: painel web do emulador de AWS do Heimdall-ai, com S3, Lambda, Glue, Athena e console geral, protegido por senha e código de 6 dígitos.", """
<h1>Cloud</h1>
<p>O Heimdall Cloud é um painel web para usar o emulador de AWS (LocalStack, com o Moto como alternativa) pelo navegador. Serve para estudar engenharia de dados na AWS sem custo e sem depender de um console visual: as páginas são texto, títulos, tabelas e formulários simples, boas para leitor de tela.</p>
<section aria-labelledby="entrar"><h2 id="entrar">Como entrar</h2>
<ol><li>Endereço: <a href="https://cloud.heimdall-ai.tech">cloud.heimdall-ai.tech</a>. É de uso pessoal, não é aberto ao público.</li>
<li>A entrada pede uma senha forte e um código de 6 dígitos, que o aplicativo Senhas da Apple gera e troca a cada 30 segundos.</li>
<li>O painel só responde com o computador ligado e o sistema rodando. No próprio computador, o endereço é http://localhost:8010.</li></ol></section>
<section aria-labelledby="fazer"><h2 id="fazer">O que dá para fazer</h2>
<ul><li><strong>S3</strong>: criar e apagar buckets, enviar, baixar e apagar arquivos.</li>
<li><strong>Lambda</strong>: criar uma função a partir de código Python, executar com um evento e ver a resposta e o registro de saída.</li>
<li><strong>Glue</strong>: bancos de dados, tabelas (a partir de uma pasta do S3 em CSV, JSON ou Parquet), crawlers e jobs.</li>
<li><strong>Athena</strong>: consultas SQL sobre os arquivos do S3, com o resultado em tabela e o histórico das últimas consultas.</li>
<li><strong>Console geral</strong>: qualquer operação de qualquer serviço (DynamoDB, SQS, SNS, Kinesis, IAM, CloudFormation e outros), com os parâmetros em JSON e exemplos prontos.</li></ul></section>
<section aria-labelledby="roteiro"><h2 id="roteiro">Do arquivo à consulta</h2>
<ol><li>No S3, crie um bucket e envie um arquivo CSV para dentro de uma pasta.</li>
<li>No Glue, crie um banco de dados.</li>
<li>No Glue, crie uma tabela apontando para a pasta do S3, com as colunas e os tipos.</li>
<li>No Athena, escolha o banco e rode um SELECT na tabela.</li></ol>
<p>O roteiro completo, com exemplos, o teste do Lambda e a solução de problemas, está em <a href="https://github.com/mrl2bolonhini/heimdall-ai/blob/main/LEIAME_cloud_roteiro.txt">LEIAME_cloud_roteiro.txt</a>.</p></section>
<section aria-labelledby="seguranca"><h2 id="seguranca">Segurança</h2>
<ul><li>O painel escuta só em 127.0.0.1. A porta do emulador nunca é exposta, porque ela não tem senha.</li>
<li>Entrada com senha (guardada só como hash PBKDF2) e código de 6 dígitos (TOTP), que não pode ser reaproveitado.</li>
<li>Limite de tentativas por endereço e global, com bloqueio de 15 minutos.</li>
<li>Sessão em cookie HttpOnly e SameSite=Strict, com validade, e token contra CSRF nos formulários.</li>
<li>Só atende os nomes de site permitidos, manda cabeçalhos de segurança e entrega os arquivos baixados sempre como anexo.</li>
<li>Executar funções Lambda dá ao emulador controle do Docker do computador. Por isso a entrada tem duas camadas, e a execução pode ser desligada com <code>HEIMDALL_LOCALSTACK_DOCKER=0</code>.</li></ul></section>
<section aria-labelledby="config"><h2 id="config">Configuração</h2>
<ul><li>Definir a senha e gerar o código de 6 dígitos: <code>python3 heimdall_cloud.py --definir-senha</code></li>
<li>Gerar só um novo código: <code>python3 heimdall_cloud.py --novo-codigo</code></li>
<li>Conferir se o painel está no ar: <code>curl -s http://localhost:8010/saude</code></li>
<li>Testar o painel sem o LocalStack: <code>python3 teste_cloud.py</code></li></ul>
<p>O painel sobe sozinho com o sistema quando há senha e código no <code>.env</code>. Se o LocalStack recusar a licença, o sistema avisa e usa o Moto no lugar, onde Lambda, Glue e Athena são só simulados. Veja os comandos completos em <a href="comandos.html">Comandos</a> e o histórico em <a href="novidades.html">Novidades</a>.</p></section>
""")
    out["notas.html"] = pagina("notas.html", "Notas", "Heimdall Notas: site simples para ler as notas de estudo e ouvir os áudios, com o mesmo login do painel Cloud.", """
<h1>Heimdall Notas</h1>
<p>O Heimdall Notas é um site simples e agradável para ler as notas de estudo e ouvir os áudios gerados pelo Heimdall-ai. Ela lê direto do cofre (notas em Markdown e áudios .m4a) e da pasta knowledge/, sem depender de nenhum aplicativo de notas. Foi feita para leitor de tela: títulos, listas e botões com nomes claros, link para pular ao conteúdo e áudio com controles nativos.</p>
<section aria-labelledby="abrir"><h2 id="abrir">Como abrir</h2>
<ol><li>No próprio computador: http://localhost:8011, depois de subir o sistema.</li>
<li>A entrada usa a mesma senha e o mesmo código de 6 dígitos do painel Cloud.</li>
<li>Para abrir de fora de casa, o site pode ganhar um endereço público próprio pelo túnel Cloudflare, em notes.heimdall-ai.tech. Isso é opcional e só funciona com o computador ligado.</li></ol></section>
<section aria-labelledby="fazer"><h2 id="fazer">O que dá para fazer</h2>
<ul><li><strong>Ler</strong>: cada nota vira uma página limpa, com títulos, listas e tabelas, e as tags e os conceitos em linhas simples.</li>
<li><strong>Ouvir</strong>: o leitor de áudio fica no topo da nota, com velocidade de 0,75 a 1,5 vez, botões de voltar e avançar 15 segundos, e a página lembra onde você parou.</li>
<li><strong>Navegar</strong>: início com as últimas notas e os temas, lista por tema e botões de nota anterior e próxima nota.</li>
<li><strong>Buscar</strong>: procura nas notas e nos documentos de texto, sem diferenciar acentos nem maiúsculas.</li>
<li><strong>Documentos</strong>: os arquivos de knowledge/ (PDF abre na própria página; Markdown e texto são lidos como nota; outros formatos são baixados).</li></ul></section>
<section aria-labelledby="privacidade"><h2 id="privacidade">O que aparece</h2>
<ul><li>Por padrão aparece o cofre inteiro: temas de estudo, Second Brain, Monitor de Privacidade, Saúde e as demais pastas.</li>
<li>Só o Digest fica de fora, porque terá outro uso.</li>
<li>Para tirar outras pastas, use <code>HEIMDALL_BIBLIOTECA_EXCLUIR="heimdall-digest,saude"</code> no <code>.env</code>. Para mostrar só algumas, <code>HEIMDALL_BIBLIOTECA_PASTAS="pasta-um,pasta-dois"</code>.</li>
<li>Como inclui notas pessoais, o endereço público exige a senha e o código de 6 dígitos em toda visita.</li></ul></section>
<section aria-labelledby="seguranca"><h2 id="seguranca">Segurança</h2>
<ul><li>Escuta só em 127.0.0.1 e é somente de leitura: nada ali grava ou apaga arquivos.</li>
<li>Senha forte e código de 6 dígitos que não pode ser reaproveitado, limite de tentativas, sessão em cookie HttpOnly e SameSite=Strict.</li>
<li>Só atende os nomes de site permitidos. Os caminhos são conferidos contra fuga de pasta, todo texto é escapado e arquivos que não são PDF ou áudio só baixam, nunca executam.</li></ul></section>
<section aria-labelledby="config"><h2 id="config">Configuração</h2>
<ul><li>O Heimdall Notas sobe sozinho com o sistema quando há senha e código no <code>.env</code> (os mesmos do Cloud).</li>
<li>Conferir se está no ar: <code>curl -s http://localhost:8011/saude</code></li>
<li>Reiniciar só ela: <code>pkill -f heimdall_biblioteca.py</code> e subir o sistema como de costume.</li>
<li>Testar sem rede: <code>python3 teste_biblioteca.py</code></li>
<li>Se algo falhar: <code>tail -20 biblioteca_debug.log</code></li></ul></section>
""")
    out["404.html"] = pagina("404.html", "Página não encontrada", "Página não encontrada.", f'<h1>Página não encontrada</h1><p>Volte ao <a href="index.html">início</a> ou veja o <a href="arquitetura.html">mapa do projeto</a>.</p>')
    return out


# ---------------------------------------------------------------------------------------------------------
# README: tabelas automáticas entre marcadores
# ---------------------------------------------------------------------------------------------------------


def md_tabelas(ferr, modelos, mcp, fluxos):
    t = {}
    t["MODELOS"] = "| Nome no LiteLLM | Modelo no Ollama | Uso | Observações |\n|---|---|---|---|\n" + "\n".join(
        "| `%s` | `%s` | %s | %s |" % (m["model_name"], (m.get("litellm_params") or {}).get("model", ""), *MODELOS_NOTAS.get(m["model_name"], ("", ""))) for m in modelos)
    t["FERRAMENTAS"] = "| Ferramenta | Grupo | Parâmetros | O que faz |\n|---|---|---|---|\n" + "\n".join(
        "| `%s` | %s | `%s` | %s |" % (f["nome"], "público (8001)" if f["grupo"] == "público" else "Mac (8000)", ", ".join(f["params"]), f["doc"].split(". ")[0].rstrip(".") + ".") for f in ferr)
    t["FLUXOS"] = "| Fluxo | Quando | O que faz |\n|---|---|---|\n" + "\n".join(
        "| %s | %s | %s |" % (f["nome"], f["quando"], FLUXO_DESCRICAO.get(f["id"], "(descrição pendente)")) for f in fluxos)
    t["SERVICOS"] = "| Serviço | Porta | Função |\n|---|---|---|\n" + "\n".join("| %s | %s | %s |" % (n, p, f) for n, f, p, c in SERVICOS)
    return t


def atualizar_readme(tab, so_checar):
    arq = AQUI / "README.md"
    if not arq.exists():
        print("Aviso: README.md não existe; nada a atualizar.")
        return True
    txt = arq.read_text(encoding="utf-8")
    novo = txt
    for nome, conteudo in tab.items():
        novo = re.sub(r"(<!-- AUTO:%s -->\n)(?:.*?\n)?(<!-- /AUTO:%s -->)" % (nome, nome), lambda m: m.group(1) + conteudo + "\n" + m.group(2), novo, flags=re.S)
    if novo != txt and not so_checar:
        arq.write_text(novo, encoding="utf-8")
    return novo == txt


def main():
    so_checar = "--check" in sys.argv
    ferr = ler_ferramentas()
    modelos, mcp = ler_config()
    fluxos = ler_fluxos()
    paginas = gerar_paginas(ferr, modelos, mcp, fluxos)
    arquivos = dict(paginas)
    arquivos["style.css"] = CSS
    arquivos["heimdall.js"] = JS
    arquivos["favicon.svg"] = favicon_svg()
    arquivos["logo.svg"] = logo_arquivo(False)
    arquivos["logo-escuro.svg"] = logo_arquivo(True)
    arquivos["simbolo.svg"] = simbolo_arquivo()
    arquivos["simbolo-uma-cor.svg"] = simbolo_mono()
    arquivos["CNAME"] = DOMINIO + "\n"
    arquivos[".nojekyll"] = ""
    arquivos["robots.txt"] = "User-agent: *\nAllow: /\n"
    pend = [f["id"] for f in fluxos if f["id"] not in FLUXO_DESCRICAO]
    pend += [m["model_name"] for m in modelos if m["model_name"] not in MODELOS_NOTAS]
    if pend:
        print("Atenção: faltam descrições em gerar_docs.py para:", ", ".join(pend))
    desatualizado = []
    DOCS.mkdir(exist_ok=True)
    for nome, conteudo in arquivos.items():
        arq = DOCS / nome
        if not arq.exists() or arq.read_text(encoding="utf-8") != conteudo:
            desatualizado.append("docs/" + nome)
            if not so_checar:
                arq.write_text(conteudo, encoding="utf-8")
    readme_ok = atualizar_readme(md_tabelas(ferr, modelos, mcp, fluxos), so_checar)
    if not readme_ok:
        desatualizado.append("README.md")
    if so_checar:
        if desatualizado:
            print("Desatualizado:", ", ".join(desatualizado), "\nRode: python3 gerar_docs.py")
            return 1
        print("Documentação em dia.")
        return 0
    print("Gerado: %d arquivos em docs/ (%d mudaram). %d ferramentas, %d modelos, %d fluxos." % (len(arquivos), len(desatualizado), len(ferr), len(modelos), len(fluxos)))
    return 1 if pend else 0


if __name__ == "__main__":
    sys.exit(main())
