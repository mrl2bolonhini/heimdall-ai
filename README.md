# Heimdall-ai

Assistente de Inteligência Artificial que roda no próprio Mac, com ferramentas (MCP), base de conhecimento pessoal e automações (n8n). Desenvolvido por Murillo Bolonhini Cita. O chat é privado e o acesso é por convite; o código é aberto à leitura, mas os dados ficam no Mac do autor.

Documentação publicada: https://heimdall-ai.tech (gerada da pasta docs/ pelo GitHub Pages).

Este README é mantido junto com o código. As tabelas entre marcadores `AUTO` são geradas por `python3 gerar_docs.py`; não as edite à mão.

## Acessos

1. Chat: https://chat.heimdall-ai.tech (por convite).
2. Automações: https://flows.heimdall-ai.tech (login do administrador).
3. Status: https://status.heimdall-ai.tech (acesso restrito).
4. Documentação: https://heimdall-ai.tech

Contato: suporte@heimdall-ai.tech e https://www.linkedin.com/in/murillobolonhinicita

## Propósito

Heimdall, na mitologia nórdica, guarda a ponte Bifröst. O projeto vigia e conecta as ferramentas de quem o criou, com três objetivos: manter os modelos de linguagem sob controle de quem os usa, dar a eles ferramentas reais (web, arquivos, documentos, memória, Notas, Calendário) e automatizar rotinas (resumos, estudo, vigilância de privacidade, avisos no iPhone). Foi pensado para uso por pessoa cega: tudo opera por texto e comandos, com notas e áudio acessíveis.

## Arquitetura em resumo

1. Ollama executa os modelos no Mac.
2. LiteLLM Proxy (porta 9000) é o ponto único de acesso, com API compatível com a da OpenAI, e expõe os servidores MCP.
3. Dois servidores MCP em Python (8000, só do Mac; 8001, público) e o servidor de documentação da AWS fornecem as ferramentas.
4. O n8n agenda fluxos; o agente do Mac (8003) liga o n8n ao app Notas, ao Calendário, aos Lembretes e à voz do macOS; o Bark entrega avisos no iPhone.

Detalhes em https://heimdall-ai.tech/arquitetura.html.

### Serviços e portas

