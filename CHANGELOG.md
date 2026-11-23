# Novidades

Registro dos recursos do Heimdall-ai, do mais recente ao mais antigo. Cada recurso novo ganha um bloco "## AAAA-MM-DD - título" com itens iniciados por hífen, acima dos anteriores. As páginas do site são geradas deste arquivo.

## 2026-11-23 - Perguntar em estilo de chat e abas mais enxutas no leitor de tela
- O Perguntar não precisa mais do botão Atualizar respostas: ao enviar, o foco continua no campo, a página confere sozinha de 3 em 3 segundos e, quando o modelo termina, o leitor de tela anuncia "Resposta pronta" com o texto. As respostas ficam acima do campo, em ordem de conversa (a mais recente embaixo, perto do campo). Vale para Finance, Health, News, Notes e Learn. Sem JavaScript, um botão Atualizar respostas continua existindo.
- O campo não tem mais o atributo obrigatório (o balão de validação do navegador atrapalhava o VoiceOver); pergunta vazia é avisada no estado, sem recarregar.
- Abas: cada aba deixou de ter a descrição "Atalho: Option Shift N", que o VoiceOver lia a cada seta e na leitura da página. Agora há uma dica só, ligada ao conjunto de abas ("Atalho: Option Shift 1 a N"), e o texto oculto não entra mais na leitura corrida.

## 2026-11-23 - Learn: Resumo na tela inicial e Novo estudo numa tela só
- A tela inicial do Learn começa com um Resumo em texto: quantos temas estão cadastrados e, por tema, a categoria, quantos documentos de consulta, estudos e lições. Os botões Novo estudo e Ajustes ficam acima, e a lista numerada de temas leva ao tema.
- Novo estudo é um formulário só: dê o nome do tema (ou escolha a pasta mãe), envie os arquivos, escolha a categoria e o tipo de estudo numa lista de opções, com a explicação de cada tipo logo abaixo do nome, e toque em Criar. Os arquivos aceitos entram na hora; os que não servem são avisados pelo nome. Tipo novo se cadastra ali mesmo.
- A página "Tipos de estudo e suas regras" saiu do menu e agora fica em Ajustes.

## 2026-11-23 - Perguntar no Learn
- Campo Perguntar no fim de cada aba do tema (Estudos, Lições, Exercícios, Cards, Progresso) e na lista de temas. O modelo responde só com o seu progresso e o que você fez no tema: estudos com pergunta, resposta e correção, lições e notas, exercícios errados, cards. Os trechos estudados (do estudo e da lição, com a explicação) vão junto, para você perguntar sobre o texto e pedir explicação; o livro inteiro e o gabarito de lição em aberto não vão; a resposta de um tema não aparece em outro.
- Nova regra no CLAUDE.md: todo serviço com dados pessoais tem o Perguntar.

## 2026-11-23 - Learn organizado por tema
- A tela inicial do Learn agora é a lista de temas (a aba Início deixou de existir), com os botões Novo estudo e Ajustes. Ao escolher um tema, as abas passam a mostrar só o que é dele: tema sequencial tem Lições, Exercícios, Cards e Progresso; tema aleatório tem Estudos, Cards e Progresso. Trocar de tema volta à lista.
- Mudar a categoria de um tema muda as abas na hora e não apaga nada: se o tema já tem lições (ou estudos), a aba correspondente continua aparecendo para consulta.
- Ajustes virou um botão no topo, ao lado de Trocar de tema, e abre uma tela sem abas: geral (agenda, avisos, estudos por dia) e, com um tema escolhido, as configurações dele (agenda, importar documentos, categoria e tipo, arquivar).
- A aba Estudos lista todos os estudos do tema (inclusive os importados das notas antigas) e tem o botão de sortear; a aba Lições tem o progresso e o botão Próxima lição por pasta.
- A migração também leva as notas dos primeiros dias em que o modelo não devolveu pergunta: elas entram com o trecho lido e o estado "erro na pergunta", e o botão Tentar de novo gera a pergunta no Learn.
- A simulação da migração (heimdall learn --migrate) agora conta as notas por pasta e avisa os temas do cofre que ainda não têm pasta no Learn.

## 2026-11-23 - Estudos no Learn; Notes só com triagem, diários e privacidade
- Os estudos saíram do Notes. Com HEIMDALL_LEARN=1, o Notes não mostra mais os temas de estudo (knowledge/ e os livros do cofre) e fica com triagem, diários, privacidade, Second Brain e saúde; HEIMDALL_LEARN=0 devolve os estudos ao Notes. O Notes passou a ser só do dono: convidado não entra nele, e Notes não pode mais ser dado a convidado na aba Usuários.
- Migração do que já existe: heimdall learn --migrate mostra o que seria levado (notas dos livros no cofre e a tabela estudos do banco) e heimdall learn --migrate --apply grava no Learn com o estado importado, copiando os áudios. Pode rodar de novo sem duplicar, e nada é apagado nem movido nos originais.
- Estudos por dia no Learn: às 6h, 13h e 20h a agenda sorteia uma pasta com material e um trecho, faz a pergunta e avisa. Padrão 3 por dia para o dono e 0 para convidados; escolha de 0 a 3 na aba Ajustes. Isso substitui o fluxo "estudo dos livros" do n8n: com o Learn ligado, o instalador dos fluxos importa o fluxo 13, mas o deixa desligado (para desligar já, abra o n8n e desative "Heimdall: estudo dos livros").
- O modelo de chat Notes perdeu a conexão com a tabela de estudos (banco-estudos): perguntas de estudo vão para o modelo Learn.

## 2026-11-23 - Dados separados por pessoa: fundação e Learn
- A sessão de convidado do Cloudflare Access agora carrega quem é a pessoa (um id derivado do e-mail, assinado dentro do cookie). Novo heimdall_pessoas.py decide onde ficam os dados de cada uma. O dono mantém os caminhos de sempre, sem migração.
- Learn: cada convidado tem a sua pasta em db/pessoas/<id>/ com o próprio banco, o próprio material (fora do knowledge/ do dono, então a busca nos documentos não o enxerga), áudios, agenda, cards, lições, progresso e ajustes. A agenda percorre o dono e cada pessoa; só o dono recebe aviso no Mac e no iPhone (convidados veem os cards na aba Cards). Tarefas em segundo plano (perguntas, lições, correções) trabalham com os dados de quem pediu.
- Sessões antigas de convidado, sem a pessoa dentro, são mandadas entrar de novo pelo Access. HEIMDALL_PESSOAS=0 devolve o comportamento anterior (todos usam os dados do dono); heimdall env --set HEIMDALL_PESSOAS 0 ou 1.
- Os outros serviços (Cloud, Notes, News, Games e o Chat) já sabem quem é a pessoa, mas ainda guardam os dados juntos: entram nas próximas fases do plano.

## 2026-11-23 - Plano de dados separados por pessoa
- Novo guides/dados_por_pessoa_plano.txt: desenho para que cada pessoa tenha os seus dados separados dos do dono em todos os serviços (uma pasta por pessoa, com um banco por serviço, e um módulo único que escolhe o caminho). Só o plano; nada foi construído.

## 2026-11-23 - Learn: aba Ajustes
- Nova aba Ajustes no Learn: pausar ou ligar a agenda de cards e lições e os avisos (vale na hora, sem reiniciar; HEIMDALL_LEARN_AGENDA=0 e HEIMDALL_LEARN_NOTIFICAR=0 no .env continuam mandando), e, para cada pasta, cards por dia, lições por dia e horário. Atalhos para Novo estudo e para os tipos.
- Arquivar pasta, com confirmação: a pasta e as subpastas saem do Learn e da busca nos documentos, mas nada é apagado. Os arquivos vão para knowledge/.arquivo/ (pasta oculta, o nome ganha (2) se já existir) e o histórico de lições, estudos e cards fica guardado. Para desfazer, mova a pasta de volta para knowledge/ e rode heimdall learn --sync. Os documentos já indexados na busca saem do índice na próxima vez que você rodar heimdall ingest.

## 2026-11-23 - Learn: abas novas e Novo estudo por botão
- As abas do Learn agora são Início, Lições, Exercícios, Cards e Progresso. Nova pasta e Tipos saíram das abas: no Início há o botão Novo estudo (nome, categoria e tipo, ou um tipo novo na hora) e o botão Ver os tipos de estudo e suas regras.
- Aba Exercícios: todos os exercícios das lições com a sua resposta e o resultado (certo, parcial ou errado); a resposta esperada só aparece depois de concluir a lição. Filtro para ver só o que você errou.
- Aba Progresso: dias seguidos de estudo, por pasta (lições concluídas, média, estudos corrigidos, cards lidos) e acertos por tipo de exercício.

## 2026-11-23 - App do Mac com o Learn
- O app ganhou o Learn no menu Abrir (janela própria, atalho Command+7) e o comando Cadastrar as pastas de estudo novas (heimdall learn --sync) no menu Arquivo e no menu de estado. Com o Learn entrando na ordem alfabética, News passou a Command+8, Notes a Command+9, e Status e Flows ficam sem atalho. Rode heimdall app de novo para compilar.
- heimdall env --set agora grava HEIMDALL_LEARN_AGENDA e HEIMDALL_LEARN_NOTIFICAR (só 0 ou 1), para ligar e desligar a agenda e o aviso do Learn sem editar o .env.

## 2026-11-23 - Heimdall Learn completo: lições, voz, cards e modelo Learn
- Fase 3, lições sequenciais: em pasta sequencial, Próxima lição gera explicação, trecho de estudo e 3 a 5 exercícios (alternativas e texto) a partir do material, dois trechos por lição, uma lição aberta por vez. Você responde, a correção vem exercício a exercício (certo, parcial, errado) e a lição conclui. Há progresso da pasta e áudio do trecho e da explicação.
- Fase 4, voz: o botão Gravar resposta usa o microfone do navegador, transcreve no Mac (whisper-cpp, mlx_whisper ou whisper, com ffmpeg ou afconvert), você edita o texto e envia. O áudio é apagado depois de transcrito (HEIMDALL_LEARN_GUARDAR_VOZ=1 guarda em db/voz). Variáveis: HEIMDALL_LEARN_WHISPER_MODELO e HEIMDALL_LEARN_WHISPER_TAMANHO.
- Fase 5, cards e agenda: por pasta, de 0 a 3 cards por dia (de 4 em 4 horas a partir do horário) e uma lição por dia em pasta sequencial. Aviso no Mac e no Bark com o texto do card; HEIMDALL_LEARN_AGENDA=0 desliga a agenda e HEIMDALL_LEARN_NOTIFICAR=0 tira o aviso. Se o modelo falhar, tenta de novo em 30 minutos. Aba Cards com marcar como lido.
- Modelo Learn no chat (agora 8 modelos), com a conexão banco-learn: learn_progresso, learn_licoes (com seus erros) e learn_cards, só leitura. Rode heimdall chat --import.
- Modelos locais por padrão; se a nuvem estiver ligada, lições e correções entram no teto de US$ 15 por mês.

## 2026-11-22 - Heimdall Learn, fase 2 (modo aleatório) e catálogo de tipos
- Learn publicado em learn.heimdall-ai.tech: rota no túnel (porta 8019), DNS e o endereço entrou no aplicativo do Cloudflare Access do dono (mesma política, com Authenticator). Continua desligado no Mac até HEIMDALL_LEARN=1.
- Catálogo de tipos com regras próprias (heimdall_learn_tipos.py): Idiomas, Programação, Exatas, Arquitetura e dados, Filosofia, Humanas, Direito, Medicina, Esoterismo e Outro. Cada um define a categoria sugerida, o que a IA faz, o que evita, as regras do prompt e o que vem depois. A aba Tipos mostra tudo; tipo que você cadastra usa o perfil genérico. Na criação da pasta, sem categoria escolhida, vale a sugerida pelo tipo.
- Modo aleatório: em pasta de categoria aleatório, o botão Sortear trecho e perguntar escolhe um trecho do material (txt, Markdown, Word, EPUB e PDF com pdftotext, também nas subpastas, sem repetir os últimos 30), o modelo faz uma pergunta, você responde, e a correção vem com base no trecho, mais o trecho consultado, matérias sugeridas e o botão Gravar áudio do trecho (voz do macOS, no idioma de estudo quando a pasta é de idiomas). Tudo fica em db/learn.db (tabela estudos); áudios em db/audio.
- O modelo Learn do chat fica para a fase 3, junto com as ferramentas que leem lições e progresso.

## 2026-11-22 - Heimdall Learn, fase 1 (site novo de estudos)
- Novo serviço Heimdall Learn (porta 8019, heimdall learn), desligado por padrão: ligue com heimdall env --set HEIMDALL_LEARN 1 e heimdall update --restart. Usa o mesmo login do Cloud e entra na lista do Cloudflare Access e dos convidados.
- Pastas de estudo em knowledge/ com categoria (aleatório ou sequencial) e tipo aberto (Idiomas, Programação, Filosofia, Medicina, Exatas, Humanas, Arquitetura e dados, Esoterismo, Outro, e os que você cadastrar). Idiomas pede o idioma de estudo. Subpastas herdam categoria, tipo e idioma.
- Importação de documentos pelo site (PDF, Markdown, texto, Word, EPUB, M4A, MP3; limite de 50 MB em HEIMDALL_LEARN_MAX_MB; nunca sobrescreve; permissão só do dono).
- Banco próprio db/learn.db (pastas, tipos, documentos). heimdall learn --sync cadastra as pastas que já existem em knowledge/.
- Fases seguintes, já especificadas em guides/learn_especificacao.txt: perguntas aleatórias com áudio, lições sequenciais com exercícios, voz do aluno, cards e agenda.

## 2026-11-22 - Modelos do Open WebUI criados por comando
- A chave da API do Open WebUI pode ser gravada no .env sem aparecer na tela: copie a chave com Command+C e rode heimdall env --set HEIMDALL_WEBUI_API_KEY.
- Estudos dos livros passaram do Alerts para o Notes: o Notes ganhou a conexão banco-estudos (só banco_buscar e banco_consultar, para a tabela estudos) além da memória e dos documentos, e o prompt do Alerts manda perguntas de estudo para o Notes. O modelo Código virou Code (id code). Rode heimdall chat --import para criar a conexão nova e atualizar os modelos.
- Modelos do chat renomeados e reduzidos de 7 para 6: General (junta Conversas e Curiosidades: conversa livre e pesquisa na web), Alerts (era Meus Dados: diários, e-mails oficiais, estudos, privacidade, avisos e Second Brain), Notes (era Documentos e Memória), Health, Finance e Código. Os ids também mudaram (general, alerts, notes, health, finance). Saíram o modelo Curiosidades e a conexão Internet e Utilidades (feeds, Reddit, NASA e transcrições do YouTube deixam de estar no chat). Rodar heimdall chat --import cria os novos e esconde os antigos, que podem ser apagados no Open WebUI.
- O seletor de modelos do chat mostra só os modelos criados: depois de criá-los, heimdall chat --models esconde os modelos de base (gemma, qwen, deepseek e os -local), que continuam funcionando por baixo. --keep-base não esconde e --show-all mostra de novo.
- Novo heimdall chat --import (scripts/importar_modelos_webui.sh): cria ou atualiza pela API do Open WebUI as conexões de ferramentas (já com o filtro de funções, sem colar à mão) e os 7 modelos com os prompts padrão. --tools faz só as conexões e --models só os modelos. As outras conexões que você já tem ficam como estão. Usa uma chave de API (HEIMDALL_WEBUI_API_KEY no .env, ou digitada na hora, sem aparecer na tela). --dry-run só lista.

## 2026-11-22 - Subpastas em inglês e pasta própria da Saúde
- A Saúde ganhou pasta própria na raiz, como o Finance: health/inbox (solte aqui exames, receitas e encaminhamentos), health/archive (os originais já lidos, só do dono) e health/review (o que não deu para ler, com o motivo). Antes ficava em db/documentos. A migração é automática: na primeira subida a pasta é movida (mesmos arquivos, nada copiado nem apagado) e entrada, arquivados e revisar viram inbox, archive e review. health/ não vai para o Git.
- Subpastas do db: copias para copies, caixa_recebidos para mailbox, avisos_mac para alerts, pessoas para people (a permissão 0700 de people continua). No finance/inbox: importados para imported e revisar para review (e importados para imported dentro de finance/sheets).
- O app do Mac (macapp) passou a ler db/alerts; enquanto o app não for recompilado, o Heimdall mantém avisos_mac se ela já existir. Corrigido de passagem: o app procurava a pasta banco, que já se chamava db.
- Corrigido: o .env tinha HEIMDALL_VAULT_DIR apontando para cerebro, e por isso os serviços recriavam a pasta vazia; agora aponta para brain.
- Teste novo em tests/core/teste_pastas.py cobre todas essas migrações.

## 2026-11-22 - Mais pastas padronizadas e poda dos backups
- Padrão de nomes: pasta em inglês, uma palavra só, sem sublinhado. Mudaram: banco para db, cerebro para brain, qdrant_storage para qdrant, app_mac para macapp e, dentro do finance, entrada para inbox e entrada_planilhas para sheets. As pastas de dados do Mac são renomeadas sozinhas na primeira subida (heimdall update --restart), com os mesmos dados, sem copiar nem apagar; a do Qdrant é feita pelo start_heimdall.sh, que remove o contêiner do Qdrant e o recria apontando para a pasta nova (os dados ficam na pasta). Se não der para renomear, o Heimdall segue com o nome antigo.
- Quem abre a pasta cerebro no Obsidian precisa abrir brain como cofre depois da migração.
- Novo scripts/podar_backups.sh: depois de cada backup do Open WebUI, do n8n e do Qdrant, mantém só os 3 mais recentes de cada tipo (HEIMDALL_BACKUPS_MANTER no .env muda). Cada cópia do Open WebUI tem cerca de 1 GB e a pasta backups tinha chegado a 12 GB. Só mexe em arquivos .tgz com os nomes dos backups.
- O .gitignore passou a ignorar .env.* e *.bak (o .env.bak, com segredos, estava solto).

## 2026-11-22 - Repositório reorganizado em pastas
- Testes: os 64 arquivos de teste saíram da raiz para tests/<serviço>/ (finance, health, news, notes, games, cloud, account, controls, agent, chat, design, monitor, core). Novo ./rodar_testes.sh roda todos (ou uma pasta: ./rodar_testes.sh finance; ./rodar_testes.sh -l lista). Onde estas novidades antigas dizem "python3 teste_x.py", o arquivo agora está em tests/<serviço>/.
- Guias e ajudas foram para guides/ (LEIAME_*, heimdall_ajuda.txt, modelos_open_webui.txt, PUBLICAR_PAGINAS.md, instructions.txt); os prompts do chat para prompts/; os scripts de shell (instalar_*, trocar_*, guardar_no_env.sh etc.) para scripts/. Ficam na raiz subir.sh, start_heimdall.sh, start_ecosystem.sh e heimdall.zsh, porque os LaunchAgents do Mac apontam para eles.
- Fluxos do n8n: n8n_flows, n8n_flows_avancados e n8n_flows_monitor viraram flows/basic, flows/advanced e flows/monitor. A pasta jogos/ virou games/.
- A pasta de dados do Finance, dados_financas/, passa a se chamar finance/. A migração é automática: na primeira subida (heimdall update --restart) a pasta é renomeada, com os mesmos dados (nada é copiado nem apagado). Se HEIMDALL_FINANCE_DIR estiver no .env, ele continua mandando. Novo heimdall_pastas.py guarda a regra.
- O comando heimdall e os instaladores continuam iguais para quem usa; só os caminhos dos arquivos mudaram. Novo teste: tests/core/teste_pastas.py.

## 2026-11-22 - Conversas com pesquisa na web, Qwen3 na nuvem e guia do Open WebUI reescrito
- O Conversas agora pesquisa na web quando a pergunta pede (SearXNG, leitura de página, cálculo e hora), por uma conexão nova e enxuta, a "Web básica (Conversas)", para gastar menos tokens com a lista de ferramentas. Ele passa a ter a base "conversas" no LiteLLM: local, é o mesmo gemma de antes; com HEIMDALL_NUVEM=1 vira o Qwen3 30B do Workers AI, bem mais barato por token que o gpt-oss e o Mistral, com o gemma local como volta (conversas-local). O prompt ganhou a linha /no_think, que desliga o raciocínio do Qwen3 e poupa tokens.
- HEIMDALL_NUVEM_CONVERSAS_MODELO troca o modelo do Conversas (por exemplo, o Mistral Small 3.1: workers-ai/@cf/mistralai/mistral-small-3.1-24b-instruct). Atenção: a página do Qwen3 30B no Workers AI mostrava uma data de descontinuação de 20/11/2026; se a nuvem falhar nesse modelo, o Conversas cai no gemma local e some a pesquisa. Teste com uma pergunta e, se preciso, troque o modelo.
- O guia do Open WebUI (modelos_open_webui.txt) foi reescrito como passo a passo da primeira configuração: antes de começar, seis conexões de ferramentas, sete modelos, teste com pergunta real e o que vai para a nuvem. Os arquivos para importar estão em openwebui/ (agora com a conexão web-basica e o modelo Conversas novos).
- Todos os modelos locais continuam no LiteLLM: listar um modelo não gasta memória (o Ollama só carrega o que é chamado) e todos têm uso: gemma e dolphin (segurança), qwen3-vl (fluxos e imagens), deepseek-coder (GitOps), gemma3-4b (resumos do News) e llama-3.1-8b (modelo local padrão do Perguntar).

## 2026-11-22 - Chat na nuvem (LiteLLM com o gpt-oss-120b)
- Com HEIMDALL_NUVEM=1, o chat do Open WebUI passa a responder pelo gpt-oss-120b da Cloudflare (gateway "heimdall", teto de gasto no gateway) em vez do modelo local, que era lento. Valem para os modelos Meus Dados, Saúde, Finanças, Curiosidades e Documentos e Memória (base qwen3-vl-instruct) e para o Código (base deepseek-coder-v2:16b). O gpt-oss chama as ferramentas (MCP) normalmente.
- Plano de volta: o modelo local continua na lista com o nome "<modelo>-local" e é usado sozinho se a nuvem falhar ou o limite de gasto cortar. Com HEIMDALL_NUVEM=0 (ou sem a chave da Cloudflare) vale o litellm_config.yaml exatamente como antes.
- O Conversas usa outro modelo da nuvem (ver o bloco acima).
- Novo heimdall_litellm.py: gera, a cada subida, banco/litellm_config_efetivo.yaml (permissão 600, fora do git, leva a chave lida do .env) e inicia o LiteLLM com ele; start_heimdall.sh e o Controls passaram a usá-lo. Diferente dos outros usos da nuvem, aqui o interruptor só vale depois de reiniciar o LiteLLM (heimdall restart ou religar o LiteLLM pelo Controls).
- Novo teste: python3 teste_litellm_nuvem.py (sem rede).

## 2026-11-22 - Finance: tudo do Pluggy e abas criadas pelos dados
- O sincronizador do Pluggy passou a ler também contas e cartões (saldo, limite, fechamento, cheque especial), faturas de cartão, investimentos, movimentações de investimentos e empréstimos e financiamentos. Cada leitura vira uma foto do dia nos conjuntos "Pluggy: ..." (histórico de saldos e posições), com todas as colunas que o Pluggy mandar e uma visão "Principais". Se o plano ou o banco não liberar um produto, a página Importar extrato avisa e as transações seguem normais.
- Identidade (CPF, endereço, telefones) não é lida, de propósito.
- Abas criadas pelos dados: Contas (extratos, separados dos cartões), Cartões (limite, fatura, faturas), Investimentos e uma aba por tipo de crédito encontrado (Financiamento de veículo, Financiamento imobiliário, Consignado, Empréstimo pessoal, Outros), mais Todas as dívidas quando há mais de um tipo. Dívidas vindas de planilha caem nas mesmas abas. Aba sem dados não aparece.
- Atenção: como as abas variam, o número do atalho Option+Shift+número de cada aba pode mudar quando uma aparece.

## 2026-11-22 - Finance: planilhas, investimentos, empréstimos e visões personalizadas
- Novas abas no Finance: Planilhas, Investimentos, Empréstimos e Visões. Em Planilhas você envia xlsx ou csv (ou solta o arquivo na pasta entrada_planilhas, que o Heimdall confere a cada minuto) de gastos, investimentos, empréstimos ou qualquer outro assunto.
- O Heimdall descobre o tipo e o papel de cada coluna pelas palavras do cabeçalho; quando não basta, pergunta ao modelo de linguagem (só o cabeçalho e as 5 primeiras linhas; HEIMDALL_FINANCE_PLANILHAS_NUVEM=0 usa só o modelo local). Se mesmo assim não tiver certeza, guarda o arquivo e faz uma pergunta na página Planilhas (tipo da planilha, qual coluna é o valor etc.); a resposta importa o arquivo.
- O jeito de ler fica gravado pelas colunas: o próximo arquivo com o mesmo layout (ou 70% parecido) entra sozinho no mesmo conjunto, sem duplicar linhas já importadas nem arquivos idênticos. Planilhas de gastos também alimentam as transações, os orçamentos e o resumo.
- Investimentos e Empréstimos resumem a posição mais recente de cada ativo ou contrato (total, por tipo, saldo devedor, parcelas por mês).
- Visões: em cada conjunto você cria visões com as colunas que quiser, na ordem que quiser (botões Mover para cima, Mover para baixo, Tirar da visão e Incluir), com ordenação, filtro por texto e agrupamento com soma. Ficam gravadas e são calculadas na hora de abrir, então as linhas de planilhas futuras aparecem nelas sozinhas.
- Leitura de xlsx sem biblioteca externa (datas e porcentagens do Excel viram texto legível). Testes: teste_planilhas.py e teste_finance_planilhas.py. O teste_finance_analise.py foi atualizado: o Perguntar usa a nuvem quando ligada.
- Não incluído: leitura de PDF de investimentos/empréstimos e dados de investimento vindos do Pluggy; hoje entram por planilha.

## 2026-11-22 - Análise de saúde lida pelo VoiceOver sem armadilhas e estudos conferíveis
- Faixas como "20‑30 min" (com hífen especial entre os números) eram lidas pelo VoiceOver como "2000 minutos". Agora todo o texto da análise passa por um ajuste: faixas viram "20 a 30 min" e milhares com espaço ("1 776 passos") viram "1776". O modelo também foi instruído a escrever faixas por extenso.
- Estudos: cada citação agora traz, além da leitura do modelo, o começo do resumo do próprio estudo, para você conferir se ele sustenta mesmo a afirmação (o modelo chegou a citar uma revisão sobre canabinoides para falar de remédios). O modelo foi instruído a citar um estudo só quando o título e o resumo sustentarem diretamente a frase, e a usar em "a favor" e "contra" só fatos presentes nos dados.
- Texto: sem pontos duplicados nas hipóteses, perigos e recomendações.

## 2026-11-22 - Análise de saúde: datas, unidades, correlações em palavras e motivo da falha do modelo
- Cada medida agora diz a data (e se é hoje, ontem ou há N dias), o sono vem em horas e minutos ("3 h 48 min"), os números usam vírgula e o texto diz quão raro foi ("nenhum dos 30 dias anteriores foi tão baixo").
- Correlações: o coeficiente r deixou de aparecer solto. O texto diz a força (moderada, forte, muito forte), o sentido (sobem juntas ou em sentidos opostos), o período e o que isso significa. Medidas da mesma família (passos, distância, energia ativa, exercício; as fases do sono; os tipos de pulso) não se correlacionam entre si, e correlação de 0,97 ou mais (a mesma grandeza medida de dois jeitos) é descartada.
- Sem o modelo, a análise do código ficou mais explicativa (o que cada medida é, o impacto, leituras cruzadas como "noite curta explica REM baixo") e diz POR QUE o modelo não respondeu: nuvem desligada, HTTP 401/429, modelo local sem resposta ou resposta fora do formato. O modelo ganhou uma segunda tentativa se responder fora do formato.
- Correção: rodado à mão no terminal, o analista não lia a chave do LiteLLM do .env, e o modelo local falhava em silêncio. Agora lê a chave direto do .env.

## 2026-11-22 - Análise de saúde com o gpt-oss-120b
- O analista de saúde e a interpretação dos alertas de anomalia agora usam o gpt-oss-120b da nuvem (gateway da Cloudflare) quando HEIMDALL_NUVEM=1. Se a nuvem falhar ou o limite de gasto cortar, cai sozinho para o modelo local. O fim da análise diz qual modelo respondeu.
- Atenção: com a nuvem, os números de saúde da análise saem do Mac, pelo gateway (autenticado, sem guardar o conteúdo). Para manter só a saúde no modelo local: HEIMDALL_SAUDE_ANALISTA_NUVEM=0 no .env. Os termos enviados ao PubMed continuam genéricos.

## 2026-11-22 - Analista de saúde: todas as métricas, correlações, hipóteses e estudos
- Novo analista (heimdall_analista_saude.py): depois que chegam dados de saúde, no máximo uma vez por dia, o código monta um dossiê com todas as medidas (cada uma contra o seu normal, desvio percentual, raridade, tendência de 7 dias), correlações calculadas (mesmo dia e com um dia de atraso), treinos, sintomas, exames fora da faixa e as condições do .env, e o modelo escreve a análise: o que cada sinal mede e o impacto, como as medidas se relacionam, hipóteses com probabilidade (a favor e contra), perigos e quando agir, recomendações priorizadas e o que acompanhar.
- Sem o freio de "não sou médico": o modelo pode levantar hipóteses de condições de saúde, sempre como hipótese; a decisão de procurar um médico é sua. O texto termina dizendo isso uma vez.
- Literatura: busca resumos de estudos no PubMed (cache de 30 dias) com termos genéricos em inglês, sem nenhum valor seu, e o modelo cita pelo número PMID. O código descarta citação de estudo que não foi fornecido. Sem internet, a análise sai sem estudos.
- Segurança: limiares de referência (oxigênio abaixo de 90, glicose abaixo de 54, pulso em repouso acima de 100...) são cruzados pelo código e sempre aparecem, e a gravidade nunca fica abaixo do que eles exigem, mesmo se o modelo errar ou não responder. Sem modelo, sai uma análise feita só pelo código (desvios explicados e correlações), dizendo isso.
- Onde aparece: aba Avisos do Heimdall Health, sempre; notificação no Mac (e Bark) só quando a gravidade é atenção com mudança, importante ou urgente, e no domingo. Comando novo: `heimdall health --analysis` (roda agora). Rota do agente: POST /saude/analise.
- Interruptores no .env: HEIMDALL_SAUDE_ANALISTA=0 (desliga a automática), HEIMDALL_SAUDE_LITERATURA=0, HEIMDALL_SAUDE_ANALISTA_MODELO e HEIMDALL_SAUDE_ANALISTA_URL (usar outro modelo), HEIMDALL_SAUDE_CONDICOES.

