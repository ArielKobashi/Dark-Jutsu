# Motor de transferencia Firebase -> SQL

## Objetivo

Criar um motor local e repetivel para transferir dados do Firebase Realtime Database para PostgreSQL, com validacao, idempotencia, auditoria e rollback.

O motor deve suportar tres modos:

- **Inventario**: baixa/inspeciona dados sem gravar SQL.
- **Dry-run**: transforma e valida, mas nao persiste alteracoes finais.
- **Apply**: grava no SQL com checkpoint, auditoria e comparacao.

## Arquitetura

```text
Firebase Realtime Database
  -> Extractor
    -> arquivos raw JSON versionados por execucao
      -> Inspector
        -> Transformer por dominio
          -> Loader SQL
            -> Validator
              -> relatorio de migracao
```

Componentes:

- `extractors`: baixam caminhos Firebase e salvam JSON bruto.
- `inspectors`: contam registros, medem chaves e detectam formatos estranhos.
- `transformers`: convertem cada endereco Firebase para linhas SQL.
- `loaders`: gravam em PostgreSQL com upsert e transacao.
- `validators`: comparam totais/checksums Firebase x SQL.
- `reports`: geram JSON/Markdown por rodada.

## Estado implementado em 2026-06-29

Arquivos criados no repositorio:

- `scripts/migration/firebase_client.py`: cliente REST do Firebase Realtime Database, com login por `FIREBASE_ID_TOKEN` ou email/senha.
- `scripts/migration/extract_firebase.py`: exporta caminhos Firebase para `_migration_runs/<run-id>/raw/*.json`.
- `scripts/migration/run_transfer.py`: orquestra `inspect` e `transfer` por dominio.
- `scripts/migration/domains/cooperat.py`: dominio piloto com dry-run e apply SQL.
- `scripts/migration/domains/inventory.py`: inventario inicial de `estoqueGlobal` em inspect/dry-run.
- `scripts/migration/integrity_check.py`: verificador pos-migracao Cooperat.

Status por dominio:

| Dominio | Extract | Inspect | Apply SQL | Integridade |
| --- | --- | --- | --- | --- |
| `cooperat` | via arquivo local ou Firebase exportado | pronto | executado no PostgreSQL local | raw-only e raw-vs-SQL prontos, `0` findings |
| `inventory` | pronto via `extract_firebase.py --path estoqueGlobal` ou export completo | pronto | executado no PostgreSQL local | raw-only e raw-vs-SQL prontos, `0` findings |
| `users` | pronto via export completo | pronto | executado no PostgreSQL local | raw-only e raw-vs-SQL prontos, `0` findings |
| `dashboard` | pronto via export completo | pronto | executado no PostgreSQL local | raw-only e raw-vs-SQL prontos, `0` findings |
| `counting` | pronto via export completo | pronto | executado no PostgreSQL local | raw-only e raw-vs-SQL prontos, `0` findings |
| `occurrences` | pronto via export completo | pronto | executado no PostgreSQL local | raw-only e raw-vs-SQL prontos, `0` findings |
| `chat` | pronto via export completo | pronto | executado no PostgreSQL local | raw-only e raw-vs-SQL prontos, `0` findings |
| `automus` | pronto via export completo | pronto | executado no PostgreSQL local | raw-only e raw-vs-SQL prontos, `0` findings |

O inspetor de `inventory` aceita dois formatos de origem:

- JSON direto do caminho `estoqueGlobal`;
- export completo do Realtime Database contendo a chave raiz `estoqueGlobal`.

## Diretorios propostos

```text
scripts/migration/
  __init__.py
  config.py
  firebase_client.py
  sql_client.py
  transfer_engine.py
  run_transfer.py
  extract_firebase.py
  inspect_firebase_export.py
  compare_firebase_sql.py
  domains/
    __init__.py
    cooperat.py
    inventory.py
    users.py
    counting.py
    labels.py
    dashboard.py
    occurrences.py
    chat.py
    automus.py
  reports/
```

