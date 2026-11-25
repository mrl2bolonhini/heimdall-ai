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
         "Todas as páginas têm o link Pular para o conteúdo no início, um único título principal e abas com setas, Home e End. Option+Shift+1 a 5 abre a aba pelo número no macOS, e Alt+Shift+1 a 5 no Windows e no Linux (cada serviço tem no máximo 5 posições; se a quinta for o menu Mais, o mesmo atalho o abre). Nos serviços com o campo Perguntar, Option+Shift+P (Alt+Shift+P no Windows e no Linux) leva ao campo. A tabela completa está no Guia de comandos."),
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
         "Na aba Nuvem, com as subabas Continuidade e Consumo de IA, que mostram o consumo e os limites de gasto configurados."),
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
# Termos de Uso e Política de Privacidade (MINUTA): o texto descreve o que o Heimdall faz hoje. Os dados de identificação do responsável
# ficam no .env (HEIMDALL_RESPONSAVEL, HEIMDALL_ENCARREGADO, HEIMDALL_FORO), nunca no código, porque o repositório é público.
# ---------------------------------------------------------------------------------------------------------------------
def _cfg(chave: str, padrao: str = "") -> str:
    return (os.environ.get(chave) or _env_arquivo(chave) or padrao).strip()


def responsavel() -> str:
    return _cfg("HEIMDALL_RESPONSAVEL", "[NOME E DOCUMENTO DO RESPONSÁVEL: defina HEIMDALL_RESPONSAVEL]")


def encarregado() -> str:
    return _cfg("HEIMDALL_ENCARREGADO", f"o próprio responsável, pelo e-mail {EMAIL_SUPORTE}")


def foro() -> str:
    return _cfg("HEIMDALL_FORO", "São Paulo")


def data_por_extenso(iso: str = None) -> str:
    meses = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro")
    a, m, d = (iso or VERSAO_POLITICA).split("-")
    return f"{int(d)} de {meses[int(m) - 1]} de {a}"


