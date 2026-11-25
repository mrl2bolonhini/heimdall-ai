# Roadmap

Os próximos recursos do Heimdall-ai, na ordem em que pretendo fazê-los. São intenções, não promessas, e não têm data.

<!-- Formato: cada "## Nome" é uma etapa, com uma linha de nota e itens "- Título: descrição". O site é gerado deste arquivo (python3 gerar_docs.py); o que for entregue passa para o CHANGELOG.md. Ordem revisada pelo PO em 25/11/2026. -->

## Em andamento
O que está sendo montado ou conferido agora, na ordem de prioridade.
- Servidor próprio, fase 0 (plano em guides/migracao_servidor.txt): a conta na Locaweb foi criada e o chamado com as seis perguntas (Docker, SLA, multa, preço nos 24 meses, backup, IP e proteção) foi aberto em 25/11/2026. Próximos passos: registrar as respostas no plano, decidir contrato e orçamento (a VPS fica fora do teto de US$ 15 da Cloudflare) e só então contratar e começar a fase 1 (servidor em paralelo, só leitura). Enquanto a resposta não chega, a fase 2 (embeddings com bge-m3 no Workers AI, medindo a qualidade em português) pode andar, porque só depende da Cloudflare.
- Continuidade na nuvem, conferência (plano em guides/continuidade_nuvem.txt): implantada em 23/11/2026, com Worker, rotas, contêiner, cópia cifrada dos bancos no R2 e deploy automático pela main. Próximos passos: teste de queda de verdade (desligar o Mac de propósito), medir a subida a frio e a memória do standard-1 com os sete sites, conferir se o Cloudflare Access libera a requisição antes do contêiner e acompanhar o consumo do mês na aba Nuvem. O diário de alterações (fase 5) espera o servidor virar a fonte dos dados, para não ser feito duas vezes.
- Validar os modelos do chat: as ferramentas e os 8 modelos (heimdall chat --import) estão prontos. Falta testar cada modelo com perguntas reais e acertar o formato das respostas; um modelo local já inventou números quando não tinha acesso à ferramenta.
- Dados separados por pessoa (plano em guides/dados_por_pessoa_plano.txt): a fundação, o Learn e o site de Saúde já separam os dados de cada pessoa. Próximos passos: o backup diário incluir db/people e, depois, Notes, News, Games e o Chat guardarem os dados por pessoa.
- Revisão da navegação e dos textos de todos os serviços: Health (portal com Resumo, Medidas, Prontuário e Acompanhamento) e Finance já seguem o padrão. Próximos passos, serviço por serviço (Lab, Notes, News, Learn, Games, Controls): poucas abas agrupadas por assunto, subabas, subaba Ajuda dentro dos Ajustes, mensagens de erro e aviso em linguagem de produto e sem dados pessoais do dono (por exemplo, o perfil de exemplo em flows/advanced/7-digest-hiperpersonalizado.json). Depois: README, notificações (Bark e Mac) e site público.
- Exames no relatório da semana e lembrete de documento pendente há dias: hoje a triagem avisa os pendentes a cada 4 horas, mas o relatório da semana ainda não traz os exames. Glicemia: as regras de alerta e o tipo glicose no Atalho já existem; falta chegar dado de glicose no app Saúde.

## Depois
Recursos maiores, que dependem dos anteriores.
- Servidor próprio, fases 1 a 6: servidor em paralelo, fonte dos dados no servidor, Mac como ponte Apple, continuidade apontando para o servidor, cópia cifrada também dos arquivos (não só dos bancos) no R2 e chat próprio sobre o LiteLLM no lugar do Open WebUI (cada projeto com instrução, modelo, artefatos e histórico próprios). Cada fase com interruptor no .env e cópia no Mac.
- Conectores dos seus aplicativos: caixa de correio (heimdall-sync), cliente do Mac, Integrações na Conta, endereço do Health Auto Export e conversor do Atalho prontos. Próximos passos: montar o Atalho mestre uma vez, compartilhá-lo por link do iCloud e personalizar com código de pareamento; Notas, Lembretes e Calendário por conta Apple ou Google; Atalhos do iPhone e do Android. Cada conector com tela de ligar, testar e desligar.
- Vários sistemas (Windows, macOS, iPhone e Android), em partes: primeiro conferir documentos de saúde e as demais ações pelo painel, sem terminal, e enviar documentos pelo celular; depois instalador e comando equivalente ao heimdall para Windows e Linux; por fim, alternativa ao agente do Mac (Calendário e Lembretes) em outros sistemas.
- App nativo do Heimdall para iPhone (fase 7 do servidor): HealthKit com entrega em segundo plano, Calendário e Lembretes pela API de eventos do iOS, login sem colar token e envio à caixa de correio. Depende da conta de desenvolvedor da Apple (US$ 99 por ano), dos dados por pessoa e do teste com VoiceOver no Mac.
- App do Heimdall para o Mac, distribuição: a primeira versão está em uso (heimdall app). Falta o instalador .pkg e assinar e notarizar com a mesma conta de desenvolvedor.
- Documentos pesquisáveis: Paperless-ngx em subdomínio próprio, com leitura de texto nos PDFs e etiquetas automáticas.
- Linha do tempo de privacidade e processos: diários oficiais, menções na internet e e-mails de serviços públicos lado a lado.
- Mesa de operações em simulação (trading): tela feita para teclado e leitor de tela, só em simulação, com limites por ordem e de perda por dia; a IA avisa, quem decide é você e a execução fica em código com regras fixas.

## Ideias em avaliação
Ainda sem decisão.
- Health e Finance para várias pessoas, com política de dados para clientes: cada usuário com os próprios dados, isolamento total, consentimento e nenhum dado real compartilhado.
- Produto financeiro próprio (fintech) por parceria com uma instituição receptora do Open Finance (plano em guides/fintech_plano.txt). Depende do item acima.
- Áudio no iPhone: anexar o áudio dos estudos às notas direto pelo iPhone.
- App nativo para Android, só se alguém precisar: Health Connect, Calendário do Android e Tarefas do Google; conta de desenvolvedor do Google (cerca de US$ 25) ou APK instalado direto.
