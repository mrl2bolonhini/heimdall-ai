# Heimdall-ai

Assistente de Inteligência Artificial que roda no próprio Mac, com ferramentas (MCP), base de conhecimento pessoal e automações (n8n). Desenvolvido por Murillo Bolonhini Cita. O chat é privado e o acesso é por convite; o código é aberto à leitura, mas os dados ficam no Mac do autor.

Documentação publicada: https://heimdall-ai.tech (gerada da pasta docs/ pelo GitHub Pages).

Este README é mantido junto com o código. As tabelas entre marcadores `AUTO` são geradas por `python3 gerar_docs.py`; não as edite à mão.

## Acessos

1. Chat: https://chat.heimdall-ai.tech (por convite).
2. Automações: https://flows.heimdall-ai.tech (login do administrador).
3. Status: https://status.heimdall-ai.tech (acesso restrito).
4. Cloud: https://cloud.heimdall-ai.tech (painel do emulador de AWS; senha e código de 6 dígitos).
4b. Saúde: https://health.heimdall-ai.tech (painel de saúde, somente leitura; senha e código de 6 dígitos).
4c. Jogos: https://games.heimdall-ai.tech (jogos leves para leitor de tela; senha e código de 6 dígitos).
5. Documentação: https://heimdall-ai.tech (página do Cloud: https://heimdall-ai.tech/cloud.html)

Contato: suporte@heimdall-ai.tech e https://www.linkedin.com/in/murillobolonhinicita

## Propósito

Heimdall, na mitologia nórdica, guarda a ponte Bifröst. O projeto vigia e conecta as ferramentas de quem o criou, com três objetivos: manter os modelos de linguagem sob controle de quem os usa, dar a eles ferramentas reais (web, arquivos, documentos, memória, Notas, Calendário) e automatizar rotinas (resumos, estudo, vigilância de privacidade, avisos no iPhone). Foi pensado para uso por pessoa cega: tudo opera por texto e comandos, com notas e áudio acessíveis.

## Arquitetura em resumo

1. Ollama executa os modelos no Mac.
2. LiteLLM Proxy (porta 9000) é o ponto único de acesso, com API compatível com a da OpenAI, e expõe os servidores MCP.
3. Três servidores MCP em Python (8000, só do Mac; 8001, público; 8004, só o banco pessoal e só em 127.0.0.1, para o Open WebUI) e o servidor de documentação da AWS fornecem as ferramentas.
4. O n8n agenda fluxos; o agente do Mac (8003) liga o n8n ao app Notas, ao Calendário, aos Lembretes e à voz do macOS; o Bark entrega avisos no iPhone, e o app do Mac mostra os mesmos avisos, completos, como notificações do macOS.

Detalhes em https://heimdall-ai.tech/arquitetura.html.

### Serviços e portas

