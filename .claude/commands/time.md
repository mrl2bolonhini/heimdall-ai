---
description: Aciona o time de desenvolvimento do Heimdall (PO, tech lead, UX, QA funcional, QA de acessibilidade) conforme a demanda
argument-hint: <demanda> [--so po,ux,...] [--analisar]
---

Demanda: $ARGUMENTS

Conduza esta demanda como o time do Heimdall, usando as skills em `.claude/skills/`. Leia o CLAUDE.md primeiro.

1. Escolha só os papéis necessários. Se o usuário passou `--so`, use apenas esses. Se passou `--analisar`, não implemente: devolva a análise e a ordem de execução proposta.
2. Ordem padrão: `po` (escopo e critérios de aceite) → `ux` (se houver tela ou texto) → `tech-lead` (plano e implementação) → `qa-funcional` → `qa-acessibilidade` (se houver tela). Pule o que não se aplica e diga por quê em uma linha.
3. Rode a revisão de QA com um subagente separado (contexto limpo), para não revisar o próprio trabalho.
4. Conflito entre papéis ou com uma regra do CLAUDE.md: apresente as opções ao usuário e espere a decisão.
5. Resposta final curta, em português, em texto corrido e listas numeradas: o que cada papel concluiu, o que mudou, o que não foi testado e o que o usuário precisa decidir.
