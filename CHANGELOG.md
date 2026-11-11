# Novidades

Registro dos recursos do Heimdall-ai, do mais recente ao mais antigo. Cada recurso novo ganha um bloco "## AAAA-MM-DD - título" com itens iniciados por hífen, acima dos anteriores. As páginas do site são geradas deste arquivo.

## 2026-11-11 - Triagem obrigatória de avisos importantes
- Novo sistema de triagem: o que for importante vira um lembrete na lista "Heimdall: Triagem" do app Lembretes (iPhone e Mac), com o resumo e o caminho para a nota completa no Notas. O Heimdall insiste pelo Bark até você agir. Concluir o lembrete dispensa o aviso; mudar a prioridade classifica a importância (alta, média ou baixa); mudar o horário adia.
- O que entra na triagem: comunicações do Diário da Justiça (pela OAB), aviso de fonte dos diários indisponível há 24 horas, e-mails suspeitos de golpe e e-mails oficiais urgentes, achados de privacidade de risco médio ou alto (os de risco baixo, como páginas suas, ficam só no relatório) e sinais de saúde "muito relevantes" do resumo das 5h50.
- Insistência: aviso a cada 2 horas das 7h às 21h, sem tocar à noite; com prioridade baixa no lembrete, a cada 8 horas. Itens críticos (por exemplo, audiência, mandado, bloqueio, prazo curto, febre ou oxigênio) usam o nível crítico do Bark, que fura o modo silencioso: o primeiro aviso sai na hora, a qualquer hora, e as repetições seguem o horário das 7h às 21h. Menções do Diário da Justiça viram críticas depois de 24 horas sem ação. Se você baixar a prioridade de um item crítico, ele deixa de furar o silêncio.
- Novo fluxo "triagem de avisos" no n8n: a cada 15 minutos chama o agente do Mac, que lê os lembretes, registra a sua decisão no banco (nova tabela triagem: estado, prioridade que você deixou, quando decidiu, adiamento, número de avisos) e envia os avisos. Se o agente ficar 1 hora sem responder, avisa uma vez só.
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
