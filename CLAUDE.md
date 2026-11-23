# Regras do repositório Heimdall-ai

## Heimdall Design (obrigatório em toda atualização de interface)
Antes de criar ou mudar qualquer página dos sites do Heimdall (Cloud, Notas, News, Saúde, Jogos, Finance), leia a página de Design
(gerada em gerar_docs.py, seção "Heimdall Design") e siga-a. A fonte única de cores, tipografia, medidas, foco e botão é `heimdall_design.py`.
- Link lê, botão age (`design.botao`; paginação em `heimdall_paginacao.py`).
- Nada de cor, tamanho de fonte ou foco definido só numa página: use as variáveis (`var(--texto)` etc.). Precisa de algo novo? Acrescente primeiro ao `heimdall_design.py` e à página de Design.
- Acessibilidade para leitor de tela (VoiceOver) e teclado: lang pt-BR, pular para o conteúdo, um só h1, tabelas com caption e scope, campos com label, avisos com role status/alert.
- Rode `python3 tests/design/teste_design.py` e o teste do serviço alterado antes de enviar.

## Evento ou lembrete (obrigatório em toda aplicação que escreve na agenda)
- Evento (Calendário, calendário Heimdall) é o que acontece numa data e hora ou tem data fixa: consulta, prazo. Lembrete (app Lembretes) é o que o usuário precisa fazer e marcar como feito.
- A regra e a tabela de tipos ficam em `heimdall_agenda.py` (DESTINOS). Tipo novo de item na agenda: cadastre-o lá escolhendo evento ou lembrete, e use `agenda.enviar`. Rode `python3 tests/agent/teste_agenda.py`.
- O usuário aceitou que o Calendário sincronize com a nuvem da Apple (ela já fornece dados de saúde ao Heimdall): o evento leva especialidade, médico e local. HEIMDALL_AGENDA_DETALHES=0 volta ao título genérico.

## Perguntar (obrigatório em todo serviço com dados pessoais)
- Todo serviço que mostra dados pessoais do usuário (Finance, Health, News, Notes, Learn) tem o campo Perguntar no fim do painel de cada aba (`heimdall_perguntar.bloco_html`): o código do serviço monta o contexto só com os dados daquela tela, o modelo responde só com base nele (com os trechos que o usuário estudou, para poder perguntar sobre o texto, nunca o livro inteiro nem o gabarito ainda secreto) e a rota POST /perguntar exige CSRF e valida o endereço de volta. Serviço novo com dados pessoais já nasce com o Perguntar e um teste dele. O Cloud também tem o Perguntar (contexto: o estado do emulador, com conhecimento geral de AWS permitido, sem executar nada). Games e Controls ficam de fora por ora. O Perguntar usa o modelo leve da nuvem (Qwen3 30B com /no_think; HEIMDALL_NUVEM_PERGUNTAR_MODELO troca) e o campo é de várias linhas: Enter envia, Shift+Enter pula linha, Option+Shift+P leva ao campo.

## Comandos do terminal
- Nomes de comando, subcomando e opção do `heimdall` são em inglês (health, labs, --today, --without); o texto que o usuário lê continua em português. O script Python por trás pode ter opções em português: o heimdall.zsh traduz com `_heimdall_tr`.

## Entrega e atualização do Mac
- Depois de enviar à develop, diga ao usuário como atualizar: `heimdall update --restart` (ou `heimdall update -r`) faz o pull da branch atual e reinicia os serviços. Sem reinício: `heimdall update`; se mudou fluxo do n8n, `heimdall flows`; se mudou só o agente, `./subir.sh --reiniciar`.
- Diga sempre se precisa reiniciar, rodar instalador ou instalar algo (brew, pip) e quais permissões do macOS podem ser pedidas.
- Segredo no .env: dê comando de terminal que lê o valor do .env (grep, cut, pbcopy), nunca peça para colar a chave.
- Resposta final curta, em português, em texto corrido e listas numeradas simples, dizendo o que não foi testado.