Arquivos de saida por execucao:

```text
_migration_runs/
  2026-06-27_070000/
    manifest.json
    raw/
      estoqueGlobal.json
      usuarios.json
      contagens.json
    reports/
      inventory.md
      cooperat.md
      summary.json
```

`_migration_runs/` deve ficar fora do Git.

## Configuracao

Variaveis esperadas:

```text
FIREBASE_API_KEY=
FIREBASE_DATABASE_URL=
FIREBASE_EMAIL=
FIREBASE_PASSWORD=
DATABASE_URL=postgresql://dark_jutsu:dark_jutsu_dev@localhost:5432/dark_jutsu
MIGRATION_RUN_DIR=_migration_runs
```

Tambem deve aceitar argumentos CLI:

```powershell
python scripts/migration/run_transfer.py transfer --domain cooperat --mode dry-run
python scripts/migration/run_transfer.py transfer --domain cooperat --mode apply
python scripts/migration/run_transfer.py transfer --domain inventory --source _migration_runs/.../raw/estoqueGlobal.json --mode dry-run
```

## Controle de execucao

Cada execucao cria uma linha em `import_runs`:

- `source`: dominio ou caminho Firebase.
- `source_path`: caminho Firebase ou arquivo local.
- `source_hash`: hash SHA-256 do JSON bruto.
- `started_at`, `finished_at`.
- `status`: `running`, `dry_run_ok`, `applied`, `failed`, `rolled_back`.
- `totals`: contagens por entidade.
- `raw_metadata`: versoes, opcoes e arquivos gerados.

Dominios grandes tambem podem usar tabelas especificas:

- Cooperat: `cooperat_import_runs`.
- Estoque: `inventory_snapshots`.

## Idempotencia

O motor deve poder rodar mais de uma vez sem duplicar dados.

Regras:

- Usar chaves naturais/legadas sempre que existirem.
- Usar `upsert` em dados de estado atual.
- Usar `legacy_path` ou `legacy_key` para registros vindos do Firebase.
- Eventos historicos devem ter chave de deduplicacao quando possivel.
- Toda carga deve armazenar `import_run_id` ou `source`.

Exemplos:

- `cooperat_purchase_codes.code`: upsert por codigo.
- `cooperat_purchase_events`: deduplicar por `(code, requisition, event_date, description, requested_qty, supplied_qty, low_value)`.
- `inventory_items.legacy_key`: upsert por chave calculada do item.
- `counting_sessions.legacy_path`: upsert por caminho completo `contagens/data/usuario/pushId`.
- `label_print_jobs.legacy_path`: upsert por caminho completo.
- `occurrences.id`: upsert por `id`.
- `chat_messages(room_id, legacy_key)`: upsert por sala + pushId.

## Checkpoints

O motor deve registrar checkpoints por dominio:

```json
{
  "run_id": "...",
  "domain": "inventory",
  "steps": {
    "extract": "ok",
    "inspect": "ok",
    "transform": "ok",
    "load": "ok",
    "validate": "ok"
  },
  "last_successful_entity": "inventory_balance_history"
}
```

Para dominios grandes, usar lote:

- Cooperat: lote por codigo.
- Estoque: lote por itens e depois historico.
- Contagens: lote por data.
- Chat: lote por sala.

## Ordem de transferencia

### Fase 0: base de referencia

1. Exportar snapshot bruto de todos os caminhos.
2. Calcular hash por arquivo.
3. Rodar inventario e gerar relatorio.
4. Nao gravar SQL ainda.

### Fase 1: piloto historico

1. `historicoComprasCooperat`
2. Validar:
   - total de codigos;
   - total de eventos;
   - amostras por codigo;
   - maior codigo/eventos.

Motivo: e grande, importante e pouco concorrente.

### Fase 2: estoque base