## 2026-11-22 - Avisos mais úteis: privacidade só com o que é seu, saúde explicada
- Monitor de privacidade: a análise do modelo agora decide primeiro se a página é mesmo sobre você. Mesmo sobrenome não basta: parente, homônimo ou empresa/jogo que não cita seu nome completo, e-mail ou usuário são descartados e não entram no nível de atenção, no Bark nem na triagem. Também descarta o que é inofensivo e não pede ação. As descartadas ficam numa seção do relatório ("Descartados pela análise"), com o motivo, para você conferir. Nunca descarta quando o seu e-mail ou usuário aparece na página, nem em caso de vazamento ou dado sensível. Quando só sobram descartadas, o Bark diz "Nada relevante hoje".
- Saúde: os avisos de anomalia deixam de ser só "HRV 20 ms, normal 29 ms". Cada sinal traz o percentual de desvio e quão raro foi (por exemplo, "31 por cento abaixo; só em 1 dos últimos 30 dias foi tão baixo"), e o aviso explica o que a medida representa, as causas mais comuns e o impacto prático. O modelo local foi instruído a explicar assim, em linguagem simples; se ele não responder, um glossário fixo garante a explicação. O texto do aviso pode ter até cerca de 1500 caracteres.
- Para valer: `heimdall flows` (fluxo do monitor de privacidade mudou) e `heimdall update --restart`.

## 2026-11-22 - Avisos completos direto no Mac
- Os mesmos avisos enviados ao iPhone pelo Bark agora também chegam ao Mac como notificações nativas do macOS, com o texto completo (inclusive títulos e resumos de saúde e finanças), sem passar por servidor de terceiros. O Bark do iPhone continua com o texto genérico.
- Como funciona: o Heimdall grava o aviso em banco/avisos_mac/ (pasta só do dono) e o app do Mac lê a cada 4 segundos, mostra a notificação e apaga o arquivo. Na primeira vez o macOS pede permissão para notificações; o Foco do Mac é respeitado.
- Onde nasce: triagem de pendências, avisos urgentes do e-mail oficial e os fluxos do n8n que usavam o Bark (alerta do Mac, estudo, resumo agrupado, GitOps, Second Brain, aviso de falha), por um nó "Avisar o Mac" ao lado de cada nó do Bark. Rotas novas do agente: POST /avisos/mac.
- Configurações do app: caixa "Mostrar os avisos do Heimdall como notificações do Mac". Desligar de vez: HEIMDALL_AVISOS_MAC=0 no .env.
- Instalador dos fluxos básicos (instalar_fluxos_n8n.sh) agora também preenche o token do agente.

## 2026-11-22 - App do Mac: Configurações e novos atalhos do menu Abrir
- Novo item "Configurações…" (Command+vírgula) no menu Heimdall e no menu de estado: escolher qual serviço abre ao iniciar o app (qualquer um, ou nenhum; padrão Chat), iniciar o Heimdall quando o Mac ligar (cria ou apaga o mesmo LaunchAgent do heimdall app --entrar; vale a partir do próximo login) e ligar os serviços ao abrir o app (só liga se nada estiver no ar). As escolhas ficam nas preferências do app. Clicar no ícone do Dock sem janelas abre o serviço escolhido.
- O menu Heimdall ganhou Sobre o Heimdall, Ocultar o Heimdall (Command+H), Ocultar os outros (Option+Command+H) e Mostrar tudo.
- Atalhos do menu Abrir, em ordem alfabética (e o menu também fica em ordem alfabética): Account é Command+0; Chat 1, Cloud 2, Controls 3, Finance 4, Games 5, Health 6, News 7, Notes 8, Status 9. Flows fica sem atalho. O zoom "Tamanho normal" passou de Command+0 para Option+Command+0.

## 2026-11-22 - App do Mac: menus em português e menu Sistema dentro de Arquivo
- O menu Sistema deixou de existir: ligar, reiniciar e parar os serviços, estado em detalhe, diagnóstico das janelas, consumo da nuvem, modelo na nuvem, sincronização com os celulares e atualizar passaram para o menu Arquivo (os mesmos atalhos: Command+E, Command+U, Command+B). A barra fica Heimdall, Arquivo, Edição, Visualizar, Abrir e Janela.
- Português: os itens que o próprio macOS acrescenta aos menus (ditado, emojis, mover e redimensionar a janela...) saíam em inglês porque o pacote do app não declarava português. O Info.plist agora declara pt-BR e o heimdall app cria Contents/Resources/pt-BR.lproj. Os nomes dos sites no menu Abrir continuam os nomes reais em inglês (Controls, Notes, News, Health, Games, Finance, Cloud, Account, Chat, Flows, Status), pela regra do projeto.

## 2026-11-22 - App do Mac: sempre app normal, abre o Chat ao iniciar
- O diagnóstico mostrou que, ao trocar o app de "só barra de menus" para "app normal" com a janela já aberta, o macOS não tratava o Heimdall como app ativo (o app em primeiro plano continuava sendo o anterior) e a barra de menus do alto não era a do Heimdall. O app agora é um app normal desde o início (sem LSUIElement no Info.plist): aparece no Dock e em Command+Tab, e a barra de menus do alto é a dele quando ele está em primeiro plano. Fechar a janela não encerra o app: ele continua com o ícone na barra de estado, e clicar no ícone do Dock abre o Chat de novo.
- Ao iniciar, o app abre sozinho o Chat, uma única vez, assim que a lista de endereços chega.

## 2026-11-22 - App do Mac: menu Arquivo
- A barra de menus do app ganhou o menu Arquivo (Imprimir, com Command+P, pela impressão do WebKit, e Fechar a janela, com Command+W), antes dos menus Edição, Visualizar, Abrir, Sistema e Janela. A barra aparece quando uma janela de site está aberta e o app está em primeiro plano. Para valer, recompile o app com heimdall app.
- Correção: com a janela aberta, a barra de menus do alto continuava sendo a do app anterior, porque o macOS não tratava o Heimdall como app ativo logo depois de ele virar app normal. A janela agora ativa o app de novo um instante depois de abrir. Se ainda acontecer, Command+Tab até o Heimdall mostra os menus.
- Se meio segundo depois de abrir a janela o macOS ainda não tratar o Heimdall como app ativo, o app pede a ativação ao próprio sistema. Novo item "Diagnóstico das janelas" (menu de estado e menu Sistema): mostra a política do app, se ele é o app ativo, qual app está em primeiro plano e os menus montados, para investigar quando a barra de menus do alto não é a do Heimdall.

## 2026-11-21 - Saúde por pessoa na caixa de correio
- Cada pessoa tem o seu banco de saúde: banco/pessoas/<nome>/heimdall.db (pasta só do dono do Mac, com cópia diária própria). O banco do dono continua onde sempre esteve. heimdall mailbox pull agora importa a saúde de todas as pessoas, cada uma no seu banco; antes só a do dono entrava e as outras ficavam na cópia local.
- Correção: o caminho da caixa importava só treinos, ECG, frequência por hora e eventos; passos, sono, energia, frequência em repouso, HRV, oxigênio e as demais métricas diárias só eram tratadas pelo n8n. Agora a caixa também grava essas métricas (heimdall_saude_diaria.py). Quem manda direto ao n8n continua como antes; o resumo diário das 5h50 do n8n segue usando só o que o n8n recebeu.
- Conversor do Atalho do iPhone (heimdall_atalhos.py): amostras no formato versão 1 viram o formato do Health Auto Export. O Atalho deve mandar dias inteiros; os totais do dia são refeitos a cada envio, então enviar a mesma janela duas vezes não duplica.
- Ainda falta: o site de Saúde ler o banco da pessoa que entrou (hoje só mostra o do dono), por isso só o dono ativa a Saúde na página Integrações; e o Atalho em si (a geração automática do arquivo não foi feita, ver ROADMAP). O backup diário ainda não inclui banco/pessoas.

## 2026-11-21 - Integrações na Conta e endereço do Health Auto Export na caixa
- A página Account ganhou "Integrações" (account.heimdall-ai.tech/integracoes, também no link de navegação do alto): um bloco por integração, com o estado e o que fazer. A Saúde já funciona: o botão "Ativar a Saúde" gera o token da pessoa, mostra-o uma vez num campo somente leitura, com o endereço e o passo a passo para o app Health Auto Export do iPhone; "Trocar o token" invalida o anterior e "Desativar a Saúde" o revoga. Por enquanto só o dono ativa (os dados dele entram no banco de saúde pelo heimdall mailbox pull); para convidados a página explica que falta o armazenamento por pessoa. Notas, Lembretes e Calendário (conta Apple ou Google) aparecem como "em preparação". Android: Calendário e Tarefas pela conta Google quando prontos; Saúde do Android precisa de app próprio, ainda não existe.
- O Worker da caixa aceita o corpo do Health Auto Export direto em POST /v1/hae, com o token da pessoa no cabeçalho Authorization, e o guarda como saúde da própria pessoa (mesmos limites: 5 MB por envio, 50 MB e 500 envios por dia). Exige publicar o Worker de novo (cloudflare/caixa.js) para valer.
- As ações do Account são formulários POST com token csrf, origem conferida e acesso só de quem entrou; novo design.botao_post no Heimdall Design. O estado fica em banco/integracoes.json (só o dono lê); o token nunca é guardado ali.

## 2026-11-21 - App do Heimdall na barra de menus do Mac (primeira versão)
- Novo comando heimdall app: compila neste Mac o app Heimdall (Swift, menus nativos que o VoiceOver lê) e o instala em ~/Applications/Heimdall.app, com assinatura local gratuita (sem conta de desenvolvedor). Fica em segundo plano, sem ícone no Dock, com o nome Heimdall na barra de menus.
- Menu: estado, ligar, reiniciar e parar os serviços; abrir Controls, Notes, News, Health, Games, Finance, Cloud, Account e Chat (os nomes reais dos sites; os endereços vêm de heimdall urls), cada um em janela própria do app, com o WebKit (motor do Safari), sem abrir o navegador e sem Electron (login, envio de arquivos, downloads e Command+R, Command+[ e Command+] funcionam); consumo da nuvem; buscar na caixa de correio (também sozinho, de 10 em 10 minutos); ligar ou desligar a nuvem e a caixa; atualizar o Heimdall com reinício. Atalhos: Command+E estado, Command+U consumo, Command+B caixa, Command+A atualizar, Command+Q sair.
- Opção heimdall app --login abre o app sozinho ao entrar no Mac; --remove-login desfaz. Precisa das ferramentas de linha de comando da Apple (xcode-select --install). Teste sem compilar: python3 teste_app_mac.py; a compilação em si só roda no Mac.

## 2026-11-21 - App do Mac: menu redesenhado
- O menu de estado agora começa com três linhas de estado (serviços ligados ou desligados; modelo de IA nuvem ou local; sincronização com celulares ligada ou desligada) e os itens se habilitam conforme o estado: Ligar só vale com os serviços desligados, Reiniciar e Parar só com eles ligados, Sincronizar agora só com a sincronização ligada; nada vale enquanto outra tarefa roda. O app sabe se os serviços estão ligados vendo se a porta do Controls (HEIMDALL_CONTROLS_PORT, padrão 8017) responde; só lê do .env os interruptores HEIMDALL_NUVEM e HEIMDALL_CAIXA e essa porta.
- Nomes novos: grupo "Abrir serviço" (os sites), grupo "Nuvem (Cloudflare)" (consumo e custo; ligar ou desligar o modelo grande) e grupo "Celulares" (a antiga "caixa de correio": sincronizar agora, resultado da última sincronização, ligar ou desligar). Os dois pares Ligar/Desligar viraram um item só, que troca de título conforme o estado. Na barra de menus do app, "Sites" virou "Abrir" e "Serviços" virou "Sistema".
- O estado olha a porta de cada serviço (a lista vem de heimdall urls): a linha mostra "todos ligados", "N de M ligados" ou "desligados"; Ligar vale quando falta algum, Reiniciar e Parar quando há algum ligado; "Ver o estado em detalhe" começa listando quem está ligado e quem está fora do ar, antes do relatório do heimdall status. O app vê se a porta responde, não se o serviço está saudável.

## 2026-11-21 - App do Mac: todos os serviços pelo Cloudflare Access
- As janelas do app abrem os endereços públicos (https), todos atrás do Cloudflare Access: entra-se uma vez e os serviços não pedem a senha e o código locais de novo. Novo heimdall urls --public lista esses endereços (Controls, Notes, News, Health, Games, Finance, Cloud, Account, Chat, Flows e Status); heimdall urls --public --check confere, sem entrar, se cada um está mesmo protegido pelo Access ou ABERTO. O app não aceita mais http (a exceção para localhost saiu do Info.plist). A senha e o código locais continuam valendo pela porta local, fora do app.

## 2026-11-21 - Seu nome no Account em vez de "Dono"
- Quem entra pela porta local (senha e código) aparecia como "Dono" no menu Conta e na página Account. Agora aparece com o nome de HEIMDALL_DONO_NOME no .env (uma palavra, sem espaços): heimdall env --set HEIMDALL_DONO_NOME Murillo, seguido de heimdall restart. Sem a variável, continua "Dono". Quem entra pelo Cloudflare Access segue com o nome da conta Microsoft. Teste: python3 teste_conta.py.

## 2026-11-21 - Barra de menus do app Heimdall
- Com uma janela aberta, o app mostra a barra de menus completa: Heimdall, Edição, Visualizar (tela cheia com Control+Command+F, recarregar, voltar, avançar, zoom com Command+ + - 0), Sites (Controls, Notes, News, Health, Games, Finance, Cloud, Account e Chat, com Command+1 a 9, para ir de um serviço a outro sem voltar ao menu de estado), Serviços (estado, ligar, reiniciar, parar, consumo, caixa, atualizar) e Janela (minimizar, zoom, fechar). As janelas aceitam tela cheia.

## 2026-11-21 - Docker Desktop em segundo plano
- Ao subir o Heimdall, o Docker Desktop agora é aberto escondido e sem tomar o foco (open -g -j), em start_heimdall.sh e start_ecosystem.sh. Novo script silenciar_docker.sh (--desfazer volta ao normal): desliga na configuração do Docker a abertura do painel ao iniciar, com cópia de segurança. Teste: bash teste_silenciar_docker.sh. Se em 40 segundos o Docker não subir escondido, o script tenta o modo normal (open -a Docker). Não testado contra o Docker real; o ícone do Docker no Dock continua enquanto ele roda.

## 2026-11-21 - Correção: janela do app não se perde mais
- Com o app só na barra de menus, a janela de um site ia para trás das outras ao perder o foco e não havia como voltar a ela. Agora, enquanto há uma janela aberta, o app aparece no Dock e em Command+Tab (e o menu do app aparece no lugar do menu do Safari); ao fechar a última janela, volta a ficar só na barra de menus. Escolher o site de novo no submenu também traz a janela para a frente.

## 2026-11-21 - Correção: Chat na janela do app
- A janela Chat mostrava "Your provider has not provided a trusted header": o Open WebUI só aceita entrada pelo endereço público (HEIMDALL_WEBUI_HOST, padrão chat.heimdall-ai.tech), onde o Cloudflare Access envia o cabeçalho de identidade; por localhost:3000 esse cabeçalho não existe. O app agora abre o Chat pelo endereço público, e o login do Access acontece na própria janela.

## 2026-11-21 - Correção: app do Mac abre em qualquer macOS recente
- O heimdall app compilava com exigência de macOS 28 num Mac com 27.3, e o macOS recusava abrir o app (erro -10825). A compilação agora fixa o alvo em macOS 12.

## 2026-11-21 - Cliente da caixa de correio no Mac (heimdall mailbox)
- Novo comando heimdall mailbox com os subcomandos status, start, add NOME, remove NOME e pull. O start cria o token de dono provando acesso com a chave da Cloudflare e o grava no .env; o add cria o token de uma pessoa e o copia para a área de transferência (não aparece na tela); o pull busca as entradas, grava uma cópia em banco/caixa_recebidos/ (permissão só do dono) e só depois apaga da caixa. Se algo falhar no meio, o item fica na caixa.
- Interruptor HEIMDALL_CAIXA (heimdall env --set HEIMDALL_CAIXA 1 liga, 0 desliga). O pull importa para o banco de saúde os itens de saúde (formato Health Auto Export) do seu próprio celular, a pessoa "eu" (heimdall mailbox add eu; o nome muda em HEIMDALL_CAIXA_MEU_NOME). Itens de outras pessoas e as notas ficam só na cópia local até existir armazenamento por pessoa. O pull ainda é manual (falta agendá-lo). Teste: python3 teste_caixa_cliente.py.

## 2026-11-21 - Caixa de correio na Cloudflare (publicada, ainda sem cliente no Mac)
- Novo Worker cloudflare/caixa.js ("heimdall-caixa"): cada pessoa tem um token e uma caixa de entrada (o celular deixa saúde, notas) e uma de saída (o Mac deixa lembretes e eventos para o celular aplicar). O Mac do dono busca e apaga; o R2 descarta sozinho o que sobrar após 7 dias. No KV fica só o hash dos tokens. Limites: 5 MB por item (cabe um lote grande de saúde), 500 envios e 50 MB por pessoa por dia, para não estourar o teto de gasto. Não é criptografia de ponta a ponta.
- O primeiro token do dono é entregue a quem prova ter acesso à conta da Cloudflare. Teste: node cloudflare/teste_caixa.mjs (31 verificações, incluindo isolamento entre pessoas). Publicada em https://heimdall-caixa.mbolonhinic.workers.dev com o bucket R2 heimdall-caixa (apaga em 7 dias) e o KV heimdall-caixa-tokens. Cada busca entrega até 10 itens (cerca de 20 MB). Ainda não está ligada ao Mac: falta o cliente.

## 2026-11-21 - Perguntar ao modelo pelo terminal
- Novo comando heimdall ask "pergunta": responde com o gpt-oss-120b da nuvem se HEIMDALL_NUVEM=1 (e cai para o modelo local, avisando, se a nuvem falhar) ou direto pelo modelo local. Opções --local (só o local) e --cloud (só a nuvem, mesmo com o interruptor em 0, para testar). Uma linha no fim diz qual modelo respondeu. A pergunta não fica guardada.

## 2026-11-21 - Monitor da Cloudflare (comando e aba)
- Novo comando heimdall usage (opção --days, de 1 a 31): mostra requisições, tokens de entrada e de saída e custo estimado do modelo grande na nuvem, por modelo e por dia, comparados com o teto de US$ 10 do gateway e o teto combinado de US$ 15 por mês.
- Nova aba Monitor no Heimdall Controls, com a mesma informação em tabelas (período de 1, 7 ou 30 dias, resposta guardada por 1 minuto). As abas passam a ser 7: Option+Shift+7 abre Manutenção.
- Lê as análises pela API GraphQL da Cloudflare (heimdall_cfmonitor.py). O token heimdall-news precisa da permissão Conta > Análises (Account Analytics) > Leitura; sem ela o comando e a aba explicam o que acrescentar. O custo é uma estimativa; a fatura é a referência.

## 2026-11-21 - Modelo grande na nuvem com interruptor
- Novo heimdall_nuvem.py: com HEIMDALL_NUVEM=1 no .env, as perguntas do Heimdall (Notes, catalogação, Finance e os demais que usam o Perguntar) vão primeiro ao gpt-oss-120b da Cloudflare, pelo gateway de IA "heimdall" (autenticado, sem guardar conteúdo, teto de US$ 10 por mês). Se a nuvem falhar, a pergunta volta sozinha ao modelo local. Vale sem reiniciar, porque o .env é lido a cada chamada.
- Liga e desliga: heimdall env --set HEIMDALL_NUVEM 1 (ou 0, que volta ao que era). Novo comando heimdall cloudai mostra se está ligada e faz uma pergunta de teste. O gpt-oss gasta parte dos tokens raciocinando; por isso cada pedido recebe 1000 tokens de folga.
- Fica de fora por enquanto: o chat do Open WebUI e os fluxos do n8n, que passam pelo LiteLLM; a ligação deles ao gateway é a etapa seguinte.

## 2026-11-21 - Gateway de IA da Cloudflare (início da migração)
- Criado na conta o gateway de IA "heimdall": exige autenticação, não guarda o conteúdo das conversas, repete até 3 vezes em caso de falha e tem teto de US$ 10 por mês. O teto total da nuvem é de US$ 15 por mês e cada fase terá interruptor no .env para voltar ao que era (regras no CLAUDE.md).
- heimdall cloudflare --test agora também chama o gateway com o gpt-oss-120b (custo de uma fração de centavo). O token heimdall-news precisa das permissões AI Gateway Lido, Executar e Editar. Os modelos ainda não usam o gateway: a ligação com o LiteLLM e o interruptor HEIMDALL_NUVEM vêm depois deste teste passar.

## 2026-11-21 - Abas em duas linhas
- Páginas com mais de 5 abas passam a usar duas linhas equilibradas em vez de uma fila longa: 6 abas = 3+3, 7 = 4+3, 8 = 4+4, 9 = 5+4; com mais de 9, 5 na primeira linha, 4 na segunda e o menu Mais no quinto lugar da segunda. Até 5 abas continuam numa linha só. Em tela estreita, duas colunas. Setas, Option+Shift+1 a 9 e 0 e a ordem de leitura não mudam (design.por_linha em heimdall_design.py).

## 2026-11-21 - Notes cataloga notas e liga com o Notion
- A aba Início do Heimdall Notes ganha um campo com dois botões: Perguntar (o modelo local responde com trechos das suas notas) e Salvar nota. Ao salvar, a IA local separa a nota em ideias, contatos, endereços, lembretes e eventos.
- Lembrete (algo a fazer) vai para o app Lembretes e evento (algo numa data e hora) para o Calendário, na hora, com botão Desfazer. Se a data estiver ausente, ambígua ou no passado, o item fica pendente e pede a data. Tipos novos na tabela de heimdall_agenda.py: lembrete_nota e evento_nota; o agente ganha POST /calendario/desfazer e /lembretes/desfazer.
- Ideias, contatos e endereços vão para três bancos de dados do Notion (heimdall_notion.py; Desfazer arquiva a página). Saúde e finanças nunca vão para o Notion: ficam só numa nota local "Heimdall Notas". Sem Notion configurado, ou se ele falhar, nada se perde: o item vai para a nota local.
- Novo comando heimdall notion confere token e bancos. Segredos entram pelo .env com heimdall env --set HEIMDALL_NOTION_TOKEN (e _DB_IDEIAS, _DB_CONTATOS, _DB_ENDERECOS), lendo da área de transferência.

