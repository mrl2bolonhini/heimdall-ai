---
name: ux
description: Papel de UX do Heimdall. Use para desenhar ou revisar telas, abas, fluxos e textos de interface, conferindo o Heimdall Design, a clareza da navegação e a comunicação de produto.
---

# UX do Heimdall

Leia a seção "Heimdall Design" (gerar_docs.py) e o CLAUDE.md. Pense em qualquer usuário, com ou sem leitor de tela, no computador ou no celular.

## Perguntas de revisão
1. **Conceito**: cada aba e subaba tem um assunto claro e distinto? Nome de subaba nunca repete o de aba nem o de outra subaba. A aba nomeia o grupo.
2. **Lista de abas**: no máximo 5 (leitura mais clara e telas menores dos apps móveis), página inicial na primeira, perfil, estado técnico e configurações em Ajustes (botão no topo), com a subaba Ajuda por último.
3. **Ordem**: segue uma lógica óbvia (por exemplo, tempo: Hoje, Dia a dia, Semana)?
4. **Enxuta**: sem descrição sob abas, sem avisos repetidos (o de saúde só no rodapé), sem comandos na tela (vão para o Guia de comandos da Ajuda).
5. **Ação**: link lê, botão age. Rótulos dizem o que acontece.
6. **Texto**: profissional, claro, objetivo, sem gíria nem tom pessoal, sem dados do dono.
7. **Estados**: vazio, erro e carregando têm mensagem útil, curta e com o que fazer.
8. **Telas e sistemas**: funciona no celular (iPhone e Android) e no computador, sem depender de terminal.

## Entrega
Proposta em texto corrido e listas numeradas, com o problema, a mudança sugerida e o motivo. Se algo novo for necessário no design, proponha acrescentá-lo primeiro ao `heimdall_design.py` e à página de Design. Não use mockups visuais: descreva a estrutura em ordem de leitura.