1. `estoqueGlobal/dados`
2. `estoqueGlobal/dadosMortos`
3. `estoqueGlobal/ajustesItens`
4. `estoqueGlobal/historicoSaldo`
5. `estoqueGlobal/movimentacoesMata185`
6. `estoqueGlobal/configContagem`
7. `estoqueGlobal/configuracoesEtiquetas`
8. `estoqueGlobalBackups/automus_last`

Validar dashboard contra Firebase antes de cortar leitura.

### Fase 3: usuarios e permissoes

1. `usuarios`
2. `usuariosBanidos`
3. `solicitacoesCadastro`
4. indices `nicknames*` apenas como validacao, nao como tabela final.

Firebase Auth pode continuar ativo nesta fase. A API valida token e cruza com tabela `users`.

### Fase 4: dashboard e avaliador

1. `dashboardConfig/paineis`
2. `dashboardConfig/avaliadorPedidos`
3. `dashboardConfig/ocorrenciasCampos`
4. `dashboardConfig/ocorrenciasAvaliadorSenha`

### Fase 5: contagens e etiquetas

1. `contagens`
2. `contagemRascunhos`
3. `contagemAtual`
4. `contagemStatusMaquinas`
5. `contagemControle`
6. `etiquetasGeradas`
7. `rankingEtiquetas`

Historico finalizado vai para SQL. Dados vivos podem ir para SQL no primeiro momento, mas o plano ideal e mover presenca/typing para cache depois.

### Fase 6: ocorrencias

1. `ocorrencias`
2. `chatGlobal/ocorrencias`
3. deduplicar por `id`
4. importar `historico` para `occurrence_history`

### Fase 7: chat

1. `chatRooms/*/messages`
2. `chatRooms/*/senha`
3. `chatReadState`
4. ignorar ou expirar `chatRooms/*/typing`

### Fase 8: Automus

1. `automus/releases`
2. `version.json`/manifestos locais

## Contrato por dominio

Cada dominio deve implementar esta interface conceitual:

```python
class DomainTransfer:
    name: str
    firebase_paths: list[str]

    def extract(self, firebase, run_dir) -> list[RawArtifact]: ...
    def inspect(self, artifacts) -> InspectionResult: ...
    def transform(self, artifacts) -> TransformResult: ...
    def load(self, sql, transformed, mode) -> LoadResult: ...
    def validate(self, sql, artifacts, load_result) -> ValidationResult: ...
```

## Transformacoes principais

### Timestamps

Firebase usa milissegundos em muitos campos. Converter para `timestamptz`.

Regra:

- inteiro maior que `100000000000`: tratar como epoch milliseconds.
- string ISO: parse direto.
- `dataBr`: manter como label se nao houver ISO confiavel.

### Chaves Firebase

Guardar sempre:

- `legacy_key`: chave local do mapa.
- `legacy_path`: caminho completo quando houver.
- `raw_data`: JSON original.

### Senhas e segredos

Durante transferencia:

- `usuarios.senha` e `senhaAntiga`: nao expor em relatorios.
- `solicitacoesCadastro.senha`: migrar somente se ainda for necessario para aprovar solicitacao pendente; marcar como legado.
- `chatRooms/*/senha`: transformar em hash antes de gravar `chat_rooms.password_hash`.
- `dashboardConfig/ocorrenciasAvaliadorSenha`: transformar em hash ou migrar como segredo controlado pela API.

## Validacao

Validacoes globais:

- JSON bruto tem hash salvo.
- Quantidade de registros por caminho bate com SQL.
- Amostras deterministicas batem por chave.
- Campos obrigatorios nao nulos.
- Sem duplicidade nas chaves esperadas.
- Relatorio gerado por dominio.

Validacoes por dominio:

