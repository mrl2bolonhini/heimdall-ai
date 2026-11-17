# Regras do repositório Heimdall-ai

## Heimdall Design (obrigatório em toda atualização de interface)
Antes de criar ou mudar qualquer página dos sites do Heimdall (Cloud, Notas, News, Saúde, Jogos, Finance), leia a página de Design
(gerada em gerar_docs.py, seção "Heimdall Design") e siga-a. A fonte única de cores, tipografia, medidas, foco e botão é `heimdall_design.py`.
- Link lê, botão age (`design.botao`; paginação em `heimdall_paginacao.py`).
- Nada de cor, tamanho de fonte ou foco definido só numa página: use as variáveis (`var(--texto)` etc.). Precisa de algo novo? Acrescente primeiro ao `heimdall_design.py` e à página de Design.
- Acessibilidade para leitor de tela (VoiceOver) e teclado: lang pt-BR, pular para o conteúdo, um só h1, tabelas com caption e scope, campos com label, avisos com role status/alert.
- Rode `python3 teste_design.py` e o teste do serviço alterado antes de enviar.

## Outras regras fixas
- O usuário é cego e usa VoiceOver: respostas em português, texto corrido e listas numeradas simples, sem elementos visuais.
- Cada recurso novo atualiza gerar_docs.py, README, heimdall_ajuda.txt e CHANGELOG.md.
- Dados de saúde e finanças nunca saem do Mac; segredos vêm do .env, nunca colados.
- Trabalhar em develop; `main` só avança com o sim explícito do usuário.
