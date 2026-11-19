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
                if getattr(t, "id", "") in ("PUBLIC_TOOLS", "MAC_TOOLS", "DADOS_TOOLS"):
                    grupos[t.id] = [e.id for e in n.value.elts if isinstance(e, ast.Name)]
    saida = []
    for grupo, rotulo in (("PUBLIC_TOOLS", "público"), ("MAC_TOOLS", "mac"), ("DADOS_TOOLS", "dados")):
        for nome in grupos.get(grupo, []):
            if grupo == "DADOS_TOOLS" and any(nome in grupos.get(g, []) for g in ("PUBLIC_TOOLS", "MAC_TOOLS")):
                continue  # já listada no grupo onde nasceu; aqui só entram as exclusivas do chat
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
    ("Servidor MCP de dados", "Só as ferramentas do banco pessoal (saúde, diários, e-mails, estudos, Second Brain) e as de consulta do Finance, para o Open WebUI. Escuta só em 127.0.0.1.", "8004", "start_heimdall.sh"),
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
    ("Heimdall News", "Notícias das últimas 24 horas com resumo feito por IA (sinalizado como tal), 10 por página, e feeds RSS com chave secreta para o app de feeds do iPhone. Atualiza de 30 em 30 minutos e guarda 30 dias no banco pessoal. Mesmo login do Heimdall Cloud. Escuta só em 127.0.0.1.", "8012", "sobe sozinho com HEIMDALL_CLOUD_SENHA_HASH e HEIMDALL_CLOUD_TOTP_SEGREDO no .env"),
    ("Heimdall Jogos", "Jogos leves para leitor de tela no navegador: forca, senha (Mastermind), jogo da velha, número secreto, 2048, cinco letras, sudoku, xadrez, batalha naval, campo minado, caça-níqueis e quatro aventuras de texto com níveis de dificuldade. Cada jogada é lida em voz alta por uma região aria-live. Não guarda nada. Mesmo login do Heimdall Cloud. Escuta só em 127.0.0.1.", "8014", "sobe sozinho com HEIMDALL_CLOUD_SENHA_HASH e HEIMDALL_CLOUD_TOTP_SEGREDO no .env"),
    ("Heimdall Finance", "Finanças pessoais em páginas de texto e tabelas: importa extratos OFX e CSV, classifica gastos por categoria com regras que você ajusta, mostra o resumo do mês, os maiores gastos, as tendências e alertas. Banco SQLite só no Mac (dados_financas, fora do git); só sai do Mac o que você ligar de propósito: a conexão com os bancos pelo Meu Pluggy (dados passam pelos servidores dele) e a leitura de e-mail (somente leitura). Mesmo login do Heimdall Cloud. Escuta só em 127.0.0.1.", "8016", "sobe sozinho com HEIMDALL_CLOUD_SENHA_HASH e HEIMDALL_CLOUD_TOTP_SEGREDO no .env"),
    ("Heimdall Saúde", "Painel somente de leitura com as análises do app Saúde: como você está agora, tendências, sono, atividade, recuperação, coração e ECG, treinos, sintomas, humor, medicamentos, relatório da semana, diário em tabela e o estado dos dados (mostra se a exportação contínua do iPhone parou). Mesmo login do Heimdall Cloud. Escuta só em 127.0.0.1.", "8013", "sobe sozinho com HEIMDALL_CLOUD_SENHA_HASH e HEIMDALL_CLOUD_TOTP_SEGREDO no .env"),
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
    "gemma-4-uncensored": ("Uso geral", "Confira a chamada de ferramentas com test_models_tools.py."),
    "dolphin3-cyber-8b": ("Segurança e conversa livre, só texto", "Não chama ferramentas no Ollama; use para análises de texto, não nos fluxos com MCP."),
    "deepseek-coder-v2:16b": ("Código (usado pelo GitOps)", "O GitOps usa este modelo na etapa de análise de código."),
    "qwen3-vl-instruct": ("Modelo padrão dos fluxos; entende imagens", "Declara suporte a imagens no LiteLLM."),
    "gemma3-4b": ("Modelo pequeno e rápido (3 GB), usado nos resumos do Heimdall News", "No teste com um parágrafo resumiu certo em português; baixe com ollama pull gemma3:4b."),
    "llama-3.1-8b": ("Uso geral; aceita ferramentas", "Template do Ollama com suporte a ferramentas; respondeu bem em português."),
}

FLUXO_DESCRICAO = {
    "hdAwsDiario0001": "Lê o feed de novidades da AWS, filtra os serviços de dados (Glue, Redshift, Athena, S3, Kinesis e outros), resume em português e avisa no iPhone.",
    "hdVersoesSem0001": "Consulta os lançamentos dos projetos que o Heimdall usa, avalia se vale atualizar e avisa no iPhone.",
    "hdSaudeMac00001": "Lê as métricas do Mac pelo MCP e avisa quando RAM, swap ou disco passam dos limites configurados.",
    "hdDisponib000001": "Lê a página de status do Uptime Kuma, monta o relatório de disponibilidade do dia e avisa no iPhone.",
    "hdEstudoDiario01": "Para cada tema da base de conhecimento (subpastas de knowledge/), sorteia um trecho, monta uma leitura, cria pergunta e resposta, busca de 1 a 3 artigos na web e grava a nota no app Notas, na pasta com o nome do tema, com áudio narrado.",
    "hdGitOps00000001": "A cada git push, divide o código alterado em trechos de até 5 mil caracteres, analisa os trechos tocados pelo commit com o modelo de código (um de cada vez, para poupar memória), que responde com edições pontuais validadas uma a uma, e abre um Pull Request em rascunho com as refatorações sugeridas. Se o GitHub recusar o PR, apaga a branch para não deixar lixo e avisa com o motivo e o resumo dos achados. Sempre avisa o resultado, inclusive quando não há nada a refatorar. Quando houve Pull Request proposto ou trechos descartados, grava também uma nota de histórico em Heimdall-ai/GitOps, com cada motivo de descarte.",
    "hdDigest00000001": "Lê feeds de notícias, filtra pelo que interessa, cruza com as notas e os livros e grava um resumo personalizado no app Notas. Não avisa pelo Bark: as notícias chegam pelo Heimdall News e pelos feeds RSS.",
    "hdSecondBrain001": "Observa as notas alteradas do app Notas (nunca as de pastas privadas), cria embeddings, encontra conexões e lacunas e grava a análise na pasta Cérebro.",
    "hdFalhaAviso0001": "Quando qualquer fluxo falha, avisa no iPhone qual fluxo, em que etapa e por quê. Fluxos nunca falham em silêncio.",
    "hdMonitor00000001": "Pesquisa na web os identificadores pessoais configurados pelo dono (nome, e-mails, usuários) em busca de menções, comentários, vazamentos e imagens, separa homônimos, analisa o risco e grava o relatório. Tem memória: só avisa o que é novo.",
    "hdDiario00000001": "Procura o nome do dono nos diários oficiais do município de São Paulo, da União e do Estado de SP e, se a OAB estiver configurada, as comunicações dela no Diário da Justiça Eletrônico Nacional (CNJ). Avisa só o que for novo. Se uma fonte externa falhar, repete a consulta dela a cada 2 horas (até 72 h), avisa na hora quando voltar e, depois de cerca de 24 h fora do ar, manda um único aviso de indisponibilidade. Nunca finge que não há nada.",
    "hdResumo00000001": "Junta os avisos de rotina em três notificações por dia (6h, 8h e 10h), em vez de uma por fluxo. Avisos urgentes e os de situação (falhas, GitOps, alerta do Mac) continuam na hora.",
    "hdSaude000000001": "Recebe os dados do app Saúde (iPhone e Apple Watch) e escreve às 5h50 um resumo de sono, pulso, variabilidade, respiração e atividade contra a média de 30 dias. Se o sono da noite chegar depois das 5h50, refaz o resumo uma vez. Quando duas ou mais medidas da noite saem juntas do seu intervalo típico (estilo Sinais Vitais da Apple), destaca e abre um item de triagem. As regras decidem o que é relevante, o modelo só redige e uma verificação barra texto com sentido trocado.",
    "hdTriagem0000001": "A cada 15 minutos chama o agente do Mac, que lê a lista \"Heimdall: Triagem\" do app Lembretes, registra o que você concluiu, reclassificou ou adiou e insiste pelo Bark nos itens pendentes, num só aviso que lista todos (em vez de um aviso por item): a cada 4 horas das 7h às 21h, a cada 2 horas se houver item crítico (que fura o modo silencioso), e a cada 8 horas se só restarem itens de prioridade baixa. Menções do Diário da Justiça viram críticas depois de 24 horas sem ação.",
    "hdSaudeSemanal01": "Todo domingo às 9h pede ao agente do Mac o relatório de saúde da semana, que grava na pasta Saúde do app Notas, com áudio, e avisa pelo Bark com uma frase sem números. Tem botão para gerar na hora.",
    "hdSeguranca00001": "O modelo dolphin3-cyber-8b revisa a segurança do Mac sem usar ferramentas: o agente coleta os dados e ele analisa. Todo dia às 4h30 olha os logs das últimas 24 horas (acessos recusados e erros repetidos); aos domingos, às 5h, os commits da semana (segredos, caminhos pessoais, IPs privados, arquivos sensíveis) e, às 5h30, a exposição à rede (portas em escuta, Tailscale Funnel, firewall) comparada com a semana anterior. Cada achado do modelo precisa citar um trecho dos dados, e o script confere. Grava a nota em Segurança só quando há o que dizer; gravidade média vira aviso no grupo das 10h e a alta fura a fila e entra na triagem.",
    "hdBackup00000001": "Todo dia às 3h30 pede ao agente do Mac uma cópia do banco pessoal, criptografada com senha, enviada a uma pasta (iCloud Drive) e ao Cloudflare R2 quando configurado, mantendo as 14 mais recentes e uma por mês. Aos domingos, às 4h, baixa a cópia mais recente, decifra e confere a integridade. Qualquer falha aciona o aviso de falha pelo Bark.",
    "hdLembrete0000001": "Lembrete mensal para conferir, nos aplicativos oficiais, serviços que exigem login (INSS, FGTS, Carteira de Trabalho, Registrato e Serasa).",
}

