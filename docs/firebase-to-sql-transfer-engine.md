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
python scripts/migration/run_transfer.py --domain cooperat --mode dry-run
python scripts/migration/run_transfer.py --domain cooperat --mode apply
python scripts/migration/run_transfer.py --domain inventory --from-file _migration_runs/.../raw/estoqueGlobal.json --mode apply
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
python scripts/migration/run_transfer.py extract --domain all

# inspeciona ultimo export
python scripts/migration/run_transfer.py inspect --run latest

# dry-run Cooperat
python scripts/migration/run_transfer.py transfer --domain cooperat --mode dry-run

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