def termos_de_uso() -> list:
    return [
        ("1. Aceitação e definições", [
            f"Estes Termos de Uso regulam o acesso e a utilização dos serviços do Heimdall (Account, Finance, Health, Notes, News, Learn, Games, Lab e Chat), operados por {responsavel()} (\"Responsável\"). "
            "\"Usuário\" é a pessoa que acessa os serviços mediante convite. Ao entrar, o Usuário declara ter lido e concordado com o quanto se segue, bem como com a Política de Privacidade, que integra estes termos."]),
        ("2. Descrição dos serviços", [
            "O Heimdall reúne serviços pessoais de organização e acompanhamento: Account (acesso, integrações, ajuda e suporte), Finance (finanças), Health (saúde), Notes (notas), News (notícias), "
            "Learn (estudos), Games (jogos), Lab (laboratório de serviços de nuvem) e Chat (conversa com modelos de inteligência artificial). Cada Usuário vê apenas os serviços liberados no seu convite."]),
        ("3. Acesso e conta", [
            "O acesso é pessoal e por convite, mediante autenticação pelo Cloudflare Access com conta Microsoft. O Usuário é responsável por manter sua conta e seus dispositivos seguros e por não compartilhar o acesso com terceiros. "
            "Deve avisar o suporte, sem demora, caso suspeite de uso indevido da sua conta."]),
        ("4. Uso permitido e condutas vedadas", [
            "O Usuário se compromete a usar os serviços de forma lícita. É vedado:",
            "tentar acessar dados de outras pessoas ou áreas para as quais não recebeu acesso;",
            "interferir no funcionamento dos serviços, contornar a autenticação ou testar a segurança deles sem autorização por escrito;",
            "enviar conteúdo ilícito ou que viole direitos de terceiros;",
            "usar os serviços para acesso automatizado em massa ou para fins comerciais não autorizados."]),
        ("5. Recursos de inteligência artificial", [
            "Parte dos serviços usa inteligência artificial para resumir, classificar e responder perguntas. As respostas podem conter erros e devem ser conferidas pelo Usuário. "
            "São informativas e não substituem orientação médica, jurídica, contábil ou financeira."]),
        ("6. Saúde e finanças", [
            "As análises de saúde e de finanças são informativas. O Heimdall não realiza diagnóstico nem recomenda tratamento, investimento ou operação financeira, e nenhuma decisão deve ser tomada apenas com base nelas. "
            "Em caso de urgência médica, procure atendimento imediato."]),
        ("7. Disponibilidade e suporte", [
            "Os serviços são oferecidos no estado em que se encontram, sem garantia de disponibilidade contínua. Podem ficar indisponíveis por manutenção, falha de energia, de rede ou de provedores externos, e alguns recursos podem operar em modo reduzido nessas situações. "
            f"O suporte é prestado pelo formulário da página Ajuda e suporte, que gera um número de protocolo, ou pelo e-mail {EMAIL_SUPORTE}. As respostas são enviadas ao e-mail da conta do Usuário, sem prazo garantido."]),
        ("8. Conteúdo do Usuário", [
            "Os dados e arquivos enviados pelo Usuário continuam sendo dele. O Usuário autoriza o Responsável a tratá-los apenas para prestar os serviços, conforme a Política de Privacidade, e declara ter o direito de enviá-los."]),
        ("9. Propriedade intelectual", [
            "O software, a interface, os textos e as marcas do Heimdall pertencem ao Responsável ou a seus licenciantes. Estes termos não transferem direitos de propriedade: concedem ao Usuário uma licença pessoal, "
            "não exclusiva, intransferível e revogável de uso dos serviços enquanto o acesso estiver ativo."]),
        ("10. Limitação de responsabilidade", [
            "Na extensão permitida pela lei, e ressalvados os direitos do consumidor, o Responsável não responde por danos decorrentes de indisponibilidade dos serviços, de falhas de provedores externos, "
            "de erros nas respostas de inteligência artificial, de decisões tomadas com base nas informações exibidas ou do uso indevido da conta pelo próprio Usuário."]),
        ("11. Suspensão e encerramento", [
            "O acesso pode ser suspenso ou encerrado em caso de descumprimento destes termos ou de risco à segurança. O Usuário pode pedir o encerramento da sua conta e a exclusão dos seus dados pelo suporte."]),
        ("12. Alterações", [
            "Estes termos podem ser atualizados. A data da versão vigente aparece no início desta página, e mudanças relevantes serão comunicadas aos Usuários. O uso dos serviços após a atualização indica concordância com o novo texto."]),
        ("13. Lei aplicável e foro", [
            "Aplica-se a legislação brasileira para todos os efeitos desta relação, independentemente de onde se dar o uso dos serviços, quer seja em território nacional ou estrangeiro. "
            f"Fica eleito o foro de {foro()} para dirimir quaisquer conflitos, ressalvados os direitos do consumidor, quando cabíveis."]),
        ("14. Contato", [f"Dúvidas sobre estes termos podem ser enviadas pelo formulário de suporte ou para {EMAIL_SUPORTE}."]),
    ]