<!-- AUTO:SERVICOS -->
| Serviço | Porta | Função |
|---|---|---|
| Ollama | 11434 | Executa os modelos de linguagem no Mac. |
| LiteLLM Proxy | 9000 | Ponto único de acesso (API compatível com a da OpenAI) aos modelos; também expõe os servidores MCP. |
| Servidor MCP do Mac (admin) | 8000 | Ferramentas que mexem no Mac: arquivos, métricas, memória e documentos. |
| Servidor MCP público | 8001 | Ferramentas seguras para convidados: web, cálculo, feeds, transcrições. |
| Servidor MCP de dados | 8004 | Só as ferramentas do banco pessoal (saúde, diários, e-mails, estudos, Second Brain) e as de consulta do Finance, para o Open WebUI. Escuta só em 127.0.0.1. |
| SearXNG | 8080 | Mecanismo de busca na web que não rastreia quem pesquisa. |
| Qdrant | 6333 | Base vetorial: busca por significado nos documentos e nas notas. |
| Open WebUI | 3000 | Interface de chat usada pelos convidados e pelo dono. |
| Open Terminal | 8002 | Terminal acessível pelo Open WebUI. |
| n8n | 5678 | Automações e tarefas agendadas. |
| Agente do Mac | 8003 | Ponte entre o n8n (no Docker) e o app Notas, o Calendário, os Lembretes e a voz do macOS. |
| Docling | 5001 | Extração de texto de PDFs, com OCR. |
| Uptime Kuma | 3001 | Painel de disponibilidade dos serviços. |
| Dozzle | 8081 | Leitor de logs dos contêineres. |
| Emulador de AWS (Moto ou LocalStack) | 4566 | Para testar código de AWS sem custo. |
| Heimdall Learn | 8019 | Plataforma de estudos (fases 1 e 2): pastas em knowledge/ com categoria (aleatório ou sequencial) e tipo com regras próprias (catálogo em heimdall_learn_tipos.py), importação de documentos, modo aleatório (sorteia trecho, pergunta, corrige, grava áudio e sugere matérias) e banco próprio db/learn.db. Mesmo login do Heimdall Cloud. |
| Heimdall Notes | 8011 | Site para ler as notas de estudo e ouvir os áudios (velocidade, voltar e avançar 15 segundos, busca, documentos de knowledge/). Mesmo login do Heimdall Cloud. Escuta só em 127.0.0.1. |
| Heimdall News | 8012 | Notícias das últimas 24 horas com resumo feito por IA (sinalizado como tal), 10 por página, e feeds RSS com chave secreta para o app de feeds do iPhone. Atualiza de 30 em 30 minutos e guarda 30 dias no banco pessoal. Mesmo login do Heimdall Cloud. Escuta só em 127.0.0.1. |
| Heimdall Games | 8014 | Jogos leves para leitor de tela no navegador: forca, senha (Mastermind), jogo da velha, número secreto, 2048, cinco letras, sudoku, xadrez, batalha naval, campo minado, caça-níqueis e quatro aventuras de texto com níveis de dificuldade. Cada jogada é lida em voz alta por uma região aria-live. Não guarda nada. Mesmo login do Heimdall Cloud. Escuta só em 127.0.0.1. |
| Heimdall Finance | 8016 | Finanças pessoais em páginas de texto e tabelas: importa extratos OFX e CSV, classifica gastos por categoria com regras que você ajusta, mostra o resumo do mês, os maiores gastos, as tendências e alertas. Banco SQLite só no Mac (finance, fora do git); só sai do Mac o que você ligar de propósito: a conexão com os bancos pelo Meu Pluggy (dados passam pelos servidores dele) e a leitura de e-mail (somente leitura). Mesmo login do Heimdall Cloud. Escuta só em 127.0.0.1. |
| Heimdall Controls | 8017 | Terminal completo e acessível (um shell de verdade no Mac, com a pasta e as variáveis persistentes, a saída no próprio campo de comando, como num terminal, e atalhos de teclado para interromper, limpar, reiniciar e copiar a última saída ou as últimas N) e painel de serviços com botões de atualizar, reiniciar, diagnosticar e ver logs. Só o dono entra: Cloudflare Access (Authenticator) ou senha e código de 6 dígitos, e cada comando fica anotado sem a saída. Escuta só em 127.0.0.1. |
| Heimdall Health | 8013 | Painel somente de leitura com as análises do app Saúde: como você está agora, tendências, sono, atividade, recuperação, coração e ECG, treinos, sintomas, humor, medicamentos, relatório da semana, diário em tabela, exames de laboratório, receitas e encaminhamentos já conferidos, e o estado dos dados (mostra se a exportação contínua do iPhone parou). Mesmo login do Heimdall Cloud. Escuta só em 127.0.0.1. |
| Heimdall Cloud | 8010 | Painel web do emulador de AWS (S3, Lambda, Glue, Athena e console geral), com senha e código de 6 dígitos. Escuta só em 127.0.0.1; o acesso público é pelo túnel Cloudflare. |
<!-- /AUTO:SERVICOS -->

## Requisitos

1. Mac com chip Apple e 16 GB de memória ou mais.
2. Docker Desktop, Ollama, Python 3.12 e uv.
3. Aplicativo Bark no iPhone (avisos) e Tailscale (acesso remoto).
4. Modelo de embeddings: `ollama pull nomic-embed-text`.

## Instalação

1. Clone o repositório e entre na pasta: `git clone https://github.com/mrl2bolonhini/heimdall-ai.git ~/heimdall-ai && cd ~/heimdall-ai`.
2. Crie o ambiente Python em `venv` (o `start_heimdall.sh` o usa): `python3.12 -m venv venv`, e instale nele os pacotes que os scripts importam: fastmcp, litellm com proxy, feedparser, psutil, pypdf, requests, starlette, pyyaml e youtube-transcript-api.
3. Crie o arquivo `.env` com as chaves (nunca vai para o repositório) e proteja-o: `chmod 600 .env`. As variáveis estão descritas no cabeçalho de `start_heimdall.sh`.
4. Coloque os documentos pessoais em `knowledge/`, uma subpasta por tema.
5. Suba o sistema (próxima seção).

## Subir, parar e conferir

```
./subir.sh                 # sobe uma vez só, guarda o log em logs/ e avisa quando tudo estiver no ar
./subir.sh --update        # os argumentos são os do start_heimdall.sh
./subir.sh --status        # confere agora o que está no ar
./subir.sh --log           # últimas linhas do log da subida atual
./subir.sh --log notas     # idem, de um serviço (mcp, agente, cloud, notas, open_terminal...)
./subir.sh --logs          # lista os logs em logs/
./subir.sh --limpar        # apaga os logs antigos que ficavam soltos na pasta do projeto
./subir.sh --reiniciar     # encerra a subida em andamento e sobe de novo
docker ps --format '{{.Names}}: {{.Status}}'
```