SCRIPTS = [
    ("heimdall_agente.py", "Agente do Mac (porta 8003). Recebe pedidos do n8n com um token e grava notas no app Notas, cria eventos no Calendário e lembretes no app Lembretes, narra textos com a voz do macOS e busca em dois sites públicos permitidos. Só escreve nas pastas do próprio Heimdall e nunca lê notas de pastas privadas."),
    ("heimdall_triagem.py", "Triagem obrigatória de avisos importantes. Cria lembretes na lista \"Heimdall: Triagem\" do app Lembretes (menções do Diário da Justiça, alertas de saúde, e-mails suspeitos ou urgentes e achados de privacidade de risco médio ou alto) e insiste pelo Bark até você concluir, reclassificar ou adiar. Roda dentro do agente do Mac."),
    ("heimdall_email_oficial.py", "Vigia o Gmail a cada hora, só lendo. Confere se e-mails de serviços públicos (INSS, gov.br, FGTS, Receita, Serasa e outros) são autênticos, resume os verdadeiros, alerta sobre imitações e cria evento e lembrete quando há prazo. Nunca segue links."),
    ("heimdall_notas.py", "Heimdall Notas (porta 8011): site para ler as notas de estudo do cofre e ouvir os áudios, com velocidade, voltar e avançar 15 segundos, busca e os documentos de knowledge/. Mesmo login do Heimdall Cloud; mostra o cofre inteiro, menos o Digest."),
    ("heimdall_cfaccess.py", "Entrada pelo Cloudflare Access com Microsoft Entra ID: a aprovação chega como notificação no Microsoft Authenticator e os painéis abrem a sessão sem senha nem código de 6 dígitos. Confere a assinatura do Cloudflare só com a biblioteca padrão. Desligado até haver HEIMDALL_CFACCESS_EQUIPE, _AUD e _EMAILS no .env; --status confere a configuração. Passo a passo em LEIAME_autenticacao_microsoft.txt."),
    ("heimdall_acesso.py", "Troca a senha e o código de 6 dígitos que valem para todos os serviços com login (Cloud, Notas, News e Saúde): --tudo, --senha ou --codigo. A senha é pedida sem aparecer na tela e fica só como hash no .env."),
    ("heimdall_news.py", "Heimdall News (porta 8012): lê os feeds de noticias_fontes.json de 30 em 30 minutos, tira repetidas, traduz títulos em inglês e pede a um modelo local um resumo de cada matéria (sempre marcado como feito por IA). Guarda 30 dias na tabela noticias do banco pessoal, mostra as últimas 24 horas em páginas de 10 e serve feeds RSS (geral, por categoria e OPML) em endereços com chave secreta."),
    ("heimdall_design.py", "Heimdall Design: o padrão de interface igual em todos os sites (link lê, botão age): botão de ação como formulário GET, com nome acessível, e o CSS compartilhado."),
    ("CLAUDE.md", "Regras do repositório: toda atualização de interface segue o Heimdall Design."),
    ("diagnostico.py", "Diagnóstico de desempenho do Mac (heimdall doctor): memória, troca em disco, processador, disco, Docker, Ollama e serviços."),
    ("financas_boletos.py", "Leitor de boletos: linha digitável de 47 e 48 números, dígitos verificadores, vencimento e contas a pagar no banco local."),
    ("teste_boletos.py", "Teste do leitor de boletos, com linhas inventadas montadas por contas independentes."),
    ("teste_finance_chat.py", "Teste das ferramentas do Finance no chat: leitura, filtros, conexão somente leitura, desligar e banco ausente."),
    ("financas_analise.py", "Análise de consultor do Finance: fatos calculados em código (semana e mês), texto fixo, reescrita pelo modelo local com conferência dos números e contexto das perguntas."),
    ("heimdall_perguntar.py", "Perguntar ao modelo local, reutilizável pelos sites: contexto montado pelo código, resposta só com base nele, conferência dos valores e tarefas em segundo plano. Sem reserva na nuvem."),
    ("teste_finance_analise.py", "Teste da análise e do Perguntar com modelo simulado."),
    ("financas_pluggy.py", "Conexão com os bancos pelo Open Finance, com o plano pessoal gratuito do Meu Pluggy: autenticação e leituras (GET) de contas e transações em /v2/transactions, conversão de sinais (conta corrente pelo tipo, cartão pela fatura), importação sem duplicar, aviso de autorização perto de vencer e gravação das chaves no .env a partir da área de transferência. Nada é movido nem pago; os dados passam pelos servidores do Pluggy."),
    ("financas_consulta.py", "Consultas do Finance no terminal (heimdall finance --balance, --latest, --summary): saldo de cada conta e fatura de cada cartão, últimos lançamentos com filtros e resumo do mês, em texto corrido e listas numeradas. Só lê o banco local e o saldo guardado na última sincronização."),
    ("modelos_chat.py", "Fonte única dos modelos personalizados do chat (Open WebUI): base, prompt, temperatura e a lista de funções que cada modelo pode usar. Gera o guia modelos_open_webui.txt e a tabela do README."),
    ("openwebui/modelos_importar.json", "Os sete modelos do chat prontos para importar no Open WebUI (Workspace, Modelos, Importar): prompt, temperatura, chamada de função nativa e a conexão de ferramentas de cada um. Gerado por gerar_docs.py; entram só para o administrador."),
    ("openwebui/ferramentas_importar.json", "As cinco conexões de ferramentas (MCP) prontas para importar no Open WebUI, no mesmo formato que o Open WebUI exporta. O filtro de funções não viaja nele: o filtro de cada conexão (as funções do servidor que ela deve esconder, no formato !funcao) fica em openwebui/filtro_<id>.txt, para copiar com pbcopy e colar à mão."),
    ("teste_modelos_chat.py", "Confere que cada função citada existe e pertence ao servidor certo, que cada prompt só fala das funções do seu modelo e que o guia está em dia."),
    ("prompt_chat_saude.txt", "Instrução de sistema do modelo Saúde do chat: como escolher entre as funções de saúde, sem diagnóstico e sem inventar números."),
    ("prompt_chat_financas.txt", "Instrução de sistema do modelo Finanças do chat: como escolher entre as funções do Finance, só leitura, sem conselho de investimento e sem pagar nada."),
    ("teste_email_prioridade.py", "Testa o rebaixamento de e-mails oficiais de serviços sem interesse (Serasa, SPC, Boa Vista, Quod): não viram triagem nem lembrete; golpe imitando eles continua alertando."),
    ("teste_finance_pluggy.py", "Testa o sincronizador do Pluggy com uma API simulada: sinais, cursor, duplicidade, nomes de conta, avisos, chaves no .env. Sem rede."),
    ("financas_email.py", "Leitura do Gmail (somente leitura) atrás de boletos e Pix, no corpo e nos PDFs anexados, com conferência da autenticação do remetente. Nunca abre links."),
    ("teste_finance_email.py", "Teste da leitura de boletos por e-mail com mensagens montadas no teste."),
    ("teste_diagnostico.py", "Teste do diagnóstico: análise dos textos do macOS sem depender do Mac."),
    ("teste_design.py", "Teste do Heimdall Design: falha se um link de painel tiver texto de ação, se algum contraste de cor ficar abaixo do mínimo, se o foco for removido ou houver cor solta fora do Heimdall Design."),
    ("heimdall_paginacao.py", "Paginação em botões usada pelo Heimdall News, Notas e Finance: Página anterior, números de página com a atual marcada, Próxima página e Última página, em um formulário GET que mantém o tema, a categoria ou a busca."),
    ("heimdall_jogos.py", "Heimdall Jogos (porta 8014): entrega os jogos da pasta jogos/ (JavaScript sem dependências; as aventuras usam o motor.js e histórias em dados hist_*.js) atrás do mesmo login do Cloud, com política de conteúdo que só deixa rodar script do próprio site. Endereço de fora: games.heimdall-ai.tech."),
    ("heimdall_finance.py", "Heimdall Finance (porta 8016): painel web das finanças (resumo do mês, transações, tendências, importação, regras) atrás do mesmo login do Cloud, com CSRF em todo envio e política de conteúdo sem script. Endereço de fora: finance.heimdall-ai.tech."),
    ("financas_nucleo.py", "Núcleo do Heimdall Finance: banco SQLite local, leitura de extratos OFX e CSV (formatos e valores brasileiros), deduplicação, categorias por regras (as suas vencem as padrão) e relatórios de resumo e tendências. Sem internet."),
    ("financas_arquivos.py", "Arquivos do Heimdall Finance: leitura de PDF de extrato e fatura (texto extraído por pypdf ou pdftotext e lido por linhas de data, descrição e valor, com conferência do total do documento), identificação do banco e do tipo, inspeção anônima do layout (letras viram x, números viram 9) e a pasta de entrada vigiada. Sem internet."),
    ("financas_cli.py", "Comandos de terminal do Finance para arquivos: --inspect, --explain, --preview, --import, --inbox e --folder (heimdall finance ...)."),
    ("heimdall_painel_saude.py", "Heimdall Saúde (porta 8013): painel web somente de leitura com as análises do heimdall_saude.py, em páginas de texto e tabelas para leitor de tela, e o estado dos dados. Mesmo login do Cloud (senha e código de 6 dígitos). Endereço de fora: health.heimdall-ai.tech."),
    ("heimdall_voz.py", "Dicionário de pronúncia: troca palavras por uma grafia que a voz do macOS lê certo (por exemplo, Heimdall vira Háimdal), no anúncio falado do subir.sh e no áudio das notas. Aceita --importar arquivo.csv para trazer as pronúncias do VoiceOver."),
    ("pronuncias.txt", "Pronúncias que vêm com o projeto, uma por linha no formato palavra = como falar. As suas ficam em pronuncias.local.txt, que não vai para o GitHub."),
    ("importar_saude_n8n.py", "Copia para o banco pessoal o histórico de saúde que já estava guardado dentro do n8n. Pode rodar de novo sem duplicar."),
    ("teste_voz.py", "Testa o dicionário de pronúncia."),
    ("teste_saude_dados.py", "Testa as análises de saúde com 200 dias de dados sintéticos, sem tocar no seu banco."),
    ("teste_painel_saude.py", "Testa o painel Heimdall Saúde: login, páginas, segurança e acessibilidade."),
    ("cloudflare/saude_caixa.js", "Worker da Cloudflare na frente do webhook de saúde do n8n (mesmo endereço do Health Auto Export): repassa o envio quando o Mac está no ar e, quando não está, guarda no KV por 7 dias e reenvia de 5 em 5 minutos."),
    ("cloudflare/teste_vigia.mjs", "Testa o vigia da Cloudflare com KV e rede de mentira, contando as gravações por dia (limite gratuito: 1.000): node cloudflare/teste_vigia.mjs."),
    ("cloudflare/teste_saude_caixa.mjs", "Testa a caixa de entrada da saúde com KV e rede de mentira: node cloudflare/teste_saude_caixa.mjs."),
    ("cloudflare_chave.py", "Grava no .env o token da Cloudflare (pedido sem aparecer na tela) para a reserva de resumos e a leitura de páginas com navegador do News; descobre o número da conta sozinho."),
    ("cloudflare/vigia.js", "Worker da Cloudflare (cron de 5 em 5 minutos) que confere de fora de casa se chat, flows, cloud, notes, news e health respondem e avisa por e-mail quando algo cai ou volta. O destino do aviso fica na variável ALERTA_PARA, só na Cloudflare."),
    ("noticias_fontes.json", "Fontes do Heimdall News (categoria, nome, endereço do feed, idioma, limite por atualização). Edite à vontade; é relido a cada atualização."),
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
        ("Subir uma vez só, guardando o log e avisando quando tudo estiver no ar (aceita os argumentos do start_heimdall.sh)", "./subir.sh"),
        ("Ver agora o que está no ar, sem subir nada", "./subir.sh --status"),
        ("Ver as últimas linhas do log da subida atual", "./subir.sh --log"),
        ("Ver o log de um serviço (mcp, mcp_public, mcp_dados, agente, cloud, notas, news, open_terminal, ingest)", "./subir.sh --log notas"),
        ("Listar os logs, todos na pasta logs/", "./subir.sh --logs"),
        ("Apagar os logs antigos que ficavam soltos na pasta do projeto", "./subir.sh --limpar"),
        ("Encerrar a subida em andamento e subir de novo", "./subir.sh --reiniciar"),
        ("Subir tudo em segundo plano, com Open WebUI e Open Terminal", "nohup bash start_heimdall.sh --webui --terminal > heimdall.log 2>&1 &"),
        ("Subir com n8n e agente do Mac", "nohup bash start_heimdall.sh --webui --terminal --n8n --agente > heimdall.log 2>&1 &"),
        ("Subir e indexar os documentos novos antes", "nohup bash start_heimdall.sh --ingest > heimdall.log 2>&1 &"),
        ("Atualizar as imagens Docker (com backup) ao subir", "nohup bash start_heimdall.sh --update > heimdall.log 2>&1 &"),
        ("Reiniciar só o agente do Mac", "pkill -f heimdall_agente.py   # depois suba o sistema como de costume"),
        ("Nova senha e novo código de 6 dígitos (valem para Cloud, Notas, News e Saúde)", "python3 heimdall_acesso.py --tudo"),
        ("Trocar só a senha, mantendo o código de 6 dígitos", "python3 heimdall_acesso.py --senha"),
        ("Gerar só um novo código de 6 dígitos", "python3 heimdall_acesso.py --codigo"),
        ("Ver se a entrada pelo Cloudflare Access (aprovação no Microsoft Authenticator) está ligada", "python3 heimdall_cfaccess.py --status"),
        ("Reiniciar só o painel do emulador de AWS", "pkill -f heimdall_cloud.py   # depois suba o sistema como de costume"),
        ("Ver o final do log", "tail -30 heimdall.log"),
    ]),
    ("Saúde: análises no terminal", [
        ("Importar o export.zip do app Saúde", "python3 heimdall_saude.py --importar ~/Downloads/export.zip"),
        ("Análise geral dos últimos 30 dias", "python3 heimdall_saude.py --relatorio"),
        ("O que já chegou de hoje", "python3 heimdall_saude.py --hoje"),
        ("Últimos 7 dias contra a média dos 90 anteriores", "python3 heimdall_saude.py --agora"),
        ("Anomalias: cada medida contra o seu normal de 30 dias, sequências, tendência e cruzamento de sinais", "python3 heimdall_anomalias.py   # ou AAAA-MM-DD"),
        ("Sono, atividade, recuperação e tendências", "python3 heimdall_saude.py --sono   # também --atividade, --recuperacao, --tendencias"),
        ("Treinos, ECG e frequência cardíaca", "python3 heimdall_saude.py --treinos   # também --ecg e --fc"),
        ("Relatório da semana (o n8n o envia aos domingos)", "python3 heimdall_saude.py --semanal"),
        ("Fila de resumos do News", "python3 heimdall_news.py --fila"),
        ("O que cada fonte do News entrega agora (itens, idade, quantos no banco)", "python3 heimdall_news.py --fontes   # com um nome ou categoria, só essas: --fontes Astronomia"),
        ("Testar a chave da Cloudflare (Workers AI e Browser Run)", "python3 cloudflare_chave.py --testar"),
        ("Testar as análises e o painel de saúde", "python3 teste_saude_dados.py && python3 teste_painel_saude.py"),
        ("Testar a voz", "python3 teste_voz.py"),
        ("Ligar a reserva de resumos e a leitura de páginas do News na Cloudflare (token pedido sem aparecer)", "python3 cloudflare_chave.py"),
        ("Testar a caixa de entrada da saúde (Worker da Cloudflare)", "node cloudflare/teste_saude_caixa.mjs"),
        ("Testar o vigia da Cloudflare (gravações no KV)", "node cloudflare/teste_vigia.mjs"),
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
        ("Heimdall News (deve responder ok)", "curl -s http://localhost:8012/saude"),
        ("Heimdall Saúde, o painel (deve responder ok)", "curl -s http://localhost:8013/saude"),
        ("Heimdall Jogos (deve responder ok)", "curl -s http://localhost:8014/saude"),
        ("Heimdall Finance (deve responder ok)", "curl -s http://localhost:8016/saude"),
        ("Relatório de saúde da semana, sem gravar", "python3 heimdall_saude.py --semanal"),
        ("Criar ou trocar a chave dos feeds RSS e ver os endereços", "python3 heimdall_news.py --token"),
        ("Ver de novo os endereços dos feeds RSS", "python3 heimdall_news.py --urls"),
        ("Copiar o endereço de um feed sem digitar (geral, opml ou uma categoria)", "python3 heimdall_news.py --copiar geral"),
        ("Gravar um arquivo OPML com todos os feeds (traz a chave secreta: importe e apague)", "python3 heimdall_news.py --opml"),
        ("Atualizar as notícias agora, uma vez", "python3 heimdall_news.py --uma-vez"),
        ("Reiniciar só o Heimdall Notas", "pkill -f heimdall_notas.py   # depois suba o sistema como de costume"),
        ("Teste do painel do emulador de AWS (sem rede)", "python3 teste_cloud.py"),
        ("Teste do Heimdall Notas (sem rede)", "python3 teste_notas.py"),
        ("Teste do Heimdall News (sem rede)", "python3 teste_news.py"),
        ("Teste do Heimdall Jogos (servidor, regras e interface)", "python3 teste_jogos.py"),
        ("Teste do Heimdall Finance (extratos, categorias, relatórios e servidor)", "python3 teste_finance.py"),
        ("Teste dos arquivos do Finance (PDF, inspeção anônima, pasta de entrada)", "python3 teste_finance_arquivos.py"),
        ("Teste do Heimdall Design (nenhuma ação é link)", "python3 teste_design.py"),
        ("Teste do diagnóstico de desempenho", "python3 teste_diagnostico.py"),
        ("Teste do leitor de boletos", "python3 teste_boletos.py"),
        ("Teste da leitura de boletos por e-mail", "python3 teste_finance_email.py"),
        ("Teste da conexão com os bancos (Pluggy simulado)", "python3 teste_finance_pluggy.py"),
        ("Teste da análise e do Perguntar do Finance", "python3 teste_finance_analise.py"),
        ("Teste das ferramentas do Finance no chat", "python3 teste_finance_chat.py"),
        ("Teste do xadrez, da batalha naval, das aventuras e dos jogos novos (Node)", "node teste_jogos_xadrez.js && node teste_jogos_naval.js && node teste_jogos_cincoletras.js && node teste_jogos_sudoku.js && node teste_historias.js && node teste_jogos_novos.js"),
        ("Teste do painel de saúde (sem rede)", "python3 teste_painel_saude.py"),
        ("Listar notas com título que parece cortado", "python3 heimdall_notas.py --titulos-suspeitos"),
        ("Teste dos trechos de livros do estudo (sem rede, precisa do Node)", "python3 teste_trechos.py"),
        ("Login e simulação do vigia de e-mail", "bash instalar_email_oficial.sh --testar"),
        ("Ver como cada e-mail recente foi classificado, inclusive os já vistos", "heimdall mail --diagnose"),
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


def ler_ajuda_comando():
    """Lê heimdall_ajuda.txt: lista de (nome, resumo, descrição, opções [(opção, texto)], exemplos)."""
    secoes, atual, modo = [], None, ""
    for linha in (AQUI / "heimdall_ajuda.txt").read_text(encoding="utf-8").splitlines():
        if linha.startswith("#") or not linha.strip() and atual is None:
            continue
        if linha.startswith("@ "):
            nome, _, resumo = linha[2:].partition(" | ")
            atual = {"nome": nome.strip(), "resumo": resumo.strip(), "desc": [], "opcoes": [], "exemplos": []}
            secoes.append(atual)
            modo = "desc"
        elif atual is None or not linha.strip():
            continue
        elif linha.strip() == "Opções:":
            modo = "opcoes"
        elif linha.strip() == "Exemplos:":
            modo = "exemplos"
        elif modo == "opcoes":
            partes = re.split(r"\s{2,}", linha.strip(), maxsplit=1)
            atual["opcoes"].append((partes[0], partes[1] if len(partes) > 1 else ""))
        elif modo == "exemplos":
            atual["exemplos"].append(linha.strip())
        else:
            atual["desc"].append(linha.strip())
    return secoes


def pagina_comando_heimdall():
    secoes = ler_ajuda_comando()
    indice = "".join(f'<li><a href="#c-{s["nome"]}"><code>heimdall {html.escape(s["nome"])}</code></a>: {html.escape(s["resumo"])}</li>' for s in secoes)
    corpo = []
    for s in secoes:
        ex = "".join(comando(e, f"Exemplo de heimdall {s['nome']}") for e in s["exemplos"])
        corpo.append(f'<section aria-labelledby="c-{s["nome"]}"><h2 id="c-{s["nome"]}">heimdall {html.escape(s["nome"])}</h2>'
                     f'<p>{html.escape(s["resumo"])}. {html.escape(" ".join(s["desc"]))}</p>'
                     + tabela(f"Opções de heimdall {s['nome']}", ["Opção", "O que faz"], [[o, t] for o, t in s["opcoes"]])
                     + (f"<h3>Exemplos</h3>{ex}" if ex else "") + "</section>")
    return f"""
<h1>Comando heimdall</h1>
<p>O comando <code>heimdall</code> reúne o ecossistema no terminal do Mac, no formato <code>heimdall SERVIÇO --opção</code>: o comando é o serviço e o que ele faz vem em opções. Toda opção tem a forma longa, com dois hífens, e a curta, de uma letra com um hífen (<code>--help</code> e <code>-h</code>). Cada comando mostra só as suas variações com <code>heimdall COMANDO --help</code>. Esta página também abre com <code>heimdall help --doc</code>.</p>
<section aria-labelledby="instalar"><h2 id="instalar">Instalar</h2>
<ol><li>Na pasta do projeto: <code>bash instalar_comando_heimdall.sh</code>. Ele faz cópia do ~/.zshrc, remove uma função heimdall antiga e liga o heimdall.zsh do projeto.</li>
<li>Depois: <code>source ~/.zshrc</code>. A partir daí o comando se atualiza com <code>heimdall update</code>.</li>
<li>Se o projeto não estiver em ~/heimdall-ai, defina HEIMDALL_DIR no ~/.zshrc antes da linha do source.</li></ol></section>
<section aria-labelledby="indice"><h2 id="indice">Todos os comandos</h2><ul>{indice}</ul></section>
{"".join(corpo)}
"""


def gerar_paginas(ferr, modelos, mcp, fluxos):
    out = {}
    n_pub = sum(1 for f in ferr if f["grupo"] == "público")
    n_mac = len(ferr) - n_pub
    out["index.html"] = pagina("index.html", "Heimdall-ai", "Heimdall-ai: assistente de Inteligência Artificial que roda no próprio computador, com ferramentas, documentos e automações. Documentação do projeto.",
                               corpo_inicio(len(modelos), len(ferr), n_pub, n_mac, len(mcp), len(fluxos)), home=True)
    import heimdall_design as _d
    _linhas_cor = "".join(
        f"<tr><th scope=\"row\">{H(k)}</th><td>{H(_d.PAPEL_DAS_CORES[k])}</td><td><code>{_d.CORES_CLARO[k]}</code></td><td><code>{_d.CORES_ESCURO[k]}</code></td></tr>" for k in _d.CORES_CLARO)
    _linhas_ctr = "".join(
        f"<tr><th scope=\"row\">{H(a)} sobre {H(b)}</th><td>{_d.contraste(_d.CORES_CLARO[a], _d.CORES_CLARO[b]):.1f} para 1</td><td>{_d.contraste(_d.CORES_ESCURO[a], _d.CORES_ESCURO[b]):.1f} para 1</td><td>{str(m).replace('.', ',')} para 1</td></tr>" for a, b, m in _d.PARES_DE_CONTRASTE)
    out["design.html"] = pagina("design.html", "Design", "Heimdall Design: cores, tipografia, componentes, acessibilidade e o passo a passo para criar páginas dos sites do Heimdall.", f"""
<h1>Heimdall Design</h1>
<p>O Heimdall Design é a única fonte de tudo que é aparência e comportamento de interface nos sites do Heimdall (Cloud, Notas, News, Saúde, Jogos e Finance): cores, tipografia, medidas, componentes, acessibilidade e tom do texto. Ele foi pensado para leitor de tela e teclado. <strong>Toda página nova e toda mudança numa página existente segue esta página.</strong> O código está em <code>heimdall_design.py</code> (cores, tipografia, CSS e botão) e <code>heimdall_paginacao.py</code> (paginação); o teste <code>teste_design.py</code> confere as regras que dá para conferir sozinho; e o arquivo <code>CLAUDE.md</code> do repositório obriga a seguir o padrão em cada atualização.</p>
<section aria-labelledby="regra"><h2 id="regra">1. Link lê, botão age</h2>
<ol><li><strong>Link</strong> leva a outro lugar para ler: o menu, "Voltar", o nome de um item em lista ou tabela (um bucket, uma nota, um jogo, uma categoria), "Leia mais" e os links dentro de um texto.</li>
<li><strong>Botão</strong> faz uma ação ou comando, mesmo quando o resultado é abrir outra página: baixar, atualizar, continuar, confirmar, alterar, classificar, importar, trocar a visão ou o período, paginar, "Ver todos..." e "Ver resultado".</li>
<li>Uma ação que só consulta é um formulário GET com um botão (<code>design.botao(rota, rótulo, parâmetros, nome_acessível, atual)</code>). Funciona sem JavaScript e o leitor de tela anuncia como botão. Ações que mudam dados são formulários POST com token csrf.</li>
<li>Botões repetidos numa lista levam o nome do item para o leitor de tela diferenciar, por exemplo "Alterar categoria de Mercado".</li>
<li>A opção escolhida num grupo de botões é marcada com aria-current.</li>
<li>Exceção única: quando o destino é um esquema de aplicativo (por exemplo, o app Atalhos do iPhone), o botão é um link com role="button", porque um formulário não abre esse tipo de endereço de forma confiável.</li></ol></section>
<section aria-labelledby="cores"><h2 id="cores">2. Cores</h2>
<p>As cores seguem o sistema: claro de dia, escuro à noite, sem o usuário precisar escolher. Use sempre as variáveis (<code>var(--texto)</code>), nunca um código de cor solto numa página. Cor nunca diz algo sozinha: erro e sucesso sempre vêm com texto ("Erro: ...", "Concluído").</p>
<table><caption>Variáveis de cor</caption><thead><tr><th scope="col">Variável</th><th scope="col">Para que serve</th><th scope="col">Claro</th><th scope="col">Escuro</th></tr></thead><tbody>{_linhas_cor}</tbody></table>
<table><caption>Contraste medido (padrão WCAG)</caption><thead><tr><th scope="col">Par</th><th scope="col">Claro</th><th scope="col">Escuro</th><th scope="col">Mínimo exigido</th></tr></thead><tbody>{_linhas_ctr}</tbody></table>
<p>Se mudar uma cor em <code>heimdall_design.py</code>, o teste recalcula estes números e falha se algum ficar abaixo do mínimo; esta tabela é gerada dos mesmos valores.</p></section>
<section aria-labelledby="tipo"><h2 id="tipo">3. Tipografia e medidas</h2>
<ul><li>Texto do corpo: fonte do sistema, {_d.TAMANHO_BASE_PX} px, entrelinha 1,5. Nunca menos que isso no texto corrido; textos pequenos só em notas e legendas, nunca abaixo de 0,85 em relação ao corpo.</li>
<li>Títulos e nome da marca: fonte com serifa ({H(_d.FONTE_TITULO.split(",")[0].strip('"'))} e alternativas).</li>
<li>Código e saídas de comando: fonte monoespaçada, com quebra de linha (nada de rolagem horizontal obrigatória).</li>
<li>Largura do conteúdo: até 60 rem, centralizado, com margem lateral de 1 rem; o texto quebra e nunca estoura a tela do iPhone.</li>
<li>Alvos de clique e toque: altura mínima de {_d.ALTURA_MINIMA_ALVO} (cerca de 44 px) em botões de paginação e botões de ação.</li>
<li>Foco do teclado: contorno de 3 px na cor de destaque, com recuo de 2 px, sempre visível. Nunca remover o contorno do foco.</li></ul></section>
<section aria-labelledby="comp"><h2 id="comp">4. Componentes</h2>
<ul><li><strong>Cabeçalho de marca:</strong> o símbolo (decorativo, escondido do leitor de tela) mais o nome do serviço, o menu e a faixa de seis cores. Peças em <code>heimdall_cloud.cabecalho</code> e <code>SIMBOLO</code>.</li>
<li><strong>Menu:</strong> lista de links numa região <code>nav</code> com nome ("Principal"); a página atual leva aria-current="page" e fica em negrito com sublinhado dourado.</li>
<li><strong>Tabela:</strong> sempre com <code>caption</code>, <code>th scope="col"</code> (e <code>scope="row"</code> quando a primeira célula nomeia a linha). Quando há muitas colunas, prefira lista com rótulos a tabela.</li>
<li><strong>Formulário:</strong> cada campo com <code>label</code> ligado por for/id, um campo por linha, autocomplete correto, botão de envio com verbo claro ("Entrar", "Importar extrato").</li>
<li><strong>Avisos:</strong> sucesso com <code>role="status"</code> e classe ok; erro com <code>role="alert"</code> e classe erro. A mensagem diz o que aconteceu e o que fazer.</li>
<li><strong>Paginação:</strong> botões num só formulário: Página anterior, números (a atual com aria-current), Próxima página e Última página, mais um resumo "Mostrando X a Y de Z". Quem usa: News, Notas e Finance.</li>
<li><strong>Bloco de código/saída:</strong> elemento <code>pre</code> com borda e fundo de superfície.</li></ul></section>
<section aria-labelledby="acess"><h2 id="acess">5. Acessibilidade: lista de conferência</h2>
<ol><li>Documento com <code>lang="pt-BR"</code>, <code>title</code> próprio e o nome do serviço, e meta viewport.</li>
<li>Primeiro elemento: link "Pular para o conteúdo"; o conteúdo principal em <code>main id="principal"</code>.</li>
<li>Um só <code>h1</code> por página e subtítulos em ordem, sem pular nível.</li>
<li>Todo link e botão tem nome que faz sentido fora de contexto; ícones e imagens decorativas ficam escondidos do leitor de tela (aria-hidden) e imagens informativas levam texto alternativo.</li>
<li>Tudo funciona só com o teclado, na ordem natural da página, sem armadilha de foco.</li>
<li>Mudanças de estado e resultados de ações aparecem em região com <code>role="status"</code> ou <code>role="alert"</code>.</li>
<li>Nada depende de JavaScript para o essencial; nada depende só de cor, som ou posição.</li>
<li>Animações respeitam <code>prefers-reduced-motion</code> (sem movimento, ou só quando o usuário pedir).</li>
<li>Áudio sempre com texto equivalente ao lado.</li>
<li>Teste final no VoiceOver: ler a página de cima a baixo, navegar por títulos, por links e por botões, e executar a ação principal.</li></ol></section>
<section aria-labelledby="tom"><h2 id="tom">6. Texto e tom</h2>
<ul><li>Português do Brasil, frases curtas, na segunda pessoa ("você"), sem jargão; termos técnicos entre aspas ou explicados na primeira vez.</li>
<li>Rótulos de botão começam com verbo no infinitivo ("Baixar tudo em CSV", "Alterar categoria de X").</li>
<li>Mensagem de erro: o que houve, por que, o que fazer agora. Nunca só um código.</li>
<li>Dados de saúde e finanças aparecem só nas páginas protegidas e nunca vão em avisos, notificações ou endereços (URL).</li></ul></section>
<section aria-labelledby="novo"><h2 id="novo">7. Ao criar ou mudar uma página</h2>
<ol><li>Importe <code>heimdall_design</code> e use o <code>CSS</code> dele (por <code>heimdall_cloud.CSS</code>). Não escreva cor, tamanho de fonte nem foco por conta própria: use as variáveis.</li>
<li>Use <code>design.botao</code> para qualquer ação de consulta e <code>heimdall_paginacao</code> para listas longas.</li>
<li>Monte a página pela estrutura padrão (<code>heimdall_cloud.pagina</code> e <code>cabecalho</code>).</li>
<li>Passe pela lista de acessibilidade da seção 5.</li>
<li>Rode <code>heimdall test --run design</code> e o teste do serviço mexido.</li>
<li>Se precisar de algo que o Heimdall Design ainda não tem (uma cor, um componente), acrescente aqui primeiro, no <code>heimdall_design.py</code>, e documente nesta página, em vez de criar um estilo só naquele site.</li></ol></section>
""")
    out["marca.html"] = pagina("marca.html", "Marca", "Logotipo, cores e tipografia do Heimdall-ai.", corpo_marca())

    # ---- arquitetura
    linhas = [(H(n), H(f), "<code>%s</code>" % p, H(c)) for n, f, p, c in SERVICOS]
    out["arquitetura.html"] = pagina("arquitetura.html", "Arquitetura", "Como as peças do Heimdall-ai se ligam: modelos, LiteLLM, MCP, Qdrant, n8n, agente do Mac e serviços.", f"""
<h1>Arquitetura</h1>
<section aria-labelledby="mapa"><h2 id="mapa">Mapa</h2>
{diagrama()}</section>
<section aria-labelledby="saudecam"><h2 id="saudecam">Dados de saúde e painéis</h2>
<ol><li>O iPhone e o Apple Watch guardam os dados no app Saúde. O app Health Auto Export manda os números ao n8n por um webhook, em automações agendadas (métricas gerais e frequência cardíaca de hora em hora, o resto uma vez por dia).</li>
<li>O n8n repassa ao agente do Mac, que grava no banco pessoal (SQLite, só nesta máquina).</li>
<li>Seis serviços web leem o banco e os arquivos do Mac: Cloud (8010), Notas (8011), News (8012), Saúde (8013) e Jogos (8014, que não lê nada, só entrega os jogos) e Finance (8016, com banco próprio só das suas finanças). Todos escutam só em 127.0.0.1, têm o mesmo login (senha e código de 6 dígitos) e chegam de fora pelo túnel Cloudflare.</li>
<li>Aos domingos, às 9h, o n8n pede o relatório da semana: ele vira nota com áudio e um aviso no Bark sem números.</li></ol></section>
<section aria-labelledby="cfarq"><h2 id="cfarq">Serviços da Cloudflare</h2>
<ol><li><strong>Túnel</strong> leva os endereços .heimdall-ai.tech até o Mac, sem abrir portas.</li>
<li><strong>Vigia</strong> (Worker com cron de 5 em 5 minutos) confere de fora de casa se os serviços respondem e avisa por e-mail quando algo cai ou volta. A Cloudflare também avisa quando o túnel cai.</li>
<li><strong>Caixa de entrada da saúde</strong> (Worker com KV) guarda os envios do Health Auto Export quando o Mac está fora e os reenvia depois.</li>
<li><strong>Email Routing</strong> encaminha o e-mail de suporte do domínio.</li>
<li><strong>Workers AI e Browser Rendering</strong> servem só ao News, como reserva de resumos e para ler páginas que dependem de JavaScript.</li></ol></section>
<section aria-labelledby="camadas"><h2 id="camadas">Visão geral</h2>
<p>O Heimdall-ai tem quatro camadas, da base para o topo.</p>
<ol>
<li><strong>Modelos.</strong> O Ollama executa os modelos de linguagem no Mac (chip Apple, 16 GB de memória).</li>
<li><strong>Acesso único.</strong> O LiteLLM Proxy (porta 9000) expõe todos os modelos em uma API compatível com a da OpenAI e repassa os servidores MCP. Clientes como o Open WebUI e aplicativos de iPhone falam só com ele.</li>
<li><strong>Ferramentas.</strong> Três servidores MCP em Python (portas 8000, 8001 e 8004, este só com o banco pessoal e só nesta máquina) e o servidor de documentação da AWS dão ao modelo ferramentas: busca na web, leitura de páginas, arquivos, memória, documentos pessoais.</li>
<li><strong>Automações.</strong> (Veja também o caminho dos dados de saúde, mais abaixo.) O n8n agenda fluxos que usam os modelos e as ferramentas. O agente do Mac (porta 8003) liga o n8n, que roda em Docker, aos aplicativos do macOS. O Bark entrega os avisos no iPhone.</li>
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
<li><strong>Falha externa não vira falso &quot;nada novo&quot;.</strong> Quando uma fonte de fora não responde, o fluxo tenta de novo a cada 2 horas, avisa assim que ela volta e, se ela passar de cerca de 24 horas fora do ar, manda um aviso de indisponibilidade com a data em que ela parou de responder, repetido aos 3 dias, aos 7 dias e a cada semana, sempre com o tempo atualizado. Nunca finge que não há novidade.</li>
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
    for grupo, titulo_g, desc in (("público", "Ferramentas públicas", "Seguras para convidados. Servidas na porta 8001."), ("mac", "Ferramentas do Mac (administrador)", "Acessam arquivos, métricas e memória do computador. Servidas na porta 8000; só para o dono."), ("dados", "Ferramentas só do chat de dados", "Só consultam, em modo somente leitura, o banco do Finance. Servidas na porta 8004, só em 127.0.0.1. HEIMDALL_FINANCE_CHAT=0 no .env desliga.")):
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
    out["comando-heimdall.html"] = pagina("comando-heimdall.html", "Comando heimdall", "O comando heimdall do terminal: todos os comandos e opções, com a forma longa e a curta de cada uma.", pagina_comando_heimdall())
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
<li>A sessão é única para Cloud, Notas, News e Saúde: entrando em um, os outros três já reconhecem você (o cookie vale para *.heimdall-ai.tech e é assinado com uma chave que sai da senha e da chave do código). Sair em um sai em todos; trocar a senha ou o código derruba todas as sessões. Em localhost a sessão fica só no endereço aberto.</li>
<li>Só atende os nomes de site permitidos, manda cabeçalhos de segurança e entrega os arquivos baixados sempre como anexo.</li>
<li>Executar funções Lambda dá ao emulador controle do Docker do computador. Por isso a entrada tem duas camadas, e a execução pode ser desligada com <code>HEIMDALL_LOCALSTACK_DOCKER=0</code>.</li></ul></section>
<section aria-labelledby="config"><h2 id="config">Configuração</h2>
<ul><li>Definir a senha e gerar o código de 6 dígitos (os mesmos valem para Cloud, Notas, News e Saúde): <code>python3 heimdall_acesso.py --tudo</code></li>
<li>Trocar só a senha: <code>python3 heimdall_acesso.py --senha</code></li>
<li>Gerar só um novo código: <code>python3 heimdall_acesso.py --codigo</code></li>
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
<li>Para tirar outras pastas, use <code>HEIMDALL_NOTAS_EXCLUIR="heimdall-digest,saude"</code> no <code>.env</code>. Para mostrar só algumas, <code>HEIMDALL_NOTAS_PASTAS="pasta-um,pasta-dois"</code>.</li>
<li>Como inclui notas pessoais, o endereço público exige a senha e o código de 6 dígitos em toda visita.</li></ul></section>
<section aria-labelledby="leitura"><h2 id="leitura">Leitura e navegação</h2>
<ul><li>As listas têm 10 notas por página, com paginação em botões (Página anterior, números com a atual marcada, Próxima página e Última página), na página inicial, nos temas e na busca.</li>
<li>Os títulos aparecem inteiros: textos longos quebram em várias linhas em vez de serem cortados.</li>
<li>O visual segue a marca do Heimdall (a mesma paleta do site e dos outros painéis, claro e escuro). Veja <a href="marca.html">Marca</a>.</li></ul></section>
<section aria-labelledby="seguranca"><h2 id="seguranca">Segurança</h2>
<ul><li>Escuta só em 127.0.0.1 e é somente de leitura: nada ali grava ou apaga arquivos.</li>
<li>Senha forte e código de 6 dígitos que não pode ser reaproveitado, limite de tentativas, sessão em cookie HttpOnly e SameSite=Strict.</li>
<li>Só atende os nomes de site permitidos. Os caminhos são conferidos contra fuga de pasta, todo texto é escapado e arquivos que não são PDF ou áudio só baixam, nunca executam.</li></ul></section>
<section aria-labelledby="config"><h2 id="config">Configuração</h2>
<ul><li>O Heimdall Notas sobe sozinho com o sistema quando há senha e código no <code>.env</code> (os mesmos do Cloud).</li>
<li>Conferir se está no ar: <code>curl -s http://localhost:8011/saude</code></li>
<li>Reiniciar só ela: <code>pkill -f heimdall_notas.py</code> e subir o sistema como de costume.</li>
<li>Testar sem rede: <code>python3 teste_notas.py</code></li>
<li>Se algo falhar: <code>tail -20 logs/notas_debug.log</code></li></ul></section>
""")
    out["news.html"] = pagina("news.html", "News", "Heimdall News: notícias das últimas 24 horas com resumo feito por IA e feeds RSS para o iPhone.", """
<h1>Heimdall News</h1>
<p>O Heimdall News reúne as notícias das fontes que você escolheu, atualiza de 30 em 30 minutos e mostra as das últimas 24 horas, com um resumo feito por um modelo local de IA. Também serve feeds RSS para você ler no iPhone em um app de feeds. Foi feito para leitor de tela: o título de cada notícia é um cabeçalho, o resumo vem sempre identificado como feito por IA e há link para pular ao conteúdo.</p>
<section aria-labelledby="abrir"><h2 id="abrir">Como abrir</h2>
<ol><li>No próprio computador: http://localhost:8012, depois de subir o sistema.</li>
<li>A entrada usa a mesma senha e o mesmo código de 6 dígitos do painel Cloud e do Heimdall Notas.</li>
<li>Para abrir de fora de casa, o site pode ganhar um endereço próprio pelo túnel Cloudflare, em news.heimdall-ai.tech. O endereço já existe no túnel; o site continua privado, pois exige a senha e o código de 6 dígitos.</li></ol></section>
<section aria-labelledby="fazer"><h2 id="fazer">O que mostra</h2>
<ul><li><strong>Últimas 24 horas</strong>, da mais nova para a mais antiga, 10 por página, com paginação em botões (Página anterior, números com a atual marcada, Próxima página e Última página).</li>
<li><strong>Cada notícia</strong>: título como cabeçalho, o resumo sempre marcado como "Resumo feito por IA", o link "Leia mais sobre ..." para a matéria original, que abre em uma nova aba (o leitor de tela avisa), e a fonte, a categoria e a hora.</li>
<li><strong>Títulos em inglês</strong> são traduzidos por IA e sinalizados. Matérias ainda sem resumo mostram o trecho original da fonte, e o resumo entra na atualização seguinte.</li>
<li><strong>Categorias</strong>: filtro por categoria, com a contagem de cada uma.</li>
<li><strong>Estado das fontes</strong>: mostra a última atualização, a fila de resumos e cada fonte (ok ou falhou desde quando, avisando se passar de 24 horas fora do ar).</li></ul></section>
<section aria-labelledby="banco"><h2 id="banco">Banco pessoal</h2>
<p>Tudo fica 30 dias na tabela noticias do banco pessoal (entra na cópia de segurança criptografada). O site mostra só as últimas 24 horas; o resto serve para consulta, pelo chat ou por SQL. Matérias com mais de 30 dias são apagadas sozinhas.</p></section>
<section aria-labelledby="rss"><h2 id="rss">Feeds RSS para o iPhone</h2>
<ol><li>Crie a chave: <code>python3 heimdall_news.py --token</code> e reinicie com <code>./subir.sh --reiniciar</code>. Isso mostra o endereço de um feed geral, de um feed por categoria e de um arquivo OPML que traz todos de uma vez.</li>
<li>Se o app pedir um arquivo em vez de um endereço: <code>python3 heimdall_news.py --opml</code> grava <code>heimdall-news.opml</code> na pasta atual (com permissão 600). Ele leva a chave secreta dentro; importe no app e apague o arquivo.</li>
<li>Para copiar um endereço sem digitar: <code>python3 heimdall_news.py --copiar geral</code> (ou <code>opml</code>, ou o nome de uma categoria). Depois cole no app de feeds; a área de transferência universal leva do Mac para o iPhone.</li>
<li>Apps de feeds não digitam o código de 6 dígitos, por isso o endereço leva uma chave secreta. Quem tem o endereço lê os feeds; para trocar, rode o comando da chave de novo (os endereços antigos param de valer).</li>
<li>O feed guarda 72 horas de notícias, cada item com o resumo de IA identificado. Matérias que ainda esperam o resumo só entram no feed depois de 2 horas, porque os apps de feeds não atualizam um item já baixado.</li></ol></section>
<section aria-labelledby="fontes"><h2 id="fontes">Fontes e modelo</h2>
<ul><li>As fontes ficam em <code>noticias_fontes.json</code> (as mesmas do Digest). Para trocar, é só editar: o serviço relê o arquivo a cada atualização. Campos: categoria, nome, url, idioma (pt ou en), limite de matérias novas por atualização, ler_materia, ativa, renderizar (ler a matéria com um navegador da Cloudflare) e lingua (idioma pedido ao site, por exemplo en: a AWS só entrega o feed atual em inglês).</li>
<li>O modelo é o <code>gemma3-4b</code> (Gemma 3 de 4 bilhões, 3 GB) pelo LiteLLM; baixe com <code>ollama pull gemma3:4b</code>. Foi escolhido em um teste com o Tucano e ele: o Tucano (2,4 bilhões) respondeu texto sem sentido e repetido, e o Gemma resumiu certo em cerca de 8 segundos. Para trocar por outro, use <code>HEIMDALL_NEWS_MODELO="nome-do-modelo"</code> no <code>.env</code>.</li>
<li>Para não competir com o chat, cada atualização faz no máximo 10 resumos (<code>HEIMDALL_NEWS_RESUMOS_POR_CICLO</code>), das notícias mais novas para as mais antigas, e as outras esperam na fila. <code>HEIMDALL_NEWS_PAUSA="1-6"</code> suspende os resumos de madrugada.</li>
<li>Se o modelo ou o LiteLLM estiver fora do ar, as matérias ficam na fila sem perder tentativa e o site avisa.</li></ul></section>
<section aria-labelledby="cf"><h2 id="cf">Cloudflare (opcional)</h2>
<p>Com uma chave da Cloudflare no <code>.env</code> (<code>python3 cloudflare_chave.py</code>, depois <code>./subir.sh --reiniciar</code>), o News ganha dois recursos. Só as matérias públicas passam por lá; dados pessoais e de saúde nunca saem do Mac.</p>
<ul><li><strong>Reserva de resumos:</strong> se o modelo local não responder, o resumo é feito pelo Workers AI (modelo mistral-small-3.1, de 24 bilhões). Limite de 60 por dia, ajustável em <code>HEIMDALL_NEWS_RESERVA_POR_DIA</code>; para desligar, <code>HEIMDALL_NEWS_RESERVA=0</code>.</li>
<li><strong>Leitura com navegador:</strong> em uma fonte de <code>noticias_fontes.json</code>, <code>"renderizar": true</code> faz a matéria ser lida por um navegador da Cloudflare, para sites que só mostram o texto com JavaScript. Limite de 20 por dia (<code>HEIMDALL_NEWS_RENDER_POR_DIA</code>); se falhar, volta ao jeito normal.</li>
<li>A página Estado das fontes mostra se a Cloudflare está ligada e quanto foi usado. O token precisa das permissões Workers AI (leitura) e Browser Rendering (edição).</li></ul></section>
<section aria-labelledby="seguranca"><h2 id="seguranca">Segurança</h2>
<ul><li>Escuta só em 127.0.0.1 e é somente de leitura. Senha forte e código de 6 dígitos que não pode ser reaproveitado, limite de tentativas, sessão em cookie HttpOnly e SameSite=Strict, só nomes de site permitidos e todo texto escapado.</li>
<li>Os feeds RSS só respondem à chave certa; tentativas erradas têm limite próprio e a chave nunca aparece no log.</li>
<li>Feeds e matérias só são baixados de endereços públicos (nunca da sua rede ou do próprio Mac), e o texto deles é tratado como dado: o modelo é instruído a ignorar qualquer ordem que apareça nele.</li>
<li>Resumos de IA podem conter erros; o site e os feeds avisam e levam à matéria original.</li></ul></section>
<section aria-labelledby="config"><h2 id="config">Configuração</h2>
<ul><li>Sobe sozinho com o sistema quando há senha e código no <code>.env</code> (os mesmos do Cloud).</li>
<li>Conferir se está no ar: <code>curl -s http://localhost:8012/saude</code></li>
<li>Atualizar agora, uma vez: <code>python3 heimdall_news.py --uma-vez</code></li>
<li>Testar sem rede: <code>python3 teste_news.py</code></li>
<li>Se algo falhar: <code>tail -20 logs/news_debug.log</code> ou <code>./subir.sh --log news</code></li></ul></section>
""")
    out["jogos.html"] = pagina("jogos.html", "Jogos", "Heimdall Jogos: jogos leves no navegador, feitos para leitor de tela, atrás do mesmo login dos outros painéis.", """
<h1>Heimdall Jogos</h1>
<p>Jogos leves para jogar no navegador, pensados para leitor de tela. Tudo é botão, campo de texto ou lista, e cada jogada é descrita em voz alta por uma região aria-live. O servidor não guarda nada: só entrega as páginas.</p>
<section aria-labelledby="abrir"><h2 id="abrir">Como abrir</h2>
<ol><li>No próprio computador: <code>heimdall games</code> abre o endereço público pelo Cloudflare Access; <code>heimdall games --local</code> (ou <code>-L</code>) abre http://localhost:8014 direto neste Mac, depois de subir o sistema.</li>
<li>De fora de casa: games.heimdall-ai.tech, pelo túnel Cloudflare (veja Colocar no ar, abaixo).</li>
<li>A entrada usa a mesma senha e o mesmo código de 6 dígitos do Cloud, do Notas, do News e do Saúde.</li></ol></section>
<section aria-labelledby="lista"><h2 id="lista">Os jogos</h2>
<p>A página inicial mostra as categorias em ordem alfabética, e cada categoria tem a sua página com os jogos: Ação (arqueiro, labirinto), Aventuras de texto (inclui a Travessia das Três Provas), Cartas (paciência e poker), Cassino (caça-níqueis, blackjack, roleta, bacará e poker caribenho), Números e lógica (senha, número secreto, sudoku, 2048), Palavras e letras (forca, cinco letras) e Tabuleiro e estratégia (xadrez, batalha naval, sonar, jogo da velha, campo minado, gramado).</p>
<h3>Ação</h3>
<ul><li><strong>Arqueiro de áudio:</strong> o primeiro jogo guiado só pelo som, em estéreo; use fones de ouvido. Pássaros cruzam o céu, da esquerda para a direita ou ao contrário, em nove pontos, e piam a cada passo no lado onde estão. Você move a mira com as setas (cada passo faz um ping no lado da mira) e atira com a barra de espaço; quando o ping e o pio soam no mesmo ponto, atire. Também há botões e comandos (<code>esquerda</code>, <code>direita</code>, <code>atirar</code>, <code>posição</code>, <code>pontos</code>, <code>ajuda</code>). São 10 alvos; pássaro acertado dá 3 pontos. Fácil: devagar, tolerância de um passo e duas flechas. Normal: ritmo médio e mira exata. Difícil: rápido, o pássaro às vezes muda de rumo e aparecem corvos de som grave que tiram 2 pontos se atingidos. O seletor Narração escolhe quanto o jogo fala: completa (descreve tudo), curta (frases enxutas) ou mínima (só o essencial: acertou, errou, 3 de 10 e o resultado final); o rótulo do campo do jogo também encurta conforme a narração; o padrão é completa no fácil, curta no normal e mínima no difícil, e dá para trocar. O botão Testar o som toca três sons em sequência (só esquerda, meio, só direita) para conferir o estéreo e, depois do último, lê a explicação. As setas e o espaço funcionam em qualquer lugar da página durante a partida; se o VoiceOver reter as setas, desligue a Navegação Rápida ou use os botões. Sem áudio no navegador, o jogo diz em texto onde o alvo está. <strong>Importante:</strong> a lógica foi testada, mas o som e o comportamento com o VoiceOver ainda não; vale experimentar com calma e dizer o que funcionou, antes de criarmos outros jogos de áudio.</li>
<li><strong>Labirinto:</strong> ache a saída de um labirinto sorteado. Você começa no canto de cima à esquerda, e a saída fica no canto de baixo à direita. Ande com norte, sul, leste e oeste (<code>leste 3</code> anda até três casas e <code>correr leste</code> segue o corredor até uma bifurcação). O jogo descreve as passagens: no fácil a cada passo, no normal só em cruzamentos e becos, e no difícil só quando você pedir com <code>olhar</code>. O <code>farol</code> diz a direção e a distância em linha reta até a saída (os corredores dão voltas), e a <code>dica</code> diz o primeiro passo do caminho mais curto; os dois são limitados nos níveis normal e difícil. No som, passos, uma batida grave na parede e o farol ecoando do lado da saída. As setas andam.</li></ul>
<h3>Aventuras de texto</h3>
<ul><li><strong>A Caverna dos Ecos:</strong> aventura guiada pelo som. Você caiu numa caverna escura; o comando <code>escutar</code> diz o que se ouve em cada lugar (pingos, brasas, vento, eco) e mostra o caminho até o poço de saída. O comando <code>onde</code> diz onde você está.</li>
<li><strong>Estação Orion:</strong> ficção científica. Sem energia e com o ar acabando, religue o reator, converse com o robô ZEL e envie o pedido de socorro.</li>
<li><strong>O Farol Apagado:</strong> a aventura curta de introdução, com comandos como olhar, ir norte, pegar, usar e inventário.</li>
<li><strong>A Mansão dos Relógios:</strong> mistério. O relojoeiro Heitor sumiu; é preciso achar chaves, uma engrenagem, um código de cofre e a passagem secreta atrás do grande relógio. Tem uma governanta para conversar.</li>
<li><strong>O Templo Submerso:</strong> exploração contra a maré. Acender uma tocha, refletir o sol com um espelho, descer um poço com corda e vencer o enigma do guardião para trazer o Amuleto do Sol.</li>
<li><strong>A Travessia das Três Provas:</strong> aventura de escolhas numeradas, com três problemas de lógica. Você lê a cena e responde com o número da escolha (também há botões). Prova 1, o rio: levar uma raposa, uma galinha e o milho para a outra margem, de uma coisa por vez, sem deixar a raposa com a galinha nem a galinha com o milho. Prova 2, as portas: três frases, só uma verdadeira; qual porta esconde a saída. Prova 3, os guardas: um sempre diz a verdade e o outro sempre mente; em quem confiar. No fácil o jogo avisa antes do erro e dá dicas à vontade; no normal são 3 vidas e 3 dicas; no difícil, 1 vida e nenhuma dica.</li></ul>
<h3>Cartas</h3>
<ul><li><strong>Paciência:</strong> a Klondike clássica, falada. Sete colunas (só a carta de cima de cada uma começa aberta), um monte e quatro bases, uma por naipe; o objetivo é levar as 52 cartas às bases, de Ás a Rei. As cartas se escrevem com o valor (A, 2 a 10, J, Q, K) e o naipe (C copas, O ouros, P paus, E espadas), como <code>7C</code> ou <code>QE</code>; também vale <code>7 de copas</code>. Comandos: <code>comprar</code>, <code>mover 7C para 4</code> (leva junto as cartas abertas em cima dela), <code>mover descarte para 3</code>, <code>subir 7C</code>, <code>subir descarte</code>, <code>subir coluna 2</code>, <code>mesa</code>, <code>coluna N</code>, <code>descarte</code>, <code>bases</code>, <code>dica</code> e <code>desfazer</code>. Fácil: compra 1 carta e dicas à vontade. Normal: compra 1 e 3 dicas. Difícil: compra 3 por vez, sem dicas e sem desfazer. Nem todo baralho tem solução, como na paciência de verdade.</li>
<li><strong>Poker Texas hold'em:</strong> mano a mano contra o computador, com fichas de mentira. Cada um começa com o mesmo número de fichas (fácil 300, normal e difícil 200). A cada mão você recebe duas cartas só suas e a mesa recebe cinco (flop de três, turn e river), com uma rodada de apostas em cada etapa; vale a melhor mão de cinco cartas entre as sete. O jogo lê as suas cartas, a mesa, o nome da sua mão e o que o computador faz. Comandos: <code>continuar</code> (dá as cartas), <code>pagar</code>, <code>passar</code>, <code>apostar 40</code> (o total que você terá apostado na rodada; também serve para aumentar), <code>tudo</code>, <code>desistir</code>, <code>mao</code>, <code>fichas</code>, <code>tabela</code> (ordem das mãos) e <code>dica</code> (a chance de ganhar contra uma mão qualquer e o preço de pagar). As cegas começam em 5 e 10 e dobram a cada 6 mãos; a partida acaba quando alguém fica sem fichas. O computador decide pela chance de ganhar, simulada, e pelo preço de pagar: no fácil paga muito e aposta pouco; no normal aposta quando a mão é boa; no difícil aposta com força e às vezes blefa. Normal: 5 dicas; difícil: sem dicas. Não há dinheiro de verdade.</li></ul>
<h3>Cassino</h3>
<ul><li><strong>Bacará:</strong> (punto banco) com créditos de mentira. Você escolhe o valor e o lado, <code>apostar 10 banca</code>, <code>jogador</code> ou <code>empate</code>; o jogo dá as cartas, aplica sozinho as regras da terceira carta e lê cada passo e o resultado. Ás vale 1, de 2 a 9 valem o número, 10 e figuras valem 0, e a mão é a soma, ficando só o último dígito; vence quem chega mais perto de 9. Jogador e banca pagam 1 para 1 (nesta versão, se a banca vencer com três cartas somando 7, a aposta só é devolvida); empate paga 8 para 1, e nele as apostas nos outros lados voltam. Também há <code>repetir</code>, <code>tabela</code>, <code>histórico</code>, <code>saldo</code> e <code>dica</code>. Fácil: 100 créditos e dicas à vontade; normal: 100 créditos e 3 dicas; difícil: 60 créditos e sem dicas. As apostas na banca e no jogador devolvem cerca de 99%; o empate, só 86%.</li>
<li><strong>Blackjack:</strong> vinte e um contra a banca, com créditos de mentira (nunca dinheiro de verdade). Você chega mais perto de 21 que a banca sem passar; Ás vale 11 ou 1, Valete, Dama e Rei valem 10, e o blackjack natural paga 3 para 2. A banca compra até 17 e para em qualquer 17. Aposta par, de 2 a 50 créditos, com <code>apostar 10</code> ou <code>repetir</code>; depois <code>pedir</code>, <code>parar</code>, <code>dobrar</code> (só nas duas primeiras cartas) e <code>dividir</code> (um par, uma vez). Também há <code>mao</code>, <code>banca</code>, <code>saldo</code>, <code>tabela</code> (pagamentos) e <code>dica</code>, que segue a estratégia básica. Fácil: 100 créditos e dicas à vontade; normal: 100 créditos e 5 dicas; difícil: 60 créditos e sem dicas. Com a estratégia básica a banca leva só cerca de 1% do que é apostado.</li>
<li><strong>Caça-níqueis:</strong> um painel de três dígitos de 0 a 9 e um botão Girar. Três dígitos iguais (trinca) pagam 25 vezes a aposta; uma sequência de três, subindo ou descendo, como 1 2 3, 3 2 1, 9 0 1 ou 1 0 9, paga 10 vezes; dois números iguais (um par, como 4 4 7) pagam 2 vezes, um prêmio pequeno que sai em cerca de 27% das rodadas; qualquer outra combinação perde a aposta. No total, cerca de três em cada dez rodadas pagam alguma coisa, e em média você recebe de volta uns 99% do que aposta. Você começa com 30 créditos de mentira (nunca dinheiro de verdade) e aposta 1, 2 ou 5 por rodada. Os números ficam no começo de jogos/cacaniqueis.js, se quiser mudar.</li>
<li><strong>Poker caribenho:</strong> (Caribbean Stud) contra a banca, com créditos de mentira. Você aposta o ante (<code>apostar 5</code>, de 1 a 25) e recebe cinco cartas abertas, lidas com o nome da sua mão; a banca recebe cinco e mostra só uma. Então você decide: <code>desistir</code> (perde o ante) ou <code>aumentar</code> (paga mais duas vezes o ante; é preciso ter três vezes o ante em créditos). A banca só joga com Ás e Rei ou melhor: se não jogar, o ante paga 1 para 1 e o aumento volta; se jogar, vence a melhor mão, o ante paga 1 para 1 e o aumento paga pela sua mão (par 1 para 1, dois pares 2, trinca 3, sequência 4, flush 5, full house 7, quadra 20, straight flush 50, royal flush 100). Empate devolve tudo. Também há <code>repetir</code>, <code>mao</code>, <code>banca</code>, <code>saldo</code>, <code>tabela</code> e <code>dica</code>, que simula as mãos possíveis da banca e diz se vale aumentar. Jogando assim, a casa leva cerca de 5% do ante. Não há prêmio acumulado. Fácil: 100 créditos e dicas à vontade; normal: 100 créditos e 3 dicas; difícil: 60 créditos e sem dicas.</li>
<li><strong>Roleta:</strong> com créditos de mentira. Você faz uma ou mais apostas e manda <code>girar</code>; o jogo lê onde a bola parou (número, cor, par ou ímpar, alto ou baixo) e o que cada aposta rendeu. Apostas: <code>apostar 5 vermelho</code>, <code>preto</code>, <code>par</code>, <code>ímpar</code>, <code>alto</code> (19 a 36), <code>baixo</code> (1 a 18), <code>dúzia 1</code> a <code>3</code>, <code>coluna 1</code> a <code>3</code> ou um número, como <code>apostar 2 no 17</code> ou <code>apostar 1 zero</code>. Número paga 35 para 1, dúzia e coluna 2 para 1, e as demais 1 para 1; o zero só paga a quem apostou nele. Também há <code>apostas</code>, <code>limpar</code>, <code>repetir</code>, <code>tabela</code>, <code>histórico</code> e <code>saldo</code>. Fácil: 100 créditos, roleta europeia (retorno de cerca de 97%); normal: 60 créditos; difícil: 60 créditos e roleta americana, com zero e duplo zero (retorno de cerca de 95%).</li></ul>
<h3>Números e lógica</h3>
<ul><li><strong>2048:</strong> botões ou setas do teclado; cada jogada diz o que se moveu e onde surgiu a peça nova, e há um botão para ler o tabuleiro.</li>
<li><strong>Número secreto:</strong> de 1 a 100, com as dicas maior e menor e o intervalo que sobrou.</li>
<li><strong>Senha (Mastermind):</strong> descubra 4 dígitos de 1 a 6 em até 10 tentativas; a dica diz quantos estão no lugar certo e quantos no lugar errado.</li>
<li><strong>Sudoku:</strong> por comandos, com linhas, colunas e quadrantes de 1 a 9 (os quadrantes vão da esquerda para a direita e de cima para baixo). Todo tabuleiro é gerado na hora e tem uma única solução. Você coloca com <code>colocar 5 em 3 4</code> (valor, linha, coluna). Para ouvir: linha 3, coluna 4, quadrante 5, casa 3 4 (diz quais números podem entrar), tabuleiro, faltam linha 3 (quais números faltam), vazias coluna 4 e resumo. Também há apagar 3 4, desfazer, verificar, dica e desistir. Números repetidos em linha, coluna ou quadrante são sempre recusados na hora. Níveis: fácil (40 números dados, o jogo avisa na hora se o número não é o certo e dá dicas à vontade), normal (32 dados, 3 dicas, e verificar aponta os erros) e difícil (26 dados, sem dicas e sem conferência).</li></ul>
<h3>Palavras e letras</h3>
<ul><li><strong>Cinco letras:</strong> palavra secreta de 5 letras, em português, no estilo Wordle. Você digita um palpite (acentos não importam; qualquer combinação de 5 letras vale, não há dicionário para conferir) e ouve, letra por letra, se ela está no lugar certo, em outro lugar ou não tem. Letras repetidas contam só as que existem na palavra. Comandos: tentativas, pistas (lugares conhecidos, letras em outro lugar e letras que não têm), letras (as não testadas), dica e desistir. Níveis: fácil (8 tentativas e dicas à vontade), normal (6 tentativas e uma dica) e difícil (6 tentativas, sem dicas, e cada palpite precisa manter as letras certas no lugar e usar as que já estão na palavra). A palavra vem de uma lista de mais de 400 palavras comuns, no começo de jogos/cincoletras.js.</li>
<li><strong>Forca:</strong> palavras em português por categoria, 7 erros; letra ou palavra inteira, sem se importar com acentos.</li></ul>
<h3>Tabuleiro e estratégia</h3>
<ul><li><strong>Batalha naval:</strong> contra o computador, em tabuleiro 10 por 10 (colunas de A a J, linhas de 1 a 10) com a frota clássica: porta-aviões (5 casas), encouraçado (4), cruzador (3), submarino (3) e destróier (2). As duas frotas são sorteadas, e você ouve onde estão os seus navios com o comando frota. Para atirar, diga a casa (B7 ou tiro b7); a resposta diz água, acertou ou afundou, e logo em seguida o computador atira e a resposta dele também é lida. Para consultar: tiros, inimigo, restantes, linha 3, coluna c, resumo, último e dica. Níveis: fácil (o computador atira ao acaso, em média uns 96 tiros), normal (caça em volta dos acertos, uns 53) e difícil (calcula onde os navios restantes mais cabem, uns 44).</li>
<li><strong>Campo minado:</strong> três tamanhos (fácil 6 por 6 com 5 minas, médio 9 por 9 com 10 e difícil 12 por 12 com 25). O campo é uma tabela de botões, cada um com o rótulo da linha, da coluna e do estado; também dá para jogar por comando: abrir 3 4, marcar 3 4, ler 3 4, linha 3, coluna 4, tudo e resumo. A primeira jogada nunca é uma mina.</li>
<li><strong>Gramado:</strong> campo minado por movimento. Você conduz um cortador de grama a partir do canto, andando com <code>norte</code>, <code>sul</code>, <code>leste</code> e <code>oeste</code> (<code>leste 3</code> anda até três casas e para sozinho quando uma casa tem aviso). Cada casa cortada diz quantos formigueiros há ao redor, inclusive nas diagonais. Pisar num formigueiro perde; no nível fácil o sensor apita e marca o formigueiro, e você não se mexe. Há <code>marcar DIREÇÃO</code> (bandeira), <code>sensor</code>, <code>onde</code>, <code>mapa</code> e <code>dica</code> (fácil: à vontade; normal: 3; difícil: nenhuma). O gramado é gerado de modo que todas as casas seguras sejam alcançáveis.</li>
<li><strong>Jogo da velha:</strong> contra o computador, nos níveis fácil e difícil (no difícil ele não perde).</li>
<li><strong>Sonar:</strong> caça-submarinos por turnos. Você anda com norte, sul, leste e oeste e manda pings; o eco diz a que distância e em que direção está o submarino mais próximo, só de modo aproximado, então é preciso pingar de lugares diferentes e cruzar as pistas. Quando estiver exatamente sobre o submarino, use <code>lançar</code> para soltar a carga de profundidade. Há três níveis (no difícil os submarinos se movem a cada ping), e pings e cargas são limitados. No som, o eco demora mais quanto mais longe está o alvo, vem do lado dele e é mais agudo ao norte. Atalhos: setas movem, P pinga, L lança.</li>
<li><strong>Xadrez:</strong> partida completa contra o computador, com roque, en passant, promoção, xeque, mate, afogamento, repetição, regra dos cinquenta lances e material insuficiente. Você escreve o lance (e4, Cf3, Cxe5, O-O, e8=D ou de casa para casa, como e2 e4); as letras das peças são R rei, D dama, T torre, B bispo e C cavalo. Três níveis (fácil, médio e difícil), jogar de brancas ou de pretas, dica e desfazer. Para consultar: tabuleiro, linha 4, coluna e, casa e4, peças, lances, histórico, material e último. O motor de regras foi conferido contra as contagens oficiais de lances (perft) de quatro posições de referência.</li></ul>
<h3>Sons de apoio</h3>
<p><strong>Sons de apoio:</strong> todos os jogos (exceto o Arqueiro, que tem o seu próprio som) tocam sons curtos como recurso de acessibilidade: ficha ao apostar, carta ao dar, a bola da roleta, os rolos do caça-níqueis, acerto e erro, o tiro e a água da batalha naval, a peça e a captura do xadrez, os passos no gramado e um som para ganhou, perdeu, empate ou estouro. A fala espera o som terminar. O botão Sons, no começo de cada jogo, liga e desliga tudo, e a escolha fica gravada no navegador.</p>
<p>As aventuras A Caverna dos Ecos, A Mansão dos Relógios, Estação Orion e O Templo Submerso rodam no mesmo motor (jogos/motor.js) e têm três níveis, que você escolhe antes de recomeçar: <strong>fácil</strong> (dicas à vontade e sem limite de passos), <strong>normal</strong> (3 dicas e limite de passos folgado) e <strong>difícil</strong> (sem dicas, limite apertado, enigmas a mais e perigos que acabam a partida, como andar no escuro). Comandos: olhar, ir norte/sul/leste/oeste/subir/descer, pegar, largar, examinar, usar ITEM, usar ITEM em ALGO, dar ITEM a ALGUÉM, falar com ALGUÉM, digitar CÓDIGO em ALGO, empurrar, puxar, girar, abrir, inventário, objetivo, mapa, dica, tempo, salvar, carregar e recomeçar. Salvar guarda a partida só neste navegador.</p>
<p>Cada jogo está em um arquivo da pasta jogos/, em JavaScript sem dependências. As histórias do motor são só dados (jogos/hist_*.js), então dá para criar a sua copiando uma delas; o teste teste_historias.js confere as referências e joga a solução em cada nível. Para abrir um jogo direto: <code>heimdall games --play xadrez</code>.</p></section>
<section aria-labelledby="terceiros"><h2 id="terceiros">Jogos de terceiros</h2>
<p>O Heimdall só lista jogos de terceiros que tenham versão em português ou permitam tradução. Por isso o Enigma (em inglês e espanhol) e o PlayAural (sem português) foram retirados, e hoje nenhum jogo de terceiros é instalado. Se aparecer um que atenda a esse critério, ele pode ser listado em HEIMDALL_JOGOS_EXTRAS, como descrito em Outros jogos, abaixo.</p></section>
<section aria-labelledby="no-ar"><h2 id="no-ar">Colocar no ar</h2>
<ol><li>Atualize e reinicie: <code>heimdall update --restart</code>. O servidor sobe sozinho quando há senha e código no .env.</li>
<li>Conferir: <code>curl -s http://localhost:8014/saude</code> deve responder ok.</li>
<li>Para acessar de fora, no painel da Cloudflare (Zero Trust, Redes, Túneis, o seu túnel, Public Hostnames), adicione o nome games.heimdall-ai.tech apontando para o serviço HTTP localhost:8014. O DNS é criado junto.</li>
<li>Se algo falhar: <code>heimdall logs --service games</code></li></ol></section>
<section aria-labelledby="mais"><h2 id="mais">Outros jogos</h2>
<p>O portal também lista jogos que você hospeda à parte. Para listar um jogo hospedado por você, e só se ele tiver versão em português ou permitir tradução, ponha-o em HEIMDALL_JOGOS_EXTRAS no .env, no formato Nome|endereço|descrição, separados por ponto e vírgula, e reinicie. Só endereços http e https são aceitos.</p></section>
<section aria-labelledby="seg"><h2 id="seg">Segurança</h2>
<ul><li>Escuta só em 127.0.0.1, com login, limite de tentativas, sessão em cookie HttpOnly e lista de sites permitidos.</li>
<li>A política de conteúdo só deixa rodar script do próprio site, sem script embutido nem conexões externas. Só os arquivos .js do catálogo são entregues.</li></ul></section>
""")

    out["finance.html"] = pagina("finance.html", "Finance", "Heimdall Finance: extratos do banco e do cartão importados, gastos por categoria, tendências e alertas, em páginas de texto para leitor de tela.", """
<h1>Heimdall Finance</h1>
<p>Suas finanças em páginas de texto e tabelas, feitas para leitor de tela. Você importa os extratos do banco e as faturas do cartão; o painel classifica os gastos por categoria, mostra o resumo do mês, compara com o mês anterior, lista os maiores gastos e avisa quando uma categoria dispara. Nada é lido de bancos por conta própria: os dados entram por arquivo (OFX, CSV ou PDF), pelo formulário ou soltos numa pasta vigiada.</p>
<section aria-labelledby="abrir"><h2 id="abrir">Como abrir</h2>
<ol><li>No próprio computador: <code>heimdall finance</code> (http://localhost:8016), depois de subir o sistema.</li>
<li>De fora de casa: finance.heimdall-ai.tech, pelo túnel Cloudflare.</li>
<li>A entrada usa a mesma senha e o mesmo código de 6 dígitos do Cloud, ou a aprovação no Microsoft Authenticator, se você ligar o Cloudflare Access.</li></ol></section>
<section aria-labelledby="usar"><h2 id="usar">Como usar</h2>
<ol><li><strong>Importar:</strong> na página Importar extrato, escolha o arquivo (OFX, CSV com colunas de data, descrição e valor, ou PDF de extrato ou de fatura). O banco (Nubank, Itaú, Mercado Pago) e o tipo (conta ou cartão) são identificados pelo conteúdo e pelo nome do arquivo; deixe o nome da conta em branco para usar o que foi identificado (por exemplo "Nubank cartão") ou digite o seu. Importar o mesmo arquivo de novo não duplica nada. Em CSV de cartão em que os gastos vêm positivos, marque a opção de inverter (o CSV de fatura do Nubank no formato date, category, title, amount já é reconhecido sozinho).</li>
<li><strong>PDF:</strong> o texto do PDF é lido linha a linha (data, descrição, valor) e o total que o próprio documento cita, por exemplo "Total da fatura", é conferido com a soma dos lançamentos. Só o PDF que confere é importado sozinho; se não conferir, a tela pede que você revise e marque a opção de importar mesmo assim. Na fatura, compra vira gasto e estorno ou pagamento vira crédito; no extrato de conta, a coluna de saldo é ignorada. Cada banco monta o PDF de um jeito, então o leitor é genérico: por isso a conferência existe.</li>
<li><strong>Pasta de entrada:</strong> <code>heimdall finance --folder</code> abre a pasta dados_financas/entrada. Solte lá extratos e faturas; a cada minuto o Heimdall importa o que conferir (vai para a subpasta importados) e separa o que deixar dúvida (subpasta revisar, com um arquivo .motivo.txt dizendo o porquê, e a lista aparece na página Importar). Arquivo duplicado não é importado e a cópia é apagada; o .motivo.txt some sozinho quando o arquivo sai de revisar, e importar um arquivo de revisar com <code>--force</code> o move para importados. <code>heimdall finance --inbox</code> importa na hora e <code>heimdall finance --retry</code> devolve tudo de revisar para a entrada e tenta de novo.</li>
<li><strong>Linha de comando:</strong> <code>heimdall finance --preview ARQUIVO</code> mostra o que seria importado, com a conferência do total, sem gravar; <code>heimdall finance --import ARQUIVO --account "Nubank cartão"</code> importa; <code>heimdall finance --inspect ARQUIVO</code> mostra só a estrutura do arquivo, com todas as letras trocadas por x e todos os números por 9, e copia para a área de transferência. <code>heimdall finance --explain ARQUIVO</code> faz o mesmo para PDF e ainda mostra, linha por linha, o que o leitor aceitou ou descartou e por quê. É o jeito de mostrar o layout do seu banco a quem for ajustar o leitor, sem que nenhum nome, valor ou número de conta saia do seu Mac.</li>
<li><strong>PDF e requisitos:</strong> a leitura de PDF usa o pypdf, que já está no requirements.txt, ou o pdftotext (<code>brew install poppler</code>). PDF escaneado, que é imagem, não tem texto para ler. PDF com senha precisa ser salvo sem senha antes.</li>
<li><strong>Classificar:</strong> as regras padrão cuidam do óbvio (mercado, transporte, assinaturas, saúde, salário...). O resumo avisa quantos lançamentos ficaram sem categoria, e a lista deles traz um campo de categoria em cada linha. Ao corrigir, a regra nasce sozinha e vale para os lançamentos parecidos e para as próximas importações. Suas regras vencem as padrão, e o que você categoriza à mão nunca é mudado por regra.</li>
<li><strong>Resumo do mês:</strong> receitas, despesas, saldo, gastos por categoria com a variação sobre o mês anterior e os dez maiores gastos.</li>
<li><strong>Tendências:</strong> receitas, despesas e saldo mês a mês, o gasto por categoria em cada mês e alertas quando uma categoria passa de 30% da média dos três meses anteriores.</li>
<li><strong>Fora das somas:</strong> pagamento de fatura, investimentos e transferências entre suas contas não contam como despesa nem receita, para não somar duas vezes.</li>
<li><strong>Duas visões:</strong> no Resumo e nas Tendências há um link para trocar entre a visão por compra (o gasto conta no dia da compra; o pagamento da fatura fica de fora para não contar duas vezes) e a visão por saída de caixa (conta o que saiu das suas contas, inclusive o pagamento da fatura; as compras do cartão ficam de fora).</li>
<li><strong>Faturas pagas sem fatura importada:</strong> o pagamento de fatura que nenhuma fatura importada explica entra nas despesas, para você não perder o gasto, e aparece listado no Resumo. Se a fatura for de outra pessoa, mude a categoria do pagamento para "Fatura de terceiros" e ele sai das somas. Um pagamento é considerado explicado quando há um crédito de pagamento do mesmo valor em algum cartão (até 10 dias de diferença) ou quando o valor é igual ao total de uma fatura importada.</li>
<li><strong>Orçamentos:</strong> a página Orçamentos guarda um limite mensal por categoria de gasto. Mostra gasto, quanto falta ou quanto passou e a situação (dentro do limite, perto do limite a partir de 80% e estourado), seguindo a visão escolhida. O Resumo avisa dos orçamentos estourados ou perto do limite.</li>
<li><strong>Contas recorrentes:</strong> a página Contas recorrentes acha, pelo histórico, o que se repete todo mês (aluguel, assinaturas, salário), com valor e dia típicos. Separa o que ainda vem neste mês, o que já apareceu, o que passou do dia habitual sem aparecer (atrasada, ou extrato ainda não importado) e o que parou há mais de dois meses. Nada é cadastrado: é deduzido dos lançamentos importados e só vale com pelo menos 3 meses, ou 2 meses seguidos com o mesmo valor.</li>
<li><strong>Pagamentos futuros:</strong> a página Pagamentos futuros mostra, mês a mês, o que ainda vai sair ou entrar: parcelas que faltam (lidas de textos como parcela 3 de 10 nas faturas e extratos, com valor e mês de cada uma), contas recorrentes detectadas, pagamentos que você cadastra à mão (aluguel por fora, com mês inicial e final) e boletos em aberto, com o total de saídas e entradas de cada mês. Cada item detectado tem o botão Ignorar, para o caso de erro, e a seção Ignorados permite voltar atrás.</li>
<li><strong>Análise de consultor:</strong> a página Análise já traz a análise da semana (7 dias contra os 7 anteriores) e a do mês (a última gerada ou, se ainda não houver, uma calculada na hora pelas regras), cada uma com um botão para gerar uma nova com os dados de agora. Cada análise tem: resumo, o que subiu, o que baixou, pontos de atenção (orçamentos, boletos vencidos, tarifas, parcelas, contas atrasadas), onde dá para reduzir (corte de 10% nas categorias flexíveis e revisão de assinaturas) e datas de pagamento (contas que vencem antes de o salário cair e dia de maior concentração). Sem dica de investimento. Todos os números são calculados pelo Heimdall; o modelo local só redige o texto, e se citar um valor que não está nos dados, a página mostra o texto calculado. Um botão salva a análise na pasta Heimdall Finanças do Notas (que pode sincronizar com o iCloud).</li>
<li><strong>Perguntar:</strong> no fim de todas as páginas do Finance há um campo de texto para perguntas como quanto gastei com mercado neste mês, e a resposta aparece logo abaixo, a mais recente primeiro (as dez últimas ficam guardadas no banco do Mac). A pergunta é respondida em segundo plano; o botão Atualizar respostas confere. O mês que você está olhando na página entra no contexto. O Heimdall junta os dados relevantes (resumos dos meses, orçamentos, previsões, boletos e lançamentos que casam com as palavras da pergunta) e o modelo local responde só com base neles; valores que não estão nos dados aparecem com aviso. O módulo heimdall_perguntar.py é reutilizável pelos outros sites do Heimdall.</li>
<li><strong>Boletos:</strong> a página Boletos lê a linha digitável (47 números do boleto bancário ou 48 de conta de consumo e tributo), confere os dígitos verificadores e guarda valor, vencimento e quem recebe como conta a pagar, com a situação em palavras (vencido, vence hoje, a vencer). PDF de boleto solto na pasta de entrada também é registrado, e o Resumo avisa dos boletos vencidos ou que vencem em até 7 dias. Marcar como pago é só uma anotação: o Heimdall nunca paga nada. Aceita também o Pix copia e cola (confere o dígito de controle). Você cadastra as pessoas cujos boletos paga (por exemplo, noiva e filha), só pelo nome e nunca CPF; o boleto ganha uma pessoa, escolhida na hora ou achada pelo nome no campo Pagador do PDF, e a página soma o que está em aberto de cada uma. O Heimdall não consulta boletos por CPF: isso é o DDA, que só existe dentro do banco; o caminho é copiar a linha digitável ou o Pix para cá. Pix dinâmico (código com endereço e sem valor) é completado a pedido seu, pela página ou pelo comando, consultando o servidor do banco do recebedor; o endereço só é aberto se for https público (nunca IP, porta, usuário ou rede local), sem seguir redirecionamentos, sem enviar nenhum dado seu e sem verificar a assinatura, o que vira aviso. Leitura de e-mail: o painel lê o Gmail a cada 15 minutos, em modo somente leitura e com a senha de aplicativo que o monitor de e-mails oficiais já usa, e registra os boletos e Pix do corpo e dos PDFs anexados. Links nunca são abertos, só vale código com dígitos corretos e boleto de remetente que não passa na autenticação do Gmail entra com aviso de possível golpe. Boleto já programado em débito automático ou cartão (dito no e-mail de remetente autêntico, ou deduzido do histórico e das contas recorrentes) ou já pago no histórico fica como Já programado, com o motivo, fora das contas a pagar; o botão É para pagar mesmo desfaz. Contas e cartões dos bancos podem ser baixados sozinhos pelo Open Finance, com o plano pessoal gratuito do Meu Pluggy: o comando heimdall finance --sync, a rotina de 6 em 6 horas do painel e a seção Conexão automática com os bancos na página Importar extrato leem contas e transações (somente leitura; os dados passam pelos servidores do Pluggy), importam sem duplicar e avisam quando a autorização de um banco está perto de vencer. As chaves ficam no .env e são gravadas com --save-pluggy, sem aparecer na tela. Aceita também o código de barras de 44 dígitos, convertido para a linha digitável. A leitura manual aceita --days N (até 365) e explica por que cada e-mail encontrado foi descartado. Pela linha de comando: heimdall finance --bill (com --person), --bills e --read-email.</li>
<li><strong>Filtros em Transações:</strong> por mês, categoria, conta (por exemplo Itaú cartão, Nubank cartão, Mercado Pago), produto (cartão, Pix, boleto, outras transferências, entre minhas contas, pagamento de fatura, outros) e texto da descrição. Cada opção mostra quantos lançamentos tem, e acima da lista aparecem as entradas, as saídas e o saldo do filtro, para conferir com o extrato.</li>
<li><strong>Exportar:</strong> a página Transações baixa tudo em CSV.</li></ol></section>
<section aria-labelledby="no-ar"><h2 id="no-ar">Colocar no ar</h2>
<ol><li>Atualize e reinicie: <code>heimdall update --restart</code>. O servidor sobe sozinho quando há senha e código no .env, e não precisa de instalador.</li>
<li>Conferir: <code>curl -s http://localhost:8016/saude</code> deve responder ok.</li>
<li>De fora de casa, o nome finance.heimdall-ai.tech já existe no túnel (aponta para localhost:8016, com o DNS), então responde assim que o serviço estiver no ar.</li>
<li>Se algo falhar: <code>heimdall logs --service finance</code></li></ol></section>
<section aria-labelledby="seg"><h2 id="seg">Privacidade e segurança</h2>
<ul><li>Os dados ficam em um banco SQLite na pasta dados_financas do projeto (permissão só do seu usuário), fora do git e fora dos backups da nuvem. Nada é enviado para a internet, para a Cloudflare ou para modelo de fora.</li>
<li>Escuta só em 127.0.0.1, com login, limite de tentativas, sessão em cookie HttpOnly, token CSRF em todo envio de formulário e lista de sites permitidos.</li>
<li>A política de conteúdo não permite nenhum script: as páginas são HTML puro.</li></ul></section>
""")

    out["saude.html"] = pagina("saude.html", "Saúde", "Heimdall Saúde: dados do iPhone e do Apple Watch no banco pessoal, análises no terminal, relatório semanal e painel web somente de leitura.", """
<h1>Heimdall Saúde</h1>
<p>O Heimdall Saúde guarda os dados do app Saúde do iPhone e do Apple Watch no banco pessoal do Mac, analisa e mostra em um painel de texto e tabelas feito para leitor de tela. Não é diagnóstico: são números e comparações com a sua própria média.</p>
<section aria-labelledby="abrir"><h2 id="abrir">Como abrir</h2>
<ol><li>No próprio computador: http://localhost:8013, depois de subir o sistema.</li>
<li>De fora de casa: health.heimdall-ai.tech, pelo túnel Cloudflare.</li>
<li>A entrada usa a mesma senha e o mesmo código de 6 dígitos do Cloud, do Notas e do News. O painel é somente de leitura.</li></ol></section>
<section aria-labelledby="dados"><h2 id="dados">De onde vêm os dados</h2>
<ol><li><strong>Importação do histórico:</strong> exporte o app Saúde (export.zip) e rode <code>python3 heimdall_saude.py --importar ~/Downloads/export.zip</code>. Pode repetir sem duplicar.</li>
<li><strong>Envio contínuo:</strong> o app Health Auto Export, com uma automação por tipo de dado, manda ao n8n. Métricas gerais e frequência cardíaca de hora em hora; treinos, ECG e o restante uma vez por dia.</li>
<li>O que o n8n já guardava antes pode ser copiado com <code>python3 importar_saude_n8n.py</code>.</li></ol>
<p>Tabelas do banco: saude_diaria (um dia por métrica), fc_hora (frequência cardíaca por hora), treinos, ecg e saude_eventos.</p></section>
<section aria-labelledby="caixa"><h2 id="caixa">Caixa de entrada na Cloudflare</h2>
<p>Um Worker da Cloudflare (heimdall-saude-caixa) fica na frente do webhook de saúde do n8n, no mesmo endereço que o Health Auto Export usa; nada muda no app. Com o Mac no ar, ele repassa o envio como veio. Com o Mac dormindo ou sem rede, guarda o envio por até 7 dias (até 200 envios) e responde ao app que recebeu. De 5 em 5 minutos reenvia ao n8n o que ficou e apaga o que foi aceito, então nenhuma leitura se perde. Para a caixa guardar só envios com o seu cabeçalho X-Heimdall-Saude, grave o segredo <code>TOKEN_SAUDE</code> no Worker.</p></section>
<section aria-labelledby="analises"><h2 id="analises">Análises</h2>
<p>Todas existem no terminal, no painel e como ferramenta do chat (<code>analise_saude</code>).</p>
<ul><li><strong>Hoje:</strong> o que já chegou do dia, ou o aviso de que nada chegou.</li>
<li><strong>Anomalias:</strong> cada medida (pulso, variabilidade, respiração, oxigênio, sono, distúrbios respiratórios, temperatura, caminhada, atividade e medidas novas) comparada com o seu normal dos 30 dias, com mediana e desvio robusto, variação mínima por medida e sentido bom ou ruim. Aponta dias seguidos fora do normal, mudança lenta na média de 7 dias, a frequência cardíaca hora a hora e o cruzamento de sinais (estresse ou infecção; sono e respiração). O aviso na triagem só sai quando algo muda (sinal novo ou que piorou), vem interpretado pelo modelo local, que avalia se o conjunto faz sentido ou se o dado parece errado e sugere ações, e o mesmo quadro só reaparece como lembrete depois de 5 dias. Valores impossíveis (por exemplo, um dia inteiro de energia em repouso de 384 kcal) são tratados como dado incorreto, não como alerta. Não é diagnóstico.</li>
<li><strong>Estado atual:</strong> os últimos 7 dias contra a média dos 90 anteriores.</li>
<li><strong>Tendências, sono, atividade e recuperação:</strong> funcionam sem treinos. Noites com menos de 3 horas de sono não entram nas médias, por serem sinal de que o relógio não foi usado.</li>
<li><strong>Treinos e cruzamentos:</strong> só aparecem quando há treinos. O Watch só grava um treino quando você o inicia; sem isso, o relatório avisa que não há treinos.</li>
<li><strong>Coração:</strong> frequência cardíaca, ECG e eventos.</li>
<li>Datas no padrão brasileiro e um único aviso de que não é orientação médica.</li></ul></section>
<section aria-labelledby="painel"><h2 id="painel">Páginas do painel</h2>
<ul><li><strong>Anomalias:</strong> o que saiu do seu normal, os padrões combinados e o que não foi comparado.</li>
<li><strong>Início, Hoje e Semana:</strong> o resumo, o que chegou hoje e o relatório da semana.</li>
<li><strong>Relatório:</strong> a análise geral, com seletor de período.</li>
<li><strong>Coração, Treinos e Diário:</strong> tabelas dos dados, dia a dia.</li>
<li><strong>Dados:</strong> o estado dos dados, que marca o que está sem chegar há mais de 2 dias. É o primeiro lugar a olhar se algo parecer parado.</li></ul></section>
<section aria-labelledby="semanal"><h2 id="semanal">Relatório da semana</h2>
<p>Todo domingo, às 9h, o fluxo "Saúde semanal" do n8n pede o relatório ao agente. O texto vira nota na pasta Saúde do app Notas, com áudio, e o iPhone recebe um aviso no Bark só em palavras, sem números, porque o aviso passa pelo servidor do Bark. Para ver agora: <code>python3 heimdall_saude.py --semanal</code>, ou rode o fluxo à mão no n8n (Gerar agora).</p></section>
<section aria-labelledby="seguranca"><h2 id="seguranca">Privacidade e segurança</h2>
<ul><li>Os dados ficam só no Mac, no banco pessoal, e entram na cópia de segurança criptografada.</li>
<li>O painel escuta só em 127.0.0.1, exige senha e código de 6 dígitos, tem limite de tentativas, cookie HttpOnly e SameSite=Strict, só aceita os nomes de site permitidos e escapa todo texto.</li>
<li>O recebimento do Health Auto Export exige o token do agente.</li></ul></section>
<section aria-labelledby="config"><h2 id="config">Configuração e problemas</h2>
<ul><li>Conferir se está no ar: <code>curl -s http://localhost:8013/saude</code></li>
<li>Testar sem tocar no banco: <code>python3 teste_saude_dados.py</code> e <code>python3 teste_painel_saude.py</code></li>
<li>Se faltar dado, abra a página Dados do painel e confira a automação correspondente no Health Auto Export.</li>
<li>Se algo falhar: <code>./subir.sh --log saude_painel</code></li></ul></section>
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
        "| `%s` | %s | `%s` | %s |" % (f["nome"], {"público": "público (8001)", "dados": "dados (8004)"}.get(f["grupo"], "Mac (8000)"), ", ".join(f["params"]), f["doc"].split(". ")[0].rstrip(".") + ".") for f in ferr)
    import modelos_chat as mc
    t["MODELOS_CHAT"] = mc.tabela_md()
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
    import modelos_chat as mc
    for e in mc.problemas():
        print("Modelos do chat:", e)
        desatualizado.append("modelos_chat.py")
    guia = AQUI / "modelos_open_webui.txt"
    if not guia.exists() or guia.read_text(encoding="utf-8") != mc.texto_guia():
        desatualizado.append("modelos_open_webui.txt")
        if not so_checar:
            guia.write_text(mc.texto_guia(), encoding="utf-8")
    (AQUI / "openwebui").mkdir(exist_ok=True)
    for nome, conteudo in mc.json_importar().items():
        arq_j = AQUI / "openwebui" / nome
        if not arq_j.exists() or arq_j.read_text(encoding="utf-8") != conteudo:
            desatualizado.append("openwebui/" + nome)
            if not so_checar:
                arq_j.write_text(conteudo, encoding="utf-8")
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