def politica_privacidade() -> list:
    return [
        ("1. Controlador e contato", [
            f"O controlador dos dados pessoais é {responsavel()}, com contato em {EMAIL_SUPORTE}. Encarregado pelo tratamento de dados pessoais (art. 41 da LGPD): {encarregado()}."]),
        ("2. Quais dados tratamos", [
            "Conta: nome e e-mail fornecidos pela conta Microsoft no login pelo Cloudflare Access.",
            "Saúde: medidas do app Saúde do iPhone e do Apple Watch enviadas pelo Health Auto Export, e exames, receitas e encaminhamentos que o Usuário envia. São dados pessoais sensíveis.",
            "Finanças: lançamentos, saldos e investimentos das contas conectadas pelo Open Finance (por meio da Pluggy), planilhas, boletos e arquivos que o Usuário envia.",
            "Notas, estudos e preferências: o que o Usuário escreve, importa ou configura nos serviços.",
            "Suporte: o conteúdo das mensagens enviadas e os dados de contato.",
            "Registros técnicos: horários de acesso e eventos de funcionamento necessários para segurança e diagnóstico."]),
        ("3. Finalidades e bases legais", [
            "Prestar os serviços contratados e mantê-los em funcionamento: execução de contrato (art. 7, V, da LGPD).",
            "Tratar dados de saúde e conectar contas financeiras: consentimento do Usuário, dado ao ativar o serviço ou a integração (art. 11, I, e art. 7, I).",
            "Manter a segurança, prevenir fraudes e diagnosticar falhas: legítimo interesse (art. 7, IX).",
            "Responder ao suporte e cumprir obrigações legais ou ordens de autoridades: execução de contrato e cumprimento de obrigação legal (art. 7, II e V).",
            "Os dados dos serviços (saúde, finanças, notas e demais conteúdos do Usuário) não são vendidos, não são usados para publicidade e não são lidos pelo Responsável."]),
        ("4. Onde os dados ficam", [
            "Os serviços são hospedados em um servidor local do Responsável. Cópias cifradas de bancos e arquivos podem ser guardadas na nuvem da Cloudflare (armazenamento R2, com criptografia), para continuidade e recuperação.",
            "Se a hospedagem passar para um servidor contratado, esta política será atualizada e os Usuários serão avisados."]),
        ("5. Compartilhamento e operadores", [
            "Cloudflare: entrada segura (Access e túnel), armazenamento de cópias, envio e recebimento de e-mails do suporte, execução de modelos de inteligência artificial e gateway de IA.",
            "Microsoft: autenticação da conta.",
            "Pluggy: conexão com instituições financeiras pelo Open Finance, mediante autorização do Usuário.",
            "Apple: Calendário, Lembretes, Notas e iCloud, quando o Usuário usa essas integrações.",
            "Provedores de modelos de inteligência artificial acessados pelo gateway da Cloudflare, quando a nuvem está ligada. O gateway é configurado para não guardar o conteúdo das conversas.",
            "Serviço de notificações (Bark): os avisos de saúde levam apenas texto genérico, sem números de saúde.",
            "Notion: opcional, somente para ideias, contatos e endereços das notas, nunca saúde ou finanças.",
            "Os dados também podem ser compartilhados quando a lei ou uma ordem judicial exigir."]),
        ("6. Transferência internacional", [
            "Provedores como a Cloudflare podem tratar dados fora do Brasil. Nesses casos, a transferência ocorre com as garantias previstas no art. 33 da LGPD, como as cláusulas contratuais firmadas com os provedores "
            "(por exemplo, o aditamento de tratamento de dados da Cloudflare) ou, quando necessário, mediante consentimento específico do Usuário."]),
        ("7. Inteligência artificial", [
            "Os recursos de inteligência artificial recebem apenas o contexto necessário para responder, como os dados da tela em que o Usuário pergunta. As respostas podem conter erros e não substituem orientação profissional. "
            "Dependendo da configuração, os modelos rodam no servidor local do Responsável ou na nuvem."]),
        ("8. Por quanto tempo guardamos", [
            "Os dados são guardados enquanto a conta existir ou for necessário para as finalidades acima. A caixa de correio da Cloudflare, usada para receber dados do dispositivo móvel, apaga o que não foi retirado em 7 dias. "
            "Mensagens de suporte são guardadas pelo tempo necessário ao atendimento e à comprovação de contato. Os dados podem ser eliminados a pedido do Usuário, ressalvadas as hipóteses de guarda obrigatória por lei."]),
        ("9. Direitos do titular", [
            "Conforme o art. 18 da LGPD, o titular pode pedir confirmação do tratamento, acesso, correção, anonimização, portabilidade, informação sobre compartilhamento, eliminação de dados tratados com consentimento e revogação do consentimento. "
            "Para exercer esses direitos, use o formulário de suporte, com o assunto Pedido sobre os meus dados. O titular também pode reclamar à Autoridade Nacional de Proteção de Dados (ANPD)."]),
        ("10. Segurança e incidentes", [
            "São adotadas medidas como autenticação em dois fatores pelo Access, criptografia das cópias na nuvem (AES-256-GCM), proteção contra requisições forjadas, acesso restrito por papel e separação dos dados por pessoa nos serviços em que ela já existe. "
            "Nenhum sistema é totalmente imune a falhas. Em caso de incidente de segurança que possa acarretar risco ou dano relevante, os titulares afetados e a ANPD serão comunicados, conforme a lei."]),
        ("11. Crianças e adolescentes", ["Os serviços destinam-se a maiores de 18 anos. O Heimdall não trata intencionalmente dados de crianças e adolescentes."]),
        ("12. Cookies e armazenamento no navegador", [
            "São usados apenas cookies e armazenamento essenciais ao funcionamento e à segurança, como o cookie de sessão do Cloudflare Access. Não há cookies de publicidade nem de rastreamento."]),
        ("13. Alterações desta política", [
            "Esta política pode ser atualizada. A data da versão vigente aparece no início da página, e mudanças relevantes serão comunicadas aos Usuários."]),
    ]


