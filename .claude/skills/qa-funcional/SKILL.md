---
name: qa-funcional
description: Papel de QA funcional do Heimdall. Use depois de implementar para verificar se o resultado cumpre os critérios de aceite, cobrindo casos de borda, dados por pessoa, segurança básica e regressões.
---

# QA funcional do Heimdall

Verifique o que foi feito contra os critérios de aceite do PO. Não confie só no relato de quem implementou: rode e leia.

## Roteiro
1. **Critérios de aceite**: confira um a um e marque passou ou falhou.
2. **Casos de borda**: sem dados, dados demais, primeiro acesso, convidado, pessoa diferente do dono, data de fronteira (adiamento até hoje), arquivo duplicado, serviço externo fora do ar.
3. **Dados**: perfil e sugestões ficam no banco de cada pessoa; nada de dado pessoal em texto de produto; nada de segredo no código.
4. **Segurança básica**: rotas POST com CSRF e validação de endereço, convidado sem acesso indevido, saída escapada.
5. **Agenda**: evento versus lembrete conforme `heimdall_agenda.py`.
6. **Regressões**: rode `./rodar_testes.sh` nas pastas afetadas e `python3 tests/design/teste_design.py`; leia as falhas, não só a contagem.
7. **Documentação**: gerar_docs.py, README, guias e CHANGELOG batem com o que foi feito.
8. **Sistemas**: o que depende do Mac está dito, com alternativa registrada.

## Entrega
Lista numerada: passou, falhou e não testado (com motivo). Para cada falha, o passo para reproduzir e o resultado esperado. Sugira testes automatizados para o que ainda não tem.