| Dominio | Validacao minima |
| --- | --- |
| Cooperat | codigos, eventos, soma por codigo, amostra de eventos |
| Estoque | itens ativos, mortos, enderecos, ajustes, historico por item |
| Usuarios | usuarios ativos/inativos, roles, banidos, solicitacoes pendentes |
| Contagem | sessoes por data, itens contados, verificacoes vazias |
| Etiquetas | eventos por data/usuario, ranking recalculado |
| Dashboard | paineis e avaliacoes por codigo |
| Ocorrencias | total primario + fallback deduplicado, historico por ocorrencia |
| Chat | mensagens por sala, read state por usuario |

## Rollback

Antes de cada `apply`:

1. Registrar `import_runs`.
2. Criar snapshot SQL logico do dominio afetado ou usar transacao unica quando possivel.
3. Para cargas grandes, usar tabelas staging e promover ao final.

Estrategias:

- Cooperat: apagar por `import_run_id` e restaurar import anterior.
- Estoque: usar `inventory_snapshots` + transacao por bloco.
- Contagens/chat/ocorrencias: upsert idempotente; rollback por `import_run_id` quando gravado.

## Escrita dupla temporaria

Para dominios criticos, durante transicao:

- API grava SQL.
- API opcionalmente grava Firebase.
- Comparador roda por alguns dias.
- Quando bater, Firebase passa para somente leitura.

Dominios recomendados para escrita dupla:

- `estoqueGlobal`
- `contagens`
- `dashboardConfig/avaliadorPedidos`
- `ocorrencias`

Dominios que podem ter corte unico:

- `historicoComprasCooperat`
- `etiquetasGeradas`
- `rankingEtiquetas`
- `automus/releases`

## CLI proposta

```powershell
# baixa dados
python scripts/migration/extract_firebase.py --run-id firebase_export_initial

# baixa apenas estoqueGlobal
python scripts/migration/extract_firebase.py --run-id firebase_inventory_initial --path estoqueGlobal

# dry-run Cooperat
python scripts/migration/run_transfer.py transfer --domain cooperat --mode dry-run

# inventario do estoqueGlobal exportado
python scripts/migration/run_transfer.py inspect --domain inventory --run-id firebase_inventory_initial --source _migration_runs/firebase_inventory_initial/raw/estoqueGlobal.json

# aplica Cooperat
python scripts/migration/run_transfer.py transfer --domain cooperat --mode apply

# compara
python scripts/migration/run_transfer.py compare --domain cooperat --run latest
```

## Primeiro incremento implementavel

1. Criar `scripts/migration/config.py`.
2. Criar cliente Firebase REST com login por email/senha.
3. Criar cliente SQL com `psycopg`.
4. Implementar dominio `cooperat`.
5. Rodar `dry-run` no `data/historico_cooperat_antigo.json`.
6. Gravar `cooperat_import_runs`, `cooperat_purchase_codes`, `cooperat_purchase_events`.
7. Validar 10.125 codigos e 212.339 eventos.

## Resultado inicial