def aviso_minuta() -> str:
    if os.environ.get("HEIMDALL_POLITICA_APROVADA") == "1" or _env_arquivo("HEIMDALL_POLITICA_APROVADA") == "1":
        return ""
    return ('<p role="note"><strong>Minuta em revisão.</strong> Este texto ainda não foi aprovado pelo responsável e pode mudar antes da publicação.</p>')


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


def _item_html(texto: str) -> str:
    return e(texto)


def _secoes(titulo_id: str, partes: list) -> str:
    """Seções numeradas. Texto com um só parágrafo vira parágrafo; com vários, o primeiro vira introdução se terminar em dois-pontos, e os demais, itens de lista."""
    saida = ""
    for i, (tit, ps) in enumerate(partes):
        if len(ps) == 1:
            corpo = f"<p>{e(ps[0])}</p>"
        elif ps[0].endswith(":"):
            corpo = f"<p>{e(ps[0])}</p><ul>" + "".join(f"<li>{e(p)}</li>" for p in ps[1:]) + "</ul>"
        else:
            corpo = "<ul>" + "".join(f"<li>{e(p)}</li>" for p in ps) + "</ul>"
        saida += f'<section aria-labelledby="{titulo_id}-{i}"><h2 id="{titulo_id}-{i}">{e(tit)}</h2>{corpo}</section>'
    return saida


def _indice(titulo_id: str, partes: list) -> str:
    itens = "".join(f'<li><a href="#{titulo_id}-{i}">{e(tit)}</a></li>' for i, (tit, _) in enumerate(partes))
    return f'<nav aria-label="Conteúdo desta página"><h2>Conteúdo</h2><ul>{itens}</ul></nav>'


def _cabecalho_doc(titulo: str) -> str:
    return (f"<h1>{e(titulo)}</h1><p>Em vigor desde {e(data_por_extenso())}. Versão de {e(VERSAO_POLITICA)}.</p>{aviso_minuta()}")


def texto_documento(qual: str) -> str:
    """Um dos documentos em texto puro: 'termos' ou 'privacidade'."""
    titulo, partes = (("TERMOS DE USO DO HEIMDALL", termos_de_uso()) if qual == "termos" else ("POLÍTICA DE PRIVACIDADE DO HEIMDALL", politica_privacidade()))
    s = f"{titulo}\nEm vigor desde {data_por_extenso()}. Versão de {VERSAO_POLITICA}.\n"
    if aviso_minuta():
        s += "MINUTA EM REVISÃO: este texto ainda não foi aprovado pelo responsável e pode mudar antes da publicação.\n"
    s += "\nConteúdo\n" + "".join(f"{tit}\n" for tit, _ in partes) + "\n"
    for tit, ps in partes:
        s += tit + "\n"
        if len(ps) == 1:
            s += ps[0] + "\n"
        elif ps[0].endswith(":"):
            s += ps[0] + "\n" + "".join(f"- {p}\n" for p in ps[1:])
        else:
            s += "".join(f"- {p}\n" for p in ps)
        s += "\n"
    return s


def pagina_termos_de_uso() -> tuple:
    p = termos_de_uso()
    corpo = (_cabecalho_doc("Termos de Uso") + _indice("pu", p) + _secoes("pu", p)
             + '<p><a href="/politica-de-privacidade">Política de Privacidade</a> · <a href="/ajuda">Ajuda e suporte</a></p>')
    return "Termos de Uso - Heimdall", corpo


