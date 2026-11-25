#!/usr/bin/env python3
"""Ajuda e suporte do Heimdall, em um lugar só (hospedado no Heimdall Account): perguntas frequentes de todos os serviços, formulário de suporte
e as páginas de Termos de Uso e de Privacidade, que o rodapé de todos os serviços liga (heimdall_design.rodape).

Suporte: a mensagem recebe um protocolo, é gravada em db/suporte/mensagens.jsonl (permissão 600) e, se o envio de e-mail estiver configurado, segue para
o endereço de suporte pelo Cloudflare Email Sending (POST /email/sending/send). Sem a configuração, a mensagem fica só gravada e a página diz isso.
Variáveis no .env: HEIMDALL_SUPORTE_EMAIL=1 liga o envio; HEIMDALL_SUPORTE_DE (remetente no domínio já ativado no Email Sending) e
HEIMDALL_SUPORTE_PARA (destino; padrão suporte@heimdall-ai.tech); CLOUDFLARE_API_TOKEN e CLOUDFLARE_ACCOUNT_ID, como nos demais usos da Cloudflare.
HEIMDALL_POLITICA_APROVADA=1 tira o aviso de minuta das páginas de política, depois que o texto for revisado e aprovado pelo dono.
"""
import html
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
e = html.escape
EMAIL_SUPORTE = "suporte@heimdall-ai.tech"
PASTA = AQUI / "db" / "suporte"
LIMITE_POR_HORA = 5
MAX_MENSAGEM = 4000
MIN_MENSAGEM = 10
VERSAO_POLITICA = "2026-11-24"

ASSUNTOS = {"duvida": "Dúvida de uso", "problema": "Problema ou erro", "sugestao": "Sugestão", "dados": "Pedido sobre os meus dados (acesso, correção ou exclusão)", "outro": "Outro assunto"}

SERVICOS = {
    "geral": "Geral",
    "account": "Account", "controls": "Controls", "finance": "Finance", "saude": "Health", "notas": "Notes", "news": "News",
    "learn": "Learn", "jogos": "Games", "lab": "Lab", "chat": "Chat",
}

