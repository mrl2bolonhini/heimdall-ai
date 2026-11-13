# Roadmap

Os próximos recursos do Heimdall-ai, na ordem em que pretendo fazê-los. São intenções, não promessas, e não têm data.

<!-- Formato: cada "## Nome" é uma etapa, com uma linha de nota e itens "- Título: descrição". O site é gerado deste arquivo (python3 gerar_docs.py); o que for entregue passa para o CHANGELOG.md. -->

## Em andamento
O que está sendo montado ou conferido agora.
- Perguntas ao banco pelo chat: quatro ferramentas (banco_resumo, banco_consultar, banco_buscar e saude_historico) deixam perguntar em português sobre saúde, diários oficiais, e-mails, estudos, privacidade e Second Brain. Já funcionam pelo terminal; falta ligá-las ao chat, validar com cada modelo local (um modelo já inventou números quando não tinha acesso à ferramenta) e acertar o formato das respostas.

## Em seguida
O que vem depois de validar o banco.
- Painel do Second Brain: notas, conexões entre áreas, lacunas de estudo e perguntas sugeridas.
- Login pelo GitHub: entrar nos painéis com a conta do GitHub, depois de reforçá-la com senha gerada e chave de acesso.
- Cópia de segurança no Cloudflare R2: o código e o fluxo já existem e gravam em uma pasta (iCloud Drive); falta ativar o R2 no painel da Cloudflare e criar a chave de acesso para ligar o segundo destino.

## Depois
Recursos maiores, que dependem dos anteriores.
- Documentos pesquisáveis: Paperless-ngx em subdomínio próprio, com leitura de texto nos PDFs e etiquetas automáticas.
- Painéis livres: Metabase ou Grafana sobre o banco, para cruzar saúde, estudos e avisos.
- Progresso de estudos: temas vistos, lacunas e revisão espaçada, a partir da tabela de estudos.
- Linha do tempo de privacidade e processos: diários oficiais, menções na internet e e-mails de serviços públicos lado a lado.

## Ideias em avaliação
Ainda sem decisão.
- Resposta como suporte@: enviar e-mails com o endereço de suporte pelo Cloudflare Email Sending.
- Áudio no iPhone: anexar o áudio dos estudos às notas direto pelo iPhone.
- Política de dados para clientes: se o projeto passar a atendê-los, acesso separado por usuário e nenhum dado real compartilhado.
