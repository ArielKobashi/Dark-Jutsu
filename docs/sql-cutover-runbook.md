# Runbook de corte Firebase Database -> SQL

Data: 2026-07-11

Este documento guia o ensaio e o corte final do Firebase. O Realtime Database e o Firebase Auth foram substituidos por SQL/API local.

## Comandos principais

```bat
scripts\ensaio_sql_only_darkjutsu.bat
scripts\backup_postgres_darkjutsu.bat
scripts\testar_restore_backup_postgres_darkjutsu.bat
```

## Ensaio SQL-only

Ultima frente executada pelo Codex em 2026-07-12:

- `index.html` nao importa mais SDK Firebase; login/cadastro/sessao usam `POST /api/auth/login` e token SQL local.
- `dashboard.html` e `label-editor.html` usam a mesma sessao SQL local, sem Firebase Auth.
- Carga inicial de estoque usa `/api/dashboard/snapshot` e atualizacao manual usa `POST /api/inventory/automus-update`.
- Admin/cadastro/usuarios/banidos, ocorrencias, chat, read-state, typing, contagem viva, rascunhos, reset global e Automus release ficaram SQL-only no frontend principal.
- Wrappers globais de Realtime Database (`window.get`, `window.set`, `window.update`, `window.push`, `window.onValue`) agora falham fechado com erro orientando uso da API SQL.
- Automus build/update/release foi endurecido para SQL-only por padrao; `Automus/scripts/firebase_config.json` foi removido.
- Controladores Automus deixaram de autenticar/validar admin no Realtime Database; agora exigem `DARK_JUTSU_API_TOKEN` em modo SQL-only.
- `scripts/importar_historico_cooperat_firebase.py` foi transformado em stub de bloqueio, apontando para o motor SQL de migracao.
- `scripts/atualizacao/automus_update.py` e `Automus/scripts/atualizacao/automus_update.py` nao fazem mais backup remoto, leitura, PATCH ou PUT no banco legado; a publicacao termina na API SQL.
- Auditoria Firebase restante: `0` ocorrencias estaticas nos alvos principais.
- Sintaxe dos scripts extraidos de `index.html`, `dashboard.html` e `label-editor.html`: OK via `node_repl`/`node:vm`.
- API `/health`: OK em `http://192.168.5.44:8765`; `127.0.0.1:8765` nao respondeu nesta rodada.
- `GET /api/ops/status`: protegido; retornou `401` sem credencial administrativa, como esperado.
- `py_compile`: OK.
- Integridade raw-vs-SQL anterior: `0` findings em `users`, `dashboard`, `counting`, `occurrences`, `chat`, `automus`, `cooperat` e `inventory`; repetir apos delta final.
- `dashboard.html` e `label-editor.html` nao usam mais Firebase Database quando a API SQL esta disponivel.
- Automus agora assume SQL-only no build, controlador e atualizador; use `DARK_JUTSU_API_TOKEN` para execucao sem usuario Firebase.

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

Leitura da rodada atual:

1. Nao ha destino RTDB obrigatorio detectado no frontend principal, dashboard, label editor, controlador ou Automus update.
2. Firebase Auth nao e mais usado pelo frontend principal, dashboard, label editor ou API.
3. `scripts/migration/firebase_client.py` e a documentacao de migracao ainda ficam disponiveis para export/delta final ate o corte.
4. Depois do delta final e da decisao sobre Auth, arquivar/remover ferramentas de migracao que leem o banco legado.

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
6. Rode novamente `scripts\auditar_firebase_restante.py` e confirme que novas alteracoes nao reintroduziram `firebase-database`, REST `.json?auth` ou `databaseURL` fora das ferramentas de migracao.

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
- contagem viva estiver validada via polling/API SQL no ensaio real;
- o time tiver testado os fluxos reais no app.
- os usuarios que nao possuem senha SQL definida tiverem senha resetada/definida pelo admin.