# Perguntas frequentes: uma lista de (pergunta, resposta) por serviço. Linguagem de produto: clara, objetiva e neutra.
FAQ = {
    "geral": [
        ("Como entro nos serviços do Heimdall?",
         "O acesso é pelo Cloudflare Access, com a sua conta Microsoft e a aprovação no Microsoft Authenticator. Depois de entrar, o menu Conta, no alto de qualquer página, leva a todos os serviços a que você tem acesso."),
        ("Como navego com leitor de tela ou só com o teclado?",
         "Todas as páginas têm o link Pular para o conteúdo no início, um único título principal e abas com setas, Home e End. Option+Shift+1 a 9 abre a aba pelo número. Nos serviços com o campo Perguntar, Option+Shift+P leva ao campo."),
        ("O que é o campo Perguntar e posso confiar nas respostas?",
         "O Perguntar responde com base apenas nos dados da tela em que você está. As respostas são geradas por inteligência artificial e podem conter erros: confira os números e as datas. As respostas não substituem orientação médica, jurídica, contábil ou financeira."),
        ("Quem pode ver os meus dados?",
         "Cada pessoa vê os próprios dados nos serviços que já separam os dados por pessoa. O dono do Heimdall administra o ambiente. O texto completo está na Política de Privacidade, ligada no rodapé de todas as páginas."),
        ("Como falo com o suporte?",
         "Use o formulário desta página, em Falar com o suporte. Você recebe um número de protocolo para acompanhar o atendimento. Não inclua senhas, chaves nem números de cartão na mensagem."),
    ],
    "account": [
        ("Para que serve o Account?",
         "É a porta de entrada: mostra os serviços liberados para você, com um passo a passo de cada um, e reúne as Integrações, onde você liga o Heimdall aos seus aplicativos."),
        ("Como ligo a Saúde do iPhone?",
         "Em Integrações, ative a Saúde, copie o token mostrado (ele aparece uma vez) e configure o app Health Auto Export no iPhone com o endereço e o token indicados na página."),
        ("Perdi o token da Saúde. O que faço?",
         "Em Integrações, use Trocar o token. O token anterior deixa de valer e um novo é mostrado uma única vez."),
    ],
    "controls": [
        ("O que posso fazer no Controls?",
         "Ligar, parar e reiniciar os serviços, acompanhar o consumo da nuvem, gerenciar usuários e editar as variáveis do ambiente em Ajustes. O Controls é exclusivo do dono."),
        ("Mudei uma variável em Ajustes e nada mudou. Por quê?",
         "Salvar grava o valor na hora, mas cada serviço só lê o valor novo ao reiniciar. Use o botão Recarregar Heimdall, no fim da página de Ajustes."),
        ("Como acompanho o gasto da nuvem?",
         "Na aba Nuvem e na aba Monitor, que mostram o consumo e os limites de gasto configurados."),
    ],
    "finance": [
        ("De onde vêm os dados do Finance?",
         "Das contas conectadas pelo Open Finance (por meio da Pluggy), de planilhas, de boletos e de arquivos que você envia. Os valores exibidos refletem o que essas fontes informaram."),
        ("O que o campo Perguntar do Finance enxerga?",
         "Somente os dados da tela em que você está, no período exibido. Ele não executa pagamentos nem altera dados."),
        ("Não vejo um lançamento recente. O que pode ter acontecido?",
         "A instituição financeira pode ainda não ter informado o lançamento, ou a conexão pode precisar de nova autorização. Verifique o estado da conexão nos Ajustes do Finance."),
    ],
    "saude": [
        ("De onde vêm os dados do Health?",
         "Do app Saúde do iPhone e do Apple Watch, enviados pelo Health Auto Export, e dos exames, receitas e encaminhamentos que você envia ao Heimdall."),
        ("O Health faz diagnóstico?",
         "Não. As análises, os alertas e o relatório semanal são informativos e comparam suas medidas com o seu padrão recente. Em caso de sintoma ou dúvida, procure um profissional de saúde."),
        ("Por que um exame ficou pendente?",
         "Todo documento enviado fica pendente até a sua conferência, para que nenhum dado seja registrado sem a sua confirmação."),
    ],
    "notas": [
        ("O que o Notes mostra?",
         "A triagem de pendências, os diários oficiais, os alertas de privacidade e o Second Brain. Os estudos ficam no Learn. O Notes é exclusivo do dono."),
        ("O que acontece quando salvo uma nota pelo campo da tela inicial?",
         "A inteligência artificial separa a nota em ideias, contatos, endereços, lembretes e eventos. Lembretes e eventos vão para os apps Lembretes e Calendário, com a opção Desfazer. Se a data estiver ausente ou ambígua, o item fica pendente até você informá-la."),
    ],
    "news": [
        ("De onde vêm as notícias?",
         "De fontes que o dono configura. O resumo de cada notícia é gerado por inteligência artificial e deve ser conferido na fonte original."),
        ("Como leio no iPhone?",
         "Copie o endereço do feed RSS da fonte e assine no seu leitor de RSS."),
    ],
    "learn": [
        ("Como começo a estudar?",
         "Crie uma pasta, escolha a categoria (aleatório ou sequencial) e o tipo, e importe PDF, Markdown, texto, Word, EPUB ou áudio. As subpastas herdam as configurações da pasta de cima."),
        ("Como funcionam os cards e as lições?",
         "Em pastas aleatórias, o Learn sorteia trechos para perguntas e respostas. Em pastas sequenciais, gera lições crescentes com exercícios. Em Ajustes você define quantos cards e lições recebe por dia e se quer notificações."),
        ("Meu áudio fica guardado?",
         "Por padrão, não: o áudio da sua resposta é apagado depois de transcrito. A opção de guardá-lo fica nos Ajustes do Learn."),
    ],
    "jogos": [
        ("Os jogos funcionam com leitor de tela?",
         "Sim. Os jogos usam áudio e narração e foram feitos para teclado e VoiceOver. Em cada jogo, as instruções e os atalhos ficam na tela inicial."),
        ("Posso ajustar volume e ritmo da narração?",
         "Sim, nas opções do jogo, quando disponíveis (por exemplo, volume dos efeitos e ritmo da narração)."),
    ],
    "lab": [
        ("O que é o Lab?",
         "Um ambiente de estudo de AWS que usa um emulador no Mac do dono: S3, Lambda, Glue, Athena e um console geral. Nada é criado na AWS real nem gera custo."),
        ("O emulador não responde. O que faço?",
         "O emulador sobe sob demanda. No terminal do Mac, execute heimdall lab --start e aguarde a resposta."),
    ],
    "chat": [
        ("Como troco de modelo ou crio um projeto?",
         "Use o seletor de modelos do chat. Cada modelo (General, Alerts, Notes, Health, Finance, Code, Learn) tem seu próprio conjunto de funções."),
        ("As conversas usam a nuvem?",
         "Depende da configuração do dono. Com a nuvem ligada, o chat usa modelos da Cloudflare; sem ela, usa os modelos locais do Mac."),
    ],
}