O `subir.sh` recusa iniciar uma segunda subida enquanto outra estiver em andamento, grava cada log em `logs/heimdall-AAAAMMDD-HHMMSS.log` (os 15 mais recentes) e aponta `heimdall.log` para o atual. Os logs de cada serviço também ficam em `logs/` (por exemplo `logs/notas_debug.log`), com os 5 anteriores de cada um em `logs/historico/`. Ao final avisa "Tudo no ar" com notificação e voz do macOS (`SUBIR_SOM=0` desliga). O comando antigo continua valendo: `nohup bash start_heimdall.sh --webui --terminal --n8n --agente > heimdall.log 2>&1 &`.

Opções: `--webui`, `--terminal`, `--n8n`, `--agente`, `--docling`, `--ingest`, `--update`. A lista completa está no cabeçalho de `start_heimdall.sh` e em https://heimdall-ai.tech/comandos.html.

## Organização das pastas
Módulos Python, `subir.sh`, `start_heimdall.sh` e `heimdall.zsh` ficam na raiz. `tests/<serviço>/` guarda os testes (finance, health, news, notes, games, cloud, account, controls, agent, chat, design, monitor, core); `guides/` os guias e ajudas; `prompts/` os prompts do chat; `scripts/` os scripts de shell; `flows/` os fluxos do n8n (basic, advanced, monitor); `games/` os jogos; `finance/` os dados do Finance no Mac (antes `dados_financas/`, renomeada sozinha na primeira subida). `./rodar_testes.sh` roda todos os testes; `./rodar_testes.sh finance` só os de uma pasta.

## Testar

```
./rodar_testes.sh                                  # todos os testes (./rodar_testes.sh finance roda só uma pasta; -l lista)
venv/bin/python tests/chat/test_mcp.py                       # servidores MCP, direto e pelo LiteLLM
venv/bin/python tests/chat/test_models_tools.py              # chamada de ferramentas por modelo
python3 heimdall_agente.py --teste                # Notas, Calendário e Lembretes
python3 heimdall_agente.py --voz                  # voz e velocidade do áudio
python3 tests/cloud/teste_cloud.py                        # painel do emulador de AWS (sem rede)
python3 tests/core/teste_avisos.py                  # avisos de saúde e finanças (sem rede)
python3 tests/design/teste_abas_mais.py               # menu Mais das abas (navegador)
python3 tests/core/teste_migrar_avisos.py           # migração das notas antigas (sem rede)
python3 tests/notes/teste_catalogo.py                # catalogação de notas e cliente do Notion (sem rede e sem modelo)
python3 tests/cloud/teste_cfmonitor.py               # monitor de consumo e custo da Cloudflare (sem rede)
python3 tests/cloud/teste_caixa_cliente.py          # cliente da caixa de correio da Cloudflare (sem rede)
python3 tests/health/teste_saude_pessoas.py           # saúde por pessoa: banco separado, métricas diárias e conversor do Atalho (sem rede)
python3 tests/health/teste_analista_saude.py          # analista de saúde: dossiê, correlações, PubMed simulado, modelo simulado (sem rede)
python3 tests/account/teste_account.py                  # Account: tour, Integrações (csrf, origem, ativar e desativar) e quem.json
python3 tests/agent/teste_app_mac.py                  # confere o app de barra de menus do Mac sem compilar
bash tests/core/teste_silenciar_docker.sh            # script que impede o Docker de abrir o painel ao iniciar (pasta falsa)
node cloudflare/teste_caixa.mjs           # Worker da caixa de correio (KV e R2 falsos)
python3 tests/cloud/teste_nuvem.py                   # modelo grande na nuvem (gateway da Cloudflare), interruptor e volta ao modelo local (sem rede)
python3 tests/cloud/teste_litellm_nuvem.py           # LiteLLM: chat na nuvem com o local como volta, interruptor HEIMDALL_NUVEM (sem rede)
python3 tests/notes/teste_notas.py                   # Heimdall Notes (sem rede)
python3 tests/learn/teste_learn_dados.py             # Heimdall Learn: banco e pastas
python3 tests/learn/teste_learn_site.py              # Heimdall Learn: site
python3 tests/learn/teste_learn_estudo.py            # Heimdall Learn: modo aleatório
python3 tests/news/teste_news.py                    # Heimdall News (sem rede)
python3 tests/notes/teste_trechos.py                      # trechos de livros do estudo (sem rede)
bash scripts/instalar_email_oficial.sh --testar           # login e simulação do vigia de e-mail
python3 heimdall_email_oficial.py --diagnostico   # como cada e-mail recente foi classificado (inclui os já vistos)
python3 tests/chat/teste_modelos_chat.py                  # funções por modelo do chat e guia em dia
python3 tests/monitor/teste_email_prioridade.py                 # rebaixamento e diagnóstico do vigia de e-mail
python3 gerar_docs.py --check                     # documentação em dia
```

### Lembretes, Calendário e Notas sem abrir os apps

