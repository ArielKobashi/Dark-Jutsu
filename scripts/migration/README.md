# Motor de migracao Firebase -> SQL

Incrementos implementados:

- dominio `cooperat` com dry-run, apply SQL e integridade;
- extrator Firebase REST para snapshots raw;
- dominio `inventory` em modo inspect/dry-run para o snapshot `estoqueGlobal`.

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

Pendente:

- instalar driver PostgreSQL para `apply`;
- subir PostgreSQL para testar `apply`;
- rodar integridade Cooperat em modo raw-vs-SQL;
- criar cargas SQL para `users`, `dashboard`, `counting`, `occurrences`, `labels`, `chat` e `automus`.