# ---------------------------------------------------------------------------------------------------------------------
# Termos de Uso e Política de privacidade (MINUTA): o texto descreve o que o Heimdall faz hoje; os campos [entre colchetes]
# dependem do dono do Heimdall e de revisão jurídica antes da publicação.
# ---------------------------------------------------------------------------------------------------------------------
TERMOS_DE_USO = [
    ("1. Objeto", ["Estes termos regem o uso dos serviços do Heimdall (Controls, Finance, Health, Notes, News, Learn, Games, Lab, Chat e Account), operados por [NOME DO RESPONSÁVEL E DOCUMENTO]. Ao entrar, você declara ter lido e concordado com estes termos e com a Política de Privacidade."]),
    ("2. Acesso", ["O acesso é pessoal e por convite, mediante autenticação pelo Cloudflare Access com conta Microsoft. Você é responsável por manter sua conta e seus dispositivos seguros e por não compartilhar o acesso com terceiros."]),
    ("3. Uso permitido", ["Você se compromete a usar os serviços de forma lícita e a não tentar acessar dados de outras pessoas, interferir no funcionamento dos serviços ou testar a segurança deles sem autorização por escrito."]),
    ("4. Recursos de inteligência artificial", ["Parte dos serviços usa inteligência artificial para resumir, classificar e responder perguntas. As respostas podem conter erros e devem ser conferidas. Elas são informativas e não substituem orientação médica, jurídica, contábil ou financeira."]),
    ("5. Saúde e finanças", ["As análises de saúde e de finanças são informativas. O Heimdall não realiza diagnóstico nem recomenda tratamento, investimento ou operação financeira, e nenhuma decisão deve ser tomada apenas com base nelas."]),
    ("6. Disponibilidade", ["Os serviços são oferecidos no estado em que se encontram, sem garantia de disponibilidade contínua. Podem ficar indisponíveis por manutenção, falha de energia, de rede ou de provedores externos, e alguns recursos podem operar em modo reduzido nessas situações."]),
    ("7. Seus conteúdos", ["Os dados e arquivos que você envia continuam sendo seus. Você nos autoriza a tratá-los apenas para prestar os serviços, conforme a Política de Privacidade."]),
    ("8. Suspensão e encerramento", ["O acesso pode ser suspenso ou encerrado em caso de descumprimento destes termos ou de risco à segurança. Você pode pedir o encerramento da sua conta e a exclusão dos seus dados pelo suporte."]),
    ("9. Alterações", ["Estes termos podem ser atualizados. A data da versão vigente aparece no início desta página, e mudanças relevantes serão comunicadas aos usuários."]),
    ("10. Lei aplicável e foro", ["Aplica-se a legislação brasileira. Fica eleito o foro de [COMARCA A DEFINIR] para resolver conflitos, ressalvados os direitos do consumidor, quando cabíveis."]),
]

POLITICA_PRIVACIDADE = [
    ("1. Quem é o controlador dos dados", ["[NOME DO CONTROLADOR], [CPF OU CNPJ], com contato em " + EMAIL_SUPORTE + ". Encarregado pelo tratamento de dados pessoais (art. 41 da LGPD): [A DEFINIR]."]),
    ("2. Quais dados tratamos", [
        "Conta: nome e e-mail fornecidos pela sua conta Microsoft no login pelo Cloudflare Access.",
        "Saúde: medidas do app Saúde do iPhone e do Apple Watch enviadas pelo Health Auto Export, e exames, receitas e encaminhamentos que você envia.",
        "Finanças: lançamentos, saldos e investimentos das contas conectadas pelo Open Finance (por meio da Pluggy), planilhas, boletos e arquivos que você envia.",
        "Notas, estudos e preferências: o que você escreve, importa ou configura nos serviços.",
        "Suporte: o conteúdo das mensagens que você nos envia e seus dados de contato.",
        "Registros técnicos: horários de acesso e eventos de funcionamento necessários para segurança e diagnóstico."]),
    ("3. Para que usamos os dados", ["Para prestar os serviços que você usa, mantê-los seguros, responder ao suporte e cumprir obrigações legais. Não vendemos dados pessoais e não os usamos para publicidade."]),
    ("4. Onde os dados ficam", [
        "Os serviços são hospedados em um computador do responsável. Cópias cifradas de bancos e arquivos podem ser guardadas na nuvem da Cloudflare (armazenamento R2, com criptografia), para continuidade e recuperação.",
        "Se a hospedagem passar para um servidor contratado, esta política será atualizada e os usuários serão avisados."]),
    ("5. Com quem compartilhamos", [
        "Cloudflare: entrada segura (Access e túnel), armazenamento de cópias, execução de modelos de inteligência artificial e gateway de IA.",
        "Microsoft: autenticação da sua conta.",
        "Pluggy: conexão com instituições financeiras pelo Open Finance, mediante a sua autorização.",
        "Apple: Calendário, Lembretes, Notas e iCloud, quando você usa essas integrações.",
        "Provedores de modelos de inteligência artificial acessados pelo gateway da Cloudflare, quando a nuvem está ligada. O gateway é configurado para não guardar o conteúdo das conversas.",
        "Serviço de notificações (Bark): os avisos de saúde levam apenas texto genérico, sem números de saúde.",
        "Notion: opcional, somente para ideias, contatos e endereços das notas, nunca saúde ou finanças.",
        "Compartilhamos dados também quando a lei ou uma ordem judicial exigir."]),
    ("6. Transferência internacional", ["Provedores como a Cloudflare podem tratar dados fora do Brasil. Nesses casos, o tratamento observa os requisitos do art. 33 da LGPD. [CONFERIR AS BASES E CLÁUSULAS ANTES DA PUBLICAÇÃO]"]),
    ("7. Inteligência artificial", ["Os recursos de inteligência artificial recebem apenas o contexto necessário para responder (por exemplo, os dados da tela em que você pergunta). As respostas podem conter erros e não substituem orientação profissional. Dependendo da configuração, os modelos rodam no computador do responsável ou na nuvem."]),
    ("8. Por quanto tempo guardamos", ["Guardamos os dados enquanto sua conta existir ou for necessário para os fins acima. A caixa de correio da Cloudflare, usada para receber dados do iPhone, apaga o que não foi retirado em 7 dias. Mensagens de suporte são guardadas pelo tempo necessário ao atendimento e à comprovação de contato. Dados podem ser eliminados a seu pedido, ressalvadas as hipóteses de guarda obrigatória por lei."]),
    ("9. Seus direitos", ["Conforme o art. 18 da LGPD, você pode pedir confirmação do tratamento, acesso, correção, anonimização, portabilidade, informação sobre compartilhamento, eliminação de dados tratados com consentimento e revogação do consentimento. Para exercer esses direitos, use o formulário de suporte, com o assunto Pedido sobre os meus dados. Você também pode reclamar à Autoridade Nacional de Proteção de Dados."]),
    ("10. Segurança", ["Adotamos medidas como autenticação em dois fatores pelo Access, criptografia das cópias na nuvem (AES-256-GCM), proteção contra requisições forjadas, acesso restrito por papel e separação dos dados por pessoa nos serviços em que ela já existe. Nenhum sistema é totalmente imune a falhas; em caso de incidente relevante, comunicaremos os afetados e a ANPD conforme a lei."]),
    ("11. Alterações desta política", ["Esta política pode ser atualizada. A data da versão vigente aparece no início da página, e mudanças relevantes serão comunicadas aos usuários."]),
]


