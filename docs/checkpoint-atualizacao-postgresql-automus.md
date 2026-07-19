# Checkpoint da atualizacao PostgreSQL pelo Automus

Antes de acionar a atualizacao no Automus:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\checkpoint_atualizacao_postgres.ps1 -Etapa antes
```

O comando valida a conexao, cria um dump restauravel, salva o schema e registra a
quantidade e a assinatura SHA-256 exata de cada tabela. Nenhum dado e alterado.

Depois que o Automus terminar (com sucesso ou erro):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\checkpoint_atualizacao_postgres.ps1 -Etapa depois
```

O relatorio `RELATORIO.md` mostra tabelas que mudaram, nao mudaram, surgiram ou
foram removidas, com contagens antes/depois. `comparacao.json` contem os hashes
para auditoria. Os dumps `.backup` permitem restauracao com `pg_restore`.

Os artefatos ficam em `_db_update_checkpoints/` e nao sao versionados. Se a
instalacao do PostgreSQL estiver em outro local, defina `PG_BIN`. Para outro
banco, informe `-DatabaseUrl`; nao salve senhas no relatorio ou no Git.
