# Novidades

Registro dos recursos do Heimdall-ai, do mais recente ao mais antigo. Cada recurso novo ganha um bloco "## AAAA-MM-DD - título" com itens iniciados por hífen, acima dos anteriores. As páginas do site são geradas deste arquivo.

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
