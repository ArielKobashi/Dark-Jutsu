# Motor de migracao Firebase -> SQL

Incrementos implementados:

- dominio `cooperat` com dry-run, apply SQL e integridade;
- extrator Firebase REST para snapshots raw;
- dominio `inventory` em modo inspect/dry-run para o snapshot `estoqueGlobal`;
- dominios `users`, `dashboard`, `counting`, `occurrences`, `chat` e `automus` com apply SQL e integridade.

## Modos

Exportar caminhos do Firebase para `_migration_runs/<run-id>/raw`:

```powershell
$env:FIREBASE_DATABASE_URL="https://<projeto>.firebaseio.com"
$env:FIREBASE_ID_TOKEN="<id-token>"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\extract_firebase.py --run-id firebase_export_initial
```

Tambem e possivel exportar apenas um caminho:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\extract_firebase.py --run-id firebase_inventory_initial --path estoqueGlobal
```

Inspecionar/dry-run usando o JSON local:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py inspect --domain cooperat --run-id initial_cooperat_dry_run
```

Inspecionar estoque a partir de um snapshot Firebase exportado:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py inspect --domain inventory --run-id firebase_inventory_initial --source _migration_runs\firebase_inventory_initial\raw\estoqueGlobal.json
```

Inspecionar estoque a partir de um export completo do Realtime Database:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py inspect --domain inventory --run-id firebase_inventory_export_20260629 --source "C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json" --sample-size 30
```

Aplicar no PostgreSQL:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@localhost:5432/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain cooperat --mode apply
```

Aplicar estoque no PostgreSQL local portatil:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain inventory --mode apply --run-id inventory_apply_local_initial --source "C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json" --sample-size 30
```

Verificar integridade raw-only:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain cooperat --run-id initial_cooperat_dry_run --fail-on high
```

Verificar integridade inventory raw-vs-SQL:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain inventory --run-id inventory_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

Aplicar usuarios, solicitacoes e banidos no PostgreSQL local portatil:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain users --mode apply --run-id users_apply_local_initial --source "C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json" --sample-size 20
```

Verificar integridade users raw-vs-SQL:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain users --run-id users_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

Aplicar dashboard/avaliador no PostgreSQL local portatil:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain dashboard --mode apply --run-id dashboard_apply_local_initial --source "C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json" --sample-size 20
```

Verificar integridade dashboard raw-vs-SQL:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain dashboard --run-id dashboard_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

Aplicar contagens/etiquetas no PostgreSQL local portatil:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain counting --mode apply --run-id counting_apply_local_initial --source "C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json" --sample-size 20
```

Verificar integridade counting raw-vs-SQL:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain counting --run-id counting_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

Aplicar ocorrencias no PostgreSQL local portatil:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain occurrences --mode apply --run-id occurrences_apply_local_initial --source "C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json" --sample-size 20
```

Verificar integridade occurrences raw-vs-SQL:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain occurrences --run-id occurrences_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

Aplicar chat no PostgreSQL local portatil:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain chat --mode apply --run-id chat_apply_local_initial --source "C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json" --sample-size 20
```

Verificar integridade chat raw-vs-SQL:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain chat --run-id chat_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