## Organização do repositório (padrão de pastas)
- Pastas com nome em inglês, de uma palavra só e sem sublinhado, igual ao do serviço (finance, flows, games, db, brain, inbox, sheets, qdrant, macapp). Pasta de dados do Mac que mude de nome precisa de migração automática em `heimdall_pastas.py` (renomeia a antiga na primeira subida e nunca apaga dados). Pasta de Docker (qdrant) migra no `start_heimdall.sh`, recriando o contêiner.
- Dados de saúde que o usuário solta (exames, receitas, encaminhamentos) ficam em `health/` (inbox, archive, review), como o Finance em `finance/inbox`; `db/` guarda só bancos e cópias (copies, mailbox, alerts, people). Subpasta também em inglês e de uma palavra.
- Backups em `backups/`: `scripts/podar_backups.sh` mantém só os últimos 3 de cada tipo (HEIMDALL_BACKUPS_MANTER); quem criar um tipo novo de backup acrescenta o padrão do nome nesse script.
- `tests/<serviço>/`: cada teste vai na pasta do serviço que ele cobre (finance, health, news, notes, games, cloud, account, controls, agent, chat, design, monitor, core). Teste novo começa com o bloco de raiz que os outros têm (define `RAIZ` e põe a raiz no sys.path) e usa `RAIZ` para achar arquivos do projeto. `./rodar_testes.sh` roda tudo; `./rodar_testes.sh finance` roda uma pasta; `./rodar_testes.sh -l` lista as pastas. Os testes dos Workers ficam em `cloudflare/`.
- `guides/`: guias, ajudas e LEIAME (inclui `heimdall_ajuda.txt` e o `modelos_open_webui.txt`, gerado). `prompts/`: prompts do chat. `scripts/`: scripts de shell de instalação e manutenção. `flows/` (basic, advanced, monitor): fluxos do n8n.
- Na raiz ficam só: os módulos Python (importam uns aos outros), `subir.sh`, `start_heimdall.sh`, `start_ecosystem.sh` e `heimdall.zsh` (os LaunchAgents do Mac apontam para eles: não mover), os arquivos de configuração e README, CHANGELOG, ROADMAP e CLAUDE.
- Arquivo novo: guia vai para `guides/`, script para `scripts/` (com `cd "$(dirname "$0")/.."` no começo) e teste para `tests/<serviço>/`.

## Outras regras fixas
- O usuário é cego e usa VoiceOver: respostas em português, texto corrido e listas numeradas simples, sem elementos visuais.
- Padrão combinado em conversa que valha para o projeto todo vai para este CLAUDE.md, para as próximas conversas seguirem.
- Cada recurso novo atualiza gerar_docs.py, README, guides/heimdall_ajuda.txt e CHANGELOG.md.
- Segredos vêm do .env, nunca colados.
- Migração para a Cloudflare (decisão do usuário em 21/11/2026): a regra "saúde e finanças nunca saem do Mac" foi abandonada; saúde, finanças e o resto podem ir para a nuvem da Cloudflare, com dados protegidos (R2 com chave do cliente, acesso restrito). O Mac continua hospedando o Heimdall (sem VPS por enquanto) e o agente da Apple. O desenvolvimento segue na assinatura Pro do Claude, não na API.
- Limite de gasto da nuvem: no máximo US$ 15 por mês, somando Workers, Workers AI, AI Gateway e créditos de modelos. Ative alertas e limites ANTES de ligar cada fase; nenhuma fase começa sem eles.
- Plano de volta: toda fase da migração precisa poder ser desligada por um interruptor no .env (ex.: HEIMDALL_NUVEM=0) que devolve o comportamento anterior (modelos locais, dados no Mac), e os dados enviados à nuvem têm cópia de volta no Mac antes de qualquer remoção. Nunca apagar a cópia local antes de o usuário confirmar que a fase vale a pena.
- Trabalhar em develop; `main` só avança com o sim explícito do usuário.