<!-- AUTO:SERVICOS -->
| Serviço | Porta | Função |
|---|---|---|
| Ollama | 11434 | Executa os modelos de linguagem no Mac. |
| LiteLLM Proxy | 9000 | Ponto único de acesso (API compatível com a da OpenAI) aos modelos; também expõe os servidores MCP. |
| Servidor MCP do Mac (admin) | 8000 | Ferramentas que mexem no Mac: arquivos, métricas, memória e documentos. |
| Servidor MCP público | 8001 | Ferramentas seguras para convidados: web, cálculo, feeds, transcrições. |
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
nohup bash start_heimdall.sh --webui --terminal --n8n --agente > heimdall.log 2>&1 &
tail -30 heimdall.log
curl -s http://localhost:8003/saude
docker ps --format '{{.Names}}: {{.Status}}'
```

Opções: `--webui`, `--terminal`, `--n8n`, `--agente`, `--docling`, `--ingest`, `--update`. A lista completa está no cabeçalho de `start_heimdall.sh` e em https://heimdall-ai.tech/comandos.html.

## Testar

```
venv/bin/python test_mcp.py                       # servidores MCP, direto e pelo LiteLLM
venv/bin/python test_models_tools.py              # chamada de ferramentas por modelo
python3 heimdall_agente.py --teste                # Notas, Calendário e Lembretes
python3 heimdall_agente.py --voz                  # voz e velocidade do áudio
bash instalar_email_oficial.sh --testar           # login e simulação do vigia de e-mail
python3 gerar_docs.py --check                     # documentação em dia
```

Os testes dos fluxos (`test_*.js` com Node e `test_*.py` com Python) ficam na pasta do projeto.

## Modelos de linguagem

<!-- AUTO:MODELOS -->
| Nome no LiteLLM | Modelo no Ollama | Uso | Observações |
|---|---|---|---|
| `qwen-3.8-uncensored` | `ollama_chat/eriktonon/qwen3.8-uncensored:9b` | Uso geral | Confira a chamada de ferramentas com test_models_tools.py. |
| `gemma-4-uncensored` | `ollama_chat/eriktonon/gemma4-uncensored` | Uso geral | Confira a chamada de ferramentas com test_models_tools.py. |
| `dolphin3-cyber-8b` | `ollama_chat/mparvin/dolphin3-cyber-8b-gguf:q8_0` | Segurança e conversa livre | Confira a chamada de ferramentas com test_models_tools.py. |
| `deepseek-coder-v2:16b` | `ollama_chat/deepseek-coder-v2:16b` | Código (usado pelo GitOps) | O GitOps usa este modelo na etapa de análise de código. |
| `qwen3-vl-instruct` | `ollama_chat/qwen3-vl:8b-instruct` | Modelo padrão dos fluxos; entende imagens | Declara suporte a imagens no LiteLLM. |
| `bonsai-27b` | `ollama_chat/eriktonon/bonsai-2-uncensored:27b` | Modelo grande, respostas mais elaboradas | Confira a chamada de ferramentas com test_models_tools.py. |
| `medgemma` | `ollama_chat/medgemma:4b` | Modelo médico pequeno; só para testes | Trocou o sentido de uma variação nos testes de saúde; não é usado nos fluxos. |
<!-- /AUTO:MODELOS -->

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
<!-- /AUTO:FERRAMENTAS -->

Para criar uma ferramenta: escreva a função em `heimdall_tools.py` com tipos e docstring claro, acrescente-a a `PUBLIC_TOOLS` ou `MAC_TOOLS`, reinicie, rode `test_mcp.py` e `gerar_docs.py`. Ferramentas públicas são seguras para convidados; as do Mac acessam arquivos e memória e são só do administrador.

## Fluxos do n8n

<!-- AUTO:FLUXOS -->
| Fluxo | Quando | O que faz |
|---|---|---|
| resumo diário da AWS para dados | todo dia às 7h45 | Lê o feed de novidades da AWS, filtra os serviços de dados (Glue, Redshift, Athena, S3, Kinesis e outros), resume em português e avisa no iPhone. |
| vigia de versões (semanal) | toda semana (segunda às 9h) | Consulta os lançamentos dos projetos que o Heimdall usa, avalia se vale atualizar e avisa no iPhone. |
| alerta de saúde do Mac | a cada 1 hora(s) | Lê as métricas do Mac pelo MCP e avisa quando RAM, swap ou disco passam dos limites configurados. |
| relatório diário de disponibilidade | todo dia às 5h45 | Lê a página de status do Uptime Kuma, monta o relatório de disponibilidade do dia e avisa no iPhone. |
| GitOps inteligente (auditor e refatorador) | a cada git push (webhook) | A cada git push, divide o código alterado em trechos de até 5 mil caracteres, analisa os trechos tocados pelo commit com o modelo de código (um de cada vez, para poupar memória), que responde com edições pontuais validadas uma a uma, e abre um Pull Request em rascunho com as refatorações sugeridas. Se o GitHub recusar o PR, apaga a branch para não deixar lixo e avisa com o motivo e o resumo dos achados. Sempre avisa o resultado, inclusive quando não há nada a refatorar. |
| digest hiperpersonalizado (7h45 e 18h) | cron 45 7 * * * | Lê feeds de notícias, filtra pelo que interessa, cruza com as notas e os livros e grava um resumo personalizado no app Notas. |
| Second Brain (notas, conexões e lacunas) | a cada 5 minutos | Observa as notas alteradas do app Notas (nunca as de pastas privadas), cria embeddings, encontra conexões e lacunas e grava a análise na pasta Cérebro. |
| aviso de falha | quando outro fluxo falha | Quando qualquer fluxo falha, avisa no iPhone qual fluxo, em que etapa e por quê. Fluxos nunca falham em silêncio. |
| monitor de privacidade (diário) | cron 45 9 * * * | Pesquisa na web os identificadores pessoais configurados pelo dono (nome, e-mails, usuários) em busca de menções, comentários, vazamentos e imagens, separa homônimos, analisa o risco e grava o relatório. Tem memória: só avisa o que é novo. |
| diários oficiais (diário) | cron 40 9 * * * | Procura o nome do dono nos diários oficiais do município de São Paulo, da União e do Estado de SP e, se a OAB estiver configurada, as comunicações dela no Diário da Justiça Eletrônico Nacional (CNJ). Avisa só o que for novo. Se uma fonte falhar, o aviso diz qual e nunca finge que não há nada. |
| checagem mensal de serviços públicos | cron 50 9 1 * * | Lembrete mensal para conferir, nos aplicativos oficiais, serviços que exigem login (INSS, FGTS, Carteira de Trabalho, Registrato e Serasa). |
| estudo dos livros (6h, 13h e 20h) | cron 0 6,13,20 * * * | Para cada tema da base de conhecimento (subpastas de knowledge/), sorteia um trecho, monta uma leitura, cria pergunta e resposta, busca de 1 a 3 artigos na web e grava a nota no app Notas, na pasta com o nome do tema, com áudio narrado. |
| resumo agrupado (6h, 8h e 10h) | cron 0 6 * * * | Junta os avisos de rotina em três notificações por dia (6h, 8h e 10h), em vez de uma por fluxo. Avisos urgentes e os de situação (falhas, GitOps, alerta do Mac) continuam na hora. |
| monitor de saúde (resumo das 5h50) | todo dia às 5h50 | Recebe os dados do app Saúde (iPhone e Apple Watch) e escreve às 5h50 um resumo de sono, pulso, variabilidade, respiração e atividade contra a média de 30 dias. As regras decidem o que é relevante, o modelo só redige e uma verificação barra texto com sentido trocado. |
<!-- /AUTO:FLUXOS -->

Resumos agrupados: os avisos de rotina saem em três notificações por dia (6h, 8h e 10h) pelo fluxo "Resumo agrupado" (webhook `heimdall-resumo`); falhas, GitOps, alerta do Mac e o estudo continuam na hora. O "Monitor de saúde" (webhook `heimdall-saude`, resumo às 5h50) recebe os dados do Health Auto Export; as regras decidem o que é relevante e o modelo só redige.

Instalação: `bash instalar_fluxos_n8n.sh` (básicos), `bash instalar_automacoes_avancadas.sh` (GitOps, digest, Second Brain, estudo) e `bash instalar_monitor_privacidade.sh` (monitor e diários). Rodar um fluxo agora: `docker exec -e N8N_RUNNERS_BROKER_PORT=5680 n8n n8n execute --id=<id>`.

## Privacidade e segurança

1. Dados pessoais, chaves e identificadores ficam só no Mac. `.env`, `knowledge/`, `qdrant_storage/` e backups nunca são versionados.
2. Notas de pastas privadas nunca são lidas, indexadas nem analisadas.
3. O agente do Mac exige token e só grava nas pastas do próprio Heimdall.
4. O vigia de e-mail é somente leitura, só confia no remetente confirmado pelo Gmail e nunca segue links.
5. Falhas nunca são silenciosas; fonte indisponível nunca vira "nada novo".
6. Textos de fontes externas são tratados como dados, não como ordens.
7. Este repositório pode ser público: o código não traz dados pessoais (caminhos, IPs e e-mail vêm de variáveis ou do `.env`, que nunca é versionado). Antes de publicar, confira o histórico com `git log --all --oneline -- .env` e `git log --all -p | grep -ciE "api_key|token|senha"`.

## Publicação da documentação

A pasta docs/ é publicada pelo GitHub Pages com o domínio heimdall-ai.tech (arquivo `docs/CNAME`). O fluxo `.github/workflows/pages.yml` confere se a documentação está em dia e publica a cada push em `main`. O passo a passo de DNS no Cloudflare está em `PUBLICAR_PAGINAS.md`. Observação: GitHub Pages em repositório privado exige plano pago; em repositório público é gratuito.

## Como manter (a cada recurso novo)

1. Implemente e teste o recurso.
2. Acrescente um bloco no topo de `CHANGELOG.md`: `## AAAA-MM-DD - título`, com itens iniciados por hífen.
3. Se criou fluxo, modelo ou ferramenta novo, acrescente a descrição em `gerar_docs.py` (`FLUXO_DESCRICAO`, `MODELOS_NOTAS`; ferramentas leem o docstring). O gerador avisa o que faltar.
4. Se mudou comandos de uso, atualize `COMANDOS` em `gerar_docs.py` e as seções manuais deste README.
5. Rode `python3 gerar_docs.py` e confira com `python3 gerar_docs.py --check`.
6. Faça commit de tudo (código, CHANGELOG, README e docs/) no mesmo commit.

## Licença

Projeto privado. Todos os direitos reservados a Murillo Bolonhini Cita.