def aviso_minuta() -> str:
    if os.environ.get("HEIMDALL_POLITICA_APROVADA") == "1" or _env_arquivo("HEIMDALL_POLITICA_APROVADA") == "1":
        return ""
    return ('<p role="note"><strong>Minuta em revisão.</strong> Este texto ainda não foi aprovado pelo responsável. Os trechos entre colchetes dependem de preenchimento e '
            "de revisão jurídica antes da publicação.</p>")


def _env_arquivo(chave: str) -> str:
    try:
        for ln in (AQUI / ".env").read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln.startswith("export "):
                ln = ln[7:]
            k, _, v = ln.partition("=")
            if k.strip() == chave:
                return v.strip().strip("'\"")
    except OSError:
        pass
    return ""


def _secoes(titulo_id: str, partes: list) -> str:
    saida = ""
    for i, (tit, paragrafos) in enumerate(partes):
        corpo = ""
        lista = [p for p in paragrafos]
        if len(lista) > 1:
            corpo = "<ul>" + "".join(f"<li>{e(p)}</li>" for p in lista) + "</ul>"
        else:
            corpo = f"<p>{e(lista[0])}</p>"
        saida += f'<section aria-labelledby="{titulo_id}-{i}"><h2 id="{titulo_id}-{i}">{e(tit)}</h2>{corpo}</section>'
    return saida


def texto_documentos() -> str:
    """Termos de Uso e Política de Privacidade em texto puro, para leitura e revisão (heimdall support --documents)."""
    aviso = ""
    if aviso_minuta():
        aviso = "MINUTA EM REVISÃO: este texto ainda não foi aprovado pelo responsável. Os trechos entre colchetes dependem de preenchimento e de revisão jurídica antes da publicação.\n\n"

    def bloco(titulo: str, partes: list) -> str:
        s = f"{titulo}\nVersão de {VERSAO_POLITICA}\n\n{aviso}"
        for tit, paragrafos in partes:
            s += tit + "\n"
            s += "".join(("- " if len(paragrafos) > 1 else "") + x + "\n" for x in paragrafos) + "\n"
        return s
    return bloco("TERMOS DE USO DO HEIMDALL", TERMOS_DE_USO) + "\n" + bloco("POLÍTICA DE PRIVACIDADE DO HEIMDALL", POLITICA_PRIVACIDADE)


def pagina_termos_de_uso() -> tuple:
    corpo = (f"<h1>Termos de Uso</h1><p>Versão de {e(VERSAO_POLITICA)}.</p>{aviso_minuta()}" + _secoes("pu", TERMOS_DE_USO)
             + f'<p><a href="/privacidade">Política de Privacidade</a> · <a href="/ajuda">Ajuda e suporte</a></p>')
    return "Termos de Uso - Heimdall", corpo


def pagina_privacidade() -> tuple:
    corpo = (f"<h1>Política de Privacidade</h1><p>Versão de {e(VERSAO_POLITICA)}.</p>{aviso_minuta()}" + _secoes("pp", POLITICA_PRIVACIDADE)
             + f'<p><a href="/termos-de-uso">Termos de Uso</a> · <a href="/ajuda">Ajuda e suporte</a></p>')
    return "Política de Privacidade - Heimdall", corpo


# ---------------------------------------------------------------------------------------------------------------------
# Ajuda e suporte
# ---------------------------------------------------------------------------------------------------------------------
def servico_valido(chave: str) -> str:
    return chave if chave in SERVICOS and chave != "geral" else ""


