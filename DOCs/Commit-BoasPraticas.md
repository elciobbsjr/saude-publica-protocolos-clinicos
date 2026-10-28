# Guia Rápido de Commits Semânticos

O uso de commits semânticos padroniza o histórico de alterações do repositório, facilitando a leitura do código, a automação de changelogs e a organização da equipe.

## Estrutura Básica

```
    [TIPO](escopo): Descrição breve do que foi feito
```

## Tipos Principais com exemplos

- [FEAT] — Introduz uma nova funcionalidade ao projeto.  
  `[FEAT](chunking) Adiciona suporte a divisão automática de texto`
- [FIX] — Correção de um bug (conserto de falhas).  
  `[FIX](auth) Resolve problema de expiração prematura do token`
- [DOCS] — Alterações apenas na documentação (README, comentários, etc.).  
  `[DOCS](api) Atualiza exemplos de rotas no Swagger`
- [STYLE] — Alterações que não afetam o código em si (espaçamento, formatação, ponto e vírgula, etc.).  
  `[STYLE](ui) Aplica padrão de indentação nos arquivos CSS`
- [REFACTOR] — Alteração de código que não corrige bugs nem adiciona novos recursos (melhoria interna).  
  `[REFACTOR](parser) Simplifica lógica de validação de arquivos`
- [TEST] — Adição ou correção de testes automatizados.  
  `[TEST](checkout) Adiciona testes unitários para o fluxo de pagamento`
- [CHORE] — Tarefas de manutenção, atualização de dependências ou build.  
  `[CHORE](deps) Atualiza versão da biblioteca Supabase`

## Boas Práticas

1. Use o imperativo: Escreva a descrição como uma ordem ou ação ("Adiciona...", "Corrige...", "Atualiza..."), e não no passado.
2. Mantenha curto: O resumo principal deve ser conciso (idealmente até 50 caracteres).
