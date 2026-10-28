# Guia de Nomes para Branches (Git Branching)

Padronizar a nomenclatura das branches ajuda a equipe a identificar o propósito de cada alteração e quem está responsável por ela.

## Estrutura Básica

```
nome-da-pessoa/tipo/descricao-curta
```

- `nome-da-pessoa/` : Identifica quem está trabalhando na branch (primeiro nome em minúsculas ou iniciais).
- `tipo/` : Categoria da tarefa (semelhante aos commits).
- `descricao-curta/` : Resumo em kebab-case (palavras separadas por hífen) do que está sendo feito.

## Tipos Principais (Prefixos)

- `feat/` — Para novas funcionalidades ou recursos.

  `feat/joao/chunking-automatico`

- `fix/` — Para correção de bugs e falhas.

  `fix/maria/correcao-token-auth`

- `refactor/` — Para melhorias internas de código que não adicionam features nem corrigem bugs.

  `refactor/carlos/limpeza-logica-parser`

- `docs/` — Para alterações exclusivas em documentação.

  `docs/ana/atualiza-readme-instalacao`

- `test/` — Para adição ou ajuste de testes automatizados.

  `test/lucas/testes-fluxo-pagamento`

- `chore/` — Para manutenção, build, dependências ou tarefas de infraestrutura.

  `chore/beatriz/atualiza-dependencias-supabase`

## Boas Practicas para a Equipe

**1. Use kebab-case na descrição:**

- Evite espaços, letras maiúsculas e acentos. Prefira hífens (-).  
   Errado: `feat/Joao/Nova Funcionalidade`  
   Certo: `feat/joao/nova-funcionalidade`

**2. Mantenha o nome da pessoa padronizado:**

- Usarão o primeiro nome (joao) + sobrenome caso duas pessoas com mesmo nome para que todos sigam o mesmo padrão.

**3. Mantenha a branch atualizada:**

- Faça merges frequentes da branch principal (main ou develop) na sua branch para evitar conflitos gigantescos no final.

**4. Exclua após o merge:**

- Uma vez que o Pull Request foi aprovado e integrado, delete a branch (tanto local quanto remota) para manter o repositório limpo.