def _faq_html(servico: str) -> str:
    ordem = (["geral"] if not servico else [servico, "geral"]) + [k for k in SERVICOS if k not in ("geral", servico)]
    saida = ""
    for k in ordem:
        itens = FAQ.get(k) or []
        if not itens:
            continue
        tid = f"faq-{k}"
        blocos = "".join(f'<h3>{e(q)}</h3><p>{e(a)}</p>' for q, a in itens)
        saida += f'<section aria-labelledby="{tid}"><h2 id="{tid}">Perguntas frequentes: {e(SERVICOS[k])}</h2>{blocos}</section>'
    return saida


def formulario_suporte(csrf: str, servico: str = "", valores: dict = None) -> str:
    v = valores or {}
    ops_a = "".join(f'<option value="{k}"{" selected" if v.get("assunto") == k else ""}>{e(t)}</option>' for k, t in ASSUNTOS.items())
    ops_s = "".join(f'<option value="{k}"{" selected" if (v.get("servico") or servico or "geral") == k else ""}>{e(t)}</option>' for k, t in SERVICOS.items())
    return ('<section aria-labelledby="suporte-t"><h2 id="suporte-t">Falar com o suporte</h2>'
            f'<p>Descreva sua dúvida ou problema. Você recebe um número de protocolo ao enviar. Não inclua senhas, chaves nem números de cartão. O suporte responde para o e-mail da sua conta.</p>'
            f'<form method="post" action="/suporte"><input type="hidden" name="csrf" value="{e(csrf)}">'
            f'<p><label for="s-servico">Serviço</label><br><select id="s-servico" name="servico">{ops_s}</select></p>'
            f'<p><label for="s-assunto">Assunto</label><br><select id="s-assunto" name="assunto">{ops_a}</select></p>'
            f'<p><label for="s-msg">Mensagem (de {MIN_MENSAGEM} a {MAX_MENSAGEM} caracteres)</label><br>'
            f'<textarea id="s-msg" name="mensagem" rows="8" cols="60" maxlength="{MAX_MENSAGEM}" required>{e(v.get("mensagem", ""))}</textarea></p>'
            '<p><button type="submit">Enviar mensagem</button></p></form></section>')


def pagina_ajuda(csrf: str, servico: str = "", aviso: str = "", erro: str = "", valores: dict = None, dono: bool = False) -> tuple:
    servico = servico_valido(servico)
    topo = f'<p role="alert">{e(erro)}</p>' if erro else (f'<p role="status">{e(aviso)}</p>' if aviso else "")
    nome = f" do {SERVICOS[servico]}" if servico else ""
    corpo = (f"<h1>Ajuda e suporte{e(nome)}</h1>{topo}"
             '<p>Encontre abaixo as perguntas frequentes e, no fim da página, o formulário para falar com o suporte. '
             f'Documentos: <a href="/termos-de-uso">Termos de Uso</a> e <a href="/privacidade">Política de Privacidade</a>.</p>'
             + ('<p><a href="/suporte/mensagens">Mensagens de suporte recebidas (somente dono)</a></p>' if dono else "")
             + _faq_html(servico) + formulario_suporte(csrf, servico, valores))
    return "Ajuda e suporte - Heimdall", corpo


# ---- Suporte: gravar e enviar ----
class ErroSuporte(Exception):
    """Erro de validação com mensagem própria para o usuário."""


def _limpar(texto: str) -> str:
    texto = (texto or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[^\S\n]+", " ", re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", texto)).strip()