- Lembretes e Calendário rodam pelo EventKit (heimdall_eventkit.py), sem abrir os apps. Precisa de `venv/bin/pip install pyobjc-framework-EventKit` e da permissão do macOS (pedida uma vez). Conferir: `venv/bin/python heimdall_eventkit.py --status`. Se faltar o pacote ou a permissão, o agente usa o AppleScript de antes. Desligar: `HEIMDALL_EVENTKIT=0` no .env.
- O Notas só pode ser usado com o app aberto. O agente o abre escondido, não o fecha (`HEIMDALL_APPS_FECHAR=1` fecha depois de 20 s) e registra cada abertura no log do agente.
- O Second Brain só consulta o Notas quando há nota nova: o agente olha a data do banco do Notas sem abrir o app e consulta se mudou, ou depois de uma gravação do Heimdall. Se o macOS não deixar ver o banco (falta Acesso Total ao Disco ao Terminal), só consulta depois de uma gravação do Heimdall; `HEIMDALL_NOTAS_VARREDURA_MIN=240` (minutos) liga uma consulta periódica de segurança.


Os testes dos fluxos (`test_*.js` com Node e `test_*.py` com Python) ficam na pasta do projeto.

## Modelos de linguagem

<!-- AUTO:MODELOS -->
| Nome no LiteLLM | Modelo no Ollama | Uso | Observações |
|---|---|---|---|
| `gemma-4-uncensored` | `ollama_chat/eriktonon/gemma4-uncensored` | Uso geral | Confira a chamada de ferramentas com tests/chat/test_models_tools.py. |
| `conversas` | `ollama_chat/eriktonon/gemma4-uncensored` | Base do modelo General do Open WebUI | Local é o mesmo gemma de gemma-4-uncensored; com HEIMDALL_NUVEM=1 o heimdall_litellm.py o troca pelo Qwen3 30B da nuvem e deixa este como volta (conversas-local). |
| `dolphin3-cyber-8b` | `ollama_chat/mparvin/dolphin3-cyber-8b-gguf:q8_0` | Segurança e conversa livre, só texto | Não chama ferramentas no Ollama; use para análises de texto, não nos fluxos com MCP. |
| `deepseek-coder-v2:16b` | `ollama_chat/deepseek-coder-v2:16b` | Código (usado pelo GitOps) | O GitOps usa este modelo na etapa de análise de código. |
| `qwen3-vl-instruct` | `ollama_chat/qwen3-vl:8b-instruct` | Modelo padrão dos fluxos; entende imagens | Declara suporte a imagens no LiteLLM. |
| `gemma3-4b` | `ollama_chat/gemma3:4b` | Modelo pequeno e rápido (3 GB), usado nos resumos do Heimdall News | No teste com um parágrafo resumiu certo em português; baixe com ollama pull gemma3:4b. |
| `llama-3.1-8b` | `ollama_chat/llama3.1:8b` | Modelo local padrão do Perguntar; aceita ferramentas | Template do Ollama com suporte a ferramentas; respondeu bem em português. Nenhum modelo do chat o usa. |
<!-- /AUTO:MODELOS -->

## Modelos do chat

Modelos personalizados do Open WebUI, um por contexto, cada um com seu prompt e só com as funções do seu assunto (o filtro da conexão de ferramentas limita o que o modelo enxerga). A fonte é `modelos_chat.py`; o passo a passo para criá-los no Open WebUI está em `guides/modelos_open_webui.txt`, gerado por `python3 gerar_docs.py`.

<!-- AUTO:MODELOS_CHAT -->
| Modelo | Base | Ferramentas (conexão) | Funções | Temperatura |
|---|---|---|---|---|
| Alerts | `qwen3-vl-instruct` | `banco-pessoal` | `banco_resumo`, `banco_consultar`, `banco_buscar`, `saude_historico`, `get_system_timestamp` | 0,2 |
| Health | `qwen3-vl-instruct` | `banco-saude` | `saude_historico`, `analise_saude`, `frequencia_cardiaca_resumo`, `ecg_resumo`, `treinos_resumo`, `relatorio_saude`, `exames_resumo`, `exame_historico`, `analise_exames`, `exames_pendentes`, `receitas_encaminhamentos`, `banco_consultar`, `get_system_timestamp` | 0,2 |
| Finance | `qwen3-vl-instruct` | `banco-financas` | `financas_resumo`, `financas_transacoes`, `financas_orcamentos`, `financas_recorrentes`, `financas_boletos`, `financas_futuros`, `get_system_timestamp` | 0,2 |
| Code | `deepseek-coder-v2:16b` | nenhuma |  | 0,2 |
| General | `conversas` | `web-basica` | `search_searxng`, `fetch_url`, `calculate_expression`, `get_system_timestamp` | 0,8 |
| Learn | `qwen3-vl-instruct` | `mac-admin`, `banco-learn` | `memory_save`, `memory_search`, `memory_forget`, `rag_temas`, `rag_search`, `learn_progresso`, `learn_licoes`, `learn_cards`, `get_system_timestamp` | 0,3 |
| Notes | `qwen3-vl-instruct` | `mac-admin`, `banco-estudos` | `memory_save`, `memory_search`, `memory_forget`, `rag_temas`, `rag_search`, `banco_buscar`, `banco_consultar` | 0,2 |
<!-- /AUTO:MODELOS_CHAT -->

