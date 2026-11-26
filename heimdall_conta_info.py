#!/usr/bin/env python3
"""Texto do tour da página Account (account.heimdall-ai.tech): o que cada serviço faz e como configurar. A chave é a mesma de heimdall_usuarios.SERVICOS.

Para acrescentar um serviço ou mudar um texto, edite só aqui. "como" é uma lista de passos; "so_dono" avisa que convidados não o recebem;
"multiusuario" diz o que muda quando outras pessoas puderem usá-lo (aparece só para quem pode abrir o serviço).
"""
INFO = {
    "lab": {
        "oque": "Painel web do emulador de AWS do Heimdall, com S3, Lambda, Glue, Athena e um console geral, para estudar e testar sem custo.",
        "como": ["Entre pelo Cloudflare Access, com a sua conta Microsoft e a aprovação no Authenticator.",
                 "Escolha na barra do alto o serviço da AWS que quer usar: S3, Lambda, Glue, Athena ou Console.",
                 "Nada precisa ser configurado: os recursos ficam em um emulador local, sem custo na AWS."],
    },
    "notas": {
        "oque": "Site simples para ler as notas de estudo e ouvir os áudios, feito para leitor de tela.",
        "como": ["Abra o serviço e escolha a nota na lista.",
                 "Para ouvir, use o botão de reproduzir da própria nota.",
                 "O conteúdo vem do app Notas e da triagem do Heimdall."],
    },
    "news": {
        "oque": "Notícias das últimas 24 horas com resumo feito por inteligência artificial, e feeds RSS para ler no iPhone.",
        "como": ["Abra o serviço e leia os resumos por fonte.",
                 "Para ler no iPhone, copie o endereço do feed RSS da fonte e assine no seu leitor de RSS.",
                 "As fontes são configuradas pelo dono do Heimdall."],
    },
    "saude": {
        "oque": "Dados do iPhone e do Apple Watch num banco pessoal, análises, relatório semanal e um painel somente de leitura.",
        "como": ["No iPhone, o app Health Auto Export envia os dados ao Heimdall com o token gerado em Integrações, no Account.",
                 "Abra o painel para ver o dia, as anomalias e as tendências.",
                 "Para conferir se os dados estão chegando, veja o estado da integração em Integrações, no Account."],
        "so_dono": True,
        "multiusuario": "Hoje o serviço é usado apenas pelo dono. Uma versão para outras pessoas está prevista no roadmap: cada uma conectará os próprios serviços de saúde, com os dados guardados separadamente.",
    },
    "learn": {
        "oque": "Plataforma de estudos: pastas de material com categoria (aleatório ou sequencial) e tipo (idiomas, programação, filosofia, medicina e outros), e importação de documentos.",
        "como": ["Crie uma pasta, escolha a categoria e o tipo, e importe PDF, Markdown, texto, Word, EPUB ou áudio.",
                 "Subpastas herdam categoria, tipo e idioma da pasta de cima.",
                 "A partir do material, o Learn gera perguntas, lições e cards, e você responde por texto ou por voz."],
        "so_dono": True,
    },
    "trading": {
        "oque": "Mesa de operações em simulação, feita para teclado e leitor de tela: cotação, ordens a mercado e limitadas, carteira, limite por ordem e limite de perda por dia. Nenhuma ordem é enviada a corretora.",
        "como": ["Na Mesa, informe o código do ativo, a quantidade e o tipo da ordem, e use Comprar ou Vender. Os atalhos da Mesa estão no Guia de comandos, na Ajuda.",
                 "Em Ajustes, defina os limites, a fonte das cotações (simulada, manual ou brapi) e o caixa inicial da conta simulada.",
                 "A IA só descreve os números e os movimentos recentes: nunca recomenda comprar ou vender. Quem decide é você."],
        "so_dono": False,
    },
    "memory": {
        "oque": "Documentos pesquisáveis: envie PDF, foto, Word ou texto, e o Memory lê o texto (com OCR em imagens), sugere título, tipo e etiquetas e permite pesquisar em tudo.",
        "como": ["Em Adicionar, envie arquivos pelo navegador ou coloque-os na pasta de entrada.",
                 "Em Documentos, pesquise por qualquer palavra do texto, do título, do emissor ou das etiquetas; a busca ignora acentos.",
                 "Documentos novos ficam em A revisar até você confirmar ou corrigir as sugestões. Excluir manda para a lixeira."],
        "so_dono": False,
    },
    "jogos": {
        "oque": "Jogos leves no navegador, feitos para leitor de tela: forca, jogo da velha, xadrez, sudoku, 2048, batalha naval, aventuras de texto e outros.",
        "como": ["Abra o serviço e escolha o jogo na lista.",
                 "O que acontece na partida é dito em voz alta pelo leitor de tela, e tudo se joga com teclado.",
                 "Nada é gravado no servidor; não há o que configurar."],
    },
    "finance": {
        "oque": "Contas conectadas pelo Open Finance, extratos, planilhas, boletos e investimentos reunidos em páginas de texto para leitor de tela, com gastos por categoria, tendências, alertas e o campo Perguntar.",
        "como": ["Conecte suas contas pelo Open Finance ou importe extratos e planilhas nos Ajustes do Finance.",
                 "Abra o serviço para ver gastos por categoria, tendências, boletos e investimentos.",
                 "Os dados ficam no ambiente do Heimdall; cópias cifradas podem ser mantidas na nuvem da Cloudflare, conforme a Política de Privacidade."],
        "so_dono": True,
        "multiusuario": "Hoje o serviço é usado apenas pelo dono. Uma versão para outras pessoas está prevista no roadmap: cada uma conectará as próprias contas bancárias, com os dados guardados separadamente.",
    },
    "controls": {
        "oque": "Central de controle do Heimdall: Terminal no navegador, serviços ligados e desligados, usuários e acessos, ajustes do .env e manutenção.",
        "como": ["Entre como dono pelo Cloudflare Access.",
                 "Use a aba Usuários para convidar pessoas e escolher os serviços de cada uma.",
                 "Use a aba Ajustes para mudar as variáveis e Manutenção para reiniciar e atualizar."],
        "so_dono": True,
    },
    "chat": {
        "oque": "Chat: conversa com modelos de inteligência artificial, locais ou da nuvem conforme a configuração do dono, com histórico e ferramentas. Tecnologia: Open WebUI.",
        "como": ["Abra o serviço: a entrada é automática, pelo e-mail da sua conta Microsoft.",
                 "Escolha o modelo no alto da conversa e escreva a mensagem.",
                 "Uma conta é criada na primeira entrada; o dono pode ajustar o que ela vê."],
    },
    "flows": {
        "oque": "Flows: automações e agendamentos do Heimdall, como o resumo de e-mails e a chegada dos dados de saúde. Tecnologia: n8n.",
        "como": ["Entre pelo Cloudflare Access e depois pelo login próprio do n8n, que o programa não deixa desligar.",
                 "Abra o fluxo desejado para ver ou editar os passos.",
                 "Mudanças nos fluxos do repositório são aplicadas pelo dono com studio flows."],
        "so_dono": True,
    },
    "status": {
        "oque": "Status: monitora se os serviços do Heimdall estão no ar e avisa quando algum cai. Tecnologia: Uptime Kuma.",
        "como": ["Abra o serviço: ele entra direto no painel.",
                 "Cada monitor mostra a disponibilidade; em Configurações ficam as notificações e a aparência.",
                 "Pausar e retomar serviços também se faz na aba Serviços do Controls."],
        "so_dono": True,
    },
}