def _ler_registros() -> list:
    try:
        return [json.loads(ln) for ln in (PASTA / "mensagens.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    except (OSError, ValueError):
        return []


def novo_protocolo(agora: datetime = None) -> str:
    return "HMD-" + (agora or datetime.now()).strftime("%Y%m%d") + "-" + secrets.token_hex(3).upper()


def validar(assunto: str, servico: str, mensagem: str) -> tuple:
    if assunto not in ASSUNTOS:
        raise ErroSuporte("Escolha um assunto da lista.")
    if servico not in SERVICOS:
        raise ErroSuporte("Escolha um serviço da lista.")
    m = _limpar(mensagem)
    if len(m) < MIN_MENSAGEM:
        raise ErroSuporte(f"A mensagem precisa ter pelo menos {MIN_MENSAGEM} caracteres.")
    if len(m) > MAX_MENSAGEM:
        raise ErroSuporte(f"A mensagem pode ter no máximo {MAX_MENSAGEM} caracteres.")
    return assunto, servico, m


def registrar(p: dict, assunto: str, servico: str, mensagem: str, agora: datetime = None) -> dict:
    """Valida, aplica o limite por hora, grava e devolve o registro (com o protocolo)."""
    assunto, servico, m = validar(assunto, servico, mensagem)
    agora = agora or datetime.now()
    email = p.get("email") or "local"
    recentes = [r for r in _ler_registros() if r.get("email") == email and agora.timestamp() - r.get("ts", 0) < 3600]
    if len(recentes) >= LIMITE_POR_HORA:
        raise ErroSuporte(f"Você já enviou {LIMITE_POR_HORA} mensagens na última hora. Aguarde um pouco para enviar outra.")
    reg = {"protocolo": novo_protocolo(agora), "data": agora.isoformat(timespec="seconds"), "ts": agora.timestamp(), "email": email, "nome": p.get("nome", ""),
           "assunto": assunto, "servico": servico, "mensagem": m, "estado": "recebida"}
    PASTA.mkdir(parents=True, exist_ok=True)
    arq = PASTA / "mensagens.jsonl"
    with open(arq, "a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    try:
        os.chmod(arq, 0o600)
    except OSError:
        pass
    return reg


def _atualizar_estado(protocolo: str, estado: str, motivo: str = "") -> None:
    arq = PASTA / "mensagens.jsonl"
    regs = _ler_registros()
    for r in regs:
        if r.get("protocolo") == protocolo:
            r["estado"] = estado
            if motivo:
                r["motivo"] = motivo
            else:
                r.pop("motivo", None)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in regs), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(arq)


def _conf() -> dict:
    ch = ("HEIMDALL_SUPORTE_EMAIL", "HEIMDALL_SUPORTE_DE", "HEIMDALL_SUPORTE_PARA", "HEIMDALL_SUPORTE_TOKEN", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")
    c = {k: (os.environ.get(k) or _env_arquivo(k)) for k in ch}
    c["TOKEN_ENVIO"] = c.get("HEIMDALL_SUPORTE_TOKEN") or c.get("CLOUDFLARE_API_TOKEN") or ""
    return c


def envio_configurado(c: dict = None) -> bool:
    c = c if c is not None else _conf()
    return c.get("HEIMDALL_SUPORTE_EMAIL") == "1" and bool(c.get("HEIMDALL_SUPORTE_DE")) and bool(c.get("TOKEN_ENVIO")) and bool(c.get("CLOUDFLARE_ACCOUNT_ID"))


def _post(req, timeout):
    return urllib.request.urlopen(req, timeout=timeout)


def _enviar_cf(c: dict, para: str, assunto: str, texto: str, responder_para: str = "") -> tuple:
    """Envia um e-mail de texto pelo Cloudflare Email Sending. Devolve (ok, motivo). Se a Cloudflare recusar o reply_to, tenta de novo sem ele."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{c['CLOUDFLARE_ACCOUNT_ID']}/email/sending/send"
    cab = {"Authorization": f"Bearer {c['TOKEN_ENVIO']}", "Content-Type": "application/json"}
    corpo = {"to": para, "from": c["HEIMDALL_SUPORTE_DE"], "subject": assunto, "text": texto}
    tentativas = [dict(corpo, reply_to=responder_para)] if responder_para else []
    tentativas.append(corpo)
    motivo = ""
    for i, dados in enumerate(tentativas):
        req = urllib.request.Request(url, data=json.dumps(dados).encode("utf-8"), method="POST", headers=cab)
        try:
            with _post(req, 20) as r:
                if bool(json.loads(r.read().decode("utf-8", "replace")).get("success")):
                    return True, ""
                motivo = "A Cloudflare não confirmou o envio."
        except urllib.error.HTTPError as err:
            motivo = f"HTTP {err.code}: {err.read().decode('utf-8', 'replace')[:300]}"
            if err.code == 400 and i == 0 and responder_para:
                continue  # reply_to recusado: tenta sem
            return False, motivo
        except Exception as err:  # noqa: BLE001
            return False, f"{type(err).__name__}: {str(err)[:200]}"
    return False, motivo


def _email_valido(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", s or ""))


def enviar_email(reg: dict) -> bool:
    """Envia ao suporte pelo Cloudflare Email Sending, com o e-mail de quem escreveu como endereço de resposta. Devolve True se a Cloudflare aceitou; qualquer falha deixa a mensagem gravada e devolve False."""
    c = _conf()
    if not envio_configurado(c):
        faltam = [k for k in ("HEIMDALL_SUPORTE_EMAIL", "HEIMDALL_SUPORTE_DE", "TOKEN_ENVIO", "CLOUDFLARE_ACCOUNT_ID") if not c.get(k) or (k == "HEIMDALL_SUPORTE_EMAIL" and c.get(k) != "1")]
        reg["motivo"] = "Envio desligado ou incompleto: " + ", ".join(faltam)
        _atualizar_estado(reg["protocolo"], "gravada_sem_envio", reg["motivo"])
        return False
    assunto = f"[{reg['protocolo']}] {ASSUNTOS.get(reg['assunto'], reg['assunto'])} - {SERVICOS.get(reg['servico'], reg['servico'])}"
    texto = (f"Protocolo: {reg['protocolo']}\nData: {reg['data']}\nDe: {reg.get('nome') or '-'} <{reg['email']}>\nServiço: {SERVICOS.get(reg['servico'], reg['servico'])}\n"
             f"Assunto: {ASSUNTOS.get(reg['assunto'], reg['assunto'])}\n\n{reg['mensagem']}\n")
    ok, motivo = _enviar_cf(c, c.get("HEIMDALL_SUPORTE_PARA") or EMAIL_SUPORTE, assunto, texto, reg["email"] if _email_valido(reg["email"]) else "")
    reg["motivo"] = motivo
    _atualizar_estado(reg["protocolo"], "enviada" if ok else "gravada_sem_envio", motivo)
    return ok


def responder(protocolo: str, texto: str, para: str = "") -> tuple:
    """Responde de suporte@ (remetente HEIMDALL_SUPORTE_DE) a quem escreveu. Devolve (ok, mensagem). Com protocolo, usa o e-mail gravado; sem protocolo, exige 'para'."""
    texto = (texto or "").strip()
    if len(texto) < 2 or len(texto) > MAX_MENSAGEM:
        return False, f"A resposta precisa ter de 2 a {MAX_MENSAGEM} caracteres."
    reg = next((r for r in _ler_registros() if r.get("protocolo") == protocolo), None) if protocolo else None
    destino = para or (reg or {}).get("email", "")
    if not _email_valido(destino):
        return False, "Não há um e-mail válido para responder." + (" Informe o endereço." if not reg else " Quem escreveu entrou pela porta local, sem e-mail gravado; informe o endereço.")
    c = _conf()
    if not envio_configurado(c):
        return False, "O envio de e-mail não está configurado (HEIMDALL_SUPORTE_EMAIL, HEIMDALL_SUPORTE_DE e token da Cloudflare)."
    assunto = f"Re: [{protocolo}] {ASSUNTOS.get((reg or {}).get('assunto'), 'Suporte')}" if protocolo else "Resposta do suporte Heimdall"
    rodape = f"\n\n--\nSuporte Heimdall\n{EMAIL_SUPORTE}" + (f"\nProtocolo: {protocolo}" if protocolo else "")
    ok, motivo = _enviar_cf(c, destino, assunto, texto + rodape, EMAIL_SUPORTE)
    if not ok:
        return False, "Não foi possível enviar: " + motivo
    if reg:
        regs = _ler_registros()
        for r in regs:
            if r.get("protocolo") == protocolo:
                r["estado"] = "respondida"
                r.setdefault("respostas", []).append({"data": datetime.now().isoformat(timespec="seconds"), "texto": texto})
        arq = PASTA / "mensagens.jsonl"
        tmp = arq.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in regs), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(arq)
    return True, f"Resposta enviada para {destino}."


def pagina_mensagens(csrf: str, aviso: str = "", erro: str = "") -> tuple:
    """Lista as mensagens recebidas, com formulário de resposta (somente dono)."""
    topo = f'<p role="alert">{e(erro)}</p>' if erro else (f'<p role="status">{e(aviso)}</p>' if aviso else "")
    regs = list(reversed(_ler_registros()))[:50]
    blocos = []
    for r in regs:
        resp = "".join(f'<p>Resposta de {e(x["data"])}: {e(x["texto"])}</p>' for x in r.get("respostas", []))
        mot = f'<p>Motivo da falha de envio: {e(r["motivo"])}</p>' if r.get("motivo") else ""
        pode = _email_valido(r.get("email", ""))
        form = (f'<form method="post" action="/suporte/responder"><input type="hidden" name="csrf" value="{e(csrf)}"><input type="hidden" name="protocolo" value="{e(r["protocolo"])}">'
                f'<p><label for="r-{e(r["protocolo"])}">Resposta para {e(r["email"])}</label><br>'
                f'<textarea id="r-{e(r["protocolo"])}" name="texto" rows="5" cols="60" maxlength="{MAX_MENSAGEM}" required></textarea></p>'
                '<p><button type="submit">Enviar resposta</button></p></form>') if pode else "<p>Sem e-mail gravado para responder (mensagem enviada pela porta local).</p>"
        blocos.append(f'<section aria-labelledby="m-{e(r["protocolo"])}"><h2 id="m-{e(r["protocolo"])}">{e(r["protocolo"])}</h2>'
                      f'<p>{e(r["data"])}. De {e(r.get("nome") or "-")} ({e(r["email"])}). {e(SERVICOS.get(r["servico"], r["servico"]))}, {e(ASSUNTOS.get(r["assunto"], r["assunto"]))}. Estado: {e(r["estado"])}.</p>'
                      f'<p>{e(r["mensagem"])}</p>{mot}{resp}{form}</section>')
    corpo = (f'<h1>Mensagens de suporte</h1>{topo}<p>Somente o dono vê esta página. As respostas saem de {e(EMAIL_SUPORTE)} para o e-mail de quem escreveu. '
             f'<a href="/ajuda">Voltar para Ajuda e suporte</a>.</p>' + ("".join(blocos) or "<p>Nenhuma mensagem recebida ainda.</p>"))
    return "Mensagens de suporte - Heimdall", corpo


def enviar(p: dict, assunto: str, servico: str, mensagem: str) -> tuple:
    """(registro, enviado_por_email)."""
    reg = registrar(p, assunto, servico, mensagem)
    return reg, enviar_email(reg)


def mensagem_de_confirmacao(reg: dict, enviado: bool) -> str:
    base = f"Mensagem recebida. Seu protocolo é {reg['protocolo']}."
    if enviado:
        return base + f" Ela foi enviada ao suporte, que responde para {reg['email']}."
    return base + f" Ela foi registrada, mas o envio por e-mail não está ativo agora. Se for urgente, escreva para {EMAIL_SUPORTE} informando o protocolo."


def _api(metodo: str, caminho: str, token: str, corpo=None) -> dict:
    req = urllib.request.Request("https://api.cloudflare.com/client/v4" + caminho, method=metodo, data=(json.dumps(corpo).encode("utf-8") if corpo is not None else None),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with _post(req, 25) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8", "replace"))
        except ValueError:
            return {"success": False, "errors": [{"message": f"HTTP {e.code}"}]}


def _gravar_no_env(chave: str, valor: str) -> None:
    arq = AQUI / ".env"
    linhas = [ln for ln in (arq.read_text(encoding="utf-8").splitlines() if arq.exists() else []) if not ln.startswith(chave + "=")]
    linhas.append(f"{chave}='{valor}'")
    tmp = arq.with_suffix(".novo")
    tmp.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(arq)


def criar_token_envio() -> int:
    """Cria, com o token atual da Cloudflare, um token só com a permissão Email Sending e o grava no .env (HEIMDALL_SUPORTE_TOKEN), sem exibi-lo."""
    c = _conf()
    base, conta = c.get("CLOUDFLARE_API_TOKEN"), c.get("CLOUDFLARE_ACCOUNT_ID")
    if not base or not conta:
        print("Faltam CLOUDFLARE_API_TOKEN e CLOUDFLARE_ACCOUNT_ID no .env.")
        return 1
    g = _api("GET", "/user/tokens/permission_groups", base)
    if not g.get("success"):
        print("O token atual da Cloudflare não pode criar tokens (falta a permissão API Tokens: Edit). Motivo: " + "; ".join(e.get("message", "") for e in g.get("errors", [])))
        print("Alternativa: no painel, Perfil, Tokens de API, Criar token personalizado, permissão Conta, Email Sending, Edit; depois copie o valor e rode: bash scripts/guardar_no_env.sh HEIMDALL_SUPORTE_TOKEN")
        return 1
    grupos = [x for x in g["result"] if "email sending" in x.get("name", "").lower() and "account" in " ".join(x.get("scopes", [])).lower()]
    escolhido = next((x for x in grupos if re.search(r"write|edit", x["name"], re.I)), None)
    if not escolhido:
        print("A Cloudflare não lista a permissão Email Sending para este token. Grupos de e-mail encontrados: " + ", ".join(x["name"] for x in g["result"] if "email" in x.get("name", "").lower()))
        return 1
    corpo = {"name": "Heimdall - envio de e-mail do suporte", "policies": [{"effect": "allow", "resources": {f"com.cloudflare.api.account.{conta}": "*"}, "permission_groups": [{"id": escolhido["id"]}]}]}
    r = _api("POST", "/user/tokens", base, corpo)
    if not r.get("success") or not r.get("result", {}).get("value"):
        print("Não foi possível criar o token: " + "; ".join(e.get("message", "") for e in r.get("errors", [])))
        return 1
    _gravar_no_env("HEIMDALL_SUPORTE_TOKEN", r["result"]["value"])
    print(f"Token criado com a permissão '{escolhido['name']}' e gravado no .env como HEIMDALL_SUPORTE_TOKEN (não é exibido). Rode: heimdall support --test")
    return 0


def main() -> int:
    import sys
    if "--ultimas" in sys.argv:
        for r in _ler_registros()[-10:]:
            print(f"{r['protocolo']}  {r['estado']:18}  {r['email']}  {ASSUNTOS.get(r['assunto'])}  {r['mensagem'][:60]}")
            if r.get("motivo"):
                print(f"    motivo: {r['motivo']}")
        return 0
    if "--documentos" in sys.argv:
        arq = AQUI / "guides" / "termos_e_privacidade.txt"
        arq.write_text(texto_documentos(), encoding="utf-8")
        print(f"Termos de Uso e Política de Privacidade gravados em {arq.relative_to(AQUI)}.")
        return 0
    if "--responder" in sys.argv:
        a = sys.argv[1:]
        def _v(op):
            return a[a.index(op) + 1] if op in a and a.index(op) + 1 < len(a) else ""
        proto, para = _v("--responder"), _v("--para")
        texto = " ".join(x for x in a if x not in ("--responder", "--para", proto, para))
        if proto.startswith("--") or not texto:
            print('Uso: heimdall support --reply PROTOCOLO "texto da resposta"   (ou --reply - --to endereco "texto", para e-mails sem protocolo)')
            return 2
        ok, msg = responder("" if proto == "-" else proto, texto, para)
        print(msg)
        return 0 if ok else 1
    if "--token" in sys.argv:
        return criar_token_envio()
    if "--testar" in sys.argv:
        c = _conf()
        destino = c.get("HEIMDALL_SUPORTE_PARA") or EMAIL_SUPORTE
        reg, ok = enviar({"email": destino, "nome": "Teste do envio"}, "outro", "geral", "Teste do envio de e-mail do suporte, feito por heimdall support --test.")
        print(f"Protocolo {reg['protocolo']}: " + ("enviado para " + destino + ". Confira a caixa de entrada e o spam." if ok else "não enviado."))
        if not ok:
            print("Motivo: " + (reg.get("motivo") or "não informado"))
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