Todos usam o prefixo `ollama_chat/` no LiteLLM (o prefixo `ollama/` não suporta chamada de ferramentas) e contexto de 8192 tokens. Modelo padrão dos fluxos: `qwen3-vl-instruct` (`HEIMDALL_FLOW_MODEL`). Embeddings: `nomic-embed-text`.

## Ferramentas MCP

<!-- AUTO:FERRAMENTAS -->
| Ferramenta | Grupo | Parâmetros | O que faz |
|---|---|---|---|
| `search_searxng` | público (8001) | `query` | Pesquisa informações recentes, notícias ou dados na web usando o SearXNG local. |
| `calculate_expression` | público (8001) | `expression` | Calcula uma expressão matemática. |
| `get_system_timestamp` | público (8001) | `` | Retorna a data e a hora atuais do sistema. |
| `get_hackernews_top_stories` | público (8001) | `` | Busca as 5 principais histórias em alta no Hacker News. |
| `search_reddit_posts` | público (8001) | `subreddit, query=''` | Busca posts em um subreddit (ex: Python, MachineLearning). |
| `fetch_rss_feed` | público (8001) | `feed_url` | Lê as últimas notícias de um feed RSS ou Atom, a partir da URL completa do feed (começando com http:// ou https://). |
| `get_astronomy_apod` | público (8001) | `` | Retorna a Astronomia do Dia da NASA (APOD): título, explicação e link da mídia. |
| `get_youtube_transcript` | público (8001) | `video, language='pt', offset=0` | Obtém a transcrição (legendas) de um vídeo do YouTube a partir da URL ou do ID. |
| `fetch_url` | público (8001) | `url, offset=0` | Lê o texto de uma página da web (HTML, texto ou JSON) a partir da URL completa. |
| `list_directory` | Mac (8000) | `path=''` | Lista arquivos e subpastas dentro da pasta do usuário no Mac. |
| `read_file` | Mac (8000) | `file_path` | Lê o conteúdo de um arquivo de texto na pasta do usuário no Mac (até 6000 caracteres). |
| `write_file` | Mac (8000) | `file_path, content` | Escreve ou sobrescreve um arquivo de texto na pasta do usuário no Mac. |
| `get_system_metrics` | Mac (8000) | `` | Retorna o uso atual de RAM, swap e CPU do Mac (host do Heimdall). |
| `get_disk_usage` | Mac (8000) | `` | Retorna o espaço total, usado e livre do disco principal do Mac. |
| `check_ollama_models` | Mac (8000) | `` | Lista os modelos carregados agora na memória pelo Ollama local. |
| `memory_save` | Mac (8000) | `text, tags=''` | Guarda uma informação duradoura (preferência, fato, decisão) para lembrar em conversas futuras. |
| `memory_search` | Mac (8000) | `query='', limit=5` | Busca nas memórias guardadas por palavras-chave. |
| `memory_forget` | Mac (8000) | `memory_id` | Apaga uma memória pelo id (mostrado por memory_search). |
| `rag_search` | Mac (8000) | `query, top_k=4, tema=''` | Busca trechos relevantes nos documentos pessoais do usuário (base de conhecimento). |
| `rag_temas` | Mac (8000) | `` | Lista os temas (subpastas de knowledge/) da base de conhecimento e quantos trechos cada um tem. |
| `banco_resumo` | Mac (8000) | `` | Mostra o que há no banco pessoal do usuário: quantas linhas e que período cada tabela cobre (saúde, diários oficiais, e-mails, estudos, privacidade, avisos, Second Brain). |
| `banco_consultar` | Mac (8000) | `sql, limite=50` | Roda um único SELECT no banco pessoal do usuário (somente leitura) e devolve o resultado em linhas separadas por barra vertical. |
| `banco_buscar` | Mac (8000) | `termo, tabela='', limite=5` | Procura um termo (sem diferenciar maiúsculas nem acentos) em todo o banco pessoal do usuário: diários oficiais, e-mails de serviços públicos, achados de privacidade, estudos, análises do Second Brain, avisos e resumos de saúde. |
| `saude_historico` | Mac (8000) | `metrica, dias=14` | Histórico de uma métrica de saúde do usuário nos últimos dias, com média, mínimo, máximo e o último valor. |
| `treinos_resumo` | Mac (8000) | `dias=30, tipo=''` | Resumo dos treinos do Apple Saúde/Apple Watch nos últimos dias: quantos, tempo, distância, energia, frequência cardíaca, recuperação, carga da semana. |
| `ecg_resumo` | Mac (8000) | `dias=365` | Resumo dos ECG feitos no Apple Watch: quantos, classificação da Apple (ritmo sinusal, fibrilação atrial, inconclusivo), último ECG e as medidas dos batimentos calculadas pelo Heimdall. |
| `frequencia_cardiaca_resumo` | Mac (8000) | `dias=14` | Frequência cardíaca nos últimos dias: pulso em repouso, variabilidade (HRV), mínima de madrugada, hora do dia mais alta, maior pico, recuperação, VO2 máx e avisos do relógio. |
| `relatorio_saude` | Mac (8000) | `dias=30` | Relatório completo de saúde do Apple Saúde: treinos e carga, cruzamento do treino com pulso em repouso e variabilidade, frequência cardíaca, ECG, sintomas, humor e medicamentos. |
| `analise_saude` | Mac (8000) | `tema='agora', dias=90` | Análise de saúde do dia a dia, sem depender de treinos registrados. |
| `exames_resumo` | Mac (8000) | `dias=730` | Resultados dos exames de laboratório (sangue e outros) que o usuário enviou e confirmou: o último valor de cada exame, a situação diante da referência do próprio laboratório (abaixo, dentro, acima ou sem faixa clara) e o valor anterior. |
| `exame_historico` | Mac (8000) | `exame, dias=3650` | Histórico de um exame de laboratório do usuário (por exemplo vitamina D, TSH, ferritina, glicemia de jejum, hemoglobina): cada resultado com data, unidade e referência do laboratório, mais o que o Apple Watch mostrou nos 30 dias antes de cada coleta (sono, HRV, pulso em repouso, passos, exercício). |
| `analise_exames` | Mac (8000) | `exame='', dias=730` | Leitura cruzada dos exames de laboratório com os dados do relógio e do iPhone. |
| `exames_pendentes` | Mac (8000) | `` | Documentos de saúde (exames, receitas, encaminhamentos) que o Heimdall já leu e que aguardam a conferência do usuário, item por item. |
| `receitas_encaminhamentos` | Mac (8000) | `` | Receitas, encaminhamentos e consultas médicas confirmados pelo usuário: medicamentos com dose e posologia, especialidades encaminhadas, validade quando o documento informa e consultas marcadas (que também ficam no Calendário). |
| `financas_resumo` | dados (8004) | `mes='', visao='competencia'` | Resumo do mês no Finance do usuário: receitas, despesas, saldo, gasto por categoria (com variação sobre o mês anterior) e os maiores gastos. |
| `financas_transacoes` | dados (8004) | `busca='', mes='', categoria='', limite=20` | Procura lançamentos no Finance do usuário. |
| `financas_orcamentos` | dados (8004) | `mes='', visao='competencia'` | Orçamentos mensais do Finance do usuário: para cada categoria com limite, quanto gastou, quanto falta ou passou e a situação (dentro, perto do limite, estourado). |
| `financas_recorrentes` | dados (8004) | `` | Contas que se repetem todo mês no Finance do usuário (aluguel, assinaturas, salário), deduzidas do histórico, com valor e dia típicos e a situação neste mês: já chegou, por vir, atrasada ou possivelmente encerrada. |
| `financas_boletos` | dados (8004) | `` | Boletos em aberto registrados no Finance do usuário (contas a pagar), com valor, vencimento e situação: vencido, vence hoje ou a vencer. |
| `financas_futuros` | dados (8004) | `meses=6` | Pagamentos e entradas previstos nos próximos meses no Finance do usuário: parcelas que faltam, contas recorrentes, previstos cadastrados e boletos em aberto, com o total de saídas e entradas de cada mês. |
| `learn_progresso` | dados (8004) | `` | Progresso no Heimdall Learn: cada pasta de estudo com categoria (aleatório ou sequencial), tipo, idioma, lições criadas e concluídas, média das notas, estudos por sorteio feitos e a agenda de cards e lições por dia. |
| `learn_licoes` | dados (8004) | `pasta='', limite=10` | Últimas lições do Heimdall Learn: número, título, situação, nota e, nas já concluídas, os exercícios em que o aluno errou (enunciado, resposta dada e correção). |
| `learn_cards` | dados (8004) | `limite=10` | Últimos cards (pílulas de conhecimento) do Heimdall Learn, com pasta, título, texto e se já foram lidos. |
<!-- /AUTO:FERRAMENTAS -->

Para criar uma ferramenta: escreva a função em `heimdall_tools.py` com tipos e docstring claro, acrescente-a a `PUBLIC_TOOLS` ou `MAC_TOOLS`, reinicie, rode `tests/chat/test_mcp.py` e `gerar_docs.py`. Ferramentas públicas são seguras para convidados; as do Mac acessam arquivos e memória e são só do administrador.

## Fluxos do n8n

<!-- AUTO:FLUXOS -->
| Fluxo | Quando | O que faz |
|---|---|---|
| resumo diário da AWS para dados | todo dia às 7h45 | Lê o feed de novidades da AWS, filtra os serviços de dados (Glue, Redshift, Athena, S3, Kinesis e outros), resume em português e avisa no iPhone. |
| vigia de versões (semanal) | toda semana (segunda às 9h) | Consulta os lançamentos dos projetos que o Heimdall usa, avalia se vale atualizar e avisa no iPhone. |
| alerta de saúde do Mac | a cada 1 hora(s) | Lê as métricas do Mac pelo MCP e avisa quando RAM, swap ou disco passam dos limites configurados. |
| relatório diário de disponibilidade | todo dia às 5h45 | Lê a página de status do Uptime Kuma, monta o relatório de disponibilidade do dia e avisa no iPhone. |
| GitOps inteligente (auditor e refatorador) | a cada git push (webhook) | A cada git push, divide o código alterado em trechos de até 5 mil caracteres, analisa os trechos tocados pelo commit com o modelo de código (um de cada vez, para poupar memória), que responde com edições pontuais validadas uma a uma, e abre um Pull Request em rascunho com as refatorações sugeridas. Se o GitHub recusar o PR, apaga a branch para não deixar lixo e avisa com o motivo e o resumo dos achados. Sempre avisa o resultado, inclusive quando não há nada a refatorar. Quando houve Pull Request proposto ou trechos descartados, grava também uma nota de histórico em Heimdall-ai/GitOps, com cada motivo de descarte. |
| digest hiperpersonalizado (7h45 e 18h) | cron 45 7 * * * | Lê feeds de notícias, filtra pelo que interessa, cruza com as notas e os livros e grava um resumo personalizado no app Notas. Não avisa pelo Bark: as notícias chegam pelo Heimdall News e pelos feeds RSS. |
| Second Brain (notas, conexões e lacunas) | a cada 5 minutos | Observa as notas alteradas do app Notas (nunca as de pastas privadas), cria embeddings, encontra conexões e lacunas e grava a análise na pasta Cérebro. |
| aviso de falha | quando outro fluxo falha | Quando qualquer fluxo falha, avisa no iPhone qual fluxo, em que etapa e por quê. Fluxos nunca falham em silêncio. |
| monitor de privacidade (diário) | cron 45 9 * * * | Pesquisa na web os identificadores pessoais configurados pelo dono (nome, e-mails, usuários) em busca de menções, comentários, vazamentos e imagens, separa homônimos, analisa o risco e grava o relatório. Tem memória: só avisa o que é novo. |
| diários oficiais (diário) | cron 40 9 * * * | Procura o nome do dono nos diários oficiais do município de São Paulo, da União e do Estado de SP e, se a OAB estiver configurada, as comunicações dela no Diário da Justiça Eletrônico Nacional (CNJ). Avisa só o que for novo. Se uma fonte externa falhar, repete a consulta dela a cada 2 horas (até 72 h), avisa na hora quando voltar e, depois de cerca de 24 h fora do ar, manda um único aviso de indisponibilidade. Nunca finge que não há nada. |
| checagem mensal de serviços públicos | cron 50 9 1 * * | Lembrete mensal para conferir, nos aplicativos oficiais, serviços que exigem login (INSS, FGTS, Carteira de Trabalho, Registrato e Serasa). |
| estudo dos livros (6h, 13h e 20h) | cron 0 6,13,20 * * * | Para cada tema da base de conhecimento (subpastas de knowledge/), sorteia um trecho, monta uma leitura, cria pergunta e resposta, busca de 1 a 3 artigos na web e grava a nota no app Notas, na pasta com o nome do tema, com áudio narrado. |
| resumo agrupado (6h, 8h e 10h) | cron 0 6 * * * | Junta os avisos de rotina em três notificações por dia (6h, 8h e 10h), em vez de uma por fluxo. Avisos urgentes e os de situação (falhas, GitOps, alerta do Mac) continuam na hora. |
| monitor de saúde (resumo das 5h50) | todo dia às 5h50 | Recebe os dados do app Saúde (iPhone e Apple Watch) e escreve às 5h50 um resumo de sono, pulso, variabilidade, respiração e atividade contra a média de 30 dias. Se o sono da noite chegar depois das 5h50, refaz o resumo uma vez. Quando duas ou mais medidas da noite saem juntas do seu intervalo típico (estilo Sinais Vitais da Apple), destaca e abre um item de triagem. As regras decidem o que é relevante, o modelo só redige e uma verificação barra texto com sentido trocado. |
| triagem de avisos (insistência a cada 15 minutos) | cron */15 * * * * | A cada 15 minutos chama o agente do Mac, que lê a lista "Heimdall: Triagem" do app Lembretes, registra o que você concluiu, reclassificou ou adiou e insiste pelo Bark nos itens pendentes, num só aviso que lista todos (em vez de um aviso por item): a cada 4 horas das 7h às 21h, a cada 2 horas se houver item crítico (que fura o modo silencioso), e a cada 8 horas se só restarem itens de prioridade baixa. Menções do Diário da Justiça viram críticas depois de 24 horas sem ação. |
| cópia de segurança do banco (diária) e verificação (semanal) | cron 30 3 * * * | Todo dia às 3h30 pede ao agente do Mac uma cópia do banco pessoal, criptografada com senha, enviada a uma pasta (iCloud Drive) e ao Cloudflare R2 quando configurado, mantendo as 14 mais recentes e uma por mês. Aos domingos, às 4h, baixa a cópia mais recente, decifra e confere a integridade. Qualquer falha aciona o aviso de falha pelo Bark. |
| relatório de saúde da semana (Notas e Bark, domingo) | cron 3 9 * * 0 | Todo domingo às 9h pede ao agente do Mac o relatório de saúde da semana, que grava na aba Avisos do Heimdall Health e avisa pelo Bark só com um texto genérico, sem números. Tem botão para gerar na hora. |
| tarefas de segurança do dolphin (logs diários; commits e exposição semanais) | cron 30 4 * * * | O modelo dolphin3-cyber-8b revisa a segurança do Mac sem usar ferramentas: o agente coleta os dados e ele analisa. Todo dia às 4h30 olha os logs das últimas 24 horas (acessos recusados e erros repetidos); aos domingos, às 5h, os commits da semana (segredos, caminhos pessoais, IPs privados, arquivos sensíveis) e, às 5h30, a exposição à rede (portas em escuta, Tailscale Funnel, firewall) comparada com a semana anterior. Cada achado do modelo precisa citar um trecho dos dados, e o script confere. Grava a nota em Segurança só quando há o que dizer; gravidade média vira aviso no grupo das 10h e a alta fura a fila e entra na triagem. |
<!-- /AUTO:FLUXOS -->

Resumos agrupados: os avisos de rotina saem em três notificações por dia (6h, 8h e 10h) pelo fluxo "Resumo agrupado" (webhook `heimdall-resumo`); falhas, GitOps, alerta do Mac e o estudo continuam na hora. O "Monitor de saúde" (webhook `heimdall-saude`, resumo às 5h50) recebe os dados do Health Auto Export; as regras decidem o que é relevante e o modelo só redige.

Banco pessoal: o Mac guarda um SQLite (`db/heimdall.db`, fora do Git) com saúde, diários oficiais, e-mails de serviços públicos (sem o corpo), estudos, privacidade, avisos e a análise do Second Brain; o chat consulta pelas ferramentas `banco_*`, `saude_historico` e as de treinos, ECG e frequência cardíaca (roteiro em `guides/LEIAME_saude_apple.txt`). Exames, receitas e encaminhamentos vão para a pasta própria `health/inbox` (originais lidos em `health/archive`, o que não deu para ler em `health/review`). Os planos estão em `ROADMAP.md` e no site.

Instalação: `bash scripts/instalar_fluxos_n8n.sh` (básicos), `bash scripts/instalar_automacoes_avancadas.sh` (GitOps, digest, Second Brain, estudo) e `bash scripts/instalar_monitor_privacidade.sh` (monitor e diários). Rodar um fluxo agora: `docker exec -e N8N_RUNNERS_BROKER_PORT=5680 n8n n8n execute --id=<id>`.

## Privacidade e segurança

1. Dados pessoais, chaves e identificadores ficam só no Mac. `.env`, `knowledge/`, `qdrant/` e backups nunca são versionados.
2. Notas de pastas privadas nunca são lidas, indexadas nem analisadas.
3. O agente do Mac exige token e só grava nas pastas do próprio Heimdall.
4. O vigia de e-mail é somente leitura, só confia no remetente confirmado pelo Gmail e nunca segue links. Avisos de serviços sem interesse (Serasa, SPC, Boa Vista, Quod por padrão; HEIMDALL_EMAIL_BAIXA_PRIORIDADE no .env muda a lista) não viram triagem nem lembrete, mas golpe imitando eles continua alertando.
5. Falhas nunca são silenciosas; fonte indisponível nunca vira "nada novo".
6. Textos de fontes externas são tratados como dados, não como ordens.
7. Este repositório pode ser público: o código não traz dados pessoais (caminhos, IPs e e-mail vêm de variáveis ou do `.env`, que nunca é versionado). Antes de publicar, confira o histórico com `git log --all --oneline -- .env` e `git log --all -p | grep -ciE "api_key|token|senha"`.

## Publicação da documentação

A pasta docs/ é publicada pelo GitHub Pages com o domínio heimdall-ai.tech (arquivo `docs/CNAME`). O fluxo `.github/workflows/pages.yml` confere se a documentação está em dia e publica a cada push em `main`. O passo a passo de DNS no Cloudflare está em `guides/PUBLICAR_PAGINAS.md`. Observação: GitHub Pages em repositório privado exige plano pago; em repositório público é gratuito.

## Como manter (a cada recurso novo)

1. Implemente e teste o recurso.
2. Acrescente um bloco no topo de `CHANGELOG.md`: `## AAAA-MM-DD - título`, com itens iniciados por hífen.
3. Se criou fluxo, modelo ou ferramenta novo, acrescente a descrição em `gerar_docs.py` (`FLUXO_DESCRICAO`, `MODELOS_NOTAS`; ferramentas leem o docstring). O gerador avisa o que faltar.
4. Se mudou comandos de uso, atualize `COMANDOS` em `gerar_docs.py` e as seções manuais deste README.
5. Rode `python3 gerar_docs.py` e confira com `python3 gerar_docs.py --check`.
6. Faça commit de tudo (código, CHANGELOG, README e docs/) no mesmo commit.

## Licença

Projeto privado. Todos os direitos reservados a Murillo Bolonhini Cita.