def pagina_privacidade() -> tuple:
    p = politica_privacidade()
    corpo = (_cabecalho_doc("Política de Privacidade") + _indice("pp", p) + _secoes("pp", p)
             + '<p><a href="/termos-de-uso">Termos de Uso</a> · <a href="/ajuda">Ajuda e suporte</a></p>')
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


def ajuda_do_servico(servico: str, base: str = "") -> str:
    """Conteúdo da subaba Ajuda, dentro dos Ajustes de um serviço: as perguntas frequentes dele e o caminho para a Ajuda e suporte completa
    (com o formulário de mensagem), no Heimdall Account. `base` é o endereço do Account (design.base_ajuda())."""
    servico = servico if servico in SERVICOS and servico != "geral" else ""
    itens = FAQ.get(servico) or []
    blocos = "".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in itens)
    perguntas = (f'<section aria-labelledby="ajuda-faq"><h2 id="ajuda-faq">Perguntas frequentes</h2>{blocos}</section>' if blocos
                 else "<p>Ainda não há perguntas frequentes deste serviço.</p>")
    q = f"?servico={servico}" if servico else ""
    destino = f"{base}/ajuda{q}" if base else f"/ajuda{q}"
    contato = (f'<section aria-labelledby="ajuda-contato"><h2 id="ajuda-contato">Falar com o suporte</h2>'
               f'<p>Para enviar uma mensagem ao suporte e receber um protocolo, ou para ver as perguntas dos demais serviços, abra a '
               f'<a href="{e(destino)}">Ajuda e suporte do Heimdall Account</a>.</p></section>')
    return perguntas + contato


# Guia de comandos: as telas dos serviços não ensinam comandos; eles ficam aqui, por sistema operacional.
# Cada linha é (ação, comando heimdall no macOS, comando em Python para Linux e Windows). No Windows use "py" no lugar de "python3".
COMANDOS_HEALTH = [
    ("Ver os documentos aguardando conferência", "heimdall health --labs pending", "python3 heimdall_exames.py --pendentes"),
    ("Ler o que foi extraído de um documento", "heimdall health --labs read ID", "python3 heimdall_exames.py --ler ID"),
    ("Confirmar um documento", "heimdall health --labs confirm ID", "python3 heimdall_exames.py --confirmar ID"),
    ("Confirmar deixando itens de fora", "heimdall health --labs confirm ID --without 3,5", "python3 heimdall_exames.py --confirmar ID --sem 3,5"),
    ("Descartar um documento", "heimdall health --labs discard ID", "python3 heimdall_exames.py --descartar ID"),
    ("Importar um arquivo", "heimdall health --labs import ARQUIVO", "python3 heimdall_exames.py --importar ARQUIVO"),
    ("Listar receitas", "heimdall health --labs prescriptions", "python3 heimdall_exames.py --receitas"),
    ("Listar encaminhamentos", "heimdall health --labs referrals", "python3 heimdall_exames.py --encaminhamentos"),
    ("Listar atestados", "heimdall health --labs certificates", "python3 heimdall_exames.py --atestados"),
    ("Listar laudos", "heimdall health --labs reports", "python3 heimdall_exames.py --laudos"),
    ("Listar pedidos de exame", "heimdall health --labs requests", "python3 heimdall_exames.py --pedidos"),
    ("Listar consultas", "heimdall health --labs appointments", "python3 heimdall_exames.py --consultas"),
    ("Cadastrar uma consulta", "heimdall health --labs appointment --date AAAA-MM-DD --time HH:MM", "python3 heimdall_exames.py --consulta-nova --data AAAA-MM-DD --hora HH:MM"),
    ("Enviar consultas e renovações ao Calendário", "heimdall health --labs calendar", "python3 heimdall_exames.py --agenda"),
    ("Ver as sugestões de acompanhamento", "heimdall health --labs suggestions", "python3 heimdall_clinico.py --sugestoes"),
    ("Aceitar uma sugestão (com --date e --time, vira evento no Calendário)", "heimdall health --labs suggestions accept ID", "python3 heimdall_clinico.py --aceitar ID"),
    ("Recusar, adiar ou responder uma sugestão", "heimdall health --labs suggestions dismiss ID | snooze ID DIAS | answer ID TEXTO",
     "python3 heimdall_clinico.py --recusar ID | --adiar ID --dias N | --responder ID --texto TEXTO"),
    ("Adicionar um item ao perfil de saúde", "heimdall health --labs profile add condition|surgery|allergy|insurance|doctor|other TEXTO",
     "python3 heimdall_clinico.py --perfil-add condicao|cirurgia|alergia|convenio|medico|outro --texto TEXTO"),
]