Primeiro dry-run executado em `2026-06-29` com:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py inspect --domain cooperat --run-id initial_cooperat_dry_run --sample-size 25
```

Resultado:

- `run_dir`: `_migration_runs/initial_cooperat_dry_run`
- `source`: `data/historico_cooperat_antigo.json`
- `source_hash`: `ca708c12ff4c3852541baac824ac2a5f1bb3acdd131ffdbfeeb6374676521744`
- codigos declarados: `10125`
- codigos contados: `10125`
- eventos declarados: `212339`
- eventos contados: `212339`
- maior volume por codigo: `3822` eventos no codigo `62855`
- status: `ok`

Arquivos gerados:

- `_migration_runs/initial_cooperat_dry_run/manifest.json`
- `_migration_runs/initial_cooperat_dry_run/raw/historicoComprasCooperat.json`
- `_migration_runs/initial_cooperat_dry_run/reports/cooperat-summary.json`
- `_migration_runs/initial_cooperat_dry_run/reports/cooperat-summary.md`

## Resultado SQL local

PostgreSQL local portatil configurado em `2026-06-29`:

- binarios: `C:\Users\Davi.souza\Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql`
- host: `127.0.0.1`
- porta: `5433`
- database: `dark_jutsu`
- usuario local: `dark_jutsu`
- schema aplicado: `36` tabelas, migrations `001_schema` e `002_security`
- seguranca aplicada: `63` policies RLS

Carga Cooperat executada:

```powershell
$env:DATABASE_URL='postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu'
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain cooperat --mode apply --run-id cooperat_apply_local_initial --sample-size 25
```

Resultado:

- `run_id`: `cooperat_apply_local_initial`
- `import_run_id`: `a608e8ba-a9c5-4298-b629-9bba5178b6d2`
- codigos carregados: `10125`
- eventos carregados: `212339`
- hash fonte: `ca708c12ff4c3852541baac824ac2a5f1bb3acdd131ffdbfeeb6374676521744`

Integridade pos-migracao:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain cooperat --run-id cooperat_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

Resultado:

- modo: `raw-vs-sql`
- findings: `0`
- status: `ok`

## Resultado inventory real

Primeiro inventario executado sobre o export completo do Firebase:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py inspect --domain inventory --run-id firebase_inventory_export_20260629 --source 'C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json' --sample-size 30
```

Resultado:

- `run_id`: `firebase_inventory_export_20260629`
- arquivo fonte: `C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json`
- hash fonte: `13d5e3882ea394a8e4c28cc7533919ef54546b9d9d2b772a71c8ad86ca9b622e`
- itens ativos: `7681`
- itens mortos: `131`
- ajustes: `3`
- chaves de historico de saldo: `1256`
- eventos de historico de saldo: `5562`
- chaves MATA185: `4`
- `configContagem`: presente
- `configuracoesEtiquetas`: ausente dentro de `estoqueGlobal` neste export

Arquivos gerados:

- `_migration_runs/firebase_inventory_export_20260629/raw/estoqueGlobal.json`
- `_migration_runs/firebase_inventory_export_20260629/manifest-inventory.json`
- `_migration_runs/firebase_inventory_export_20260629/reports/inventory-summary.json`
- `_migration_runs/firebase_inventory_export_20260629/reports/inventory-summary.md`

## Resultado inventory SQL local

Carga executada:

```powershell
$env:DATABASE_URL='postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu'
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain inventory --mode apply --run-id inventory_apply_local_initial --source 'C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json' --sample-size 30
```

Resultado:

- `run_id`: `inventory_apply_local_initial`
- `snapshot_id`: `bb45cb90-a26f-4ff2-8f76-ab740e04c6ee`
- itens ativos carregados: `7681`
- itens mortos carregados: `131`
- enderecos carregados: `44548`
- limites Cooperat carregados: `6191`
- ajustes carregados: `3`
- eventos de historico de saldo carregados: `5562`
- snapshot raw de `movimentacoesMata185`: `1`

Integridade pos-migracao:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain inventory --run-id inventory_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

Resultado:

- modo: `raw-vs-sql`
- findings: `0`
- status: `ok`

## Resultado users SQL local

Carga executada:

```powershell
$env:DATABASE_URL='postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu'
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain users --mode apply --run-id users_apply_local_initial --source 'C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json' --sample-size 20
```

Resultado:

- `run_id`: `users_apply_local_initial`
- usuarios carregados: `25`
- usuarios banidos carregados: `12`
- solicitacoes carregadas: `47`
- `solicitacoesCadastro`: `30`
- `solicitaçõesCadastro`: `17`
- senhas puras em `signup_requests.password_plain_legacy`: `0`
- senhas legadas nao sanitizadas em `users.raw_data`: `0`
- senhas nao sanitizadas em `signup_requests.raw_data`: `0`

Integridade pos-migracao:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain users --run-id users_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

Resultado:

- modo: `raw-vs-sql`
- findings: `0`
- status: `ok`

## Resultado dashboard SQL local

Carga executada:

```powershell
$env:DATABASE_URL='postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu'
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain dashboard --mode apply --run-id dashboard_apply_local_initial --source 'C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json' --sample-size 20
```

Resultado:

- `run_id`: `dashboard_apply_local_initial`
- `dashboard_panels`: `5`
- `purchase_evaluations`: `11`
- `app_settings`: `1`
- configuracao carregada: `occurrences.fields`

Integridade pos-migracao:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain dashboard --run-id dashboard_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

Resultado:

- modo: `raw-vs-sql`
- findings: `0`
- status: `ok`

## Resultado counting SQL local

Carga executada:

```powershell
$env:DATABASE_URL='postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu'
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain counting --mode apply --run-id counting_apply_local_initial --source 'C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json' --sample-size 20
```

Resultado:

- `run_id`: `counting_apply_local_initial`
- `counting_sessions`: `20`
- `counting_items`: `3557`
- `counting_empty_checks`: `410`
- `counting_drafts`: `1`
- `counting_machine_status`: `16`
- `label_print_jobs`: `20`
- `label_user_ranking`: `0`, ausente no export

Integridade pos-migracao:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain counting --run-id counting_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

Resultado:

- modo: `raw-vs-sql`
- findings: `0`
- status: `ok`

## Resultado occurrences SQL local

Carga executada:

```powershell
$env:DATABASE_URL='postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu'
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain occurrences --mode apply --run-id occurrences_apply_local_initial --source 'C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json' --sample-size 20
```

Resultado:

- `run_id`: `occurrences_apply_local_initial`
- `occurrences`: `7`
- `occurrence_history`: `11`
- fallback `chatGlobal/ocorrencias`: `0`, ausente neste export

Integridade pos-migracao:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain occurrences --run-id occurrences_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

Resultado:

- modo: `raw-vs-sql`
- findings: `0`
- status: `ok`

## Resultado chat SQL local

Carga executada:

```powershell
$env:DATABASE_URL='postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu'
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain chat --mode apply --run-id chat_apply_local_initial --source 'C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json' --sample-size 20
```

Resultado:

- `run_id`: `chat_apply_local_initial`
- `chat_rooms`: `4`, incluindo a sala legada sintetica `chatGlobal`
- `chat_messages`: `227`
- `chat_read_states`: `14`
- salas privadas com senha migrada para hash: `2`
- mensagens legadas de `chatGlobal`: `100`
- senhas em texto aberto em `chat_rooms.raw_data`: `0`

Integridade pos-migracao:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain chat --run-id chat_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

Resultado:

- modo: `raw-vs-sql`
- findings: `0`
- status: `ok`

## Resultado Automus SQL local

Carga executada:

```powershell
$env:DATABASE_URL='postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu'
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\run_transfer.py transfer --domain automus --mode apply --run-id automus_apply_local_initial --source 'C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json' --sample-size 20
```

Resultado:

- `run_id`: `automus_apply_local_initial`
- `automus_releases`: `1`
- canal carregado: `latest`
- versao: `1.1.1`
- manifesto com `sha256`: `1`

Integridade pos-migracao:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain automus --run-id automus_apply_local_initial --database-url $env:DATABASE_URL --fail-on high
```

Resultado:

- modo: `raw-vs-sql`
- findings: `0`
- status: `ok`

## Criterio de pronto do motor

- Roda em modo `dry-run` e `apply`.
- Salva raw JSON e hash.
- Grava `import_runs`.
- E idempotente.
- Gera relatorio por dominio.
- Rejeita carga se validacao falhar.
- Nao imprime segredos.
- Usa `app.role='service'` no SQL.
- Permite retomar lote grande sem duplicar dados.

## Integracao API/frontend

A migracao dos dados do export Firebase para SQL esta completa no ambiente local. A etapa seguinte e trocar consumidores para a API SQL.

Documento de acompanhamento:

- [sql-integration-gap-analysis.md](sql-integration-gap-analysis.md)
