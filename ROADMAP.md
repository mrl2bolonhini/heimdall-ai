# Roadmap

Os próximos recursos do Heimdall-ai, na ordem em que pretendo fazê-los. São intenções, não promessas, e não têm data.

<!-- Formato: cada "## Nome" é uma etapa, com uma linha de nota e itens "- Título: descrição". O site é gerado deste arquivo (python3 gerar_docs.py); o que for entregue passa para o CHANGELOG.md. -->

## Em andamento
O que está sendo montado ou conferido agora.
- Perguntas ao banco pelo chat: quatro ferramentas (banco_resumo, banco_consultar, banco_buscar e saude_historico) deixam perguntar em português sobre saúde, diários oficiais, e-mails, estudos, privacidade e Second Brain. Já funcionam pelo terminal; falta ligá-las ao chat, validar com cada modelo local (um modelo já inventou números quando não tinha acesso à ferramenta) e acertar o formato das respostas.

## Em seguida
O que vem depois de validar o banco.

## Depois
Recursos maiores, que dependem dos anteriores.
- Documentos pesquisáveis: Paperless-ngx em subdomínio próprio, com leitura de texto nos PDFs e etiquetas automáticas.
- Heimdall Estudos: painel em subdomínio próprio, no mesmo padrão dos outros sites, com ferramentas específicas para estudar. Começa pelo progresso (temas vistos, lacunas e revisão espaçada, a partir da tabela de estudos); as demais ferramentas serão definidas por você ao longo do caminho. O Second Brain entra aqui como uma das ferramentas do painel, em vez de painel separado: notas, conexões entre áreas, lacunas de estudo e perguntas sugeridas.
- Mesa de operações em simulação (trading): tela própria, feita para teclado e leitor de tela, com atalhos para comprar, vender, zerar a posição e cancelar tudo, cotações e carteira. Começa só em simulação (papel), sem enviar ordem nenhuma, com limites de valor por ordem e de perda por dia. Uma IA local acompanha tendências e avisa enquanto você opera; quem decide e confirma cada ordem é você. A execução fica em código com regras fixas, nunca com a IA. Ordens reais só se houver uma corretora com API oficial e depois de testar na simulação.
- Linha do tempo de privacidade e processos: diários oficiais, menções na internet e e-mails de serviços públicos lado a lado.

## Ideias em avaliação
Ainda sem decisão.
- Resposta como suporte@: enviar e-mails com o endereço de suporte pelo Cloudflare Email Sending.
- Áudio no iPhone: anexar o áudio dos estudos às notas direto pelo iPhone.
- Política de dados para clientes: se o projeto passar a atendê-los, acesso separado por usuário e nenhum dado real compartilhado.