# Administração (Controls e Lab): o que as telas não ensinam. A terceira coluna vale para Linux e Windows (com Docker instalado).
COMANDOS_ADMIN = [
    ("Ver as versões instaladas e se há imagem mais nova no registro", "heimdall doctor --versions", "python3 diagnostico.py --versoes"),
    ("Diagnóstico completo (memória, disco, Docker e modelos)", "heimdall doctor", "python3 diagnostico.py"),
    ("Ligar o emulador de AWS usado pelo Lab", "heimdall lab --start", "docker start localstack (ou docker start moto)"),
    ("Desligar o emulador de AWS", "heimdall lab --stop", "docker stop localstack moto"),
]

# Atalhos de teclado: um só atalho por ação, com a forma do macOS e a do Windows e Linux (Option vira Alt; Control vira Ctrl; o resto é igual).
ATALHOS = [
    ("Abrir a aba pelo número (de 1 a 5)", "Option+Shift+1 a 5", "Alt+Shift+1 a 5"),
    ("Abrir ou fechar o menu Mais (a quinta posição, quando há mais de 5 itens; Esc também fecha)", "Option+Shift+5", "Alt+Shift+5"),
    ("Passar para a subaba anterior ou seguinte", "Option+Shift+seta esquerda ou direita", "Alt+Shift+seta esquerda ou direita"),
    ("Ir ao campo Perguntar", "Option+Shift+P", "Alt+Shift+P"),
    ("Controls, Terminal: voltar ao campo do terminal", "Option+Shift+T", "Alt+Shift+T"),
    ("Controls, Terminal: ir à lista de atalhos", "Option+Shift+H", "Alt+Shift+H"),
    ("Controls, Terminal: completar comando ou arquivo", "Control+I", "Ctrl+I"),
    ("Controls, Terminal: interromper o programa", "Control+C ou Option+Shift+I", "Ctrl+C ou Alt+Shift+I"),
    ("Controls, Terminal: limpar as saídas", "Control+L ou Option+Shift+L", "Ctrl+L ou Alt+Shift+L"),
    ("Controls, Terminal: reiniciar o shell", "Option+Shift+R", "Alt+Shift+R"),
    ("Controls, Terminal: copiar a última saída", "Option+Shift+C", "Alt+Shift+C"),
    ("Controls, Terminal: copiar as últimas 1 a 9 saídas", "Control+Shift+1 a 9", "Ctrl+Shift+1 a 9"),
    ("Controls, Terminal: copiar todas as saídas", "Control+Shift+0", "Ctrl+Shift+0"),
    ("Controls, Terminal: ir ao início da última saída", "Option+Shift+U", "Alt+Shift+U"),
    ("Controls, Terminal: ler o começo da última saída", "Option+Shift+O", "Alt+Shift+O"),
    ("Controls, Terminal: comando anterior ou seguinte do histórico", "Option+Shift+P ou Option+Shift+N", "Alt+Shift+P ou Alt+Shift+N"),
]


def _atalhos_html() -> str:
    linhas = "".join(f'<tr><th scope="row">{e(a)}</th><td><kbd>{e(m)}</kbd></td><td><kbd>{e(w)}</kbd></td></tr>' for a, m, w in ATALHOS)
    return ('<h3 id="atalhos">Atalhos de teclado</h3>'
            f'<table><caption>Atalhos de teclado por sistema</caption><thead><tr><th scope="col">Ação</th><th scope="col">macOS</th><th scope="col">Windows e Linux</th></tr></thead><tbody>{linhas}</tbody></table>'
            '<p>Cada ação tem um só atalho. A tecla Option do Mac corresponde à Alt no Windows e no Linux. Se o sistema ou o leitor de tela já usar uma combinação '
            '(por exemplo, Alt+Shift para trocar o idioma do teclado no Windows), altere a combinação do sistema. No iPhone e no Android os atalhos só valem com teclado físico; '
            'na tela, use os botões e as abas.</p>')