Aplicar Automus no PostgreSQL local portatil:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain automus --mode apply --run-id automus_apply_local_initial --source "C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json" --sample-size 20
```

Verificar integridade Automus raw-vs-SQL:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain automus --run-id automus_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

## Saidas

Cada execucao gera:

```text
_migration_runs/<run-id>/
  manifest.json
  firebase-export-manifest.json
  raw/historicoComprasCooperat.json
  raw/estoqueGlobal.json
  reports/cooperat-summary.json
  reports/cooperat-summary.md
  reports/inventory-summary.json
  reports/inventory-summary.md
  reports/integrity-inventory.json
  reports/integrity-inventory.md
  reports/integrity-inventory-differences.jsonl
  raw/users-domain.json
  reports/users-summary.json
  reports/users-summary.md
  reports/integrity-users.json
  reports/integrity-users.md
  reports/integrity-users-differences.jsonl
  raw/dashboardConfig.json
  reports/dashboard-summary.json
  reports/dashboard-summary.md
  reports/integrity-dashboard.json
  reports/integrity-dashboard.md
  reports/integrity-dashboard-differences.jsonl
  raw/counting-domain.json
  reports/counting-summary.json
  reports/counting-summary.md
  reports/integrity-counting.json
  reports/integrity-counting.md
  reports/integrity-counting-differences.jsonl
  raw/occurrences-domain.json
  reports/occurrences-summary.json
  reports/occurrences-summary.md
  reports/integrity-occurrences.json
  reports/integrity-occurrences.md
  reports/integrity-occurrences-differences.jsonl
  raw/chat-domain.json
  reports/chat-summary.json
  reports/chat-summary.md
  reports/integrity-chat.json
  reports/integrity-chat.md
  reports/integrity-chat-differences.jsonl
  raw/automus-domain.json
  reports/automus-summary.json
  reports/automus-summary.md
  reports/integrity-automus.json
  reports/integrity-automus.md
  reports/integrity-automus-differences.jsonl
  reports/integrity-cooperat.json
  reports/integrity-cooperat.md
  reports/integrity-differences.jsonl
```

## Dependencias

O `dry-run` usa apenas a biblioteca padrao do Python.

O modo `apply` precisa de um driver PostgreSQL:

```powershell
pip install psycopg[binary]
```

ou:

```powershell
pip install psycopg2-binary
```

## Estado atual

Implementado:

- leitura do `data/historico_cooperat_antigo.json`;
- hash SHA-256 do arquivo;
- contagem declarada vs contagem real;
- amostra deterministica de codigos/eventos;
- relatorios Markdown/JSON;
- carga SQL preparada para `cooperat_import_runs`, `cooperat_purchase_codes` e `cooperat_purchase_events`.
- verificador de integridade Cooperat em modo raw-only e raw-vs-SQL.
- exportador Firebase REST por caminho;
- inventario inicial de `estoqueGlobal` com contagem de itens ativos, mortos, ajustes, historico de saldo e MATA185;
- suporte a export completo do Realtime Database como origem para `inventory`.
- carga SQL de `inventory_items`, `inventory_item_addresses`, `inventory_item_limits`, `inventory_adjustments`, `inventory_balance_history`, `inventory_movements` e `inventory_snapshots`;
- verificador de integridade Inventory em modo raw-only e raw-vs-SQL.
- carga SQL de `users`, `signup_requests` e `banned_users`;
- reconciliacao dos caminhos `solicitacoesCadastro` e `solicitaçõesCadastro`;
- sanitizacao de senhas legadas em `raw_data` e bloqueio de senha pura em `signup_requests.password_plain_legacy`;
- verificador de integridade Users em modo raw-only e raw-vs-SQL.
- carga SQL de `dashboard_panels`, `purchase_evaluations` e `app_settings` para `occurrences.fields`;
- verificador de integridade Dashboard em modo raw-only e raw-vs-SQL.
- carga SQL de `counting_sessions`, `counting_items`, `counting_empty_checks`, `counting_drafts`, `counting_machine_status`, `label_print_jobs` e `label_user_ranking`;
- verificador de integridade Counting em modo raw-only e raw-vs-SQL.
- carga SQL de `occurrences` e `occurrence_history`;
- deduplicacao entre `ocorrencias` e fallback `chatGlobal/ocorrencias`;
- verificador de integridade Occurrences em modo raw-only e raw-vs-SQL.
- carga SQL de `chat_rooms`, `chat_messages` e `chat_read_states`;
- migracao de `chatGlobal` legado para sala sintetica `chatGlobal`;
- hash para senhas de salas privadas e sanitizacao de `raw_data`;
- verificador de integridade Chat em modo raw-only e raw-vs-SQL.
- carga SQL de `automus_releases`;
- verificador de integridade Automus em modo raw-only e raw-vs-SQL.

Pendente:

- criar API backend e trocar o frontend para ler/escrever via API;
- adaptar Automus para enviar atualizacoes ao SQL/API em vez de Firebase;
- preparar etapa de escrita dupla ou corte controlado antes de producao.
