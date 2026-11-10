# Novidades

Registro dos recursos do Heimdall-ai, do mais recente ao mais antigo. Cada recurso novo ganha um bloco "## AAAA-MM-DD - título" com itens iniciados por hífen, acima dos anteriores. As páginas do site são geradas deste arquivo.

## 2026-11-10 - Resumos agrupados e monitor de saúde
- Novo fluxo "Resumo agrupado": os avisos de rotina entram numa fila e saem em três notificações por dia (6h, 8h e 10h). Disponibilidade e saúde às 6h; AWS e digest da manhã às 8h; diários oficiais, privacidade, e-mails oficiais, versões e checagem mensal às 10h. Falhas, GitOps, alerta do Mac, digest das 18h e estudo continuam na hora. Urgentes furam a fila.
- Novo fluxo "Monitor de saúde": recebe os dados do app Saúde pelo Health Auto Export, calcula o que mudou contra a média de 30 dias por regras, o modelo geral redige e uma verificação descarta texto com sentido trocado. Critérios para procurar um médico são fixos. Não acompanha glicemia.
- Testes com modelos de saúde: o MedGemma de 4 bilhões trocou o sentido de uma variação e foi descartado; o qwen3-vl-instruct acertou e é o redator. Condições de saúde ficam só no .env (HEIMDALL_SAUDE_CONDICOES), fora do código público.
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