def _comandos_html() -> str:
    cab = "".join(f'<th scope="col">{c}</th>' for c in ("Ação", "macOS (comando heimdall)", "Linux e Windows (Python, na pasta do Heimdall)"))
    linhas = "".join(f'<tr><th scope="row">{e(a)}</th><td><code>{e(m)}</code></td><td><code>{e(p)}</code></td></tr>' for a, m, p in COMANDOS_HEALTH)
    linhas_admin = "".join(f'<tr><th scope="row">{e(a)}</th><td><code>{e(m)}</code></td><td><code>{e(p)}</code></td></tr>' for a, m, p in COMANDOS_ADMIN)
    return ('<section aria-labelledby="comandos"><h2 id="comandos">Guia de comandos</h2>'
            '<p>Algumas ações são feitas por comando no computador que hospeda o Heimdall. As telas dos serviços indicam esta página em vez de mostrar comandos.</p>'
            '<h3>Abrir o terminal</h3><ol>'
            '<li>macOS: pressione Command+Espaço, digite Terminal e pressione Return.</li>'
            '<li>Linux: pressione Ctrl+Alt+T, ou abra o aplicativo Terminal.</li>'
            '<li>Windows: pressione a tecla Windows, digite PowerShell e pressione Enter.</li></ol>'
            '<p>Em seguida, entre na pasta do Heimdall: <code>cd ~/heimdall-ai</code> no macOS e no Linux; <code>cd $HOME\\heimdall-ai</code> no Windows (PowerShell). '
            'No macOS o comando <code>heimdall</code> funciona de qualquer pasta. No Windows, use <code>py</code> no lugar de <code>python3</code>.</p>'
            '<h3 id="comandos-saude">Health: documentos, sugestões e perfil</h3>'
            f'<table><caption>Comandos do Health por sistema</caption><thead><tr>{cab}</tr></thead><tbody>{linhas}</tbody></table>'
            '<p>Eventos no Calendário e lembretes no app Lembretes dependem do agente do Mac; nos outros sistemas, os itens ficam registrados no Heimdall.</p>'
            '<h3 id="comandos-admin">Administração: versões e emulador do Lab</h3>'
            f'<table><caption>Comandos de administração por sistema</caption><thead><tr>{cab}</tr></thead><tbody>{linhas_admin}</tbody></table>'
            '<p>No Heimdall Controls, a aba Terminal executa esses comandos no computador que hospeda o Heimdall e mostra a saída na própria página; '
            'a aba Serviços liga e desliga o emulador por uma chave, e a aba Manutenção tem os botões Status e Diagnóstico.</p>'
            + _atalhos_html() +
            '<h3>iPhone e Android</h3>'
            '<p>Abra os painéis pelo navegador (Safari no iPhone, Chrome no Android) para consultar os dados, ver sugestões e editar o perfil. '
            'A conferência de documentos e os demais comandos acima são feitos no computador que hospeda o Heimdall. No iPhone, o botão Atualizar dados agora, '
            'no Health, abre o app Atalhos.</p></section>')


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
             '<p>Encontre abaixo as perguntas frequentes, o guia de comandos por sistema operacional e, no fim da página, o formulário para falar com o suporte. '
             f'Documentos: <a href="/termos-de-uso">Termos de Uso</a> e <a href="/politica-de-privacidade">Política de Privacidade</a>.</p>'
             + ('<p><a href="/suporte/mensagens">Mensagens de suporte recebidas (somente dono)</a></p>' if dono else "")
             + _faq_html(servico) + _comandos_html() + formulario_suporte(csrf, servico, valores))
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
        pasta = AQUI / "db" / "juridico"
        pasta.mkdir(parents=True, exist_ok=True)
        for nome, qual in (("termos_de_uso.txt", "termos"), ("politica_de_privacidade.txt", "privacidade")):
            (pasta / nome).write_text(texto_documento(qual), encoding="utf-8")
        print(f"Gravados em {pasta.relative_to(AQUI)}: termos_de_uso.txt e politica_de_privacidade.txt (a pasta db/ não vai para o GitHub).")
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
