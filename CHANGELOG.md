# Novidades

Registro dos recursos do Heimdall-ai, do mais recente ao mais antigo. Cada recurso novo ganha um bloco "## AAAA-MM-DD - título" com itens iniciados por hífen, acima dos anteriores. As páginas do site são geradas deste arquivo.

## 2026-11-16 - heimdall env grava as variáveis do Cloudflare Access
- heimdall env --set agora também aceita HEIMDALL_CFACCESS_EQUIPE, HEIMDALL_CFACCESS_AUD, HEIMDALL_CFACCESS_EMAILS e HEIMDALL_CFACCESS_CONVIDADOS com o valor direto no comando, sem copiar e colar cada um (exemplo: heimdall env --set HEIMDALL_CFACCESS_EQUIPE mrl2-bolonhini). Esses valores não são segredos.
- Segurança: o valor na linha de comando só vale para essas quatro variáveis, com formato conferido; para os segredos (chaves do R2 e senha da cópia) continua valendo só a área de transferência, e o comando recusa aspas simples e nomes fora da lista.
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
- Caixa de entrada da saúde (Worker heimdall-saude-caixa, cloudflare/saude_caixa.js): fica na frente do webhook de saúde do n8n, no mesmo endereço que o Health Auto Export já usa, sem mudar nada no app. Com o Mac no ar, repassa tudo como veio. Com o Mac dormindo ou sem rede, guarda o envio no KV (7 dias, até 200 envios, até 8 MB cada) e responde 202 ao app; de 5 em 5 minutos reenvia ao n8n o que ficou e apaga o que foi aceito. Opcional: o segredo TOKEN_SAUDE faz a caixa guardar só envios com o cabeçalho certo.
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
