# Runbook de corte Firebase Database -> SQL

Data: 2026-07-11

Este documento guia o ensaio e o corte final do Realtime Database. Firebase Auth pode continuar temporariamente; o alvo aqui e desligar o Firebase Database.

## Comandos principais

```bat
scripts\ensaio_sql_only_darkjutsu.bat
scripts\backup_postgres_darkjutsu.bat
scripts\testar_restore_backup_postgres_darkjutsu.bat
```

## Ensaio SQL-only

Ultimo ensaio executado pelo Codex em 2026-07-11:

- API `/health`: OK.
- Auditoria Firebase restante runtime: `226` ocorrencias.
- `py_compile`: OK.
- Integridade raw-vs-SQL: `0` findings em `users`, `dashboard`, `counting`, `occurrences`, `chat`, `automus`, `cooperat` e `inventory`.

1. Inicie PostgreSQL e API.
2. Rode `scripts\ensaio_sql_only_darkjutsu.bat`.
3. Abra o app com `?sqlOnly=1` ou defina no console:

```js
localStorage.setItem("darkJutsuSqlOnly", "1")
```

4. Teste os fluxos principais:
   - login;
   - usuarios/admin;
   - solicitacoes;
   - chat publico/privado;
   - ocorrencias;
   - contagem;
   - dashboard;
   - Automus.

Quando SQL-only estiver ativo, chamadas RTDB feitas pelos wrappers globais (`window.get`, `window.set`, `window.onValue`, `window.push`, `window.runTransaction`) sao bloqueadas e aparecem no console.

## Auditoria Firebase restante

O auditor gera:

```text
_migration_runs\firebase_audit_latest\firebase_audit.md
_migration_runs\firebase_audit_latest\firebase_audit.json
```

Use o Markdown para atacar os destinos restantes por prioridade:

1. `chatRooms/*/typing`
2. `contagemAtual`
3. `contagemStatusMaquinas`
4. `contagens`
5. `usuarios`, `solicitacoesCadastro`, `usuariosBanidos`, `nicknames*`
6. fallbacks de `estoqueGlobal` e `dashboardConfig`

## Backup e restore

Antes do corte:

1. Rode `scripts\backup_postgres_darkjutsu.bat`.
2. Rode `scripts\testar_restore_backup_postgres_darkjutsu.bat`.
3. Confirme que o log contem `Restore de teste OK`.

O teste restaura em `dark_jutsu_restore_test` e remove o banco temporario ao final. Ele nao sobrescreve o banco principal.

## Delta final

1. Combine uma janela curta sem uso operacional.
2. Exporte o Firebase Database.
3. Rode os migradores idempotentes.
4. Rode integridade para todos os dominios.
5. Compare contagens:
   - usuarios;
   - solicitacoes;
   - estoque;
   - contagens;
   - ocorrencias;
   - chat;
   - Automus.

## Corte

1. Ative SQL-only no app.
2. Valide fluxos reais.
3. Bloqueie escrita no Firebase Database.
4. Monitore `GET /api/ops/status`.
5. Mantenha export final Firebase e backup PostgreSQL pre-corte guardados.

## Rollback

Se algum fluxo critico falhar:

1. Remova `darkJutsuSqlOnly` do navegador.
2. Reative regras Firebase Database anteriores.
3. Use o export final para reconciliar o delta posterior.
4. Corrija o endpoint SQL/fallback e repita o ensaio.

## Criterio para desligar de vez

O Firebase Database so deve ser desligado quando:

- `scripts\ensaio_sql_only_darkjutsu.bat` passar;
- `firebase_audit.md` nao listar chamadas RTDB obrigatorias;
- restore de teste passar;
- Automus estiver validado com `AUTOMUS_SQL_ONLY=1`;
- contagem viva nao depender de `onValue`;
- o time tiver testado os fluxos reais no app.
