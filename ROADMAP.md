# Roadmap

Os próximos recursos do Heimdall-ai, na ordem em que pretendo fazê-los. São intenções, não promessas, e não têm data.

<!-- Formato: cada "## Nome" é uma etapa, com uma linha de nota e itens "- Título: descrição". O site é gerado deste arquivo (python3 gerar_docs.py); o que for entregue passa para o CHANGELOG.md. Ordem revisada pelo PO em 25/11/2026, com as prioridades escolhidas pelo usuário e o contexto de guides/contexto_projeto.txt. -->

## Em andamento
O que está sendo feito agora, na ordem de prioridade escolhida em 25/11/2026.
- Dados separados por pessoa (plano em guides/dados_por_pessoa_plano.txt): a fundação, o Learn e o Health (perfil, sugestões e painel por pessoa) já separam os dados. Próximos passos, nesta ordem: o backup diário cifrado incluir db/people, com restauração testada; depois Notes, News, Games e o Chat guardarem os dados de cada pessoa, um serviço por vez, cada um com teste de que uma pessoa não vê os dados da outra.
- Exames no relatório da semana: o relatório semanal (heimdall_saude.relatorio_semanal) passa a trazer os exames e documentos confirmados na semana e os resultados fora da faixa, e lembra o documento pendente de conferência há mais de alguns dias (hoje a triagem avisa a cada 4 horas). O aviso do Bark continua sem números de saúde. Glicemia: as regras de alerta e o tipo glicose no Atalho já existem; falta chegar dado de glicose no app Saúde.
- Revisão da navegação e dos textos dos demais serviços: Health e Finance já seguem o padrão (abas por assunto, subabas, Ajustes como botão). Ordem sugerida, um serviço por entrega: Notes, News, Learn, Lab, Controls e Games. Em cada um: até cerca de 6 abas agrupadas por assunto, subabas, telas enxutas sem comandos de terminal, mensagens de erro e aviso em linguagem de produto e sem dados pessoais do dono, e a subaba Ajuda dentro dos Ajustes (que ainda não existe em nenhum serviço). Depois: o fluxo de digest hiperpersonalizado, o README, as notificações (Bark e Mac) e o site público.
- Apps da Apple: primeiro passo do usuário, assinar o Apple Developer Program (US$ 99 por ano). Depois, nesta ordem: (1) app do Mac, que já está em uso (heimdall app) mas é assinado só localmente: assinar com o certificado de desenvolvedor, notarizar e gerar o instalador .pkg, para outras pessoas instalarem por download; (2) app do iPhone, primeira versão: HealthKit com entrega em segundo plano, Calendário e Lembretes pela API de eventos do iOS, login sem colar token e envio à caixa de correio já pronta (formato do Health Auto Export). Depende dos dados por pessoa (backup de db/people). Compilação e teste só no Mac do usuário, com VoiceOver. O app Notas do iPhone não tem API: continua pelo Atalhos ou por compartilhar a nota.

## A seguir
Já começados ou com plano pronto, depois das prioridades acima.
- Servidor próprio, fase 0 (plano em guides/migracao_servidor.txt): conta na Locaweb criada e chamado aberto com seis perguntas em 25/11/2026. Próximos passos: registrar as respostas no plano, decidir contrato e orçamento (a VPS fica fora do teto de US$ 15 da Cloudflare) e então a fase 1 (servidor em paralelo, só leitura). A fase 2 (embeddings com bge-m3 no Workers AI, medindo a qualidade em português) pode andar antes, porque só depende da Cloudflare.
- Continuidade na nuvem, conferência (guides/continuidade_nuvem.txt): implantada em 23/11/2026 com deploy automático pela main. Próximos passos: teste de queda de verdade (desligar o Mac de propósito), medir a subida a frio e a memória do contêiner com os sete sites e acompanhar o consumo na aba Nuvem. O diário de alterações espera o servidor virar a fonte dos dados.
- Validar os modelos do chat: os 8 modelos e o modo enxuto do Open WebUI estão prontos. Falta testar cada modelo com perguntas reais e acertar o formato das respostas; um modelo local já inventou números quando não tinha a ferramenta.
- Respostas pendentes (com o usuário): cotações de Open Finance (Tecnospeed, Klavi, Belvo e Pluggy; a tarefa agendada diária resume as respostas), para decidir entre o Meu Pluggy atual, uma parceria ou nenhuma mudança; escolha do nome do produto (favoritos: Baken, Bantay e Sandigan) e consulta no INPI.

## Depois
Recursos maiores, que dependem dos anteriores.
- Servidor próprio, fases 1 a 6: servidor em paralelo, fonte dos dados no servidor, Mac como ponte Apple, continuidade apontando para o servidor, cópia cifrada também dos arquivos no R2 e chat próprio sobre o LiteLLM no lugar do Open WebUI (cada projeto com instrução, modelo, artefatos e histórico próprios). Cada fase com interruptor no .env e cópia no Mac.
- Conectores dos seus aplicativos: caixa de correio (heimdall-sync), cliente do Mac, Integrações na Conta, endereço do Health Auto Export e conversor do Atalho prontos. Próximos passos: Atalho mestre compartilhado por link do iCloud com código de pareamento (ponte até o app do iPhone), Notas, Lembretes e Calendário por conta Apple ou Google e Atalhos do Android. Cada conector com tela de ligar, testar e desligar.
- Vários sistemas (Windows, macOS, iPhone e Android), em partes: primeiro conferir documentos de saúde e as demais ações pelo painel, sem terminal, e enviar documentos pelo celular; depois instalador e comando equivalente ao heimdall para Windows e Linux; por fim, alternativa ao agente do Mac (Calendário e Lembretes) em outros sistemas.
- Documentos pesquisáveis: Paperless-ngx em subdomínio próprio, com leitura de texto nos PDFs e etiquetas automáticas.
- Linha do tempo de privacidade e processos: diários oficiais, menções na internet e e-mails de serviços públicos lado a lado.
- Mesa de operações em simulação (trading): tela feita para teclado e leitor de tela, só em simulação, com limites por ordem e de perda por dia; a IA avisa, quem decide é você e a execução fica em código com regras fixas.

## Ideias em avaliação
Ainda sem decisão.
- Health e Finance para várias pessoas, com política de dados para clientes: cada usuário com os próprios dados, isolamento total, consentimento e nenhum dado real compartilhado.
- Produto financeiro próprio (fintech) por parceria com uma instituição receptora do Open Finance (plano em guides/fintech_plano.txt). Depende do item acima e das cotações de Open Finance.
- Áudio no iPhone: anexar o áudio dos estudos às notas direto pelo iPhone (pode entrar no app do iPhone).
- App nativo para Android, só se alguém precisar: Health Connect, Calendário do Android e Tarefas do Google; conta de desenvolvedor do Google (cerca de US$ 25) ou APK instalado direto.