## 2026-11-21 - Layout com abas em todos os serviços
- Heimdall Cloud, Notes, News, Health, Games e Finance trocam o menu de links pelas abas do Heimdall Design (como o Controls já tinha): setas, Home e End movem o foco, Option+Shift+1 a 9 abre a aba pelo número e o leitor de tela ouve "<nome> aberta". Sem JavaScript, as abas continuam sendo links comuns.
- Todas as páginas terminam com "Voltar para o topo" e começam num alvo de foco (#topo). O script das abas tem nonce e a política de segurança de cada serviço só o aceita para esse nonce. Detalhes novos em heimdall_design.py: nav_abas, com_abas, topo, script, csp e aba_da_rota.
- Perguntar (modelo local, só com os dados da tela) agora também existe no Heimdall Health (sono, atividade, recuperação e demais relatórios; não é diagnóstico) e no Heimdall News (as notícias das últimas 24 horas). O Finance já tinha. Cloud, Games e o Account não têm Perguntar: não há dado pessoal para consultar. Os dois botões do Notes (perguntar e salvar nota) vêm na próxima etapa.
- Com mais de 9 abas (Health e Finance), as 9 primeiras ficam como abas e as outras vão para o menu Mais, que abre com Option+Shift+0 (de novo, ou Esc, fecha). Funciona sem JavaScript. Se a página aberta está no Mais, o resumo diz "Mais, aba aberta: nome". Teste: teste_abas_mais.py.
- O Account, de uma página só, fica sem abas; já tinha o voltar ao topo.

## 2026-11-21 - Avisos de saúde e finanças fora do Notes
- Heimdall Health e Heimdall Finance ganham a aba Avisos. O relatório semanal e o resumo diário de saúde, e as análises de finanças, ficam num banco local de cada serviço (heimdall_avisos.py), com Marcar como lido e Marcar todos. Nada disso vai mais para o app Notas, nem irá para o Notion.
- O agente tem POST /avisos/gravar e, por segurança, desvia /notas/gravar com pasta Saúde ou Heimdall Finanças para os avisos. O fluxo "monitor de saúde" do n8n passa a gravar nos avisos (rode heimdall flows para instalar a nova versão). O botão Salvar no Notas do Finance foi removido: a análise gerada já vira aviso.
- O Bark segue notificando, só com texto genérico ("Heimdall Health: aviso novo. Abra a aba Avisos"). Itens de triagem de saúde ou finanças também saem sem título nem resumo no Bark; o detalhe fica no app Lembretes e no serviço.
- As notas de saúde que já estão no Notas continuam lá; apague-as pelo app Notas se quiser.
- heimdall notices (sem opção só mostra o plano; com --migrate executa) traz para a aba Avisos as notas de saúde e finanças que já estavam gravadas, tanto a cópia do cofre (com os áudios) quanto a nota do app Notas (pasta Saúde dentro de Heimdall-ai e pasta Heimdall Finanças). Importa tudo, confere que cada item chegou e só então apaga; se algo falhar, nada é apagado. O app Notas manda para "Apagadas recentemente" (30 dias). Uma pasta sua chamada Saúde fora de Heimdall-ai nunca é tocada.
- Novos: heimdall_avisos.py, migrar_avisos.py, teste_avisos.py, teste_migrar_avisos.py.

## 2026-11-21 - Heimdall Account (account.heimdall-ai.tech)
- Novo serviço, porta 8018: o tour dos serviços de cada pessoa, com link, o que cada um faz e como configurar. Dono vê todos; convidado só os seus. O texto fica em heimdall_conta_info.py (Health e Finance já explicam o plano de multiusuário). Todo e-mail de dono ou convidado entra no Account; a aba Usuários o inclui sozinha. Comando: heimdall account (-L abre o endereço do Mac).
- Cloudflare (feito pelo conector, a pedido): aplicativo e política "Heimdall Account" no Access (Microsoft e Authenticator), DNS account e rota do túnel para localhost:8018, acrescentada sem mexer nas outras.
- O menu Conta e o tour usam os nomes reais dos serviços, sem traduzir: Heimdall Notes, Heimdall Health, Heimdall Games, Heimdall Chat, Heimdall Flows e Heimdall Status (a tecnologia, Open WebUI, n8n e Uptime Kuma, vem explicada no tour). A lista do menu e do tour segue a ordem alfabética. A tabela é NOMES em heimdall_conta.py.
- /quem.json devolve nome, e-mail e serviços de quem tem o cookie do Access, com CORS e cookies só para os sites de HEIMDALL_ACCOUNT_ORIGENS. Todas as páginas do site mostram "Entrar no Heimdall" sem login e, com login, "Conta: nome" com os serviços; o login conta depois de abrir o Account uma vez (o cookie é do endereço account).
- Novos: heimdall_account.py, heimdall_conta_info.py, teste_account.py, teste_site_conta.py, LEIAME_account.txt.

## 2026-11-21 - Menu Conta em todos os serviços
- Cloud, Notas, News, Saúde, Jogos, Finance e Controls ganham o mesmo menu Conta, antes do cabeçalho: "Conta: Nome", com o nome da conta Microsoft e o e-mail, como a pessoa entrou e a lista de links dos serviços a que ela tem acesso. O dono vê todos (Chat, Status, n8n, Controls...); o convidado só os liberados para ele e que podem ser dados a convidado. O serviço atual aparece como "você está aqui". O link do Kuma abre em /dashboard.
- O nome vem de /cdn-cgi/access/get-identity da equipe no Cloudflare, chamado com o próprio token do Access, e fica só na memória (1 hora; 10 minutos se falhar, e então aparece o e-mail). Quem entra pela porta local com senha e código aparece como "Dono".
- heimdall_cloud.ManipuladorBase passou a ser a base dos servidores: guarda os cabeçalhos do pedido em curso para o menu saber quem entrou.
- Novos: heimdall_conta.py e teste_conta.py.

## 2026-11-21 - Versões dos serviços: heimdall doctor --versions e Visão geral
- heimdall doctor --versions (-v) lista as versões do macOS, Python, Docker, Ollama, LiteLLM, do código do Heimdall e de cada contêiner que está rodando (Open WebUI, n8n, Kuma, Qdrant, SearXNG, Dozzle e emuladores), e compara cada imagem com a mais nova no registro: avisa quando há atualização (heimdall restart --update). Se não der para comparar (sem rede, sem buildx), só mostra a versão.
- A Visão geral do Controls ganhou a tabela "Versões instaladas" (guardada por 10 minutos, sem rede, para a página abrir rápido).
- heimdall doctor --versions deixou de imprimir a "Conclusão: nada fora do normal". Só fala se houver o que atender: imagem mais nova no registro, contêiner rodando numa imagem antiga (já baixada, falta reiniciar), versão que o serviço não informou, Ollama com cliente e servidor em versões diferentes. Não há tabela de incompatibilidade entre programas; só entra o que dá para conferir. A Visão geral mostra os avisos que não dependem da rede.
- Novos: heimdall_versoes.py e teste_versoes.py.

## 2026-11-20 - HEIMDALL_WEBUI_SEM_SENHA passa a ser ignorada e sai dos Ajustes
- Testado no Mac: com ENABLE_PASSWORD_AUTH=false o Open WebUI responde 403 a todo login, inclusive o pelo cabeçalho do Access, e a página fica em "Fazendo login". A opção HEIMDALL_WEBUI_SEM_SENHA agora só avisa e não aplica. Com HEIMDALL_WEBUI_ACCESS=1 a senha já não é pedida pelo endereço público. A opção não aparece mais em Ajustes (lista OBSOLETAS em heimdall_config.py).

## 2026-11-20 - Ajustes: segredo só quando é segredo; SUBIR_* no lugar certo
- HEIMDALL_WEBUI_SEM_SENHA (e qualquer NOME com SEM_SENHA) é um liga/desliga e não vem mais oculto como senha. A regra agora olha as palavras do nome (senha, token, chave, hash...), não pedaços de palavra.
- SUBIR_VOZ e SUBIR_VOZ_PPM agora ficam no grupo Voz; as demais SUBIR_* formam o grupo "Subida dos serviços". Todas ganharam descrição.

## 2026-11-20 - Excluir usuário do Open WebUI
- heimdall chat --delete-user (excluir_usuario_webui.sh) apaga uma conta do Open WebUI e os dados ligados a ela (conversas e outras tabelas com user_id), sem apagar o volume: cópia em backups/, pede o e-mail digitado para confirmar e recusa apagar o último administrador.

## 2026-11-20 - Ajustes mostra variáveis lidas como $NOME
- A lista de Ajustes passa a incluir variáveis que os scripts leem como $HEIMDALL_X (sem valor padrão) e as documentadas na ajuda, como HEIMDALL_WEBUI_ACCESS e HEIMDALL_N8N_SEM_LOGIN, que antes não apareciam. Valores vazios não são gravados por heimdall env --defaults.

## 2026-11-20 - n8n com sessão longa; trocar o e-mail do Open WebUI
- n8n: o contêiner agora é recriado a cada subida para valer as opções do .env (fluxos e credenciais ficam no volume). HEIMDALL_N8N_SESSAO_HORAS (padrão 8760, um ano) estende o login próprio; HEIMDALL_N8N_SEM_LOGIN=1 tenta N8N_BASIC_AUTH_ACTIVE=false, que as versões atuais costumam ignorar.
- heimdall chat --email (trocar_email_webui.sh) troca o e-mail, que também é o usuário, de uma conta do Open WebUI sem apagar o volume: cópia em backups/, para o Open WebUI por segundos, atualiza as tabelas auth e user, confere e liga de novo. A senha não muda.
- Webhook de saúde: um GET nesse endereço responde 404 porque o n8n só aceita POST; isso mostra que o desvio do Access funciona. O teste certo é um POST com o token (LEIAME_login_sem_senha.txt).

## 2026-11-20 - Aviso: webhook de saúde precisa de desvio no Access
- Com o Access em flows.heimdall-ai.tech, o webhook de saúde (/webhook/heimdall-saude, usado pelo Health Auto Export e pelo Worker heimdall-saude-caixa) precisa de um aplicativo do Access só para esse caminho, com política Bypass. Está em LEIAME_login_sem_senha.txt. Os outros webhooks do n8n são chamados só localmente (localhost:5678) e não são afetados.

## 2026-11-20 - Chat, n8n e Kuma atrás do Access; roadmap
- Cloudflare Access ligado (pelo conector, a pedido) em chat.heimdall-ai.tech, flows.heimdall-ai.tech e status.heimdall-ai.tech: login só da Microsoft, direto, só o e-mail do dono e Authenticator (MFA) exigido. O Controls lê o Kuma pelo endereço local, então não é afetado. Quem entrava no chat com conta do Open WebUI passa a precisar estar na lista da aba Usuários.
- A aba Usuários reconhece aplicativos do Access que cobrem vários endereços (como o "Heimdall - Pessoal") e não os altera: uma política por serviço abriria todos os endereços dele. Aplicativos só de caminho (o desvio do RSS) não contam como cobertura. Sessão dos aplicativos novos: 8 h.
- Roadmap: Notion no lugar de Notes e Lembretes; Health e Finance para várias pessoas.

## 2026-11-20 - Usuários: Authenticator obrigatório, Microsoft como login padrão e AUD automático
- As políticas criadas pela aba Usuários exigem o Authenticator (regra de método de autenticação "mfa"; HEIMDALL_CLOUDFLARE_ACCESS_MFA=0 desliga). Os aplicativos novos aceitam só o login da Microsoft, direto, descoberto sozinho se a conta tem um só (ou HEIMDALL_CLOUDFLARE_ACCESS_IDP).
- Ao aplicar, os identificadores (AUD) dos aplicativos são acrescentados a HEIMDALL_CFACCESS_AUD, para os painéis aceitarem a entrada pelo Access sem pedir senha de novo.
- n8n (flows) e Uptime Kuma (status) entram na lista de serviços, só para donos.

## 2026-11-20 - Controls: aba Usuários
- Nova aba Usuários (Option+Shift+4; Ajustes passou a 5 e Manutenção a 6): donos em só leitura, convidados com os serviços liberados (Cloud, Notes, News, Games e Chat), adicionar, trocar e remover. A lista fica em HEIMDALL_CFACCESS_CONVIDADOS. Health, Finance e Controls são só de donos. Dono não é removido por ali, e ninguém remove o próprio e-mail.
- Com HEIMDALL_CLOUDFLARE_ACCESS_TOKEN e CLOUDFLARE_ACCOUNT_ID, "Ver o que vai mudar" mostra o plano sem alterar nada e "Aplicar no Cloudflare" cria ou atualiza uma política "Heimdall: Serviço" por serviço e o aplicativo do endereço público (inclusive o do chat), mantendo as outras políticas e as configurações de um aplicativo que já exista, e revoga as sessões de quem saiu. Opcional: HEIMDALL_CLOUDFLARE_ACCESS_IDP.
- heimdall env --set aceita HEIMDALL_CLOUDFLARE_ACCESS_TOKEN (lido da área de transferência, nunca pela linha de comando).

## 2026-11-20 - Open WebUI e Kuma sem senha, pelo Cloudflare Access
- Open WebUI: com HEIMDALL_WEBUI_ACCESS=1 no .env ele confia no e-mail que o Access manda no cabeçalho e entra sem senha (HEIMDALL_WEBUI_SEM_SENHA=1 tira também o formulário). A porta 3000 passa a escutar só em 127.0.0.1, para ninguém falsificar o cabeçalho. O start_heimdall.sh só liga o modo depois de conferir que o endereço público (HEIMDALL_WEBUI_HOST) está atrás do Access; senão avisa e mantém o login por senha.
- Novo: heimdall chat --check (verificar_access.py) confere, sem entrar, se um endereço está atrás do Access.
- Kuma: com o login desligado (Settings, Security, Disable Auth), pausar e retomar monitores pelo Controls não precisa mais de HEIMDALL_KUMA_USUARIO e HEIMDALL_KUMA_SENHA. Passo a passo em LEIAME_login_sem_senha.txt.

## 2026-11-20 - Controls: Visão geral útil, aba Ajustes
- A aba Configurações passou a se chamar Ajustes (endereço /ajustes; heimdall controls --open settings). Option+Shift+4 continua abrindo-a.
- A Visão geral, que é a primeira aba e a que abre ao entrar, ganhou texto novo: quantos serviços estão no ar, quais estão fora do ar sem você ter desligado, quais foram desligados de propósito e para que serve cada aba.

## 2026-11-20 - Valores padrão gravados no .env e endereços do código vindos do .env
- Novo comando: heimdall env --defaults grava no .env, de uma vez, os valores padrão que o código usa e o .env ainda não tem (nunca segredos; não muda o que já existe; cópia em .env.bak). Rode uma vez; reinicie depois. O botão "Gravar valores padrão" do Controls foi retirado.
- A vigia de e-mails (heimdall_email_oficial.py), o Finance e a página do Cloud não têm mais endereços fixos: usam HEIMDALL_AGENTE_URL, HEIMDALL_LITELLM_URL, HEIMDALL_CLOUD_ENDPOINT e a nova HEIMDALL_N8N_URL (padrão http://localhost:5678). Os scripts consultar_triagem.sh, instalar_automacoes_avancadas.sh e instalar_monitor_privacidade.sh também leem HEIMDALL_AGENTE_URL.

## 2026-11-20 - Controls: segredos ocultos, padrões preenchidos, rodapé com Recarregar e Voltar para o topo
- Configurações: variáveis de senha, chave, token e segredo vêm com o campo oculto (type=password) e um botão Mostrar/Ocultar ao lado (design.SCRIPT_SEGREDO).
- Configurações: as opções com valor padrão no código vêm com esse valor preenchido no campo.
- Configurações: as variáveis de "Outras" foram para o grupo do serviço a que pertencem (Health, Mac Agent, AWS Emulator, Cloud, Notes, GitOps, Voz, Alertas, Controls) ou para novos grupos (Modelos de IA, Gerais).
- Toda página termina com um rodapé (design.rodape): botão "Recarregar Heimdall" e o link "Voltar para o topo". O botão fica desabilitado até uma configuração mudar; depois reinicia tudo (o mesmo que Restart na Manutenção).

## 2026-11-20 - Controls: Configurações sem grupos repetidos, com explicação e Esc
- Configurações: grupos com o mesmo nome (Backup na nuvem R2, Cloudflare) agora são um só. Cada variável tem uma explicação curta em português, lida junto com o campo (heimdall_config_ajuda.py; sem explicação específica, vale a do sufixo: _PORT, _HOST, _TOKEN…).
- Esc fecha o grupo (ou o menu Conta) em que o foco está e devolve o foco ao resumo (design.SCRIPT_DETALHES).

## 2026-11-20 - Controls: textos mais curtos e atalhos em português
- Controls: o atalho de cada aba agora é dito em português ("Atalho: Option Shift 3", ligado à aba por aria-describedby) em vez de "Alt+Shift+3" (aria-keyshortcuts). Os textos ao lado dos botões da Manutenção e da aba Serviços ficaram curtos ("Para todos os serviços, menos este painel.").

## 2026-11-20 - Controls: e-mail no menu Conta não vira link do Cloudflare
- Corrigido: o Cloudflare (proteção de e-mail) trocava o e-mail do menu Conta por um link para /cdn-cgi/l/email-protection, e clicar nele abria uma página de erro do Cloudflare. As páginas do Controls agora vão entre <!--email_off--> e <!--/email_off-->, que o Cloudflare respeita; isso vale também para e-mails que apareçam no terminal e nas Configurações.

## 2026-11-20 - Controls: Sair e logs funcionam; menu Conta; Configurações em grupos
- Corrigido: Sair e o botão Exibir log (e qualquer formulário comum) davam "Pedido recusado: origem não permitida". Como o painel manda Referrer-Policy: no-referrer, o navegador envia Origin: null nos formulários comuns, e a checagem recusava. Agora Origin null não conta como informação: vale o Sec-Fetch-Site (cross-site é recusado) e o token de segurança continua obrigatório. Origin de outro site continua recusado. (Era também a causa provável do erro de token que apareceu no Aplicar.)
- Controls: o topo agora tem o menu "Conta: nome", que abre e mostra como você entrou (o e-mail do Cloudflare Access ou "Dono", pela senha e código) e o botão Sair, que encerra a sessão. Entrando pelo Access, há também o link para sair do Access.
- Configurações: as variáveis ficam em grupos que abrem e fecham (<details>), um por serviço ou assunto (Cloud, Controls, Notes, Health, Finance, Cloudflare Access, Backup, Alertas, Vigia, Outras...). Cada grupo mostra o que está no .env e as opções ainda sem valor. O filtro pelo nome abre sozinho os grupos que têm o que você procura e esconde os outros. Nova variável também é um grupo.

## 2026-11-20 - Controls: aba Configurações (etapa 2, primeira parte)
- Controls ganhou a aba Configurações (Option+Shift+4; a Manutenção passou a ser a 5). Mostra tudo o que o .env guarda, com o valor inteiro (inclusive senhas e chaves, só depois do login), e permite salvar, remover e adicionar variáveis sem recarregar a página. Lista também as cerca de 100 opções HEIMDALL_* que o código lê e o .env ainda não define, com o valor padrão quando dá para saber. Há um filtro pelo nome.
- O arquivo é gravado no mesmo formato do guardar_no_env.sh (NOME='valor', permissão 600), sem repetir linhas, e copiado para .env.bak antes de cada mudança. Valor com aspa simples ou quebra de linha é recusado. Mudar um valor só vale para o serviço quando ele for reiniciado.
- Módulo novo heimdall_config.py e teste_config.py. O atributo hidden agora esconde mesmo (regra no Heimdall Design).

## 2026-11-20 - Controls vira central de controle (etapa 1: abas e chaves de serviços)
- Controls: o botão Sair ficou no topo da página, à parte das abas (menu "Conta", antes do cabeçalho). A aba Manutenção foi refeita: Start (sobe tudo, como heimdall up), Stop (para tudo menos o painel, para o Start continuar possível), Update, Update e restart, Restart, Status, Diagnóstico e Log do serviço / Exibir log, cada botão com uma frase dizendo o que faz. Os nomes dos serviços ficaram todos como são de fato (Notes, Health, Games, Mac Agent, MCP data, AWS Emulator...).
- start_heimdall.sh não sobe um segundo Controls quando o painel já está no ar (caso do Start pelo painel).
- Controls: um pedido recusado agora diz o motivo (origem não permitida ou token que não confere) e o log do Controls anota Origin, Referer e se o token veio.
- Controls: o menu lateral virou abas (Visão geral, Terminal, Serviços, Configurações, Manutenção), acessíveis ao leitor de tela (tablist/tab/tabpanel). Setas esquerda e direita, Home e End movem entre as abas e Option+Shift+1 a 4 abre cada uma. Abrir uma aba troca só o conteúdo, sem recarregar a página (o foco fica na aba e o leitor ouve "Serviços aberta"); só o Terminal, que tem script próprio, carrega a página inteira. O componente está no Heimdall Design (design.abas).
- Controls, aba Serviços: lista os 21 serviços do Heimdall (LiteLLM, Ollama, Qdrant, SearXNG, Docling, os três MCP, Open Terminal, agente, Cloud, Notas, News, Saúde, Jogos, Finance, Kuma, Dozzle, n8n, Open WebUI e emulador de AWS) como uma chave (botão de alternância, role=switch) em cada um: Espaço ou Enter liga ou desliga na hora, sem botão de confirmar, e o resultado é lido como aviso. O que você desliga fica em .heimdall_desligados.json e continua desligado depois de heimdall update --restart (um vigia confere de 30 em 30 s, depois de 3 minutos de subida). Serviço novo: uma linha em CATALOGO no heimdall_servicos.py.
- Controls lê a situação de cada serviço também no Uptime Kuma (página de status, HEIMDALL_KUMA_URL e HEIMDALL_KUMA_SLUG) e, com HEIMDALL_KUMA_USUARIO e HEIMDALL_KUMA_SENHA no .env e o pacote python-socketio, pausa o monitor ao desligar e o retoma ao ligar (heimdall_kuma.py).
- As ações de atualizar, reiniciar, diagnóstico e logs foram para a aba Manutenção.
- Terminal: copiar as últimas N saídas passou de Option+Shift+número para Control+Shift+número (Option+Shift+número agora troca de aba). Option+Shift+C continua copiando a última.
- start_heimdall.sh: o LiteLLM agora roda em segundo plano e o script espera por ele. Antes, desligar só o LiteLLM encerrava o script e, pelo trap, derrubava MCP, Open Terminal e agente. Depois de o LiteLLM sair, o script fica de pé; heimdall restart e heimdall stop encerram do mesmo jeito.
- Teste novo: teste_servicos.py; teste_controls.py e teste_controls_navegador.py cobrem as abas e as ações.

## 2026-11-19 - Notas e Lembretes não abrem mais na tela do Mac; Controls: cursor no fim ao voltar ao campo
- O agente do Mac passou a abrir o Notas, o Lembretes e o Calendário escondidos e em segundo plano (open -g -j) quando precisa gravar neles, e a fechá-los 20 segundos depois do último uso. Só fecha o app que ele mesmo abriu e nunca um que você já deixou aberto ou que esteja na frente. As janelas deixam de pular na sua frente a cada nota, lembrete ou evento. Vale para todos os fluxos (estudos, digest, saúde, triagem, agenda), porque todos passam pelo mesmo ponto do agente. Novo teste: teste_apps_ocultos.py.
- Notas e Lembretes: o Heimdall não fecha mais o app depois de usar (fechar e abrir de novo a cada ciclo fazia o app aparecer toda hora); HEIMDALL_APPS_FECHAR=1 no .env volta a fechar depois de 20 s. Cada abertura escondida agora é registrada no log do agente (./subir.sh --log agente), com a operação que a pediu, para achar quem está abrindo o app.
- Notas e Lembretes: mesmo aberto com open -g -j, o app passava à frente ao terminar de abrir. Agora, logo depois de abrir um desses apps (só quando o próprio Heimdall o abriu), o agente espera 1,2 s, esconde o app (como Command+H, sem permissão nova) e esconde de novo no fim da primeira chamada. Se o app já estava aberto, não é tocado. Falha ao esconder vai para o log do agente ("não consegui esconder").
- Lembretes e Calendário: o agente agora usa o EventKit (heimdall_eventkit.py) para criar e ler lembretes e eventos (agenda, triagem, prazos dos e-mails), sem abrir os apps, que apareciam na tela e no Command+Tab mesmo escondidos. Se o pacote (venv/bin/pip install pyobjc-framework-EventKit) ou a permissão do macOS faltar, usa o AppleScript de antes, e o motivo vai para o log do agente. Conferir: venv/bin/python heimdall_eventkit.py --status. Desligar: HEIMDALL_EVENTKIT=0. Testes novos: teste_eventkit.py.
- Second Brain: o agente deixou de abrir o Notas a cada 5 minutos. Ele olha a data do banco do Notas sem abrir o app e só consulta quando há mudança ou depois de uma gravação do Heimdall. Sem acesso ao banco (Acesso Total ao Disco), consulta só depois de uma gravação; HEIMDALL_NOTAS_VARREDURA_MIN liga uma varredura de segurança. Teste novo: teste_second_brain_gatilho.py.
- Controls: ao sair do campo Terminal e voltar (Tab, Shift+Tab), o Safari põe o cursor no começo. O salto automático para o fim acontecia 350 ms depois de entrar e cortava a leitura do nome do campo ("terminal ar%"); sem ele, o cursor ficava no começo. Agora nada é mexido na entrada e, depois de 1,8 s, o cursor vai ao fim, só se você ainda não digitou, clicou nem moveu o cursor (digitar antes disso já manda a letra para o fim). O tempo é HEIMDALL_CONTROLS_ATRASO_CURSOR no .env, em milissegundos (0 desliga o salto). Também nesta versão: Notas e Lembretes abertos só escondidos (item acima). Teste atualizado em teste_controls_navegador.py.
- Controls: o campo Histórico segue a mesma regra do Terminal. Ele jogava o cursor ao fim no mesmo instante em que recebia o foco, e o VoiceOver passava a ler só o último caractere. Agora o cursor fica no fim enquanto o campo está sem foco, nada é mexido na entrada e, se o Safari puser o cursor no começo, ele vai ao fim depois do mesmo atraso (HEIMDALL_CONTROLS_ATRASO_CURSOR), só se você ainda não mexeu.

## 2026-11-19 - Controls: a saída inteira é lida ao fim do comando
- Ao terminar um comando o leitor de tela fala a situação e a saída inteira, por maior que seja (antes, saídas com mais de 12 linhas só tinham a contagem de linhas). Control interrompe a fala do VoiceOver. Option+Shift+O também lê a última saída inteira.

## 2026-11-19 - Controls: leitura mais limpa ao entrar no campo e ao fim do comando
- O cursor do Terminal já fica no fim enquanto o campo não tem o foco (ao sair dele e a cada atualização), então ao entrar nada se mexe e o VoiceOver lê só o nome do campo; sem atraso para ajustar.
- A situação do comando ficou curta: "concluído em 0s". O código só aparece quando é erro ("código 2, em 0,3s"). O aviso falado não conta mais comandos nem diz "comando".
- A linha digitada não aparece mais duas vezes: o zsh com o .zshrc do usuário devolvia o eco do comando; agora o eco é desligado a cada prompt (stty -echo) e, por garantia, a primeira linha da saída igual ao comando é descartada.
- O Histórico não termina mais com linha em branco.
- Enter repetido enquanto o comando ainda está sendo enviado é ignorado, e Ctrl+C nesse intervalo já interrompe.

## 2026-11-19 - Controls: Tab livre, Ctrl+I completa, o campo muda uma vez só ao executar
- O Tab deixou de ser capturado: volta a mover o foco pela página como em qualquer lugar. Para completar comandos, arquivos e pastas use só Ctrl+I.
- Ao apertar Enter, a linha digitada fica no campo até a saída chegar e então o campo troca de texto uma única vez. Antes ele apagava a linha e depois trocava tudo, e o VoiceOver lia um resquício do comando anterior no meio disso.

## 2026-11-19 - Controls: prompt sem espaço, minutos por extenso, foco em 0,3 s, Ctrl+I
- O prompt agora termina em "%" sem espaço (heimdall-ai%), para o VoiceOver não ler "espaço" ao entrar no campo. No cabeçalho de cada comando ainda há um espaço entre o prompt e o comando (heimdall-ai% ls).
- Duração com minutos: 1min e 5s, 2min (número sempre colado na unidade).
- O cursor do Terminal vai ao fim 350 ms depois do foco.
- O Tab é tomado pelo VoiceOver/Safari antes de chegar à página; o que funciona é Ctrl+I, agora indicado na lista de atalhos e na ajuda.

## 2026-11-19 - Controls: nome do campo, Tab mais firme, duração sem espaço
- O cursor do Terminal só vai ao fim 0,4 s depois de o campo receber o foco. Mexer nele na hora fazia o VoiceOver ler só o último caractere ("espaço") e engolir o nome "Terminal".
- O Tab agora é capturado na janela, antes de qualquer outro tratamento, e há uma rede de segurança: se o foco sair do campo logo após um Tab, ele volta e o Tab completa. Ctrl+I faz o mesmo que o Tab (é o Tab do terminal de verdade), para o caso de o leitor de tela não entregar o Tab à página.
- A duração do comando vem com o número colado no s e sem fração desnecessária: 0s, 0,3s, 12,3s, 37,21s (até duas casas; acima de 1 minuto, "1 min 5s").

## 2026-11-19 - Controls: aparência passa a vir do Heimdall Design
- O CSS do campo de terminal e da linha de ações foi para o heimdall_design.py (valem para qualquer site), e o Controls deixou de definir o tamanho da fonte do corpo e os títulos por conta própria. O botão que age na própria página virou design.botao_js. "Fora do ar" usa a classe padrão de erro. A página de Design descreve os componentes novos.

## 2026-11-19 - Controls: rótulos curtos, Tab que nunca sai, cd completa pastas, avisos firmes
- Os campos se chamam apenas Histórico e Terminal (sem frase longa nem título extra). O cursor do Histórico entra sempre no fim e o campo acompanha o fim quando chega comando novo, para ler do mais novo para o mais antigo subindo com a seta.
- No campo Terminal o Tab é sempre de completar: não sai mais do campo (para sair use Option+Tab ou Shift+Tab). Sem nada digitado ou com programa rodando, ele só avisa. Depois de cd ou pushd completa só pastas e, se não houver na pasta atual, procura na pasta pessoal (cd heim vira cd ~/heimdall-ai/).
- Os avisos falados (atalhos, Tab, fim de comando) usam região assertiva e se repetem mesmo quando o texto é igual, para o VoiceOver não engolir.
- Erros de ortografia: a página já desliga a verificação nos dois campos; o que sobra vem do Safari ou do VoiceOver (ver LEIAME_controls.txt).

## 2026-11-19 - Controls: foco no terminal, nenhuma letra perdida, histórico acima
- O foco vem sempre no campo Terminal: ao abrir a página, ao recarregar e ao voltar para a aba do navegador. O cursor entra sempre depois da última letra, tanto ao focar por Tab quanto automaticamente; só o clique do mouse escolhe outro ponto.
- A primeira letra digitada não se perde mais. Antes, se o cursor estivesse na saída, a proteção contra editar a saída descartava a letra; agora a letra vai para o fim da linha de digitação (vale também para colar).
- O histórico passou a ser um campo comum (as setas, Home e End funcionam como em qualquer campo, sem perder o foco), com a edição bloqueada por código e marcado como somente leitura para o leitor de tela. Antes era um campo readonly, que não segura as setas direito. Ele fica logo ACIMA do Terminal e guarda os comandos anteriores ao atual; só é reenviado ao navegador quando muda, e atualizado sem mexer no cursor nem na rolagem.
- Tab repetido rápido não confunde mais: enquanto a resposta do Tab anterior não chega, o Tab seguinte espera.

## 2026-11-19 - Controls: o campo mostra só o último comando, e Tab completa
- O campo do terminal agora mostra só o último comando e a saída dele: a cada comando novo ele recomeça, como depois de um clear. Antes ele acumulava tudo e o leitor de tela lia desde a primeira saída. Os comandos anteriores ficam na seção Histórico, num campo somente leitura, e as cópias (Option+Shift+C, 1 a 9, 0) continuam levando as últimas saídas. Enquanto o comando roda, a saída é acrescentada ao fim do campo em vez de trocar o texto todo.
- Tab completa comandos (na primeira palavra e depois de ; | &) e nomes de arquivos e pastas a partir da pasta do shell. Com uma só opção completa tudo; com várias, completa o que for igual e o leitor de tela diz as opções. Se o Tab não mudar nada, o Tab seguinte sai do campo (não prende o teclado), e com a linha vazia o Tab é o de sempre.
- Verificação de ortografia desligada no campo e no histórico (também reforçada por JavaScript). Se o VoiceOver ainda avisar erros, veja o LEIAME_controls.txt.

## 2026-11-19 - Controls: o terminal agora é um campo só, com atalhos de teclado
- A saída de cada comando aparece no próprio campo do terminal, logo abaixo do comando, como num terminal de verdade, em vez de blocos com títulos e botões mais abaixo na página. O cursor fica na última linha, depois do prompt (nome da pasta e %); Enter executa, Shift+Enter abre nova linha. Só a última linha aceita digitação: o resto é a saída, que dá para ler e copiar.
- Saiu o campo separado "Resposta ao programa". Quando um programa pergunta algo, o que você digita na última linha vai direto a ele (e não aparece, então serve para senha).
- Ao terminar um comando, o leitor de tela fala a situação e, se a saída for curta, a própria saída; se for longa, diz quantas linhas tem.
- Atalhos de teclado: Ctrl+C interrompe (sem programa rodando, apaga a linha), Ctrl+L limpa, Option+Shift+C copia a última saída, Option+Shift+1 a 9 copia as últimas N, Option+Shift+0 copia todas, Option+Shift+U leva o cursor ao início da última saída, Option+Shift+O faz o leitor falar o começo dela, Option+Shift+P e N percorrem o histórico, Option+Shift+R reinicia o shell, Option+Shift+I interrompe, Option+Shift+T volta ao terminal e Option+Shift+H vai à lista de atalhos. Os botões da seção Ações continuam, com o atalho no nome.
- Novo teste teste_controls_navegador.py, num Chrome de verdade (Playwright): saída no campo, resposta a programa, proteção do histórico contra edição, atalhos, cópia, limpar e reiniciar. Pula se não houver Playwright ou Chrome.

## 2026-11-19 - Open Terminal só local
- O Open Terminal (porta 8002) agora escuta apenas em 127.0.0.1, em vez de todas as interfaces. O Open WebUI no Docker continua alcançando-o por host.docker.internal. Se precisar do acesso pelo Tailscale, ponha HEIMDALL_TERMINAL_HOST=0.0.0.0 no .env.

## 2026-11-19 - Heimdall Controls: terminal completo e acessível
- Novo serviço, Heimdall Controls (porta 8017; de fora, controls.heimdall-ai.tech): um terminal de verdade no Mac, aberto no navegador e pensado para leitor de tela. A pasta e as variáveis continuam entre os comandos. Cada comando é um bloco com título, situação (em execução, concluído, erro com código) e a saída em texto simples, da mais recente para a mais antiga, sem cores nem códigos de tela e sem emular a tela do terminal. Programas que perguntam algo recebem a resposta por um campo próprio, e há botão para interromper (Ctrl+C). Programas de tela cheia, como vim e top, não funcionam.
- Copiar para a área de transferência: botão para a última saída, campo para escolher quantas últimas saídas, caixa para incluir ou não o comando, e um botão em cada bloco. Se o navegador não deixar copiar sozinho, o texto vai para um campo já selecionado.
- A página Serviços mostra o que está no ar e tem botões para atualizar, reiniciar, diagnosticar e ver logs. O comando é `heimdall controls` (com --open terminal ou services, e --local).
- Segurança: só o dono entra (Cloudflare Access com o Authenticator, ou senha e código de 6 dígitos); convidado do Access é sempre recusado; em endereço público todo pedido precisa vir do Access de um dono; CSRF e Origin conferidos; cada comando é anotado em logs/controls_audit.log, sem a saída. LEIAME_controls.txt traz o passo a passo do endereço público no Cloudflare.

## 2026-11-19 - Consultas e renovação de receita no Calendário; evento x lembrete
- Consulta médica e pedido de renovação de receita viram evento no Calendário (calendário Heimdall), nunca lembrete. A consulta vem de um documento de confirmação (PDF ou foto, lido e conferido como os outros) ou é cadastrada à mão: `heimdall labs appointment --date AAAA-MM-DD --time HH:MM`. O evento tem hora, duração de uma hora e alertas de 1 hora e 1 dia antes. Para receita com validade, o evento cai 7 dias antes de vencer (HEIMDALL_RENOVACAO_DIAS muda). Só entra no Calendário depois de você confirmar o documento. Se o agente do Mac estiver fora do ar, o item fica pendente e `heimdall labs calendar` o leva depois; rodar de novo não duplica.
- O Calendário pode sincronizar com a nuvem da Apple, o que você aceitou (a Apple já fornece dados de saúde ao Heimdall): o evento traz especialidade, médico e local, e a renovação traz o nome do medicamento. HEIMDALL_AGENDA_DETALHES=0 volta ao título genérico.
- Nova regra única, heimdall_agenda.py: evento é o que acontece numa data e hora ou tem data fixa; lembrete é o que você precisa fazer e marcar como feito. A tabela cadastra cada tipo (consulta, renovação, prazo oficial e triagem) e vale para toda aplicação; está no CLAUDE.md e no teste_agenda.py. O agente aceita evento com hora, duração, local e alertas.
- Os comandos do terminal ficam em inglês: `heimdall labs pending|read|confirm|discard|folder|import|result|analysis|prescriptions|referrals|appointments|appointment|calendar|documents|token`, com --without, --date, --time, --doctor, --specialty e --place. Substitui o heimdall exames, que durou algumas horas.

## 2026-11-19 - Exames, receitas e encaminhamentos na saúde
- O Heimdall agora lê o PDF ou a foto de um exame de laboratório e cataloga cada componente (hemograma, vitaminas, lipídios, glicemia, hormônios e o que mais vier) com valor, unidade e a referência do próprio laboratório; também lê receitas (medicamento, dose, posologia, validade) e encaminhamentos (especialidade). Primeiro vem a leitura por regras; o modelo local só ajuda onde as regras não alcançam, e todo valor precisa aparecer literalmente no texto do documento. A situação (abaixo, dentro, acima) só é dita quando a referência tem uma faixa clara. Nada vai para as tabelas finais antes de você conferir: `heimdall labs pending`, `ler`, `confirmar` ou `descartar`.
- Dois caminhos de entrada: a pasta do Mac (banco/documentos/entrada, vigiada pelo agente) e o atalho do iPhone na folha de compartilhamento, que envia o arquivo ao agente por Tailscale com um código só para esse envio (`heimdall labs token`). O aviso no Bark não traz nome nem número. O mesmo documento nunca entra duas vezes (SHA-256). Os originais ficam no Mac, com permissão só do dono.
- Leitura cruzada: o modelo local comenta os resultados junto com o que o relógio e o iPhone mostraram nos 30 dias antes da coleta (sono, HRV, pulso em repouso, passos, exercício), sem diagnosticar, sem sugerir remédio e só com números que estão nos dados. Novas ferramentas de chat, só de leitura: exames_resumo, exame_historico, analise_exames, exames_pendentes e receitas_encaminhamentos; confirmar e descartar não existem no chat. O painel de saúde ganhou as páginas Exames e Documentos (somente leitura).
- O banco ganhou as tabelas documentos_saude, exames_resultados, receitas e encaminhamentos. Precisa reiniciar o agente.
## 2026-11-19 - Modelos do chat por contexto
- Novo modelos_chat.py: fonte única dos modelos personalizados do Open WebUI, com base, prompt, temperatura e a lista de funções que cada um pode usar. O guia modelos_open_webui.txt e a tabela "Modelos do chat" do README agora são gerados dele por python3 gerar_docs.py.
- Dois modelos novos: Saúde (saude_historico, analise_saude, frequencia_cardiaca_resumo, ecg_resumo, treinos_resumo, relatorio_saude, banco_consultar e get_system_timestamp) e Finanças (as seis funções financas_* e get_system_timestamp, só leitura), cada um com seu prompt (prompt_chat_saude.txt e prompt_chat_financas.txt). O Meus Dados ficou com o geral: diários, e-mails, estudos, privacidade, avisos, Second Brain e métricas de saúde simples.
- O guia agora tem três conexões para o mesmo servidor de dados (banco-pessoal, banco-saude e banco-financas), cada uma com um filtro de funções, para o modelo enxergar só as funções do seu assunto. Antes o guia citava 5 das 16 funções do servidor.
- Importação pronta para o Open WebUI: openwebui/modelos_importar.json (os sete modelos, também um por arquivo em openwebui/modelos/, com prompt, temperatura, chamada nativa e conexão) e openwebui/ferramentas/ (um arquivo por conexão MCP, porque o Open WebUI importa só a primeira de cada arquivo; são cinco no formato que o Open WebUI exporta; o filtro de funções não viaja nesse formato e fica em openwebui/filtro_<id>.txt, para copiar com pbcopy e colar em cada conexão; é uma lista de exclusões, com as funções do servidor que cada conexão deve esconder, porque o servidor é compartilhado e assim o bloqueio não depende do modelo). Os ids das conexões passaram a ser os que o seu Open WebUI já usa (internet, mac-admin e banco-pessoal) mais banco-saude e banco-financas. Os modelos importados ficam só para o administrador; busca na web, terminal e ferramentas embutidas ficam desligados neles.
- Novo teste_modelos_chat.py: confere que toda função citada existe e pertence ao servidor certo, que cada prompt só fala das funções do seu modelo, que nenhuma função do servidor de dados ficou sem uso e que o guia está em dia.

## 2026-11-18 - Diagnóstico do vigia de e-mail
- Novo heimdall mail --diagnose (python3 heimdall_email_oficial.py --diagnostico): lista os e-mails recentes de serviços públicos com a classe (oficial, suspeito ou não oficial), remetente, domínio, resultado SPF/DKIM/DMARC do Gmail e o motivo, inclusive os já vistos. A simulação pula os já vistos e por isso podia terminar sem mostrar nada. O diagnóstico não envia nem grava nada e não mostra o corpo.
- Corrigido: o resumo do modelo local podia chamar de "e-mail falso" ou golpe uma mensagem que o Gmail tinha autenticado (a Serasa avisando pagamento confirmado). Agora o modelo é instruído a só resumir, e se ainda assim falar em golpe, falso ou phishing, o resumo é descartado, a urgência cai para baixa e a ação vira conferir no app oficial. Quem decide se é golpe continua sendo a checagem de domínio e DMARC.

## 2026-11-18 - Menos gravações no KV e e-mails de serviços sem interesse
- Vigia da Cloudflare (cloudflare/vigia.js): gravava duas vezes por rodada no KV (576 por dia, 58% do limite gratuito de 1.000; a Cloudflare avisou ao chegar a 50%). Agora grava o estado só quando muda e a hora da última conferência no máximo uma vez por hora (cerca de 24 por dia). O Worker publicado precisa ser atualizado na Cloudflare para valer. Novo teste: node cloudflare/teste_vigia.mjs.
- E-mails oficiais de Serasa, SPC, Boa Vista e Quod (avisos de boleto disponível, que só mandam entrar no app) não viram mais item de triagem, evento no Calendário nem lembrete, mesmo com urgência alta; continuam no registro e no resumo. A lista muda em HEIMDALL_EMAIL_BAIXA_PRIORIDADE no .env (nomes separados por vírgula; valor em branco desliga). E-mail suspeito de golpe nunca é rebaixado.

## 2026-11-18 - Alertas de saúde com contexto
- O monitor de anomalias deixou de juntar medidas sem relação. Passos, energia, exercício, caminhada, peso, frequência cardíaca média do dia e ruído agora são contexto: aparecem no relatório, mas nunca viram aviso sozinhos nem em dupla. Antes, duas medidas quaisquer muito fora do normal (frequência média do dia e ruído, por exemplo) abriam um aviso.
- Só medidas fisiológicas alertam, e só de sistemas diferentes: coração (pulso em repouso, mínimo, madrugada e horas de hoje contam como um), variabilidade, respiração e oxigênio, sono e temperatura. Os cruzamentos de estresse e de sono/respiração também só usam essas medidas.
- Esforço físico recente explica o desvio: com treino de 40 minutos ou 300 kcal ou mais hoje ou ontem, pulso, variabilidade e respiração alterados saem marcados como "provável efeito de treino forte recente" e não contam para o aviso, a menos que durem 3 dias ou mais. O alerta de pulso alto na madrugada também espera uma segunda noite alta quando houve treino forte.
- O ruído do ambiente passou a valer pelo nível, não pela mudança: abaixo de 70 dB de média no dia (limite de referência de 24 horas da OMS e da EPA) nunca é achado; acima disso é moderado, e a partir de 75 dB é forte e pode alertar sozinho.
- O modelo local que interpreta o alerta recebe o contexto (medidas de contexto, esforço recente e as regras acima) para não ligar sinais sem relação.

## 2026-11-18 - Menos avisos da triagem
- A triagem agora manda um só aviso por rodada, listando todos os itens pendentes, em vez de um aviso por item. Com um único pendente, o aviso continua individual.
- O aviso agrupado traz o começo do resumo de cada item (assunto do e-mail, sinais da saúde) e junta itens com o mesmo título numa linha só, com (x3), para dar para decidir sem abrir o app; o detalhe encolhe se o aviso ficar grande demais.
- Itens comuns (prioridade alta ou média) repetem a cada 4 horas, em vez de 2; itens críticos continuam a cada 2 horas e furam o modo silencioso, e o aviso de um grupo com crítico sai como crítico. Itens de prioridade baixa seguem a cada 8 horas. Um aviso reinicia a contagem de todos os itens listados nele. Continua sem tocar das 21h às 7h, exceto o primeiro aviso de um item crítico.

## 2026-11-18 - Consultas do Finance no terminal
- `heimdall finance --balance` diz o saldo de cada conta e a fatura em aberto de cada cartão na última leitura do banco, com o total nas contas, o total devido nos cartões e a diferença.
- Para cartão, o valor que o banco informa é o saldo devedor, que pode incluir parcelas futuras e não é a fatura do mês. Por isso `--balance` mostra o valor do cartão como "usado do limite" (conferido com o Itaú Black: 12.060,31 em uso, fatura aberta de 5.360,92), também pede ao banco as faturas do cartão (rota /bills, quando disponível) e mostra a fatura a vencer e a data de vencimento, e mostra "saldo devedor informado pelo banco" e, quando o banco informa, o limite, o disponível, quanto está usado, o fechamento, o vencimento e o pagamento mínimo.
- `heimdall finance --closing itau=1:7` guarda quando fecha a fatura de um cartão (um pedaço do nome basta): vence no dia 1 e fecha 7 dias antes, ou um dia fixo do mês como `itau=27`; com ele, `--balance` mostra a fatura em aberto calculada pelas compras desde o último fechamento, já que o banco só informa as faturas fechadas. `--balance` também avisa que o Meu Pluggy só atualiza limite, disponível e faturas a cada 24 horas.
- `heimdall finance --diagnose-card itau` mostra, para um cartão, as faturas que o banco informa e as últimas transações com situação, parcela, data da compra e a qual fatura pertencem. Serve para entender os parcelados que caem na fatura em aberto; só lê e não mostra ids nem chaves.
- Quando o banco liga cada transação à fatura (como o Itaú), a fatura em aberto passa a ser tudo o que ainda está sem fatura, e não só o que tem data depois do último fechamento. Isso pega as compras do fim do ciclo que o banco demora a lançar. Pagamentos ficam de fora, e bancos que não informam a fatura de cada transação continuam pela data do fechamento.
- A fatura em aberto estimada agora inclui as parcelas de compras antigas que caem nela. O banco só lista cada parcela depois que ela entra numa fatura fechada, com a data da compra e o código dessa fatura; por isso, a cada sincronização o Heimdall olha as parcelas da última fatura fechada que ainda têm parcelas a pagar e conta a próxima parcela de cada uma (mesmo valor) na fatura em aberto. `--balance` mostra quantas parcelas entraram e quanto somam. `--sync` agora mostra por cartão quantas parcelas entraram na fatura em aberto e quanto somam. Isso lê os últimos 400 dias de cada cartão a cada rodada, para alcançar parcelas de compras de até um ano atrás.
- `heimdall finance --sync --now` (experimental) pede ao Pluggy para reler os bancos agora e espera terminar antes de importar; se o Pluggy recusar (limite de um pedido por hora, conexão sem esse recurso, ação sua pendente), mostra o motivo e lê o que já existe. No teste real com conexões do Meu Pluggy o Pluggy respondeu erro 400 nos três bancos (a atualização só sai pelo próprio Meu Pluggy, a cada 24 horas); a mensagem agora explica isso. É a única chamada que não é só leitura, e não move dinheiro.
- `--balance` mostra o limite de conta (cheque especial: contratado, usado e disponível) nas contas correntes em que o banco informa (bankData do Pluggy).
- Corrigido: `--balance` quebrava (AttributeError) com parcela fixa cadastrada, porque a data de hoje não chegava à conta.
- `heimdall finance --parcela-fixa mercado=176,42:14/21` cadastra uma parcela que o banco cobra e não lista; a parcela avança a cada fatura e some sozinha depois da última (nada a lembrar). Tem prioridade sobre a detecção automática.
- Fatura em aberto: se toda fatura traz um valor fixo que o banco não lista como lançamento (Mercado Pago, R$ 176,42), ele é somado à estimativa; `--diagnose-card` mostra o resíduo de cada fatura.
- Fatura em aberto: pendências sem fatura com mais de 45 dias (resíduo de compra depois dividida em parcelas, como o iPhone de 28/05) deixam de contar.
- `--diagnose-card` também lista os lançamentos que ficaram sem fatura apesar de terem data até o último fechamento, para achar pendências presas ou compras lançadas com atraso.
- `heimdall finance --latest` lista os últimos lançamentos, em lista numerada. Filtros: `--limit N` (padrão 15), `--account` com um pedaço do nome (por exemplo itau), `--month AAAA-MM`, `--search TEXTO` e `--category NOME`.
- `heimdall finance --summary` dá o resumo do mês (entradas, gastos, resultado, onde mais gastou com variação sobre o mês anterior, maiores gastos e quantos lançamentos estão sem categoria); `--month AAAA-MM` escolhe outro mês.
- Tudo lê só o banco local e o saldo guardado na última sincronização; nada vai para a internet. O saldo é atualizado a cada rodada do Pluggy (a cada 6 horas ou com `heimdall finance --sync`).

## 2026-11-17 - Nomes das contas do Pluggy sem repetição
- Os nomes das contas dos bancos no Finance seguem um padrão: "Itaú conta corrente", "Itaú conta poupança", "Nubank conta corrente", "Mercado Pago conta corrente", e para cartões "Itaú cartão de crédito", "Nubank cartão de crédito" e assim por diante. Trechos entre parênteses como "(pré-pago)" e a palavra "Pluggy" nunca entram no nome. Duas contas nunca ficam com o mesmo nome: se o nome já foi tomado na mesma rodada, o Heimdall acrescenta o final ou um número. Nomes já guardados ou definidos com `--name` têm prioridade.
- Cartão sem nome de banco (como "platinum") herda o banco da conta do mesmo item, então o cartão do Nubank sai como "Nubank cartão de crédito".
- `heimdall finance --sync --list` mostra também o tipo (corrente, poupança) e o saldo, e avisa quando já existe no Finance uma conta importada por extrato do mesmo banco com outro nome.
- A sincronização do Pluggy não grava mais um lançamento que já veio de extrato ou fatura (mesma conta, dia e valor), e `heimdall finance --dedupe` mostra (com exemplos), e com `--force` apaga, os do Pluggy já gravados que repetem um de extrato (nunca os que você mexeu). O pareamento usa a descrição parecida e a parcela (01/03 e 03/03 são compras diferentes), e só depois a quantidade. A saída da sincronização diz quantos lançamentos o Pluggy devolveu por conta.
- Novo `heimdall finance --redo-from-pluggy` (com `--force` para valer) copia o banco para a pasta de backups dos dados, apaga os lançamentos das contas conectadas ao Pluggy, inclusive os de extrato, e relê tudo pelo Pluggy desde `--since` (padrão 01/01/2024). Sem `--force`, só mostra o que seria apagado e quantos lançamentos têm categoria escolhida à mão.
- Novo `heimdall finance --sync --since DATA --simulate` mostra, por conta, quantos lançamentos o Pluggy devolve e de que dia a que dia, comparado com o mais antigo que o Finance já tem, sem gravar nada.
- Novo `heimdall finance --standardize-names` renomeia sozinho as contas do Pluggy para o padrão, sem digitar nenhum nome (útil quando as aspas do terminal atrapalham).
- Novo `heimdall finance --rename-account "ATUAL=NOVO"` (pode repetir) troca o nome de uma conta já importada, com todo o histórico. O Heimdall lembra os nomes antigos e a conta do Pluggy passa a usar o nome novo sem recomeçar as datas, então reler os mesmos lançamentos depois da troca não duplica nada.

## 2026-11-17 - Contas dos bancos baixadas sozinhas pelo Meu Pluggy
- O Finance agora baixa sozinho as contas e transações dos bancos pelo Open Finance, usando o plano pessoal gratuito do Meu Pluggy (até 5 bancos, somente leitura, atualização a cada 24 horas, autorização que vale um ano por banco). Exceção consciente e aceita à regra de que dados de finanças não saem do Mac: os dados passam pelos servidores do Pluggy antes de chegar aqui. Nada é movido nem pago; o módulo só faz a autenticação e leituras (GET).
- `heimdall finance --sync` (-S) sincroniza na hora; o painel repete a cada 6 horas (HEIMDALL_FINANCE_PLUGGY=0 desliga) e a página Importar extrato ganhou a seção Conexão automática com os bancos, com a última rodada, avisos e o botão Sincronizar agora. As chaves (Client ID, Client Secret e ids dos bancos) ficam no .env e são gravadas por `--save-pluggy id|segredo|itens` (para itens, cada execução acrescenta um banco), que lê a área de transferência sem mostrar o valor e a esvazia depois do segredo.
- Conta corrente: o tipo (débito ou crédito) manda no sinal; transação agendada ou bloqueada só entra depois de liquidada. Cartão: compra vira saída e pagamento de fatura vira crédito, e a compra na fatura aberta entra. Conta que já tem extrato importado do mesmo banco reaproveita o nome e começa no dia seguinte à última data, para não duplicar; `--list` mostra os nomes e `--name N=NOME` troca. Cada rodada relê 7 dias e o id da transação evita repetir. O Heimdall avisa no Resumo e na página quando a autorização de um banco está perto de vencer (30 dias) ou venceu. Usa a rota /v2/transactions, porque a antiga deixa de existir em 31/12/2026.

## 2026-11-17 - Diagnóstico de e-mail: sem falsos números e com domínio dos links
- O diagnóstico deixou de apontar números curtos (telefone, código de cliente, data) como "parecidos com boleto": só conta sequência de 40 dígitos ou mais. Nos e-mails que só trazem link, ele agora diz os domínios dos links (só o domínio, nunca o caminho ou o código) e se algum fica no domínio do próprio remetente, para decidir se vale abrir links de remetentes confiáveis.

## 2026-11-17 - Leitura de e-mail afinada pelo primeiro uso
- A busca passou a excluir e-mails da Uber e das abas Promoções e Social do Gmail, que lotavam o limite, e o limite subiu para 150 mensagens. O diagnóstico agrupa os descartes por remetente e motivo, com a quantidade e exemplos de assunto, e diz com precisão por que um número parecido com boleto não valeu: a contagem de dígitos e qual verificador falhou, sem mostrar os dígitos. E-mail que só tem link mas não fala de cobrança deixou de ser descrito como link para o boleto. A frase de cartão ficou mais estrita: lista de formas de pagamento ("pague com cartão, Pix ou boleto") não marca mais o boleto como já programado; só vale "será cobrado no seu cartão" e parecidos.

## 2026-11-17 - Código de barras de 44 dígitos
- O Heimdall agora aceita também o código de barras do boleto, os 44 números sem a formatação da linha digitável, digitado ou colado à mão e encontrado em e-mails e PDFs. Ele converte para a linha digitável (47 ou 48 dígitos), confere o dígito verificador geral e registra do mesmo jeito; se o mesmo boleto aparecer nas duas formas, entra uma vez só. Para não confundir com chave de nota fiscal (também 44 dígitos), na leitura de textos só vale se começar com 8 ou com um código de banco conhecido.

## 2026-11-17 - Busca de e-mail mais larga e com diagnóstico
- `heimdall finance --read-email --days N` (até 365) lê os últimos N dias em vez de 7. A busca no Gmail passou a procurar também fatura, mensalidade, segunda via, nota ou aviso de cobrança, data de vencimento, valor ou total a pagar e Pix com termo de pagamento; palavras genéricas como conta e cobrança só valem junto de vencimento, pagar, pagamento ou vence, para não trazer a caixa inteira. O filtro continua sendo só a primeira peneira: só vira boleto o que tiver linha digitável ou Pix com dígitos corretos. O limite subiu para as 80 mensagens mais recentes. O comando manual agora diz quantas mensagens a busca trouxe e por que cada uma foi descartada (só link, PDF escaneado, dígitos que não conferem, sem código) e relê também as já lidas. Continua lendo só a Caixa de entrada.

## 2026-11-17 - Boletos já programados ou pagos
- Boleto já programado ou já pago não vira conta a pagar. Quando o e-mail (de remetente autêntico) diz que o pagamento é por débito automático, no cartão ou que já foi feito, o boleto entra como Já programado, com o motivo escrito, fora da lista, dos totais e do Pagamentos futuros; frase com negação, como "cadastre o débito automático" ou "você não tem débito automático", não conta. Além disso o Heimdall bate os boletos com o histórico do Finance: lançamento de saída com o mesmo valor perto do vencimento e nome parecido marca o boleto como pago; conta recorrente de mesmo nome e valor parecido vira provável débito automático (ou cobrança no cartão). Isso roda ao registrar, ao importar um extrato e ao abrir a página. O botão É para pagar mesmo devolve o boleto à lista, e o que você marcou à mão nunca é alterado sozinho. O Resumo avisa quantos ficaram de fora. O banco ganhou as colunas motivo e manual em boletos.

## 2026-11-17 - Boletos por e-mail e Pix dinâmico
- O painel do Finance passou a ler o Gmail a cada 15 minutos (somente leitura, com a senha de aplicativo que o monitor de e-mails oficiais já usa) e registra os boletos e Pix do corpo e dos PDFs anexados dos últimos 7 dias, com a pessoa achada pelo campo Pagador. Links nunca são abertos e só vale linha digitável com dígitos corretos. Como boleto falso por e-mail é golpe comum, o remetente é conferido pela autenticação (DMARC/DKIM) que o Gmail registrou: se não passar, o boleto entra com o aviso de possível golpe, mostrado na página. Comando novo `heimdall finance --read-email` para rodar na hora; HEIMDALL_FINANCE_EMAIL=0 desliga a leitura automática.
- Pix dinâmico (código com endereço e sem valor): a pedido seu, pela página ou pelo comando, o Heimdall consulta o servidor do banco do recebedor e completa valor, vencimento e quem recebe. Só abre https público (nunca IP direto, porta, usuário ou rede local), não segue redirecionamentos, não envia nenhum dado seu e avisa que a assinatura não foi verificada. Nunca é feito para código vindo de e-mail. O banco ganhou a coluna aviso em boletos.

## 2026-11-17 - Perguntar em todas as páginas e análises já prontas
- O Perguntar deixou de ser uma página: virou um campo no fim de toda página do Finance, com as respostas logo abaixo, da mais recente para a mais antiga. Assim dá para ver um dado, ficar curioso e perguntar na mesma tela; o mês que estava na página entra no contexto. As dez últimas respostas ficam guardadas (tabela perguntas). A página Análise agora já traz a análise da semana e a do mês: a última gerada ou, se não houver, uma calculada na hora pelas regras, cada uma com um botão para gerar uma nova com os dados de agora.

## 2026-11-17 - Boletos por pessoa
- A página Boletos ganhou a seção Pessoas: cadastre as pessoas cujos boletos você paga (por exemplo, a noiva e a filha), só o nome, nunca CPF. Cada boleto tem uma pessoa, escolhida ao registrar, trocada depois pelo botão Mudar pessoa ou achada sozinha pelo nome no campo Pagador do PDF. A página e o comando `heimdall finance --bills` somam o que está em aberto por pessoa, e o comando `heimdall finance --bill ... --person NOME` registra já com a pessoa. Os pagamentos futuros e o chat também mostram de quem é cada boleto. O banco ganhou a tabela pessoas e a coluna dono em boletos.

## 2026-11-17 - Finance ganha análise de consultor e o campo Perguntar
- Nova página Análise: um botão gera a análise da semana ou do mês com o que subiu e baixou, pontos de atenção, onde reduzir gastos e melhores datas de pagamento, sem dica de investimento. Os números são calculados em código; o modelo local só redige o texto e, se citar valor que não está nos dados, a página mostra o texto calculado. Há botão para salvar a análise na pasta Heimdall Finanças do Notas. Nova página Perguntar, com um campo de texto, para perguntas sobre gastos, orçamentos, parcelas, boletos e contas futuras; o modelo local responde com base nos dados e valores fora dos dados aparecem com aviso. O modelo é sempre o local, sem reserva na nuvem (HEIMDALL_PERGUNTAR_MODELO muda o modelo; padrão llama-3.1-8b). O módulo heimdall_perguntar.py pode ser usado por outros sites do Heimdall. O banco ganhou a tabela analises.

## 2026-11-17 - Boletos aceitam Pix copia e cola
- O campo da página Boletos e o comando `heimdall finance --bill` agora entendem também o Pix copia e cola (BR Code): o Heimdall confere o dígito de controle final, recusa código cortado ou alterado e guarda valor, quem recebe e cidade. Pix não tem vencimento próprio, então aparece como sem vencimento. Continua sem pagar nada.

## 2026-11-17 - Finance mostra os pagamentos futuros
- Nova página Pagamentos futuros no Finance: os próximos seis meses com o que ainda vai sair e entrar. O leitor passou a reconhecer parcelamentos nas faturas e extratos (parcela 3 de 10, Parc 03/10 e, só em cartão, 03/10 no fim da descrição), calcula quantas faltam e em que mês cai cada uma. Entram também as contas recorrentes detectadas, os pagamentos que você cadastra (descrição, valor, dia, mês inicial e final opcional, saída ou entrada) e os boletos em aberto, com total de saídas e entradas por mês. Cada item detectado tem o botão Ignorar. O chat ganhou a ferramenta financas_futuros. O banco ganhou as tabelas previstos e ignorados.

## 2026-11-17 - O chat consulta o Finance
- Cinco ferramentas novas no chat de dados (somente leitura): financas_resumo (receitas, despesas, saldo, categorias e maiores gastos de um mês), financas_transacoes (busca por trecho, mês e categoria), financas_orcamentos (limites e situação), financas_recorrentes e financas_boletos. Dá para perguntar, por exemplo, quanto gastei com mercado em outubro, quais assinaturas tenho ou que boletos vencem esta semana. As ferramentas abrem o banco do Finance em modo somente leitura, então não gravam, não importam e não pagam nada, e só existem no grupo de dados (127.0.0.1:8004), nunca no público dos convidados. Todos os modelos do chat são locais (Ollama), então os valores não saem do Mac. Para desligar, HEIMDALL_FINANCE_CHAT=0 no .env e reiniciar.

## 2026-11-17 - Finance lê boletos e guarda como contas a pagar
- Nova página Boletos no Finance e novos comandos `heimdall finance --bill` (aceita um PDF de boleto ou a linha digitável entre aspas) e `heimdall finance --bills` (lista os em aberto). O leitor entende a linha digitável de 47 números (boleto bancário) e de 48 números (conta de consumo e tributo), confere todos os dígitos verificadores e recusa o código se algum número estiver errado. Guarda valor, vencimento (inclusive depois da virada do fator de vencimento em fevereiro de 2025), banco ou segmento e quem recebe, quando o PDF diz. PDF de boleto solto na pasta de entrada é registrado sozinho em vez de ir para revisar. A página mostra vencido, vence hoje ou a vencer, com botões Marcar como pago e Remover, e o Resumo avisa dos boletos vencidos ou que vencem em até 7 dias. O Heimdall nunca paga nada: marcar como pago é só uma anotação. O banco ganhou a tabela boletos e nada sai do Mac.

## 2026-11-17 - Finance acha as contas recorrentes
- Nova página Contas recorrentes no Finance: o Heimdall procura no histórico os lançamentos que se repetem todo mês, como aluguel, assinaturas e salário, e mostra valor e dia típicos. A tabela fica dividida em esperadas neste mês e ainda não apareceram (passou do dia habitual), ainda por vir, já apareceram e possivelmente encerradas (sem aparecer há mais de dois meses). Uma conta só vale se aparece uma vez por mês em pelo menos 3 meses, ou em 2 meses seguidos com o mesmo valor, com valor variando até 25% e dia até 7 dias. Nada é cadastrado e nada sai do Mac.

## 2026-11-17 - Finance ganha orçamentos mensais
- Nova página Orçamentos no Finance: você define um limite mensal em reais para cada categoria de gasto e vê, mês a mês, o gasto, quanto falta ou quanto passou e a situação em palavras (dentro do limite, perto do limite a partir de 80% e estourado). Os gastos seguem a visão escolhida, por compra ou por saída de caixa. Cada categoria tem botões Salvar limite e Remover limite com o nome da categoria, e o Resumo avisa quando há orçamento estourado ou perto do limite, com um botão para a página. Não vale para categorias neutras (pagamento de fatura, investimentos) nem para Sem categoria. O banco ganhou a tabela orcamentos.

## 2026-11-16 - Finance lê PDF, identifica o banco e vigia uma pasta de entrada
- Novo comando `heimdall doctor` para descobrir por que o Mac está lento: memória e troca em disco (swap), carga do processador, calor, Time Machine, quem mais usa memória e processador, espaço em disco, Docker, modelos carregados no Ollama e memória de cada serviço do Heimdall, terminando com uma conclusão em linguagem simples. Opções: --memory, --cpu, --disk, --docker, --ollama, --services e --top. Só lê o sistema e mostra nomes de programas, nunca linhas de comando.
- Finance: nova categoria de gasto Parcelamento de fatura, aplicada sozinha às parcelas do tipo Pagamento da fatura de outubro, parcela 1 de 5. Assim a parcela não se mistura com Outros gastos e, quando a fatura parcelada for importada, basta passar a categoria para neutra (Pagamento de fatura) para não contar duas vezes. Juros, multa e IOF do parcelamento continuam em Impostos e tarifas.
- Finance, extrato de conta do Mercado Pago: o leitor agora entende a data com traços (dd-mm-aaaa), usa o número da operação de 13 dígitos como identificador do lançamento (fora da descrição, e é o que evita importar o mesmo lançamento duas vezes) e confere o extrato pelo saldo mostrado na mesma linha de cada lançamento: a sequência de saldos precisa fechar, senão o arquivo vai para revisar. Só vale quando fecha, então não muda a leitura dos outros bancos.
- Finance, fatura do Mercado Pago em parcelamento: Débito para pagar (ou quitar) a fatura e Crédito por parcelamento da fatura somam o total da fatura anterior (por exemplo R$ 101,94 de entrada mais R$ 419,15 financiados dão R$ 521,09), que já foi lançada, então deixam de ser lançamentos. O que sobra (parcela do parcelamento, juros, multa, IOF e compras) confere com o total da fatura atual (R$ 301,76).
- Finance: `heimdall finance --explain ARQUIVO --values` (-v) mostra, junto de cada linha lida como lançamento, os valores em reais (a descrição continua mascarada), para achar qual lançamento está com o sinal errado quando o total não confere.
- Finance, fatura do Mercado Pago: a linha do cabeçalho com data, limite e saque (só valores, sem descrição) deixa de virar um lançamento falso de R$ 50, e lançamento de cartão cujo nome começa com Crédito, Estorno, Reembolso, Devolução ou Cashback é lido como crédito mesmo quando o valor vem positivo (como "Crédito por parcelamento da fatura"). Com isso a soma dos lançamentos passa a bater com o total da fatura.
- heimdall doctor: reconhece pico de processador que já passou (carga de 5 minutos alta e de 1 minuto baixa) e a preparação de recursos de inteligência do sistema (ANECompilerService), comuns logo depois de reiniciar ou atualizar o macOS.
- heimdall doctor: quando a troca em disco está alta mas a memória está sobrando, a conclusão explica que é resíduo e sugere reiniciar o Mac; também mostra há quantos dias o Mac está ligado.
- Finance: novo comando `heimdall finance --retry` (atalho -r): move todos os arquivos de revisar de volta para a pasta de entrada, apaga os motivos antigos e importa de novo. Se já houver um arquivo com o mesmo nome na entrada, deixa o de revisar onde está e avisa.
- Finance, extrato de conta: quando um lançamento aparece do outro lado de uma linha de saldo no texto do PDF (quebra de página), dois ou mais pares de saldos vizinhos ficam com diferenças que se anulam; um trecho seguido de pares divergentes cuja soma é exatamente zero agora conta como conferido, porque os saldos das pontas fecham. O `--explain` diz quantos pares foram aceitos assim.
- Finance, extrato de conta do Itaú: a linha "JUROS LIMITE DA CONTA" (e outros juros, IOF e tarifas datados com a palavra limite ou encargos) era ignorada por causa da palavra limite, mas é lançamento de verdade e quebrava a conferência dos saldos; agora entra. O `heimdall finance --explain` passou a listar quais pares de saldos não batem, com a diferença em reais e a quantidade de lançamentos do dia.
- heimdall update agora recusa opção que não conhece em vez de ignorar (digitar --restart errado fazia a atualização terminar sem reiniciar e sem avisar) e aceita -r como atalho de --restart.
- Heimdall Design completo: heimdall_design.py passou a ser a fonte única de cores (claro e escuro), tipografia, medidas, foco, CSS compartilhado e botão; o Cloud deixou de ter CSS próprio e os demais painéis herdam dele. A página Design ficou com sete seções (link lê e botão age, cores com a tabela de contraste calculada dos mesmos valores, tipografia e medidas, componentes, lista de acessibilidade para leitor de tela e teclado, tom do texto e passo a passo para criar ou mudar páginas). O teste teste_design.py agora confere contraste mínimo nos dois temas (4,5 para texto e 3 para bordas), foco nunca removido, corpo de 18 px, alvo mínimo de toque, ausência de cores soltas nos painéis, pt-BR e viewport. O novo CLAUDE.md na raiz do repositório obriga a seguir o Heimdall Design em toda atualização.
- Finance, pasta de entrada organizada: arquivo duplicado (mesmo conteúdo já importado, cópia de um arquivo que já espera revisão, ou todos os lançamentos já existentes) não é importado e a cópia é apagada, sem deixar registro vazio no histórico. Os arquivos .motivo.txt de revisar somem sozinhos quando o arquivo some de lá, e com `heimdall finance --import ARQUIVO --force` sobre um arquivo de revisar o arquivo vai para importados e o motivo é apagado. O banco ganhou a coluna hash_arquivo em importacoes.
- O leitor de PDF repara espaços soltos no meio de datas e valores que o pypdf produz (por exemplo 99/9 9, 99/ 99, 99 ,99, 9.9 99,99). Isso fazia a fatura do Itaú perder quase metade dos lançamentos e falhar na conferência.
- A fatura de cartão que traz no fim a lista de parcelas das próximas faturas (Itaú) passou a conferir: se a soma de todos os lançamentos não bate com nenhum total do documento, o leitor procura o maior começo da lista cuja soma bate com um total citado e ignora o resto, avisando quantos lançamentos ignorou. A lista de totais mostrada na revisão passou de 6 para 12 valores.
- Heimdall Design: padrão de interface igual em todos os sites, "link lê, botão age". Novo módulo heimdall_design.py (botão de ação como formulário GET, com nome acessível), página de documentação Design e teste teste_design.py, que falha se um link de algum painel tiver texto de ação. Aplicado nos seis painéis: Cloud (Continuar, Baixar, Atualizar este resultado, Ver resultado), Notas (Nota anterior, Próxima nota, Todas as notas do tema, Baixar o arquivo original), Saúde (períodos de 7 dias e semelhantes, Ver a visão geral, Ver hoje, Conferir de novo, Ver o estado dos dados), Jogos e News (Ver as categorias, Ver todos os jogos, Ver todas as notícias) e Finance (a paginação agora usa o módulo heimdall_paginacao, igual a News e Notas, e "Ver todos os pagamentos sem fatura importada" virou botão). Única exceção: "Atualizar dados agora" da Saúde abre o app Atalhos e continua sendo link com role="button".
- Finance: o que é ação agora é botão e não link (Alterar categoria, Classificar agora, Importar extrato, Baixar tudo em CSV e a troca de visão). Link ficou só para quem leva a outra página para ler: o menu, Voltar, a paginação e as categorias do Resumo. Cada botão de "Alterar categoria" tem o nome acessível com a descrição do lançamento.
- Finance, duas visões para as somas do Resumo e das Tendências, com um link para trocar: por compra (competência, o padrão: o gasto conta no dia da compra e o pagamento da fatura fica de fora) e por saída de caixa (conta o que saiu das contas, inclusive o pagamento da fatura, e as compras do cartão ficam de fora). Nas duas, nada é contado duas vezes.
- Finance, faturas pagas sem fatura importada: o pagamento de fatura que nenhuma fatura importada explica (nenhum crédito de pagamento de mesmo valor em um cartão e nenhum total de fatura igual) entra nas despesas como "Fatura paga sem fatura importada", para não se perder o gasto, e o Resumo lista cada um com um link para mudar a categoria. Se a fatura for de outra pessoa, a categoria nova "Fatura de terceiros" tira o pagamento das somas. A página Transações ganhou o produto "Faturas pagas sem fatura importada". O banco ganhou a coluna importacao_id (preenchida sozinha para o que já existia).
- Finance, página Transações: novos filtros de conta (Nubank, Itaú, Mercado Pago, cada um com cartão ou conta) e de produto (cartão, Pix, boleto, outras transferências, entre minhas contas, pagamento de fatura e outros), com a quantidade de lançamentos em cada opção. A lista ganhou a coluna Produto e, acima dela, entradas, saídas e saldo do que o filtro mostra, para conferir com o extrato. O produto é deduzido da categoria, do nome da conta e da descrição.
- Os comandos que abrem painéis (cloud, notes, news, health, games e finance) agora abrem por padrão o endereço público, que passa pelo Cloudflare Access e pelo Microsoft Authenticator (o nome vem de HEIMDALL_<PAINEL>_HOSTS no .env, ou do padrão "<painel>.heimdall-ai.tech"). Com --local (forma curta -L) abrem o endereço deste Mac, que continua pedindo senha e código de 6 dígitos.
- Leitor de PDF: uma porcentagem (por exemplo 9,99%) não é mais lida como valor em reais; na fatura do Itaú ela era tomada como valor da compra quando havia texto com porcentagem na coluna da direita. Na fatura de cartão, a linha "IOF em R$ x,xx" da compra internacional, que vem sem data, passa a entrar como lançamento (IOF compra internacional).
- O diagnóstico (--explain) passou a mostrar, em cada linha de total do documento, o valor citado, quantos lançamentos já tinham sido lidos e a soma acumulada, e as linhas de título de seção (só palavras genéricas), para localizar onde cada seção termina.
- heimdall update agora recarrega os comandos do heimdall no próprio terminal (não precisa mais do source ~/heimdall-ai/heimdall.zsh depois de atualizar).
- O diagnóstico (--explain) informa se o texto foi lido com pdftotext ou pypdf e passou a deixar legíveis mais rótulos genéricos de fatura (parceladas, próximas, atuais, demais, titular, internacionais etc.), para mostrar onde cada seção começa. Nomes, valores e números continuam anônimos.
- Novo diagnóstico anônimo de PDF: heimdall finance --explain ARQUIVO mostra, linha por linha e sem dados reais, o que o leitor fez com cada linha (lançamento, saldo, ignorada, sem data, sem valor) e quantos saldos do dia fecham em cada orientação. A conferência de saldos do extrato ganhou uma terceira orientação (ordem do mais novo para o mais antigo, com o saldo no fim do dia).
- O Finance agora importa PDF de extrato e de fatura, além de OFX e CSV. O texto do PDF é lido por linhas de data, descrição e valor (pypdf, que já está no requirements.txt, ou pdftotext) e o total que o próprio documento cita ("Total da fatura") é conferido com a soma dos lançamentos. Só o PDF que confere entra sozinho; se não conferir, a tela e a linha de comando pedem revisão, e na pasta de entrada o arquivo vai para revisar. Na fatura, compra é gasto e estorno ou pagamento é crédito; no extrato de conta, a coluna de saldo é ignorada.
- O banco (Nubank, Itaú, Mercado Pago) e o tipo (conta ou cartão) são identificados pelo conteúdo e pelo nome do arquivo, e a conta sugerida (por exemplo "Nubank cartão") é usada quando você deixa o nome em branco. O CSV de fatura do Nubank (date, category, title, amount) é reconhecido e tem o sinal invertido sozinho.
- Pasta de entrada vigiada (dados_financas/entrada): solte os arquivos lá e, a cada minuto, o que conferir é importado (vai para importados/) e o que deixar dúvida vai para revisar/ com um .motivo.txt. A página Importar lista os arquivos para revisar.
- Novos comandos: heimdall finance --folder (abre a pasta), --inspect ARQUIVO (mostra só a estrutura do arquivo, com letras trocadas por x e números por 9, e copia para a área de transferência, para mostrar o layout do seu banco sem expor dados), --preview ARQUIVO (mostra o que seria importado, sem gravar), --import ARQUIVO [--account NOME] [--force] e --inbox (importa a pasta agora).
- O leitor entende fatura com as compras em duas colunas lado a lado (uma data, uma descrição e um valor por coluna), sem confundir a parcela "03/10" com uma data nova.
- Extrato de conta em PDF (como o do Itaú, com o saldo só nas linhas "SALDO DO DIA"): a conferência usa os saldos. Entre dois saldos do dia, a soma dos lançamentos tem de explicar a diferença; se um lançamento for lido errado, o saldo acusa. Funciona em ordem cronológica e inversa.
- O tipo (conta ou cartão) agora pesa sinais fortes ("Total desta fatura", "Limite total de crédito", "Saldo do dia") antes da palavra solta "fatura": um extrato que lista o pagamento "FATURA ITAU UNICLASS" não é mais tomado por fatura. Esse pagamento é categorizado como Pagamento de fatura, e "REND PAGO APLIC" como Investimentos.
- Fatura do Nubank em OFX: o tipo cartão agora é identificado pelas tags do próprio OFX (<CCSTMTRS>, <CREDITCARDMSGSRSV1>), e o sinal do arquivo é respeitado (compra negativa, pagamento positivo). "Pagamento recebido" e "Pagamento efetuado" na fatura são pagamento de fatura e não contam como receita. A inspeção de OFX passou a manter as tags de fechamento.
- Fatura do Nubank em PDF: lê datas no formato "28 DEZ", tira o "•••• 1234" (final do cartão) da descrição, entende o sinal de menos tipográfico (−R$) e ignora o "Saldo em atraso". O ano da compra é o que deixa a data mais perto do vencimento do documento (compra de dezembro numa fatura que vence em janeiro fica no ano anterior). A conferência também aceita o "Total de compras" sem os encargos (juros, multa e IOF). "Pagamento em ..." é pagamento de fatura, e crédito sem regra em conta de cartão fica fora das receitas.
- Aviso honesto: o leitor de PDF é genérico e foi testado com documentos inventados. O layout real de cada banco ainda precisa ser conferido; rode --inspect em um arquivo de cada tipo (conta e cartão, nos três bancos) para ajustar. Os arquivos reais nunca precisam sair do Mac.
- Novos: financas_arquivos.py, financas_cli.py e teste_finance_arquivos.py (69 verificações); teste_finance.py ganhou o envio de PDF pelo formulário.
- Para aplicar: heimdall update --restart (não precisa de instalador; o pypdf já está no requirements.txt).

## 2026-11-16 - Jogos em ordem alfabética e fim dos jogos de terceiros sem português
- Dentro de cada categoria, os jogos agora aparecem em ordem alfabética (sem diferenciar acentos e ignorando o artigo inicial: A Caverna dos Ecos fica no C). A documentação do site segue a mesma ordem, agora organizada por categoria, e heimdall games --list mostra o título de cada jogo e o comando para abri-lo, em ordem alfabética (a lista antiga nem tinha o Sonar e o Labirinto).
- Retirados o Enigma e o PlayAural, que não têm versão em português: some o instalador instalar_jogos_extras.sh, a opção heimdall games --extras e a sua ajuda. A regra agora é: jogos de terceiros só entram se tiverem versão em português ou permitirem tradução. O mecanismo HEIMDALL_JOGOS_EXTRAS continua existindo para listar um jogo que atenda a esse critério.
- Se você chegou a instalar o Enigma em Docker: o contêiner se chama heimdall-enigma, e docker stop heimdall-enigma e docker rm heimdall-enigma o removem.
- Novo teste em teste_jogos.py para a ordem dos jogos. Para aplicar: heimdall update --restart (não precisa de instalador); abra um terminal novo (ou rode source ~/.zshrc) para o comando heimdall carregar a lista nova.

## 2026-11-16 - Categorias em ordem alfabética e comandos com a grafia correta
- As categorias da página de jogos agora aparecem em ordem alfabética: Ação, Aventuras de texto, Cartas, Cassino, Números e lógica, Palavras e letras e Tabuleiro e estratégia.
- Os comandos mostrados nas ajudas, nos rótulos dos campos, nas mensagens e nas páginas de documentação agora usam a grafia correta: lançar, posição, histórico, dúzia, ímpar, peças e último. As formas sem acento (lancar, posicao, historico e assim por diante) continuam funcionando como alternativa, e as acentuadas também são aceitas quando você digita.
- Na roleta, a aposta em ímpar agora é falada com acento.
- Para aplicar: heimdall update --restart (não precisa de instalador).

## 2026-11-16 - Novo jogo: Labirinto
- Labirinto sorteado, na categoria Ação: você começa no canto de cima à esquerda e acha a saída no canto de baixo à direita, andando com norte, sul, leste e oeste (leste 3 anda até três casas; correr leste segue o corredor até uma bifurcação, um beco ou a saída). Cada labirinto tem um único caminho certo.
- Três níveis: fácil (6 por 6, descreve as passagens a cada passo, farol e dicas à vontade), normal (9 por 9, descreve só cruzamentos, curvas e becos, farol 8 vezes e 4 dicas) e difícil (12 por 12, só fala o que você pedir com olhar, farol 3 vezes e 1 dica).
- O farol diz a direção e a distância em linha reta até a saída (os corredores dão voltas); a dica diz o primeiro passo do caminho mais curto. No fim, o jogo compara os seus passos com o caminho mais curto.
- O som é a camada de acessibilidade: passos ao andar, uma batida grave na parede e o farol ecoando do lado da saída, mais demorado quanto mais longe e mais agudo ao norte, com a fala vindo depois. As setas andam.
- Novos testes: teste_jogos_labirinto.js (lógica) e o teste de interface do Labirinto em teste_jogos_ui.js. Para aplicar: heimdall update --restart (não precisa de instalador).

## 2026-11-16 - Novo jogo: Sonar
- Sonar é um caça-submarinos por turnos, na categoria Tabuleiro e estratégia. Você comanda um navio num mar quadriculado (norte, sul, leste e oeste) e manda pings de sonar: o eco diz a que distância e em que direção (oito sentidos) está o submarino mais próximo, só de modo aproximado. Pingando de lugares diferentes você cruza as pistas e acha onde ele está; então lança uma carga de profundidade na casa exata.
- Três níveis: fácil (mar de 8 por 8, 1 submarino, 20 pings, 6 cargas), normal (10 por 10, 2 submarinos) e difícil (12 por 12, 3 submarinos que se movem a cada ping). Os pings e as cargas são limitados; acabar com as cargas antes de afundar todos os submarinos é derrota.
- O som é a camada de acessibilidade: o eco demora mais quanto mais longe está o alvo, vem do lado da direção e é mais agudo quando o alvo está ao norte; a fala só vem depois do eco. Atalhos: setas movem, P pinga e L lança (também há botões e comandos digitados).
- Novos testes: teste_jogos_sonar.js (lógica) e o teste de interface do Sonar em teste_jogos_ui.js. Para aplicar: heimdall update --restart (não precisa de instalador).

## 2026-11-16 - Sons de apoio em todos os jogos e categoria Ação
- Os sons de apoio chegaram aos demais jogos: Forca (acerto e erro de letra), Senha, Número secreto (som que sobe quando o número é maior e que desce quando é menor), Cinco letras, Jogo da velha, Sudoku, 2048 (deslizar e fundir peças), Xadrez (peça, captura e xeque), Batalha naval (água, tiro e afundou), Campo minado, Gramado (passos, bandeira, sensor e explosão) e as aventuras (som de recusa e de desfecho). Todos ganharam o botão Sons para ligar e desligar, e a escolha fica gravada no navegador.
- A fala sempre espera o som terminar. Descrições longas, consultas e dicas não tocam nada: só acontecimentos claros e recusas.
- A categoria "Jogos de áudio" virou "Ação", já que o som deixou de ser o objetivo e passou a ser o recurso. O endereço antigo /categoria/audio continua abrindo a mesma página.
- Novos testes em teste_jogos_ui.js. Para aplicar: heimdall update --restart (não precisa de instalador).

## 2026-11-16 - Sons de apoio nos jogos de cassino e de cartas
- Novo módulo de sons (jogos/som.js), pensado como recurso de acessibilidade e não como atrativo: um som curto marca cada acontecimento e a fala só começa depois que o som termina, para o VoiceOver não atropelar.
- Roleta: ficha ao apostar, a bola correndo e parando ao girar, e um som de resultado (ganhou, grande, empate ou perdeu). Caça-níqueis: os três rolos parando e o som do prêmio ou da perda.
- Blackjack, Bacará, Poker caribenho, Poker Texas hold'em e Paciência: ficha nas apostas, carta ou cartas ao dar e comprar, e sons de ganhou, perdeu, empate, estouro e grande. Comandos de consulta (saldo, apostas, ajuda, histórico) nunca tocam som, e uma recusa ("Não entendi", "Aposta inválida") toca um som curto de erro.
- Cada um desses jogos ganhou o botão "Sons: ligados. Aperte para desligar", que liga e desliga tudo. A escolha fica gravada no navegador. Sem áudio no navegador, nada muda: o jogo continua falado.
- Novos testes em teste_jogos_ui.js. Para aplicar: heimdall update --restart (não precisa de instalador).

## 2026-11-16 - Arqueiro de áudio: narração completa, curta ou nenhuma
- Novo seletor "Narração" no jogo. Completa descreve tudo, como antes. Curta usa frases enxutas ("Pássaro, esquerda.", "Acertou! Mais 3.", "Errou, 6 à direita.", "Escapou."). Mínima fala só o essencial: "3 de 10." quando entra um alvo, "Acertou.", "Errou.", "Escapou.", "Corvo." e o resultado final.
- O padrão acompanha o nível: fácil com narração completa, normal com curta e difícil com mínima. Dá para trocar a narração à vontade, antes de iniciar.
- O rótulo do campo do jogo, que o VoiceOver lê toda vez que o foco entra nele, também segue a narração: completa lê a explicação toda (setas, espaço, comandos e Enter), curta lê "Área de jogo. Setas movem a mira, espaço atira." e mínima lê só "Área de jogo.".
- Dicas pedidas por você (Onde estou, Pontos, Ajuda) e a pausa continuam sempre completas. Sem áudio no navegador, a narração fica completa, porque a fala é o único jeito de saber onde está o alvo.
- Novo teste em teste_jogos_ui.js. Para aplicar: heimdall update --restart (não precisa de instalador).

## 2026-11-16 - Arqueiro de áudio: teste de som em sequência e setas que funcionam
- O botão Testar o som agora toca os três sons (só esquerda, meio, só direita) um de cada vez, com folga entre eles, e só depois do último o VoiceOver lê a explicação. Antes a fala atropelava os sons. Clicar de novo reinicia o teste sem sobrepor.
- As setas e o espaço passaram a valer em qualquer lugar da página enquanto a partida está rodando (antes só valiam com o foco dentro do campo de texto, e o VoiceOver costuma reter as setas fora dele). Continuam ignoradas no seletor de nível e em outros campos de texto, e o espaço não dispara tiro quando o foco está num botão. No campo do jogo, Enter ainda envia comandos digitados.
- Dica: se as setas ainda não responderem, desligue a Navegação Rápida do VoiceOver (setas esquerda e direita juntas) ou use os botões e comandos. (Testei marcar a área como role="application", mas isso atrapalhou o VoiceOver e foi desfeito.)
- Correção: o áudio do navegador (Safari) pode nascer suspenso e ficar mudo; o Testar o som agora retoma o áudio e só então toca os três sons.
- Novos testes em teste_jogos_ui.js. Para aplicar: heimdall update --restart (não precisa de instalador).

## 2026-11-16 - heimdall env grava as variáveis do Cloudflare Access
- heimdall env --set agora também aceita HEIMDALL_CFACCESS_EQUIPE, HEIMDALL_CFACCESS_AUD, HEIMDALL_CFACCESS_EMAILS e HEIMDALL_CFACCESS_CONVIDADOS com o valor direto no comando, sem copiar e colar cada um (exemplo: heimdall env --set HEIMDALL_CFACCESS_EQUIPE mrl2-bolonhini). Esses valores não são segredos.
- Segurança: o valor na linha de comando só vale para essas quatro variáveis, com formato conferido; para os segredos (chaves do R2 e senha da cópia) continua valendo só a área de transferência, e o comando recusa aspas simples e nomes fora da lista.
- Correção: o login pelo Access entrava em laço de redirecionamentos ("O Safari não pode abrir a página: redireções em excesso"). O caminho começa em outro site (Microsoft e Cloudflare) e o navegador não envia o cookie SameSite=Strict nos redirecionamentos dessa cadeia, então o painel nunca via a sessão recém-criada. Agora /entrar responde com uma página rápida que grava o cookie e segue sozinha para o painel (navegação do mesmo site, o cookie vai). Vale para Cloud, Notas, News, Saúde, Jogos e Finance; o cookie continua HttpOnly e SameSite=Strict.
- python3 heimdall_cfaccess.py --status e --verificar passaram a ler as variáveis do Access direto do .env quando rodados no Terminal (antes mostravam tudo vazio, porque só os serviços carregam o .env).
- Novas verificações em teste_cfaccess.py. Para aplicar: heimdall update --restart (não precisa de instalador).

## 2026-11-16 - Acesso por usuário no Cloudflare Access (dono e convidados)
- Dá para liberar pessoas diferentes em endereços diferentes: HEIMDALL_CFACCESS_EMAILS são os donos (entram em todos os painéis) e HEIMDALL_CFACCESS_CONVIDADOS libera cada convidado só nos serviços que você escolher, no formato ana@exemplo.com=jogos;beto@exemplo.com=jogos+finance. HEIMDALL_CFACCESS_AUD aceita várias tags (uma por aplicativo do Access).
- A sessão de convidado leva o nome do serviço dentro do token assinado e só vale naquele painel; o cookie do domínio todo não abre os outros. A sessão de dono continua valendo em todos. Cada painel confere isso de novo, mesmo que o Cloudflare deixasse passar por engano.
- O guia LEIAME_autenticacao_microsoft.txt agora explica a ordem do login (e-mail e senha da Microsoft antes da notificação no celular), os dois aplicativos do Access (pessoal e games) e como exigir MFA na política.
- Novos testes em teste_cfaccess.py (convidado liberado, convidado barrado em outro serviço, escopo adulterado, várias AUDs). Para aplicar: heimdall update --restart; nada muda até configurar o .env.

## 2026-11-16 - Heimdall Finance (finance.heimdall-ai.tech)
- Novo painel de finanças, no mesmo padrão dos outros (mesmo login, só em 127.0.0.1, porta 8016, CSRF em todo envio, sem script nas páginas). Você importa extratos do banco e faturas do cartão em OFX ou CSV (formatos e valores brasileiros, CSV com linhas antes do cabeçalho, inversão de sinal para fatura de cartão); importar o mesmo arquivo de novo não duplica nada.
- Categorias por regras: já vêm regras para mercado, restaurantes, transporte, contas, saúde, assinaturas, educação, lazer, compras, tarifas, salário e outros. Ao corrigir a categoria de um lançamento, a regra nasce sozinha e vale para os parecidos e para as próximas importações; as suas regras vencem as padrão, e o que você categoriza à mão nunca é alterado.
- Páginas: resumo do mês (receitas, despesas, saldo, gasto por categoria com variação sobre o mês anterior, dez maiores gastos), transações com filtro e busca, tendências mês a mês com alertas de categoria que dispara, importar extrato, regras. Tabelas com legenda e cabeçalhos para leitor de tela. Pagamento de fatura, investimentos e transferências entre contas ficam fora das somas.
- Privacidade: banco SQLite em dados_financas/ (fora do git, permissão só sua). Nada vai para a internet, para a Cloudflare ou para modelo de fora.
- Novos: heimdall finance, heimdall logs --service finance, teste_finance.py (73 verificações), financas_nucleo.py e heimdall_finance.py. Ainda não lê os bancos sozinho: a ligação com o Open Finance (MeuPluggy) vem depois, só se a conta de desenvolvedor da Pluggy continuar gratuita.
- Para aplicar: heimdall update --restart (não precisa de instalador). O nome finance.heimdall-ai.tech já foi criado no túnel Cloudflare (apontando para localhost:8016, com o DNS), então de fora ele passa a responder depois da atualização.

## 2026-11-16 - Entrada por aprovação no Microsoft Authenticator (Cloudflare Access)
- Novo módulo heimdall_cfaccess.py: os cinco painéis (Cloud, Notas, News, Saúde e Jogos) passam a aceitar a aprovação do Cloudflare Access, que usa o Microsoft Entra ID. Você aprova por notificação no Microsoft Authenticator (digitando no celular o número mostrado na tela) e entra sem senha nem código de 6 dígitos.
- Os painéis conferem a assinatura RS256 do documento do Cloudflare sem biblioteca de fora e checam emissor, aplicativo (AUD), validade e e-mail permitido. Os certificados são guardados por 1 hora e buscados de novo quando a chave gira.
- Fica desligado até você preencher HEIMDALL_CFACCESS_EQUIPE, HEIMDALL_CFACCESS_AUD e HEIMDALL_CFACCESS_EMAILS no .env. Senha e código de 6 dígitos continuam valendo como reserva e no acesso por localhost ou Tailscale. python3 heimdall_cfaccess.py --status confere a configuração.
- Novo teste: teste_cfaccess.py (chaves de teste, token adulterado, expirado, de outro aplicativo ou de e-mail não permitido, cache e fluxo HTTP). Passo a passo para criar a conta Microsoft e configurar o Cloudflare: LEIAME_autenticacao_microsoft.txt.
- Para aplicar: heimdall update --restart. Nada muda até você configurar o .env e o Cloudflare.

## 2026-11-16 - Arqueiro de áudio (primeiro jogo de som)
- Novo jogo: Arqueiro de áudio, guiado pelo som em estéreo (use fones de ouvido). Pássaros cruzam o céu em nove pontos e piam a cada passo no lado onde estão; você move a mira com as setas (cada passo faz um ping no lado da mira) e atira com a barra de espaço. Também há botões e comandos de texto. São 10 alvos, nos níveis fácil (devagar, tolerância de um passo, duas flechas), normal (mira exata) e difícil (rápido, rumo que muda e corvos que não se deve atingir).
- O botão "Testar o som" toca três sons (só esquerda, meio, só direita) para conferir o estéreo. Sem áudio no navegador, o jogo diz em texto onde o alvo está.
- Nova categoria no portal: Jogos de áudio. Novo teste: teste_jogos_arqueiro.js (testa a lógica; o som e o VoiceOver não foram testados, e é preciso experimentar). heimdall games --play arqueiro, Tab, ajuda e site atualizados.
- Para aplicar: heimdall update --restart.

## 2026-11-16 - Poker Texas hold'em
- Novo jogo: Poker Texas hold'em, você contra o computador (mano a mano), com fichas de mentira. Duas cartas só suas, flop, turn e river, quatro rodadas de apostas, e vale a melhor mão de cinco entre as sete. O jogo lê as cartas, a mesa, o nome da sua mão e cada jogada do computador. Comandos: continuar, pagar, passar, apostar N, tudo, desistir, mao, fichas, tabela, dica, resumo.
- As cegas começam em 5 e 10 e dobram a cada 6 mãos; a partida termina quando alguém fica sem fichas. O computador decide pela chance de ganhar (simulada) e pelo preço de pagar. Níveis: fácil (300 fichas, adversário que paga muito e aposta pouco, dicas à vontade), normal (200, adversário médio, 5 dicas) e difícil (200, adversário que aposta com força e blefa, sem dicas). O teste confere que o difícil vence a maioria das partidas contra o normal.
- Entra na categoria Cartas. Novo teste: teste_jogos_poker.js (inclui partidas inteiras com conferência de fichas). heimdall games --play poker, Tab, ajuda e site atualizados.
- Para aplicar: heimdall update --restart.

## 2026-11-16 - Poker caribenho
- Novo jogo: Poker caribenho (Caribbean Stud) contra a banca, com créditos de mentira. Você aposta o ante, recebe cinco cartas abertas (o jogo lê a sua mão por nome) e decide entre aumentar (mais duas vezes o ante) e desistir. A banca mostra uma carta e só joga com Ás e Rei ou melhor; o aumento paga de 1 para 1 (par) a 100 para 1 (royal flush). Sem prêmio acumulado.
- A dica simula as mãos possíveis da banca e diz se vale a pena aumentar. O teste mede que, jogando assim, a casa leva cerca de 5% do ante, como na teoria.
- Níveis: fácil (100 créditos, dicas à vontade), normal (100 créditos, 3 dicas) e difícil (60 créditos, sem dicas). Entra na categoria Cassino. Novo teste: teste_jogos_caribenho.js. heimdall games --play caribenho, Tab, ajuda e site atualizados.
- Para aplicar: heimdall update --restart.

## 2026-11-16 - Bacará
- Novo jogo: Bacará (punto banco) com créditos de mentira. Você aposta no jogador, na banca ou no empate (apostar 10 banca, repetir); o jogo dá as cartas, aplica sozinho as regras da terceira carta (conferidas por teste contra a tabela completa) e lê cada passo. Também há tabela, historico, saldo e dica.
- Pagamentos: jogador e banca 1 para 1 (a banca que vence com sete em três cartas só devolve a aposta), empate 8 para 1, e no empate as apostas nos outros lados voltam. Retorno medido no teste: cerca de 99% no jogador e na banca, 86% no empate.
- Níveis: fácil (100 créditos, dicas à vontade), normal (100 créditos, 3 dicas) e difícil (60 créditos, sem dicas). Entra na categoria Cassino. Novo teste: teste_jogos_bacara.js. heimdall games --play bacara, Tab, ajuda e site atualizados.
- Para aplicar: heimdall update --restart.

## 2026-11-16 - Roleta
- Novo jogo: Roleta com créditos de mentira. Você faz várias apostas (vermelho, preto, par, impar, alto, baixo, duzia 1 a 3, coluna 1 a 3 ou um número de 0 a 36) e manda girar; o jogo lê onde a bola parou e o resultado de cada aposta. Também há apostas, limpar, repetir, tabela, historico e saldo.
- Níveis: fácil (100 créditos, roleta europeia), normal (60 créditos, europeia) e difícil (60 créditos, roleta americana com zero e duplo zero, que é mais dura). O teste mede o retorno: cerca de 97% na europeia e 95% na americana.
- Entra na categoria Cassino. Novo teste: teste_jogos_roleta.js. heimdall games --play roleta, Tab, ajuda e site atualizados.
- Para aplicar: heimdall update --restart.

## 2026-11-16 - Blackjack e categoria Cassino
- Novo jogo: Blackjack contra a banca, com créditos de mentira. Aposta par de 2 a 50 (apostar N ou repetir), pedir, parar, dobrar, dividir, mao, banca, saldo, tabela e dica. Blackjack natural paga 3 para 2, a banca compra até 17 e para em qualquer 17, e o sapato (4 ou 6 baralhos) é embaralhado de novo quando acaba.
- Níveis: fácil (100 créditos, dicas à vontade), normal (100 créditos, 5 dicas) e difícil (60 créditos, sem dicas). A dica segue a estratégia básica; o teste mede que, jogando assim, a banca leva só cerca de 1% do apostado.
- A categoria "Sorte" do portal passou a se chamar "Cassino" (caça-níqueis e blackjack).
- Novo teste: teste_jogos_blackjack.js. heimdall games --play blackjack, Tab, ajuda e site atualizados.
- Para aplicar: heimdall update --restart.

## 2026-11-16 - Paciência (Klondike) falada
- Novo jogo: Paciência, com sete colunas, monte, descarte e quatro bases. Cartas escritas como 7C, QE ou "7 de copas". Comandos: comprar, mover CARTA para COLUNA (leva as cartas abertas em cima junto), mover descarte para COLUNA, subir CARTA/descarte/coluna N, mesa, coluna N, descarte, bases, dica, desfazer e resumo.
- Níveis: fácil (compra 1, dicas à vontade), normal (compra 1, 3 dicas) e difícil (compra 3, sem dicas e sem desfazer). A dica prefere subir para a base, depois virar uma carta fechada, e só então comprar.
- Nova categoria no portal: Cartas. Novo teste: teste_jogos_paciencia.js (inclui um robô que joga 60 partidas). heimdall games --play paciencia, Tab, ajuda e site atualizados.
- Para aplicar: heimdall update --restart.

## 2026-11-16 - A Travessia das Três Provas (aventura de escolhas com lógica)
- Nova aventura de escolhas numeradas, com três problemas de lógica: a travessia do rio (raposa, galinha e milho), as três portas com frases (só uma é verdadeira) e os dois guardas (um diz a verdade, o outro mente). Você responde com o número da escolha, ou com os botões.
- Níveis: fácil (o jogo avisa antes de um erro e não castiga, dicas à vontade), normal (3 vidas, 3 dicas) e difícil (1 vida, sem dicas). A dica do rio calcula o melhor próximo passo; cada erro explica por que a escolha não servia.
- Entra na categoria Aventuras de texto. Novo teste: teste_jogos_escolhas.js. heimdall games --play escolhas, Tab, ajuda e site atualizados.
- Para aplicar: heimdall update --restart.

## 2026-11-15 - Gramado (campo minado por movimento)
- Novo jogo: Gramado. Em vez de digitar linha e coluna, você conduz um cortador de grama com norte, sul, leste e oeste (leste 3 anda várias casas e para quando há aviso). Cada casa cortada diz quantos formigueiros há ao redor. Níveis: fácil 6 por 6 com 5 formigueiros (o sensor apita antes de você pisar e dicas à vontade), normal 8 por 8 com 10 (3 dicas) e difícil 10 por 10 com 20 (sem dicas).
- O gramado é gerado de modo que todas as casas seguras sejam alcançáveis, e a dica só afirma o que é certo pelos números já descobertos.
- Entra na categoria Tabuleiro e estratégia. Novo teste: teste_jogos_gramado.js. heimdall games --play gramado, Tab, ajuda e site atualizados.
- Para aplicar: heimdall update --restart.

## 2026-11-15 - A Caverna dos Ecos e jogos por categoria
- Nova aventura, A Caverna dos Ecos: guiada pelo som. O comando escutar (e ouvir) diz o que você ouve onde está, e isso mostra o caminho; onde diz o lugar e as saídas. Três níveis: no difícil há um enigma de ritmo na parede, é preciso montar uma corda com gancho e entrar no salão sem luz é perigoso.
- O motor de aventuras ganhou os comandos escutar e onde (campo "escuta" nas salas); não contam como passo.
- O portal agora separa os jogos em categorias (Palavras e letras, Números e lógica, Tabuleiro e estratégia, Sorte, Aventuras de texto): a página inicial lista as categorias e cada uma tem a sua página, em /categoria/ID.
- Testes, heimdall games --play caverna, Tab, ajuda e site atualizados.
- Para aplicar: heimdall update --restart.

## 2026-11-15 - Sudoku por comandos
- Novo jogo: sudoku por comandos, com o tabuleiro gerado na hora e solução sempre única (conferida por contagem de soluções). Você coloca com "colocar 5 em 3 4" (valor, linha, coluna) e ouve: linha, coluna, quadrante, casa (com os números que podem entrar), tabuleiro, quais números faltam e casas vazias. Também apagar, desfazer, verificar, dica, resumo e desistir. Números repetidos em linha, coluna ou quadrante são recusados na hora, dizendo onde já existe.
- Níveis: fácil (40 números dados, o jogo avisa na hora se o número não é o certo, dicas à vontade), normal (32 dados, 3 dicas, e verificar aponta os erros) e difícil (26 dados, sem dicas e sem conferência).
- Novo teste: teste_jogos_sudoku.js. heimdall games --play sudoku, Tab, ajuda e site atualizados.
- Para aplicar: heimdall update --restart.

## 2026-11-15 - Cinco letras (Wordle em português)
- Novo jogo: Cinco letras, no estilo Wordle. Palavra secreta de 5 letras em português, sorteada de uma lista de mais de 400 palavras comuns. Você digita um palpite (acentos não importam; qualquer combinação de 5 letras vale) e a resposta é lida letra por letra: lugar certo, em outro lugar ou não tem, com a regra correta para letras repetidas. Comandos: tentativas, pistas, letras, dica e desistir.
- Níveis: fácil (8 tentativas e dicas à vontade), normal (6 tentativas e uma dica) e difícil (6 tentativas, sem dicas, e cada palpite precisa reaproveitar o que já foi descoberto).
- Novo teste: teste_jogos_cincoletras.js. heimdall games --play cincoletras, Tab, ajuda e site atualizados.
- Para aplicar: heimdall update --restart.

## 2026-11-15 - Batalha naval e caça-níqueis mais generoso
- Novo jogo: batalha naval contra o computador (tabuleiro 10 por 10, frota clássica de 5 navios sorteada para os dois lados). Você atira dizendo a casa (B7 ou tiro b7) e ouve o resultado (água, acertou, afundou) e a resposta do computador. Comandos para ler: frota, tiros, inimigo, restantes, linha 3, coluna c, resumo, ultimo e dica. Três níveis: fácil (ao acaso, uns 96 tiros em média), normal (caça em volta dos acertos, uns 53) e difícil (calcula onde os navios restantes mais cabem, uns 44).
- Caça-níqueis: além da trinca (25 vezes) e da sequência (10 vezes), agora dois números iguais (um par) pagam 2 vezes. Cerca de 3 em cada 10 rodadas pagam algo, e o retorno médio fica perto de 99%, para o jogo não ser tão seco.
- Testes: teste_jogos_naval.js (frotas, tiros, leitura, vitória, e que o computador nunca repete casa e é mais forte a cada nível); teste_jogos_novos.js cobre o par do caça-níqueis.
- Para aplicar: heimdall update --restart.

## 2026-11-15 - Heimdall Jogos: xadrez, campo minado, caça-níqueis, aventuras com níveis e jogos de terceiros
- Três jogos novos: xadrez completo contra o computador (roque, en passant, promoção, xeque, mate, afogamento, repetição, cinquenta lances e material insuficiente; três níveis; você escreve o lance como e4, Cf3, Cxe5, O-O, e8=D ou e2 e4, com R, D, T, B e C para as peças; comandos para ler tabuleiro, linha, coluna e casa, dica e desfazer; o motor foi conferido contra as contagens oficiais de lances de quatro posições), campo minado (três tamanhos, grade de botões com rótulo de linha e coluna, ou comandos como abrir 3 4 e marcar 3 4; a primeira jogada nunca é mina) e o caça-níqueis (três dígitos de 0 a 9; trinca paga 25 vezes, sequência como 1 2 3 ou 9 0 1 paga 10 vezes, dois números iguais, um par, paga 2 vezes e sai em cerca de 27% das rodadas; o resto perde a aposta; 30 créditos de mentira, sem dinheiro de verdade).
- Novo motor de aventuras de texto (jogos/motor.js) com histórias em dados (jogos/hist_*.js) e três graus de dificuldade: fácil (dicas à vontade, sem limite de passos), normal (3 dicas, limite de passos folgado) e difícil (sem dicas, limite apertado, enigmas a mais e perigos). Tem salas com saídas travadas, itens, escuro e luz, conversas, códigos, objetivo, mapa, tempo, salvar e carregar no navegador.
- Três aventuras novas e maiores: A Mansão dos Relógios (mistério), O Templo Submerso (exploração contra a maré) e Estação Orion (ficção científica). O Farol Apagado continua como aventura curta de introdução.
- O portal agrupa os 12 jogos em Clássicos, Tabuleiro e sorte e Aventuras de texto.
- Jogos de terceiros: bash instalar_jogos_extras.sh (ou heimdall games --extras) sobe o Enigma em Docker na porta 8015, só neste Mac, com o segredo de sessão gerado e guardado no .env, e põe o link no portal; --playaural lista só o link do serviço play.ddt.one; --status e --remover. Sem teste com o VoiceOver: o Enigma é em inglês ou espanhol, tem contas próprias e não declara acessibilidade, e o PlayAural é um serviço externo fora do login do Heimdall.
- heimdall games --play aceita os novos jogos (xadrez, minas, sorte, relogios, templo, orion), com Tab para completar, e --list foi atualizado.
- Novos testes: teste_jogos_xadrez.js (contagens oficiais de lances, notação, fim de partida, IA), teste_jogos_novos.js (campo minado e caça-níqueis), teste_historias.js (valida os dados, joga a solução de cada aventura nos três níveis, confere dicas, limite de passos, perigos e salvar e carregar), e teste_jogos.py e teste_jogos_ui.js ampliados.
- Para aplicar: heimdall update --restart. Para os jogos de terceiros: heimdall games --extras --enigma (precisa do Docker Desktop aberto; a imagem do Enigma é só amd64, então no Mac com chip Apple roda por emulação, com --platform linux/amd64).

## 2026-11-15 - Heimdall Jogos: subdomínio de jogos leves para leitor de tela
- Novo serviço heimdall_jogos.py (porta 8014, games.heimdall-ai.tech): portal com seis jogos que rodam no navegador, feitos para leitor de tela. Tudo é HTML comum (botões, campos e listas) e cada jogada é dita em voz alta por uma região aria-live. O servidor não guarda nada.
- Jogos: forca (palavras em português por categoria, sem se importar com acentos), senha (Mastermind, 4 dígitos de 1 a 6 em 10 tentativas), jogo da velha contra o computador (fácil e difícil; no difícil ele não perde), número secreto, 2048 (botões ou setas, com descrição de cada jogada e botão para ler o tabuleiro) e a aventura de texto O Farol Apagado. Cada jogo é um arquivo JavaScript da pasta jogos/, sem dependências.
- Segurança: escuta só em 127.0.0.1, mesmo login do Cloud (senha e código de 6 dígitos), limite de tentativas, sessão em cookie HttpOnly, lista de sites permitidos e política de conteúdo que só deixa rodar script do próprio site (sem script embutido nem conexões externas). Só os arquivos .js do catálogo são entregues.
- HEIMDALL_JOGOS_EXTRAS no .env lista outros jogos que você hospeda à parte (por exemplo uma coleção de quebra-cabeças em Docker), no formato Nome|endereço|descrição separados por ponto e vírgula; só http e https. O portal mostra esses links junto com os jogos.
- Sobe com o start_heimdall.sh quando há senha e código no .env, aparece no subir.sh --status e no heimdall: heimdall games, heimdall games --play forca, heimdall games --list e heimdall logs --service games. Página Jogos no site.
- Novos testes: python3 teste_jogos.py (servidor, login, arquivos servidos, cabeçalhos, e os dois testes abaixo em Node), teste_jogos_logica.js (regras de cada jogo, inclusive que o computador do jogo da velha nunca perde e que a aventura tem caminho até a vitória) e teste_jogos_ui.js (interface com um DOM de mentira).
- Para aplicar: heimdall update --restart. Para acessar de fora, falta criar o nome games.heimdall-ai.tech no túnel Cloudflare, apontando para localhost:8014 (passo a passo na página Jogos do site).

## 2026-11-15 - Comando heimdall unificado no zsh
- Novo heimdall.zsh: um único comando heimdall para todo o ecossistema, todo em inglês e no padrão "heimdall SERVIÇO --opção": o comando é o serviço e tudo o que ele faz vem em opções com dois hífens. heimdall help lista tudo, e a tecla Tab completa comandos e opções.
- Serviços (sem opção abrem no navegador): chat, notes, news, cloud, health, n8n, kuma, dozzle; urls lista os endereços. Controle: up, restart, stop, status, logs, containers, models, update, docs, test, flows, hook.
- health abre o painel (--open PÁGINA abre uma página) e, com opções, roda o relatório no terminal: --today, --now, --weekly, --anomalies, --report, --sleep, --activity, --recovery, --trends, --workouts, --ecg, --fc, --import e --import-n8n. As opções em inglês são traduzidas para as dos programas, então python3 heimdall_saude.py continua igual (ganhou --anomalias).
- Outros comandos: triage, db, backup (--prepare, --password, --run, --list, --verify, --restore), mail, access (--password, --code, --all, --verify), voice, listen, ingest, env --set, cloudflare, mcp, chat --diagnose e --password, notes --clean-mirrors, --clean-private e --move-old, flows --advanced, --basic, --privacy e --email, docs --brand, test --list, --all e --run NOME.
- Ajuda por comando: heimdall COMANDO --help (ou -h) mostra só as variações daquele comando, e heimdall help lista todos os comandos. heimdall help COMANDO faz o mesmo que COMANDO --help.
- Forma curta de uma letra para toda opção documentada, como nas ferramentas de mercado: -h --help, -a --all, -v --verify, -r --run, -s --sql, -t --today e assim por diante. Cada comando tem as suas letras (heimdall COMANDO --help mostra). Letras maiúsculas separam opções com a mesma inicial (no health, -a é --anomalies e -A é --activity). Várias letras juntas, como -wt, não são aceitas: escreva -w -t.
- heimdall help --doc (ou -d) abre no navegador o documento com todos os comandos e opções explicados: a nova página Comando heimdall do site (docs/comando-heimdall.html). Ela e a ajuda do terminal vêm da mesma fonte, heimdall_ajuda.txt, e a página é gerada por gerar_docs.py.
- Correção: o Safari recusava abrir o documento por file:// ("outside the sandbox"). Agora heimdall help --doc serve a página por um servidor local mínimo em http://localhost:8099 (só 127.0.0.1, a partir da pasta docs/) e abre esse endereço. O servidor continua ligado em segundo plano e sai com heimdall stop.
- Novo teste: python3 teste_comando_heimdall.py (ajuda de todos os comandos, formas curtas, tradução das opções e help --doc).
- As ações antigas claude e gemini foram removidas, junto com a dependência do LaunchAgent e das pastas claude_version e gemini_version.
- instalar_comando_heimdall.sh faz cópia do .zshrc, remove a função antiga e liga o heimdall.zsh. Daí em diante o comando se atualiza com o git pull (heimdall update).
- A página de anomalias, com o banco sem histórico suficiente, agora diz isso em vez de dizer que nada saiu do normal.

## 2026-11-15 - Anomalias: cada medida de saúde comparada com o seu normal, em todos os dados
- Novo módulo heimdall_anomalias.py. Para cada medida guardada (pulso em repouso, variabilidade, respiração, oxigênio média e mínimo, sono total, profundo e REM, distúrbios respiratórios, temperatura do pulso, caminhada, VO2 máximo, passos, energia, exercício, horas em pé, andares, luz do dia, peso e qualquer medida nova que o Health Auto Export mande) ele compara o último dia com o seu normal dos 30 dias anteriores, usando mediana e desvio robusto, para um dia atípico no histórico não distorcer o normal.
- Cada medida tem a sua variação mínima: mudança pequena em valor absoluto não conta. Há um sentido bom e um ruim (variabilidade maior que o normal é positiva, menor é alerta). Mudança absoluta grande conta mesmo quando o seu normal é muito variável.
- Também aponta há quantos dias seguidos a medida está fora do normal e uma mudança lenta (média dos últimos 7 dias fora do normal mesmo que o último dia, sozinho, pareça normal). Medidas do dia inteiro (passos, energia etc.) são avaliadas no último dia completo, nunca no dia de hoje pela metade.
- Frequência cardíaca hora a hora: a madrugada (0h às 7h) e as horas já medidas de hoje são comparadas com as mesmas horas dos 14 dias anteriores.
- Cruzamento de sinais: pulso alto, variabilidade baixa, respiração mais rápida, oxigênio baixo, sono curto e temperatura alta, três ou mais juntos, geram um aviso de padrão de estresse, infecção ou má recuperação. Distúrbios respiratórios altos com oxigênio baixo (ou com sono curto e pulso alto na madrugada) geram um aviso de padrão compatível com o que se investiga na apneia do sono. Nada disso é diagnóstico.
- Onde aparece: nova página Anomalias do painel de saúde, um bloco "Fora do seu normal" na visão geral, a ferramenta de chat analise_saude com tema anomalias, python3 heimdall_anomalias.py [AAAA-MM-DD] no terminal e um item de triagem (alto) por dia quando há um padrão combinado ou pelo menos duas medidas muito fora do normal, aberto pelo agente a cada envio do Health Auto Export, sem duplicar.
- Medidas sem histórico suficiente (menos de 10 dias) ou sem dado recente aparecem no rodapé como não comparadas, para você saber o que o monitor não está vendo.
- Novo teste: python3 teste_anomalias.py.
- Para aplicar: ./subir.sh --reiniciar (agente, painel e MCP). Nenhum fluxo do n8n mudou.

## 2026-11-15 - Resumo de saúde refeito quando o sono chega, aviso no estilo Sinais Vitais e frequência cardíaca da madrugada
- O resumo das 5h50 saía antes de o iPhone sincronizar o sono da noite. Agora, se saiu sem o sono, o fluxo refaz o resumo uma única vez assim que chegam o sono e pelo menos um sinal da noite (pulso, variabilidade, respiração ou oxigênio). A nota do dia é atualizada, e o aviso vai ao próximo grupo (8h ou 10h) ou, depois das 10h, na hora e sem som.
- Novo aviso no estilo do app Sinais Vitais da Apple: quando duas ou mais medidas da noite (pulso em repouso, respiração no sono, oxigênio, temperatura do pulso, duração do sono) ficam fora do seu intervalo típico dos últimos 30 dias, para mais ou para menos, o resumo destaca isso e abre um item na triagem (alto). Mudança pequena em valor absoluto não conta.
- Frequência cardíaca da madrugada: quando a média entre 0h e 7h fica pelo menos 10 bpm (e 2,5 desvios) acima do seu normal dos últimos 14 dias, o agente abre um item na triagem (alto), a cada envio do Health Auto Export, sem duplicar no mesmo dia. A página Hoje do painel mostra a madrugada comparada com o normal. Isso cobre o caso em que o pulso em repouso do dia ainda não existe. Não é diagnóstico.
- Oxigênio mínimo: o monitor guardava só a média do oxigênio, que esconde quedas pontuais. Agora guarda também a menor leitura do dia (spo2_min, sem nunca subir num envio posterior). Menor leitura até 92 % entra no resumo como relevante; até 90 % vira item de triagem (alto); até 88 % vira item crítico. A página Hoje mostra a menor leitura. A leitura no pulso pode errar; não é diagnóstico.
- Temperatura do pulso e distúrbios respiratórios do sono já eram aceitos: basta o Health Auto Export enviá-los. O aviso de sinais vitais ou de apneia da Apple em si é uma notificação do iPhone e não é exportado.
- Novo teste: python3 teste_saude_fluxo.py roda os nós de código do fluxo com Node.
- Para aplicar: ./subir.sh --reiniciar (agente com o alerta de frequência cardíaca) e bash instalar_automacoes_avancadas.sh (importa o fluxo).

## 2026-11-15 - heimdall news com as opções de fontes e feeds
- heimdall news --sources [NOME] mostra o que cada feed entrega agora (quantos itens e a idade deles), heimdall news --queue a fila de resumos, heimdall news --now atualiza na hora, e --token, --urls, --copy e --opml cuidam dos feeds RSS. Todas têm a forma curta de uma letra (-s, -q, -n, -t, -u, -c, -o) e completam com Tab. Sem opção, o comando continua abrindo o site.
- heimdall update atualiza a branch em que você está (git pull --ff-only), então vale tanto para a main quanto para a develop. A instrução do roteiro da Cloud passou a usar a branch atual em vez de fixar a main.

## 2026-11-15 - Anomalias de saúde: dado errado não vira alerta, e o aviso só repete quando algo muda
- Energia em repouso chegava em kJ do Health Auto Export e era lida como kcal (8.425 "kcal" por dia, quando eram cerca de 2.000 kcal). O banco agora converte kJ para kcal ao gravar e corrige o que já estava gravado.
- O total do dia de passos, energia e demais medidas somadas era trocado pelo do último envio. Com o envio de hora em hora, o dia passava a valer só as últimas horas (por isso 384 kJ, 264 passos). O fluxo de saúde agora guarda cada hora recebida e soma todas, sem duplicar reenvios; uma exportação diária completa prevalece sobre horas parciais. Para reconstruir os dias já afetados (12 a 15/11), rode de novo o atalho "Exportar dados de saúde".
- Valores impossíveis para um dia inteiro (energia em repouso fora de 800 a 4.500 kcal, frequência fora do possível etc.) ficam fora do normal e do alerta e aparecem no rodapé como dado incorreto.
- O aviso na triagem só sai quando algo muda: sinal novo ou que piorou. O mesmo quadro não repete; reaparece como lembrete depois de 5 dias (HEIMDALL_ANOMALIAS_LEMBRETE_H). Quando o quadro normaliza e volta, conta como novidade.
- O texto do aviso agora é interpretado pelo modelo local (HEIMDALL_SAUDE_MODELO): avalia se o corpo mudou ou se o dado parece errado (relógio fora do pulso, dia incompleto, unidade, ruído), diz o que mudou desde o último aviso e sugere duas ou três ações. Sem resposta do modelo, sai o texto simples. Dados de saúde nunca vão para a Cloudflare.

## 2026-11-15 - Aviso de fonte dos diários fora do ar com o tempo real
- O aviso "Fonte dos diários oficiais indisponível há 24 horas" era enviado uma única vez, e o Bark repetia o mesmo texto a cada 2 horas, mesmo com a fonte fora havia dias. Agora o aviso traz a data e a hora em que a fonte parou de responder e o tempo decorrido (por exemplo, "sem resposta desde 10/11/2026 às 19:05, há 5 dias").
- O aviso é refeito às 24 horas, aos 3 dias, aos 7 dias e a cada 7 dias, cada um como um novo item da triagem com o tempo atualizado; avisos de marcos anteriores podem ser dispensados.
- A mensagem diz o que de fato acontece: tentativas a cada 2 horas nos primeiros 3 dias e depois uma vez por dia, na consulta das 9h40, e que não dá para saber se houve publicações enquanto a fonte estava fora. Para o fluxo atualizado valer, rode bash instalar_monitor_privacidade.sh.

## 2026-11-14 - Histórico do GitOps em nota e troca de senha do Open WebUI
- O GitOps passou a gravar uma nota em Heimdall-ai/GitOps quando um commit gera Pull Request em rascunho ou trechos descartados: repositório, branch, quantos trechos foram analisados, quais foram descartados e o motivo de cada um, e o que o modelo propôs. Commit sem achados não gera nota. Antes, o motivo dos descartes só existia no aviso do Bark.
- trocar_senha_webui.sh troca a senha de um usuário do Open WebUI sem recriar o contêiner nem perder conversas ou configurações: faz cópia do volume em backups/, pede a nova senha duas vezes sem mostrá-la, troca só o hash no banco e confere. Não reinicia nada.
- A mesma troca também oferece o Uptime Kuma (status), pelo reset de senha do próprio Kuma (só com banco sqlite) e lembra de trocar o n8n pelo painel.
- GitOps: respostas do modelo cortadas pelo limite de tamanho agora têm mais folga. A resposta passou de 1500 para 3000 tokens, os trechos de 5 mil para 3500 caracteres (resposta menor por trecho), o limite por commit de 24 para 36 trechos e o contexto do deepseek-coder-v2 de 6144 para 8192 tokens. Custo: um pouco mais de memória e análise mais demorada.
- Painel de saúde: botão "Atualizar dados agora" (só aparece no iPhone). Ele abre o atalho "Exportar dados de saúde" (nome em HEIMDALL_SAUDE_ATALHO), que roda as automações do Health Auto Export, e volta para o Estado dos dados. A página confere uma vez sozinha depois de 20 segundos, tem o link Conferir de novo e avisa se, passados 2 minutos, nenhum dado novo foi gravado. O painel continua somente leitura.
- Senha única: python3 heimdall_acesso.py --senha (ou --tudo) agora oferece aplicar a mesma senha no Open WebUI, pelo trocar_senha_webui.sh --stdin. O Open WebUI não tem o código de 6 dígitos e a senha dele não pode passar de 72 bytes (limite do bcrypt).
- Para aplicar: ./subir.sh --reiniciar (agente do Mac com a pasta GitOps) e bash instalar_automacoes_avancadas.sh (importa o fluxo).

## 2026-11-14 - Tarefas de segurança do dolphin
- O dolphin3-cyber-8b passou a trabalhar sozinho, sem ferramentas: o script coleta os dados no Mac (heimdall_seguranca.py) e o modelo só analisa o texto. Três tarefas agendadas no fluxo "tarefas de segurança do dolphin": logs das últimas 24 horas todo dia às 4h30 (acessos recusados e erros repetidos), commits da semana aos domingos às 5h (segredos, caminhos pessoais, IPs privados, e-mails, arquivos sensíveis) e exposição à rede aos domingos às 5h30 (portas em escuta, contêineres, Tailscale Funnel, firewall), comparada com a semana anterior.
- Como o modelo é de 8B e inventa achados: cada achado precisa citar um trecho dos dados e o script confere se o trecho existe; o script também define uma gravidade mínima por conta própria; sem evidência confirmada, média ou alta dita só pelo modelo vira baixa; segredos são mascarados e as notas não trazem os dados brutos. O modelo só é chamado quando há o que analisar.
- A nota vai para Heimdall-ai/Segurança só quando há o que dizer. Gravidade média vira uma linha no aviso das 10h; alta fura a fila do Bark e entra na lista de triagem. Se o dolphin não responder, vale o que o script verificou e o aviso de falha chega pelo Bark.
- Novo: rota POST /seguranca/executar no agente do Mac; python3 heimdall_seguranca.py logs|commits|exposicao [--sem-modelo] para rodar à mão; python3 teste_seguranca.py. O dolphin sai da memória 30 segundos depois do uso (keep_alive).
- Para aplicar: reiniciar o agente (./subir.sh --reiniciar) e rodar bash instalar_automacoes_avancadas.sh para importar o fluxo novo.

## 2026-11-14 - Modelos revisados
- Saíram do LiteLLM e do Ollama o qwen-3.8-uncensored e o bonsai-27b, que não estavam em uso. O agente local de teste (heimdall_agent.py) passou a usar o qwen3-vl:8b-instruct.
- Entrou o llama-3.1-8b (ollama pull llama3.1:8b): o template do Ollama traz suporte a ferramentas e ele respondeu bem em português.
- O dolphin3-cyber-8b foi marcado como sem suporte a ferramentas (supports_function_calling: false), porque não chamou ferramentas no teste de 02/11; fica para tarefas só de texto, como revisão de segurança.
- Para aplicar: reiniciar o LiteLLM e, no Mac, apagar do Ollama os dois modelos que saíram.

## 2026-11-14 - Fontes do News revisadas
- Pelo python3 heimdall_news.py --fontes: o feed do G1 São Paulo estava parado havia 8 anos e o da Agência FAPESP vinha vazio; os dois foram desligados ("ativa": false).
- Novas fontes: Metrópoles São Paulo e Câmara Municipal de São Paulo (local), Hugging Face (inteligência artificial), Universe Today (astronomia), Revista Pesquisa FAPESP e ScienceDaily (ciência). Os feeds foram conferidos como válidos e recentes.
- AWS novidades entregava títulos em português parados em 2024: a AWS serve uma versão traduzida e antiga do feed a quem pede português, e o News pedia sempre pt-BR. Nova opção "lingua" por fonte (en para a AWS novidades) escolhe o idioma pedido ao site.
- Curiosidades: o Fatos Desconhecidos não tem feed (o endereço /feed/ responde 204, sem conteúdo) e foi desligado; entrou Mental Floss (curiosidades em inglês, com título traduzido). O --fontes agora avisa qual fonte está baixando e desiste de cada uma em 15 segundos.
- O arXiv só publica de segunda a sexta, então aos sábados e domingos seus feeds vêm vazios, e isso é normal.
- python3 heimdall_news.py --fontes NOME mostra só essa fonte ou categoria, com os 3 itens mais novos e as datas.

## 2026-11-14 - Mais serviços da Cloudflare
- Caixa de entrada da saúde (Worker banco-saude-caixa, cloudflare/saude_caixa.js): fica na frente do webhook de saúde do n8n, no mesmo endereço que o Health Auto Export já usa, sem mudar nada no app. Com o Mac no ar, repassa tudo como veio. Com o Mac dormindo ou sem rede, guarda o envio no KV (7 dias, até 200 envios, até 8 MB cada) e responde 202 ao app; de 5 em 5 minutos reenvia ao n8n o que ficou e apaga o que foi aceito. Opcional: o segredo TOKEN_SAUDE faz a caixa guardar só envios com o cabeçalho certo.
- Reserva de resumos do News no Workers AI: se o modelo local não responder, o resumo da notícia é feito pelo modelo mistral-small-3.1 (24 bilhões) da Cloudflare (limite de 60 por dia, desligável com HEIMDALL_NEWS_RESERVA=0). Só o News usa isso, só com matérias públicas; dados pessoais e de saúde nunca saem do Mac.
- Leitura de páginas com navegador no News (Browser Rendering): em uma fonte de noticias_fontes.json, "renderizar": true faz a matéria ser lida por um navegador da Cloudflare, para sites que só mostram o texto com JavaScript (limite de 20 por dia; se falhar, volta ao jeito normal).
- Reserva de resumos passou a usar o endereço ai/run da Cloudflare, que aceita token com Workers AI em Leitura ou Edição; a tela do News agora mostra o motivo do modelo local e o código de resposta da Cloudflare. Novos: python3 cloudflare_chave.py --testar (testa Workers AI e Browser Run com a chave gravada) e python3 heimdall_news.py --fontes (mostra o que cada feed entrega agora).
- cloudflare_chave.py confere o token pelo endereço de verificação e, se ele não puder listar contas (só com as permissões do News), pede o número da conta, que fica no endereço do painel.
- python3 cloudflare_chave.py grava o token da Cloudflare no .env (pedido sem aparecer na tela) e descobre o número da conta sozinho. A página de status do News mostra se a Cloudflare está ligada e quanto foi usado.

## 2026-11-14 - Vigia na Cloudflare
- Aviso por e-mail da Cloudflare quando o túnel heimdall cai, fica degradado ou volta (política de Notificações da conta).
- Worker heimdall-vigia (cloudflare/vigia.js): de 5 em 5 minutos confere de fora de casa os endereços chat, flows, cloud, notes, news e health. Avisa por e-mail só nas mudanças (cai depois de duas conferências seguidas, volta quando responde), guardando o estado em um KV. Quando o Mac dorme ou perde a rede, é isso que acusa.
- O destino do e-mail fica na variável ALERTA_PARA do Worker, gravada na própria Cloudflare e nunca no GitHub.

## 2026-11-13 - Uma sessão só para os quatro serviços
- Entrar em um dos serviços (Cloud, Notas, News ou Saúde) vale para os outros três: o cookie passou a ser único (heimdall_sessao), válido em *.heimdall-ai.tech, HttpOnly, SameSite=Strict e Secure.
- A sessão é assinada (HMAC) com uma chave derivada da senha e da chave do código gravadas no .env: não depende da memória de cada serviço, então reiniciar um serviço não derruba a sessão. Trocar a senha ou o código derruba todas; sair em um sai em todos.
- Em localhost o cookie continua só no endereço aberto (cada porta é um site diferente para o navegador). O domínio pode ser mudado com HEIMDALL_COOKIE_DOMINIO no .env.

## 2026-11-13 - Conferir senha e código sem navegador
- `python3 heimdall_acesso.py --verificar` lê o .env, confere a senha digitada, mostra o código que o app deve exibir agora e diz se o código do app confere. Serve para achar se o problema é a gravação, a chave cadastrada no Senhas ou o relógio.

## 2026-11-13 - Site de documentação em dia
- Nova página Saúde: de onde vêm os dados (importação e Health Auto Export), análises, páginas do painel, relatório semanal, privacidade e solução de problemas.
- Início com os acessos de Notas, News e Saúde; mapa da arquitetura com o caminho dos dados de saúde, o banco pessoal e os painéis web, mais um texto que o descreve.
- Comandos de saúde, fila do News e voz na página Comandos; scripts de voz, importação e testes na lista de scripts; Notas e News descrevem a paginação em botões e os títulos inteiros.
- O painel de saúde saiu do Roadmap, por já estar pronto.

## 2026-11-13 - Painéis com a marca do Heimdall
- Cloud, Notas, News e Saúde passaram a usar a paleta da marca em um só lugar (o estilo compartilhado em heimdall_cloud.py): Papel (#f3f6fc) e Tinta (#0c1530) no tema claro, Noite (#080d1f) e Névoa (#e9effc) no escuro, azul da ponte nos links, campos e blocos de leitura sobre a superfície da marca. O Ouro do olhar marca só a página atual do menu e o botão de página selecionado (sublinhado e barra), nunca texto.
- Novo cabeçalho de marca: símbolo da ponte com o olho (decorativo para o leitor de tela, porque o nome vem ao lado), nome do serviço em serifa, menu e a faixa de seis cores sob o cabeçalho, como no site. Todos têm o ícone da aba (embutido, sem arquivo externo; a política de segurança ganhou apenas img-src data:).
- O menu marca a página atual (negrito, sublinhado dourado e aria-current) nos painéis que já indicavam isso (Saúde).
- Contraste conferido por teste nos dois temas: texto, links, erro e ok com pelo menos 4,5 para 1; bordas de campos com pelo menos 3 para 1.
- Para aplicar: git fetch e reset do repositório e ./subir.sh --reiniciar.

## 2026-11-13 - Paginação em botões no Notas e no News
- Os dois sites usam agora a mesma paginação, toda em botões: Página anterior, Página 1 a 5 (com a atual marcada como "Página 3 (atual)" e anunciada como página atual pelo leitor de tela), reticências quando há mais páginas, Próxima página e Última página. A janela de números acompanha a página atual. Página anterior some na primeira, Próxima e Última somem na última. Um resumo ("Página 3 de 10 · 97 notas") fica acima dos botões.
- No Notas, a paginação vale para as últimas notas do início, as notas de cada tema e os resultados da busca (10 por página); antes o início mostrava só as 15 mais recentes e os temas e a busca vinham numa lista única. No News, ela substitui os botões Anterior e Próxima (10 notícias por página, mantendo a categoria).
- O texto "Leia mais sobre..." do News tinha o mesmo corte de 45 caracteres com reticências que o do Notas; agora segue a mesma regra (inteiro até 110 caracteres).
- Código compartilhado em heimdall_paginacao.py. Para aplicar: git fetch e reset do repositório e ./subir.sh --reiniciar.

## 2026-11-13 - Títulos das notas sem corte
- No site Notas, o texto do link "Leia mais sobre ..." cortava o título em 45 caracteres e sempre acrescentava reticências, mesmo quando o título cabia. Agora o título aparece inteiro até 110 caracteres; acima disso, o corte é sempre num espaço, com reticências. A primeira frase usada para nomear notas genéricas passou de 90 para 140 caracteres.
- No fluxo de estudo, o conceito (que vira o título da nota) era cortado em 80 caracteres no meio da palavra e o título em 150; agora o corte, se necessário, é no espaço (120 caracteres) e o título não é mais cortado. O pedido ao modelo agora diz "de 2 a 6 palavras completas, no máximo 80 caracteres".
- Cabeçalhos (título da página, títulos da lista e das seções) agora quebram linha dentro da largura da tela, inclusive palavras longas e sem espaço, que antes podiam passar da borda e ficar cortadas, principalmente no iPhone.
- Notas que já foram gravadas com título cortado continuam como estão no app Notas; o site mostra o título que está dentro do arquivo. Para achá-las: python3 heimdall_notas.py --titulos-suspeitos lista as notas publicadas no site cujo título termina em conectivo (de, para, e...), pontuação, reticências, parêntese aberto ou tem um tamanho em que o Heimdall cortou títulos gravados (80, 120, 150, 200, 220 caracteres), com o caminho do arquivo e o motivo.
- Para aplicar: git fetch e reset do repositório, ./instalar_automacoes_avancadas.sh (atualiza o fluxo de estudo) e ./subir.sh --reiniciar.

## 2026-11-13 - Seção "Hoje" no relatório, no painel e no chat
- Nova seção "Hoje": o que já chegou de hoje (sono da noite, pulso em repouso, HRV, respiração, oxigênio, passos, exercício e energia até agora, frequência cardíaca por hora, treinos, ECG, sintomas e medicamentos), cada número comparado com o seu dia típico (mediana de 30 dias). Passos, exercício e energia avisam que o dia ainda não acabou.
- Se nada de hoje chegou, ela diz isso, informa a data do último dado recebido e lembra que a exportação diária pode ainda não ter rodado. Se só parte chegou, lista o que falta.
- Aparece no começo do relatório geral (e do semanal), na visão geral e numa página própria do painel (Hoje), no comando python3 heimdall_saude.py --hoje e na ferramenta analise_saude (tema hoje).
- Para aplicar: git fetch e reset do repositório e ./subir.sh --reiniciar.

## 2026-11-13 - Painel de saúde (health.heimdall-ai.tech) e Digest sem aviso no Bark
- Novo serviço heimdall_painel_saude.py (porta 8013): painel somente de leitura com visão geral (como você está agora e tendências), semana, sono, atividade, recuperação, coração e ECG, treinos, sintomas/humor/medicamentos, diário em tabela e o estado dos dados, que mostra há quantos dias cada tipo de dado não chega (útil para saber se a exportação contínua do iPhone parou). Período selecionável (7 a 365 dias). Sem gráficos: texto e tabelas, bons para leitor de tela.
- Mesmo login do Heimdall Cloud (senha e código de 6 dígitos), escuta só em 127.0.0.1, sessão HttpOnly, limite de tentativas, só atende os sites permitidos. Nunca mostra rota de treino nem forma de onda do ECG. Sobe sozinho no ./subir.sh --reiniciar.
- O fluxo do Digest deixou de avisar pelo Bark (o nó "Enviar ao iPhone" foi removido). A nota continua sendo gravada no app Notas; as notícias chegam pelo Heimdall News e pelos feeds RSS.
- Para aplicar: git fetch e reset do repositório, ./instalar_automacoes_avancadas.sh (atualiza o Digest no n8n) e ./subir.sh --reiniciar.

## 2026-11-13 - Relatório de saúde semanal (Notas e Bark)
- Todo domingo às 9h o n8n pede ao agente do Mac o relatório da semana (POST /saude/relatorio-semanal). O agente grava a nota "Saúde: semana de DD/MM a DD/MM/AAAA" na pasta Saúde do app Notas, com áudio (mesma voz e dicionário de pronúncia das outras notas), e manda um aviso pelo Bark.
- O aviso do Bark leva só uma frase qualitativa (por exemplo, se o sono saiu do seu padrão), sem números de saúde, porque o aviso passa pelo servidor do Bark. Os números ficam na nota.
- Novo fluxo do n8n: 18-saude-semanal.json, com botão para gerar na hora. Se falhar, o aviso de falha do Heimdall chega pelo Bark. Para ver o relatório sem gravar: python3 heimdall_saude.py --semanal.
- Para aplicar: git fetch e reset do repositório, ./instalar_automacoes_avancadas.sh (importa e ativa o fluxo novo) e ./subir.sh --reiniciar.

## 2026-11-13 - Análises de saúde que não dependem de treino
- O Apple Watch só grava um treino quando você inicia um no app Treino (ou aceita o aviso "parece que você está caminhando, iniciar treino?"). Sem isso o export não traz treinos, e isso não é falha do Heimdall.
- Novas análises em texto corrido, feitas com os dados do dia todo: --agora (últimos 7 dias contra a sua média dos 90 anteriores, para pulso em repouso, HRV, respiração, oxigênio e sono), --tendencias, --sono (duração, profundo, REM, eficiência, dia da semana), --atividade (passos, minutos de exercício, meta de 150 por semana, picos de esforço sem treino) e --recuperacao (o que acompanha a sua HRV e o seu pulso em repouso, dias de HRV baixa). O --relatorio passou a incluir tudo isso.
- Nova ferramenta no chat: analise_saude (tema: agora, tendencias, sono, atividade ou recuperacao).
- O texto de ECG com "Gravação Ruim" passou a ser explicado como inconclusivo, com dicas para uma gravação melhor; os ECG já gravados são reclassificados.
- Para aplicar: git fetch e reset do repositório, ./subir.sh --reiniciar (para o chat enxergar a ferramenta nova).

## 2026-11-13 - Importação do app Saúde em português
- No iPhone em português o arquivo principal do export.zip se chama exportar.xml, não export.xml, e a importação não o achava (só os ECG entravam). Agora ela reconhece os dois nomes e ignora o exportar_cda.xml (outro formato). Uma primeira versão da correção não funcionou com o arquivo real, porque o cabeçalho dele tem uma DTD longa; agora o nome basta e, para outros nomes, o conteúdo é conferido nos primeiros 60 mil bytes.
- A importação passou a dizer, no fim, quantos treinos (elementos Workout) havia no arquivo e o primeiro erro, se algum treino falhar.
- Para aplicar: git fetch e reset do repositório e rodar de novo python3 heimdall_saude.py --importar ~/Downloads/export.zip. Os ECG que já entraram não duplicam.

## 2026-11-13 - Treinos, ECG, frequência cardíaca e mais do ecossistema Apple
- Novas tabelas no banco pessoal: treinos (tipo, duração, distância, energia, frequência cardíaca e série, recuperação em 1 minuto, subida, esforço, rota), ecg (classificação da Apple e a forma de onda, com medidas dos batimentos calculadas pelo Heimdall), fc_hora (frequência cardíaca por hora) e saude_eventos (sintomas, humor, medicamentos, avisos de frequência cardíaca do relógio, ciclo).
- Duas entradas: o arquivo do app Saúde (python3 heimdall_saude.py --importar export.zip, traz o histórico inteiro, inclusive ECG e rotas) e o Health Auto Export, pelo mesmo webhook do n8n, que agora repassa ao agente do Mac (POST /saude/hae) treinos, ECG, frequência cardíaca, sintomas, humor, medicamentos e avisos.
- Análises em texto corrido: python3 heimdall_saude.py --relatorio, --treinos, --ecg e --fc, e quatro ferramentas no chat (treinos_resumo, ecg_resumo, frequencia_cardiaca_resumo, relatorio_saude). Cruzam a carga de treino com o pulso em repouso e a variabilidade.
- Um ECG classificado pela Apple como fibrilação atrial abre um item de nível alto na triagem. Tudo é informativo, não é diagnóstico.
- Privacidade: nome e data de nascimento do arquivo de exportação não são lidos; a rota dos treinos pode ser desligada com HEIMDALL_SAUDE_ROTA=0.
- Roteiro de configuração do iPhone em LEIAME_saude_apple.txt.
- Para aplicar: git fetch e reset do repositório, ./instalar_automacoes_avancadas.sh (atualiza o fluxo de saúde no n8n) e ./subir.sh --reiniciar.

## 2026-11-13 - Gravações das notas com voz de um atalho (Siri)
- Nova opção HEIMDALL_VOZ_ATALHO no .env: nome de um atalho do app Atalhos que recebe o texto e devolve o áudio (ação "Criar áudio falado a partir de texto"). Permite usar vozes que o say não enxerga, como a Siri. A voz e a velocidade ficam no próprio atalho; o dicionário de pronúncia continua valendo.
- Rodado à mão, o python3 heimdall_agente.py --voz agora lê as opções de voz do .env (antes só valiam com o serviço rodando).
- Se o atalho falhar, a gravação é feita pelo say com a voz de HEIMDALL_VOZ, e o motivo aparece no log. python3 heimdall_agente.py --voz toca uma amostra pelo atalho.
- Para aplicar: git fetch e reset do repositório e ./subir.sh --reiniciar.

## 2026-11-13 - Pronúncias do VoiceOver no dicionário
- O pronuncias.txt agora traz as 38 entradas do seu arquivo do VoiceOver (Heimdall vira Raimdall, GitHub, Whatsapp etc.). Ficaram de fora números romanos, símbolos, entradas vazias e a linha com dados pessoais.
- Novo python3 heimdall_voz.py --importar arquivo.csv: traz para o pronuncias.local.txt as entradas de um novo arquivo exportado do VoiceOver.
- O anúncio do subir.sh passou para 290 palavras por minuto (SUBIR_VOZ_PPM no .env muda).
- Para aplicar: git fetch e reset do repositório e ./subir.sh --reiniciar.

## 2026-11-13 - Dicionário de pronúncia, velocidade do anúncio e comando da fila
- Novo dicionário de pronúncia: o arquivo pronuncias.txt troca palavras por uma grafia que a voz lê certo ("Heimdall" vira "Háimdal"). Vale para o anúncio falado do subir.sh e para o áudio das notas. As suas entradas vão em pronuncias.local.txt (não sobe para o GitHub e ganha da outra). Formato: palavra = como falar.
- O anúncio do subir.sh fala a 290 palavras por minuto; mude com SUBIR_VOZ_PPM no .env. A velocidade das notas continua em HEIMDALL_VOZ_VELOCIDADE.
- Novo python3 heimdall_news.py --fila: mostra quantas notícias esperam resumo de IA, de quais fontes, o ritmo e quanto falta para esvaziar.
- Para aplicar: git fetch e reset do repositório e ./subir.sh --reiniciar.

## 2026-11-13 - Voz Felipe: reconhece "Aprimorado"
- No macOS em português a voz masculina aparece como "Felipe (Aprimorado)", no masculino, e por isso a primeira versão da SUBIR_VOZ não a achava. Agora o subir.sh procura a voz na lista do sistema (say -v '?') e usa a melhor variante instalada com aquele nome (Premium, depois Aprimorada/Aprimorado/Enhanced, depois a padrão).
- O áudio dos estudos (HEIMDALL_VOZ) também passou a tratar Aprimorado, Aprimorada e Enhanced como o mesmo nome. Para usar o Felipe nas gravações: HEIMDALL_VOZ='Felipe (Aprimorada)' no .env e ./subir.sh --reiniciar.
- Para aplicar: git fetch e reset do repositório e ./subir.sh --reiniciar.

## 2026-11-13 - News abre feeds comprimidos; voz do anúncio do subir.sh configurável
- Os feeds do G1 São Paulo e do ge futebol falhavam porque a Globo manda o corpo comprimido. O News agora pede e abre gzip/deflate (também quando o servidor comprime sem avisar), com limite de tamanho depois de descomprimir. Formatos que não abre (brotli, zstd) dão um erro claro no estado das fontes.
- Nova opção SUBIR_VOZ no .env para a voz do anúncio falado do subir.sh, por exemplo SUBIR_VOZ='Felipe (Aprimorada)'. O script tenta o nome como escrito e as variantes (Aprimorada, Enhanced, Premium) e, se a voz não estiver instalada, usa a voz do sistema. Não muda HEIMDALL_VOZ (áudio de estudo das Notas).
- Para aplicar: git fetch e reset do repositório e ./subir.sh --reiniciar.

## 2026-11-13 - News: endereço news.heimdall-ai.tech e arquivo OPML
- O endereço news.heimdall-ai.tech passou a existir no túnel Cloudflare, apontando para a porta 8012 (com o Mac ligado e o sistema no ar). O site continua protegido por senha e código de 6 dígitos, e os feeds RSS só respondem com a chave secreta.
- Novo python3 heimdall_news.py --opml [arquivo]: grava um arquivo OPML com todos os feeds (padrão heimdall-news.opml, permissão 600). Ele leva a chave secreta nos endereços; importe no app de feeds e apague o arquivo.
- Para aplicar: git fetch e reset do repositório; não precisa reiniciar para o endereço, só para o comando novo (que roda direto).

## 2026-11-13 - News: erro de fonte mais claro
- Quando uma fonte devolve uma página em vez de um feed, o estado das fontes agora diz o tipo da resposta e como ela começa (por exemplo, text/html), em vez de só "not well-formed". Ajuda a achar endereços de feed errados ou bloqueios.
- Para aplicar: git fetch e reset do repositório e ./subir.sh --reiniciar.

## 2026-11-13 - News passa a usar o gemma3-4b
- Testamos modelos pequenos para os resumos. O Tucano (Q3_K_M, 2,4 bilhões, feito para português) respondeu texto sem sentido e em repetição, mesmo com o formato de pedido que ele espera, e foi descartado. O gemma3:4b resumiu certo, sem inventar, em 8 a 25 segundos.
- Novo modelo gemma3-4b no litellm_config.yaml (ollama pull gemma3:4b), agora o padrão do News. Para voltar ao anterior: HEIMDALL_NEWS_MODELO="qwen3-vl-instruct" no .env.
- Para aplicar: git fetch e reset do repositório e ./subir.sh --reiniciar (o LiteLLM precisa reler o litellm_config.yaml).

## 2026-11-13 - News: rótulo do resumo simplificado
- O resumo passa a ser marcado sempre como "Resumo feito por IA:", sem o complemento sobre o trecho da fonte. No banco, a coluna resumo_base continua dizendo se foi lido a matéria ou só o trecho do feed.

## 2026-11-13 - News: paginação com botões
- Anterior e Próxima deixam de ser links e viram botões (mantendo a categoria escolhida). Não precisa instalador: git fetch e reset do repositório e ./subir.sh --reiniciar.

## 2026-11-13 - Acesso universal, mais fontes no News e links em nova aba
- Novo heimdall_acesso.py: a senha e o código de 6 dígitos valem para o Cloud, o Notas e o News, então o comando agora é um só. --tudo (nova senha e novo código), --senha (só troca a senha, o código continua o mesmo) e --codigo (só um código novo). Os comandos antigos do heimdall_cloud.py continuam funcionando. Depois de trocar: ./subir.sh --reiniciar.
- News: corrigido o erro "no such table: noticias" ao rodar --token, --urls ou --copiar antes da primeira subida (agora a tabela é criada na hora).
- News: seis fontes novas em português, sem tirar nenhuma: AWS Brasil (blog em português, em Dados e AWS), InfoMoney (Economia), ge futebol (Futebol), ESPN Brasil (Esportes), Jornal da USP e Agência FAPESP (Ciência). Agora são 21 fontes em 12 categorias. Se uma fonte não responder, ela aparece em "Estado das fontes".
- News: o link "Leia mais sobre ..." abre em uma nova aba (o leitor de tela anuncia "abre em nova aba").
- Para aplicar: git fetch e reset do repositório, python3 heimdall_news.py --token (se ainda não criou a chave dos feeds) e ./subir.sh --reiniciar. Se você já editou noticias_fontes.json, o git reset sobrescreve o arquivo: guarde uma cópia antes.

## 2026-11-12 - Heimdall News: notícias com resumo de IA e feeds RSS
- Novo serviço heimdall_news.py (porta 8012, news.heimdall-ai.tech quando você autorizar o endereço). Lê as 15 fontes do Digest em noticias_fontes.json (arquivo editável, relido a cada atualização) de 30 em 30 minutos, tira repetidas, traduz os títulos em inglês e pede a um modelo local (qwen3-vl-instruct por padrão, HEIMDALL_NEWS_MODELO troca) um resumo de cada matéria.
- Site com o mesmo login do Cloud e do Notas: notícias das últimas 24 horas, 10 por página (Anterior e Próxima), título como cabeçalho, resumo sempre marcado como "Resumo feito por IA" (e dito quando só havia o trecho do feed), link "Leia mais sobre ..." para a matéria, filtro por categoria e uma página de estado das fontes. Fica privado por enquanto.
- Banco pessoal: nova tabela noticias, com 30 dias de histórico para consulta (entra na cópia de segurança criptografada). O chat também enxerga a tabela.
- Feeds RSS para o app de feeds do iPhone, em endereços com chave secreta: geral, um por categoria e um OPML que traz todos. python3 heimdall_news.py --token cria ou troca a chave; --urls mostra os endereços; --copiar geral copia um endereço sem digitar. A chave nunca vai para o log.
- Para não competir com o chat: até 10 resumos por atualização (das notícias mais novas para as mais antigas, o resto espera na fila), orçamento de 20 minutos por atualização e pausa opcional de madrugada (HEIMDALL_NEWS_PAUSA). Se o modelo estiver fora do ar, as matérias esperam sem perder tentativa e o site avisa.
- Cuidados: feeds e matérias só de endereços públicos, entidades XML recusadas, texto de terceiros tratado como dado pelo modelo, fonte fora do ar não derruba as outras e aparece no estado (com aviso depois de 24 horas).
- Para aplicar: git fetch e reset do repositório, python3 heimdall_news.py --token e ./subir.sh --reiniciar. Não precisa rodar instalador. O Digest dos fluxos do n8n (7h45 e 18h) continua como está.

## 2026-11-12 - Todos os logs na pasta logs/
- Os logs de cada serviço (MCP do Mac, público e de dados, agente do Mac, Heimdall Cloud, Heimdall Notas, Open Terminal e a indexação) passam a ser gravados em logs/, por exemplo logs/notas_debug.log, em vez de ficarem soltos na pasta do projeto. A cada subida, o log anterior de cada serviço vai para logs/historico/ (os 5 mais recentes de cada), então o motivo de uma falha não se perde na subida seguinte. O log do Open Terminal continua com permissão 600, porque contém a chave.
- Mensagens, roteiros e a documentação passaram a apontar para logs/ (por exemplo: tail -20 logs/cloud_debug.log).
- subir.sh: ./subir.sh --log notas (log de um serviço), ./subir.sh --logs (lista) e ./subir.sh --limpar (apaga os logs antigos soltos na pasta do projeto: mcp_debug.log, mcp_public_debug.log, mcp_dados_debug.log, agente_debug.log, cloud_debug.log, notas_debug.log, open_terminal.log e ingest.log). Rode o --limpar depois de uma subida nova, quando esses serviços já estiverem gravando em logs/.
- subir.sh passou a esperar o start_heimdall.sh terminar de liberar as portas antes de contar serviços, para restos de uma subida anterior não aparecerem como "no ar" logo no início de um --reiniciar.
- Para aplicar: git fetch e reset do repositório, ./subir.sh --reiniciar e, depois, ./subir.sh --limpar.

## 2026-11-12 - subir.sh: sobe uma vez só, guarda o log e avisa quando tudo está no ar
- Novo comando ./subir.sh. Antes, rodar o start_heimdall.sh de novo enquanto uma subida ainda estava em andamento derrubava a anterior (aparecia "exit 137") e o heimdall.log era sobrescrito. Agora ele recusa iniciar uma segunda subida e diz como ver o andamento.
- Cada subida grava o log em logs/heimdall-AAAAMMDD-HHMMSS.log, guardando os 15 mais recentes, e heimdall.log aponta para o atual. Um heimdall.log solto de antes vai para o histórico em vez de ser apagado.
- Enquanto sobe, mostra cada serviço que ficou no ar ("No ar (3 de 11, 28s): Qdrant") e, ao final, "Tudo no ar" com notificação e voz do macOS, ou a lista do que faltou. Só confere o que deve subir naquela execução (Open WebUI, Open Terminal, n8n, agente, Cloud e Heimdall Notas dependem dos argumentos e do .env).
- Também: ./subir.sh --status (confere agora), --log (últimas 40 linhas) e --reiniciar (encerra a subida em andamento e sobe de novo). Sem argumentos usa --webui --terminal. SUBIR_ESPERA define a espera máxima (padrão 900 s) e SUBIR_SOM=0 desliga voz e notificação.
- O start_heimdall.sh continua igual e o comando antigo continua valendo. Não precisa rodar instalador nem reiniciar o agente.

## 2026-11-12 - Heimdall Notas: nomes técnicos também trocados
- O nome "Biblioteca" fica livre para o futuro: a ideia é uma biblioteca de verdade, com os documentos de knowledge/ separados em pastas por assunto e, mais adiante, uma base de conhecimento por modelo.
- Arquivos e nomes novos: heimdall_notas.py (antes heimdall_biblioteca.py), teste_notas.py, variáveis HEIMDALL_NOTAS_* no .env (PORT, HOST, HOSTS, PASTAS, EXCLUIR) e log notas_debug.log. Os nomes antigos HEIMDALL_BIBLIOTECA_* continuam valendo, então o seu .env não precisa mudar.
- Para aplicar: git fetch e reset do repositório, pkill -f heimdall_biblioteca.py (o processo antigo) e subir o sistema como de costume. O sistema libera a porta 8011 sozinho. Não precisa rodar instalador.

## 2026-11-12 - Biblioteca passa a se chamar Heimdall Notas
- O site para ler as notas e ouvir os áudios (porta 8011, notes.heimdall-ai.tech) agora se chama Heimdall Notas, nome mais fiel ao conteúdo. Mudou o nome mostrado nas páginas, no sistema e na documentação (a página do site agora é notas.html). Os nomes técnicos ficam iguais, para não quebrar o seu .env: heimdall_biblioteca.py, HEIMDALL_BIBLIOTECA_* e biblioteca_debug.log.
- Para aplicar: git fetch e reset do repositório e reiniciar com pkill -f heimdall_biblioteca.py, subindo o sistema como de costume.

## 2026-11-12 - Nomes das notas mais claros
- Heimdall Notas: o nome mostrado de cada nota perde os prefixos repetidos ("Estudo 2026-11-12 20h:", "Second Brain:") e títulos vagos ganham sentido a partir do conteúdo: "Monitor 2026-11-12" vira "Monitor de privacidade de 12/11/2026: 2 achados, atenção alto"; "Diários oficiais 2026-11-12" vira "Diários oficiais de 12/11/2026: 2 menções (DOU)"; "Saúde 2026-11-12" e títulos como "Resumo" ganham a primeira frase da nota. A data continua na linha abaixo do nome. Os arquivos e os nomes no app Notas das notas antigas não mudam.
- O link "Leia mais sobre" agora usa até 45 letras do nome, cortando em palavra inteira.
- Estudo: o título da nota nova passa a ser só o conceito (por exemplo "Média móvel simples"), sem "Estudo", data e hora; a data e a hora ficam na primeira linha do texto. Se já existir uma nota com o mesmo conceito no tema, a nova ganha " (2)", " (3)" em vez de substituir a anterior.
- Para aplicar: git fetch e reset do repositório, rodar bash instalar_automacoes_avancadas.sh (atualiza o fluxo de estudo) e reiniciar o agente (pkill -f heimdall_agente.py) e a Biblioteca (pkill -f heimdall_biblioteca.py), subindo o sistema como de costume.

## 2026-11-12 - Correção: trechos de livros do estudo vinham cortados no meio e repetidos
- Causa: em livros de PDF o texto vem em parágrafos enormes. O indexador (ingest_docs.py) cortava esses parágrafos a cada 1000 letras, no meio de palavras, e repetia a sobreposição de 150 letras duas vezes dentro do mesmo trecho. O fluxo de estudo tirava só uma das repetições, e a leitura ficava com uma frase cortada seguida da mesma frase de novo.
- O fluxo Estudo (13-estudo.json) agora desfaz a repetição também nos trechos já indexados, junta palavras partidas no fim da linha (exte-ior em duas linhas vira exterior), troca quebras de linha soltas por espaço e começa e termina a leitura em frases inteiras.
- O indexador passou a cortar em frases inteiras (e, no máximo, em espaços), com a sobreposição feita de frases completas. Vale para livros novos ou alterados; os já indexados não precisam ser refeitos (python3 ingest_docs.py --force só se quiser).
- Erros que já estão no texto do PDF (letras trocadas pelo OCR, como "nêío", ou "cilín dricas") não dá para corrigir sem mudar o arquivo de origem.
- Teste: python3 teste_trechos.py (50 conferências, usa o código real do fluxo no Node).
- Para aplicar: git fetch e reset do repositório e rodar bash instalar_automacoes_avancadas.sh (atualiza os fluxos no n8n). O ingest_docs.py novo só é usado na próxima indexação.

## 2026-11-12 - Biblioteca: cofre inteiro, sem o Digest, e "Leia mais"
- A Biblioteca agora mostra o cofre inteiro (temas de estudo, Second Brain, Monitor de Privacidade, Saúde e as demais pastas), menos o Digest. Para tirar pastas: HEIMDALL_BIBLIOTECA_EXCLUIR no .env.
- Nas listas, o nome de cada nota é um título e logo abaixo vem o link "Leia mais sobre [início do nome]...".
- Endereço público previsto: notes.heimdall-ai.tech (HEIMDALL_BIBLIOTECA_HOSTS já vem com ele). Como agora há notas pessoais, a entrada exige senha e código de 6 dígitos.
- Para aplicar: git fetch e reset do repositório e subir o sistema como de costume.

## 2026-11-12 - Biblioteca: site para ler as notas de estudo e ouvir os áudios
- Novo site simples, feito para leitor de tela, que lê direto do cofre (notas em Markdown e áudios .m4a) e de knowledge/, sem depender de aplicativo de notas. Endereço no Mac: http://localhost:8011, com a mesma senha e o mesmo código de 6 dígitos do Heimdall Cloud.
- Cada nota vira uma página limpa (títulos, listas, tabelas), com o leitor de áudio no topo: velocidade de 0,75 a 1,5 vez, voltar e avançar 15 segundos, e a página lembra onde você parou. O servidor aceita pedidos parciais (HTTP Range), exigidos pelo Safari do iPhone para tocar áudio.
- Início com as últimas notas e os temas, lista por tema, nota anterior e próxima, busca sem acento e maiúsculas, e os documentos de knowledge/ (PDF abre na página, Markdown e texto são lidos, outros formatos baixam).
- Pastas: no primeiro desenho só apareciam os temas de estudo; veja o bloco acima para o padrão atual.
- Somente leitura, escuta só em 127.0.0.1, caminhos conferidos contra fuga de pasta e todo texto escapado. O start_heimdall.sh sobe a Biblioteca sozinho quando há senha e código no .env (porta 8011, log em biblioteca_debug.log). Teste: python3 teste_biblioteca.py (66 conferências).
- Para aplicar: git fetch e reset do repositório e subir o sistema como de costume. Não precisa rodar instalador. Notas antigas podem não ter áudio; as novas terão, depois da correção da voz.

## 2026-11-12 - Emulador de AWS cai para o Moto quando o LocalStack recusa a chave
- Se o LocalStack parar logo ao subir, o start_heimdall.sh agora avisa o motivo e usa o Moto no mesmo endereço (porta 4566), em vez de deixar o painel Heimdall Cloud sem emulador. O caso comum é a licença recusada (LOCALSTACK_AUTH_TOKEN inválido, código de saída 55); o aviso diz para gerar outra chave em app.localstack.cloud e gravar no .env.
- Com o Moto, S3, DynamoDB, SQS e o console geral funcionam; Lambda, Glue e Athena ficam só simulados.
- Para aplicar: git fetch e reset do repositório e subir o sistema como de costume. Não precisa rodar instalador.

## 2026-11-12 - Heimdall Cloud: Lambda ativo, Glue e Athena
- Lambda agora executa por padrão: o LocalStack passa a receber o socket do Docker e a rede heimdall (LAMBDA_DOCKER_NETWORK), para as funções rodarem em contêineres. Para desligar: HEIMDALL_LOCALSTACK_DOCKER=0 no .env. O start_heimdall.sh recria o contêiner sozinho uma vez, quando o ajuste muda (o volume localstack é mantido). Atenção: isso dá ao LocalStack controle do Docker do Mac, e quem passa pelo painel (senha e código de 6 dígitos) executa código em contêineres.
- Nova página Glue: bancos de dados (criar, apagar), tabelas (criar a partir de uma pasta do S3 em CSV, JSON ou Parquet, com colunas e tipos; listar; apagar), crawlers (criar, executar, apagar, com a situação da última execução) e jobs (criar com o script Python guardado no bucket glue-scripts, executar, ver a última execução, apagar).
- Nova página Athena: escolha o banco do Glue, escreva o SQL e veja o resultado em tabela (até 500 linhas), com o histórico das últimas 10 consultas e a abertura de resultados antigos. Os resultados vão para o bucket athena-resultados, criado se faltar.
- A página inicial ganhou um roteiro de estudo (arquivo no S3, banco e tabela no Glue, consulta no Athena). A execução real de consultas do Athena e de crawlers e jobs do Glue depende do LocalStack; o Moto só simula parte disso.
- teste_cloud.py passou a ter 53 conferências, agora cobrindo Glue e Athena.
- Para aplicar: git fetch e reset do repositório e subir o sistema como de costume (o painel e o LocalStack reiniciam). Na primeira execução de cada runtime do Lambda, o Docker baixa a imagem, o que pode demorar.

## 2026-11-12 - Correção: áudio dos estudos sumia quando a voz estava fixada no .env
- Com HEIMDALL_VOZ="Felipe (Aprimorada)" o áudio não era gerado: o macOS lista as vozes em inglês neste Mac, como "Felipe (Enhanced)", e o nome fixado não batia. A nota era gravada sem áudio e sem aviso.
- Agora (Aprimorada), (Melhorada) e (Enhanced) valem igual, maiúsculas não importam, e, se a voz fixada não existir, o agente usa a melhor voz em português instalada e registra isso no agente_debug.log em vez de ficar sem áudio.
- Para aplicar: git fetch e reset do repositório e reiniciar o agente (pkill -f heimdall_agente.py e subir o sistema como de costume). Não precisa rodar instalador.

## 2026-11-12 - Heimdall Cloud: painel web do emulador de AWS
- Novo painel web para usar o emulador de AWS (LocalStack ou Moto) pelo navegador, em texto, títulos, tabelas e formulários simples, bons para leitor de tela. Páginas: S3 (criar e apagar buckets, enviar, baixar e apagar arquivos), Lambda (criar a partir de código, executar com o registro de saída, apagar) e Console geral, que chama qualquer operação de qualquer serviço (DynamoDB, SQS, SNS, Kinesis, Glue, IAM, CloudFormation e outros) com os parâmetros em JSON e traz exemplos prontos.
- Pensado para ficar público em cloud.heimdall-ai.tech pelo túnel Cloudflare, sem Cloudflare Access, por isso tem camadas próprias: entrada com senha forte (guardada só como hash PBKDF2 no .env) e código de 6 dígitos (TOTP, cadastrável no app Senhas da Apple); limite de tentativas por endereço e global, com bloqueio de 15 minutos; código de 6 dígitos que não pode ser reaproveitado; sessão em cookie HttpOnly e SameSite=Strict com validade de 8 horas; token contra CSRF nos formulários; só atende os nomes de site permitidos; cabeçalhos de segurança; arquivos baixados sempre como anexo. A porta 4566 do emulador continua só em 127.0.0.1, nunca exposta.
- Sem senha e código no .env o painel não sobe. Para configurar: python3 heimdall_cloud.py --definir-senha (a senha é digitada sem aparecer na tela; o código de 6 dígitos é mostrado uma vez para cadastrar no app Senhas). python3 heimdall_cloud.py --novo-codigo gera só outro código.
- Executar funções Lambda exige o socket do Docker dentro do LocalStack, que dá ao contêiner controle do Docker do Mac. Por isso é opcional: HEIMDALL_LOCALSTACK_DOCKER=1 no .env (e docker rm -f localstack uma vez, para recriar o contêiner). Sem isso, criar e listar funções funciona; executar dá erro.
- Novos arquivos: heimdall_cloud.py (usa a biblioteca padrão e o boto3, que já está no requirements.txt) e teste_cloud.py (53 conferências sem rede e sem LocalStack). O start_heimdall.sh sobe o painel sozinho (porta 8010, HEIMDALL_CLOUD_PORT muda) quando há senha e código no .env.
- Para aplicar: git fetch e reset do repositório, python3 heimdall_cloud.py --definir-senha, e reiniciar o sistema. Depois, no túnel Cloudflare, acrescentar o nome cloud.heimdall-ai.tech apontando para http://localhost:8010.

## 2026-11-11 - Cópia de segurança criptografada do banco
- O banco pessoal (saúde, diários, e-mails, estudos, privacidade, triagem) passa a ter cópia fora do arquivo original: tirada com o recurso de backup do SQLite, conferida por integridade, comprimida e criptografada com AES-256-GCM (chave derivada da senha com scrypt). Quem pegar o arquivo não lê nada sem a senha.
- Destinos: uma pasta (por exemplo no iCloud Drive, que sincroniza para fora do Mac) e, quando configurado, um bucket do Cloudflare R2. Se um destino falhar, o outro continua sendo gravado e o fluxo avisa. Cada envio é relido e comparado antes de contar como feito.
- Retenção: as 14 cópias mais recentes e a mais nova de cada um dos 6 últimos meses.
- Novo fluxo no n8n: cópia todo dia às 3h30 e verificação aos domingos às 4h (baixa a cópia mais recente, decifra e confere a integridade e as tabelas). Falha em qualquer um dos dois aciona o aviso de falha do Heimdall.
- Novo módulo heimdall_backup.py com comandos preparar, senha, fazer, verificar, listar e restaurar (nunca sobrescreve um arquivo existente). Novas rotas do agente: POST /backup/executar, POST /backup/verificar e GET /backup/estado. Novo teste_backup.py (sem rede, com R2 simulado).
- A senha fica no .env (HEIMDALL_BACKUP_SENHA). Guarde-a também fora do Mac: sem ela as cópias não abrem. As variáveis HEIMDALL_BACKUP_DESTINO e HEIMDALL_R2_* também ficam no .env.
- Para aplicar: git fetch e reset do repositório, python3 heimdall_backup.py preparar, acrescentar HEIMDALL_BACKUP_DESTINO no .env, bash instalar_automacoes_avancadas.sh e reiniciar o sistema. Depois rode python3 heimdall_backup.py fazer e python3 heimdall_backup.py verificar.

## 2026-11-11 - Triagem obrigatória de avisos importantes
- Novo sistema de triagem: o que for importante vira um lembrete na lista "Heimdall: Triagem" do app Lembretes (iPhone e Mac), com o resumo e o caminho para a nota completa no Notas. O Heimdall insiste pelo Bark até você agir. Concluir o lembrete dispensa o aviso; mudar a prioridade classifica a importância (alta, média ou baixa); mudar o horário adia.
- O que entra na triagem: comunicações do Diário da Justiça (pela OAB), aviso de fonte dos diários indisponível há 24 horas, e-mails suspeitos de golpe e e-mails oficiais urgentes, achados de privacidade de risco médio ou alto (os de risco baixo, como páginas suas, ficam só no relatório) e sinais de saúde "muito relevantes" do resumo das 5h50.
- Insistência: aviso a cada 2 horas das 7h às 21h, sem tocar à noite; com prioridade baixa no lembrete, a cada 8 horas. Itens críticos (por exemplo, audiência, mandado, bloqueio, prazo curto, febre ou oxigênio) usam o nível crítico do Bark, que fura o modo silencioso: o primeiro aviso sai na hora, a qualquer hora, e as repetições seguem o horário das 7h às 21h. Menções do Diário da Justiça viram críticas depois de 24 horas sem ação. Se você baixar a prioridade de um item crítico, ele deixa de furar o silêncio.
- Novo fluxo "triagem de avisos" no n8n: a cada 15 minutos chama o agente do Mac, que lê os lembretes, registra a sua decisão no banco (nova tabela triagem: estado, prioridade que você deixou, quando decidiu, adiamento, número de avisos) e envia os avisos. Se o agente ficar 1 hora sem responder, avisa uma vez só.
- Se o app Lembretes não responder (por exemplo, permissão de Automação pendente no Mac), nada se perde: o item fica registrado no banco, o Bark continua avisando pelas mesmas regras, com a explicação de que falta autorizar, e o lembrete é criado assim que o app voltar a responder. As chamadas ao app esperam no máximo 45 segundos e não travam mais o agente por 2 minutos. Bancos criados antes desta versão ganham a coluna lembrete sozinhos.
- Novas rotas do agente: POST /triagem/criar, POST /triagem/ciclo e GET /triagem/estado. O número de itens pendentes aparece no ícone do Bark.
- Novo módulo heimdall_triagem.py (regras e AppleScripts) e teste_triagem.py (simula o app Lembretes e o Bark; com --mac confere os scripts de verdade).
- Para aplicar: git fetch e reset do repositório, bash instalar_automacoes_avancadas.sh, bash instalar_monitor_privacidade.sh e reiniciar o sistema (o agente do Mac precisa subir de novo). Depois rode python3 teste_triagem.py --mac.

## 2026-11-11 - Diários oficiais insistem quando a fonte externa falha
- O fluxo de diários oficiais deixou de avisar "consulta incompleta" assim que uma fonte externa falha (por exemplo, o Querido Diário com erro 502 ou 520). A falha fica em silêncio e é anotada na memória do fluxo.
- Novo gatilho a cada 2 horas (às xx:30) que repete a consulta só das fontes pendentes, por até 72 horas. O diário das 9h40 continua consultando tudo.
- Quando uma fonte pendente volta a responder, o aviso sai na hora (fora da fila), dizendo qual voltou e o que encontrou; se não houver nada novo, o aviso é discreto.
- Se uma fonte ficar cerca de 24 horas sem responder, sai um único aviso de indisponibilidade, no resumo das 10h do dia seguinte. A consulta continua; o aviso de recuperação vem quando ela voltar.
- Se todas as fontes falharem no mesmo dia, o fluxo não dispara mais o aviso de falha geral: o mesmo ciclo de repetição vale. A janela de busca aumenta com os dias de falha (mínimo de 7, máximo de 30) para não perder publicações.
- A observação "há N comunicações e só as primeiras foram lidas" do Diário da Justiça passou a ser um aviso parcial, não uma falha de fonte.
- Para aplicar: git fetch e reset do repositório, depois bash instalar_monitor_privacidade.sh (não pergunta nada de novo e mantém o histórico de menções já vistas).

## 2026-11-10 - Banco de dados pessoal
- O banco_resumo agora já traz o sono dos últimos 7 dias e avisa para não ser chamado de novo: modelos pequenos o repetiam em laço sem chegar a saude_historico.
- O MedGemma saiu do litellm_config.yaml: apagá-lo do Ollama não o tira da lista do Open WebUI, porque a lista vem do LiteLLM. O teste_saude.py passou a usar o qwen3-vl-instruct por padrão.
- Novo servidor MCP de dados (porta 8004, só em 127.0.0.1) com apenas as ferramentas do banco e a hora do sistema, para ligar ao Open WebUI sem expor leitura e escrita de arquivos no chat que fica na internet. O Open WebUI não recebe as ferramentas sozinho: o administrador o liga em Configurações, Administração, Integrações, Servidores de ferramentas externos, tipo MCP (HTTP em fluxo), endereço http://host.docker.internal:8004/mcp, sem autenticação, com acesso restrito ao administrador. Sem essa ligação o modelo não enxerga as ferramentas e pode inventar números de saúde.
- Novo banco SQLite no Mac (banco/heimdall.db, fora do Git e fora do n8n) com o histórico de saúde por dia, os resumos de saúde, as menções dos diários oficiais, a análise do Second Brain de cada nota, os e-mails de serviços públicos (só remetente, assunto e classificação, nunca o corpo), cada estudo dos livros, os achados do monitor de privacidade e cada aviso de rotina do resumo agrupado. Cópia diária automática (7 últimas) em banco/copias.
- O agente do Mac ganhou as rotas /banco/resumo, /banco/esquema, /banco/gravar e /banco/consultar (um único SELECT, em conexão somente leitura). Os fluxos de saúde, diários oficiais e Second Brain gravam no banco sem mudar o que já faziam; se o banco falhar, o fluxo segue.
- Quatro ferramentas novas no chat (só no grupo do Mac, nunca para convidados): banco_resumo, banco_consultar (um único SELECT, somente leitura), banco_buscar (procura um termo sem diferenciar acento em todas as tabelas) e saude_historico (média, mínimo, máximo e último valor de uma métrica). O texto vindo do banco é tratado como dado, não como instrução. Dentro do SQL, sem_acento(coluna) ajuda nas buscas. Reinicie os servidores MCP (start_heimdall.sh) para o chat enxergar as ferramentas.
- Novo Roadmap no site (docs/roadmap.html), gerado do arquivo ROADMAP.md: em andamento, em seguida, depois e ideias em avaliação. O menu do site agora quebra em linhas em vez de esconder os últimos itens.
- Novo importar_saude_n8n.py: traz para o banco o histórico de saúde que já está dentro do n8n. Teste: python3 teste_banco.py. Consulta rápida: python3 heimdall_banco.py --sql "SELECT ...".

## 2026-11-10 - Resumos agrupados e monitor de saúde
- Novo fluxo "Resumo agrupado": os avisos de rotina entram numa fila e saem em três notificações por dia (6h, 8h e 10h). Disponibilidade e saúde às 6h; AWS e digest da manhã às 8h; diários oficiais, privacidade, e-mails oficiais, versões e checagem mensal às 10h. Falhas, GitOps, alerta do Mac, digest das 18h e estudo continuam na hora. Urgentes furam a fila.
- Novo fluxo "Monitor de saúde": recebe os dados do app Saúde pelo Health Auto Export, calcula o que mudou contra a média de 30 dias por regras, o modelo geral redige e uma verificação descarta texto com sentido trocado. Critérios para procurar um médico são fixos. Não acompanha glicemia.
- Testes com modelos de saúde: o MedGemma de 4 bilhões trocou o sentido de uma variação e foi descartado; o qwen3-vl-instruct acertou e é o redator. Condições de saúde ficam só no .env (HEIMDALL_SAUDE_CONDICOES), fora do código público.
- O monitor de saúde analisa toda métrica que chegar do Health Auto Export (pressão, temperatura, frequência cardíaca média e outras): compara com a média de 30 dias da própria pessoa e destaca só as que fogem muito; métrica sem dado é ignorada.
- Corrigido: o agente do Mac recusava gravar na pasta Saúde do Notas (só aceitava Monitor de Privacidade, Digest e Cérebro), e o fluxo não avisava. A pasta Saúde agora é sempre permitida.
- Notas em subpastas: o agente grava tudo dentro de Heimdall-ai (Digest, Saúde, Monitor de Privacidade, Cérebro e Estudos com um tema por subpasta). Os fluxos não mudam. Se a subpasta falhar, a nota vai para a pasta solta e a resposta traz um aviso. HEIMDALL_NOTAS_RAIZ no .env muda o nome da raiz; vazio volta às pastas soltas. Teste: bash teste_subpastas.sh.
- Second Brain passa a analisar todas as notas (suas, estudos, digest, diários oficiais, monitor e saúde), para correlacionar assuntos entre áreas; só os espelhos dele e as pastas privadas ficam de fora. A pasta dos espelhos agora se chama Second Brain (era Cérebro) e os títulos começam com "Second Brain: ".
- Resumo de saúde mais útil: o modelo escreve sempre que houver dado (análise e ações do dia), a média nunca inclui o próprio dia comparado, passos e energia dizem "ontem", valores que ainda não chegaram hoje caem para os de ontem (dito no texto), a lista traz o que não foi recebido e todas as métricas analisadas, e o tempo na cama serve de reserva quando não há sono dormido.
- Resumo de saúde: avisa quando faz dias que não chegam dados do Apple Watch (e trata passos baixos como possível relógio ou celular fora do corpo), escreve "ontem" quando o dado é de ontem, não atribui causas de comportamento, traduz mais nomes de métricas e não deixa linhas em branco sobrando na nota.
- Novo mover_notas_antigas.py: move as notas das pastas soltas antigas (Digest, Monitor de Privacidade, Cérebro, temas de estudo) para as subpastas de Heimdall-ai. Sem argumentos só conta; com --executar move.
- Second Brain: a nota no app Notas deixa de mostrar o bloco YAML (só Tags, Conceitos e Entidades legíveis; o arquivo do cofre guarda o YAML inteiro), tags vazias passam a vir das entidades e o texto lido de cada nota sobe de 3.000 para 6.000 caracteres (o digest inteiro).
- Novos endereços: status.heimdall-ai.tech (antes uptime) e flows.heimdall-ai.tech (antes n8n). Os antigos continuam funcionando por enquanto.
- O vigia de e-mails oficiais entrega ao resumo das 10h; e-mails urgentes ou suspeitos de golpe continuam na hora.

## 2026-11-09 - Diário da Justiça e novo endereço do Querido Diário
- O Querido Diário mudou para api.queridodiario.org.br; o endereço antigo (api.queridodiario.ok.org.br) foi desativado e recusava toda conexão segura. O fluxo de diários e o agente do Mac usam o endereço novo.
- O fluxo de diários oficiais passou a consultar também o Diário da Justiça Eletrônico Nacional (DJEN, do CNJ) pela OAB do dono, uma vez por dia, olhando os últimos 7 dias e avisando só as comunicações novas. Liga-se com HEIMDALL_OAB=NUMERO/UF no .env; sem essa linha, fica desligado.
- Comunicações canceladas pelo tribunal aparecem marcadas como canceladas, com o motivo.
- Novo teste: python3 teste_diario_justica.py confere as duas fontes e mostra só a estrutura, nunca o conteúdo das publicações.

## 2026-11-09 - Contato no rodapé
- O rodapé do site tem o e-mail de suporte (suporte@heimdall-ai.tech, encaminhado pela Cloudflare Email Routing) e o link do LinkedIn do autor.

## 2026-11-09 - GitOps apaga a branch quando o PR não abre
- Se o GitHub recusar abrir o Pull Request, o GitOps apaga a branch criada, para não acumular lixo no repositório, e avisa no iPhone o motivo e um resumo dos achados descartados. Se a exclusão também falhar, o aviso pede para apagar a branch à mão.
- Contrapartida: as edições sugeridas naquele commit não ficam guardadas na branch; o resumo do aviso é o registro.

## 2026-11-09 - Novo visual do site e marca
- O site ganhou identidade própria: logotipo (a ponte de seis faixas com um olho que acompanha o ponteiro), paleta azul e dourada, títulos em serifa e texto em fonte do sistema, tema claro e escuro, diagrama do projeto na página de arquitetura e índice lateral "Nesta página".
- Nova página Marca, com logotipo, cores (com contraste medido), tipografia e arquivos para baixar (logo.svg, logo-escuro.svg, simbolo.svg, simbolo-uma-cor.svg, og.png).
- A página inicial e o README listam os acessos: chat, automações (n8n), status e código. Imagem de compartilhamento e ícone para iPhone incluídos.

## 2026-11-09 - GitOps explica os descartes
- Quando o GitOps descarta uma refatoração por segurança, o aviso agora diz o arquivo e o motivo exato (por exemplo, tamanho fora do limite, parênteses desbalanceados, resposta cortada ou sem o arquivo corrigido).
- Se o GitHub recusar abrir o Pull Request, o aviso do iPhone diz que a branch foi criada, o motivo e traz o link de comparação.
- O GitOps entende achados escritos com negrito de markdown e, quando descarta por falta de achados, mostra um trecho do que o modelo escreveu.
- Memória: o GitOps não pede mais contexto de 12288 tokens; o modelo de código usa contexto de 6144 e a resposta tem no máximo 1500 tokens.
- O GitOps divide arquivos grandes em trechos de até 5 mil caracteres, em fronteiras de função ou comando, analisa só os trechos que o commit tocou (até 24 trechos em até 8 arquivos por commit, arquivos de até 80 mil caracteres), pede ao modelo só edições pontuais (bloco ANTES e bloco DEPOIS) em vez do trecho reescrito, valida cada edição (bloco único e exato, sem apagar código, parênteses balanceados) e junta o resultado antes de abrir o Pull Request. Edições inválidas são ignoradas sem derrubar as válidas.
- Os modelos deepseek-coder (30s), qwen3-vl-instruct (2m) e bonsai-27b (1m) são descarregados da memória logo depois do uso (keep_alive no litellm_config.yaml).
- O Ollama iniciado pelo start_heimdall.sh carrega no máximo 2 modelos, atende 1 pedido por vez e usa cache de contexto quantizado.
- O GitOps localiza o bloco a trocar mesmo quando o modelo muda espaços ou quebras de linha (comparação ignora espaços, exige bloco único de pelo menos 20 caracteres) e mostra mais do bloco quando não o encontra.
- O modelo do GitOps não pode mais sugerir remover textos de interação com o usuário (prompts e mensagens).

## 2026-11-09 - Documentação e site
- Site de documentação no GitHub Pages (pasta docs/), gerado por gerar_docs.py a partir do código: modelos, servidores MCP, ferramentas, fluxos e comandos.
- README completo com tabelas atualizadas automaticamente.
- Publicação automática pelo GitHub Actions e domínio heimdall-ai.tech.

## Anteriores - recursos construídos até a documentação
- O fluxo de estudo roda às 6h, 13h e 20h, uma nota por tema de knowledge/, em pasta do app Notas com o nome do tema.
- Cada nota traz leitura de um trecho, pergunta e resposta, 1 a 3 links de artigos e áudio narrado com voz Premium do macOS.
- ouvir_estudo.sh toca o áudio mais recente no Mac.
- Pastas com nomes próprios (Monitor de Privacidade, Digest, Cérebro), sem prefixo.
- Notas de pastas privadas nunca são lidas; limpar_privadas.py remove o que foi indexado por engano.
- Vigia de e-mail de serviços públicos no Gmail, somente leitura, com checagem de autenticidade do remetente.
- E-mails oficiais com prazo geram evento no Calendário e lembrete no app Lembretes.
- Diários oficiais do município, da União e do Estado, com aviso só do que for novo.
- Lembrete mensal para conferir INSS, FGTS, Carteira de Trabalho, Registrato e Serasa.
- Monitor de privacidade: busca menções ao dono na web, separa homônimos e avisa só o novo.
- test_models_tools.py: teste de chamada de ferramentas por modelo.
- GitOps: Pull Request em rascunho com refatorações a cada push, com aviso sempre.
- Digest, Second Brain e aviso de falha de fluxos.
