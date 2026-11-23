#!/usr/bin/env python3
"""Texto do tour da página Account (account.heimdall-ai.tech): o que cada serviço faz e como configurar. A chave é a mesma de heimdall_usuarios.SERVICOS.

Para acrescentar um serviço ou mudar um texto, edite só aqui. "como" é uma lista de passos; "so_dono" avisa que convidados não o recebem;
"multiusuario" diz o que muda quando outras pessoas puderem usá-lo (aparece só para quem pode abrir o serviço).
"""
INFO = {
    "cloud": {
        "oque": "Painel web do emulador de AWS do Heimdall, com S3, Lambda, Glue, Athena e um console geral, para estudar e testar sem custo.",
        "como": ["Entre pelo Cloudflare Access, com a sua conta Microsoft e a aprovação no Authenticator.",
                 "Escolha na barra do alto o serviço da AWS que quer usar: S3, Lambda, Glue, Athena ou Console geral.",
                 "Nada precisa ser configurado: os dados ficam no emulador, que roda no Mac do dono."],
    },
    "notas": {
        "oque": "Site simples para ler as notas de estudo e ouvir os áudios, feito para leitor de tela.",
        "como": ["Abra o serviço e escolha a nota na lista.",
                 "Para ouvir, use o botão de reproduzir da própria nota.",
                 "As notas vêm do app Notas do Mac; no terminal do dono, heimdall notes abre o site."],
    },
    "news": {
        "oque": "Notícias das últimas 24 horas com resumo feito por inteligência artificial, e feeds RSS para ler no iPhone.",
        "como": ["Abra o serviço e leia os resumos por fonte.",
                 "Para ler no iPhone, copie o endereço do feed RSS da fonte e assine no seu leitor de RSS.",
                 "O dono escolhe as fontes com heimdall news --sources NOME, no terminal."],
    },
    "saude": {
        "oque": "Dados do iPhone e do Apple Watch num banco pessoal, análises, relatório semanal e um painel somente de leitura.",
        "como": ["No iPhone, o app Health Auto Export envia os dados ao webhook do Heimdall, com o token do dono.",
                 "Abra o painel para ver o dia, as anomalias e as tendências.",
                 "No terminal do dono, heimdall health --today e heimdall doctor ajudam a conferir."],
        "so_dono": True,
        "multiusuario": "Hoje só o dono usa, e os dados dele não saem do Mac. Está no roadmap uma versão para outras pessoas, em que cada uma conectaria os próprios serviços de saúde.",
    },
    "learn": {
        "oque": "Plataforma de estudos: pastas de material com categoria (aleatório ou sequencial) e tipo (idiomas, programação, filosofia, medicina e outros), e importação de documentos.",
        "como": ["Crie uma pasta, escolha a categoria e o tipo, e importe PDF, Markdown, texto, Word, EPUB ou áudio.",
                 "Subpastas herdam categoria, tipo e idioma da pasta de cima.",
                 "Perguntas, lições, voz e cards vêm nas próximas fases."],
        "so_dono": True,
    },
    "jogos": {
        "oque": "Jogos leves no navegador, feitos para leitor de tela: forca, jogo da velha, xadrez, sudoku, 2048, batalha naval, aventuras de texto e outros.",
        "como": ["Abra o serviço e escolha o jogo na lista.",
                 "O que acontece na partida é dito em voz alta pelo leitor de tela, e tudo se joga com teclado.",
                 "Nada é gravado no servidor; não há o que configurar."],
    },
    "finance": {
        "oque": "Extratos do banco e do cartão importados, gastos por categoria, tendências e alertas, em páginas de texto para leitor de tela.",
        "como": ["No terminal do dono, importe um extrato com heimdall finance --import ARQUIVO --account NOME.",
                 "Abra o serviço para ver os gastos por categoria, as tendências e os boletos.",
                 "Os dados ficam em finance/ no Mac e nunca saem dele."],
        "so_dono": True,
        "multiusuario": "Hoje só o dono usa. Está no roadmap uma versão para outras pessoas, em que cada uma conectaria as próprias contas bancárias, com os dados dela guardados à parte dos do dono.",
    },
    "controls": {
        "oque": "Central de controle do Heimdall: Terminal no navegador, serviços ligados e desligados, usuários e acessos, ajustes do .env e manutenção.",
        "como": ["Entre como dono pelo Cloudflare Access.",
                 "Use a aba Usuários para convidar pessoas e escolher os serviços de cada uma.",
                 "Use a aba Ajustes para mudar as variáveis e Manutenção para reiniciar e atualizar."],
        "so_dono": True,
    },
    "chat": {
        "oque": "Heimdall Chat: conversa com os modelos de inteligência artificial que rodam no Mac do dono, com histórico e ferramentas. Tecnologia: Open WebUI.",
        "como": ["Abra o serviço: a entrada é automática, pelo e-mail da sua conta Microsoft.",
                 "Escolha o modelo no alto da conversa e escreva a mensagem.",
                 "Uma conta é criada na primeira entrada; o dono pode ajustar o que ela vê."],
    },
    "flows": {
        "oque": "Heimdall Flows: automações e agendamentos do Heimdall, como o resumo de e-mails e a chegada dos dados de saúde. Tecnologia: n8n.",
        "como": ["Entre pelo Cloudflare Access e depois pelo login próprio do n8n, que o programa não deixa desligar.",
                 "Abra o fluxo desejado para ver ou editar os passos.",
                 "Mudanças nos fluxos do repositório são aplicadas pelo dono com heimdall flows."],
        "so_dono": True,
    },
    "status": {
        "oque": "Heimdall Status: monitora se os serviços do Heimdall estão no ar e avisa quando algum cai. Tecnologia: Uptime Kuma.",
        "como": ["Abra o serviço: ele entra direto no painel.",
                 "Cada monitor mostra a disponibilidade; em Configurações ficam as notificações e a aparência.",
                 "Pausar e retomar serviços também se faz na aba Serviços do Heimdall Controls."],
        "so_dono": True,
    },
}
