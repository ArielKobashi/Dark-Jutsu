# Verificador de integridade pos-migracao

## Objetivo

Validar que os dados migrados do Firebase para SQL ficaram completos, consistentes e rastreaveis antes de desligar ou colocar o Firebase em somente leitura.

O verificador deve comparar:

- export bruto Firebase;
- dados carregados no PostgreSQL;
- relatorios de `import_runs`;
- amostras deterministicas por dominio.

## Principios

- Nunca alterar dados.
- Nao imprimir segredos.
- Rodar varias vezes com o mesmo resultado.
- Sair com codigo diferente de zero quando houver divergencia critica.
- Gerar relatorio legivel para decisao humana.

## Arquitetura

```text
raw Firebase export
  -> normalizadores por dominio
    -> contadores/checksums/amostras
      -> consultas SQL equivalentes
        -> comparador
          -> relatorio Markdown + JSON
```

## Diretorios propostos

```text
scripts/migration/
  integrity_check.py
  integrity/
    __init__.py
    base.py
    cooperat.py
    inventory.py
    users.py
    counting.py
    labels.py
    dashboard.py
    occurrences.py
    chat.py
    automus.py
```

Saidas:

```text
_migration_runs/<run_id>/reports/integrity-summary.md
_migration_runs/<run_id>/reports/integrity-summary.json
_migration_runs/<run_id>/reports/integrity-differences.jsonl
```

## Niveis de severidade

| Severidade | Significado | Acao |
| --- | --- | --- |
| `critical` | perda de dados, total divergente, chave ausente, checksum diferente em entidade essencial | bloquear corte |
| `high` | campo importante divergente, relacao quebrada, duplicidade | revisar antes do corte |
| `medium` | divergencia em campo derivado/recalculavel | pode corrigir por script |
| `low` | diferenca esperada de formato, acento, label ou dado transitorio | documentar |

## Comando proposto

```powershell
python scripts/migration/integrity_check.py --run latest --domain all
python scripts/migration/integrity_check.py --run 2026-06-27_070000 --domain cooperat
python scripts/migration/integrity_check.py --raw _migration_runs/latest/raw --database-url $env:DATABASE_URL
```

Flags:

| Flag | Uso |
| --- | --- |
| `--run` | usa uma execucao em `_migration_runs` |
| `--raw` | aponta para pasta de JSON bruto |
| `--domain` | `all`, `cooperat`, `inventory`, `users`, etc. |
| `--sample-size` | tamanho da amostra deterministica por dominio |
| `--fail-on` | severidade minima que gera exit code `1`; padrao `high` |
| `--json` | imprime resumo JSON no stdout |

## Validacoes globais

1. `import_runs.source_hash` bate com hash do arquivo raw.
2. Todos os caminhos esperados existem no export ou estao marcados como ausentes.
3. Cada dominio aplicado tem `status='applied'`.
4. Tabelas SQL esperadas existem.
5. RLS e migrations de seguranca existem: `001_schema`, `002_security`.
6. Nenhum relatorio contem senhas, tokens ou secrets.

## Validacoes por dominio

### Cooperat

Fonte:

- `historicoComprasCooperat.json`
- `data/historico_cooperat_antigo.json`, quando usado como fallback raw.

SQL:

- `cooperat_import_runs`
- `cooperat_purchase_codes`
- `cooperat_purchase_events`

Checks:

- total de codigos Firebase == `count(*) cooperat_purchase_codes`.
- total de eventos Firebase == `count(*) cooperat_purchase_events`.
- `sum(total_events)` por codigo bate com eventos carregados.
- amostra por codigo compara:
  - `codigo`;
  - `descricaoMaisRecente`;
  - `totalEventos`;
  - `primeiraData`;
  - `ultimaData`;
  - medias e totais principais.
- amostra por evento compara:
  - `requisicao`;
  - `data`;
  - `descricao`;
  - `unidade`;
  - quantidades;
  - `valorBaixa`.

Severidade:

- total de eventos divergente: `critical`.
- evento ausente em amostra: `critical`.
- media divergente mas eventos corretos: `medium`.

### Estoque

Fonte:

- `estoqueGlobal.json`

SQL:

- `inventory_items`
- `inventory_item_addresses`
- `inventory_adjustments`
- `inventory_balance_history`
- `inventory_movements`
- `app_settings`
- `inventory_snapshots`

Checks:

- `dados.length` == itens ativos SQL.
- `dadosMortos.length` == itens mortos SQL.
- quantidade de enderecos por item em amostra.
- saldo por item em amostra.
- min/max/reposicao e origem em amostra.
- quantidade de ajustes.
- quantidade de chaves em `historicoSaldo`.
- quantidade total de eventos de historico.
- metadados `ultimaAtualizacao` e `atualizadoPor` preservados em snapshot/settings.

Severidade:

- item ativo ausente: `critical`.
- saldo divergente: `high`.
- ajuste manual ausente: `critical`.
- historico de saldo parcial: `high`.
- label/metadado divergente: `low`.

### Usuarios e cadastro

Fonte:

- `usuarios.json`
- `solicitacoesCadastro.json`
- `usuariosBanidos.json`
- `nicknames*.json` como validacao auxiliar.

SQL:

- `users`
- `signup_requests`
- `banned_users`

Checks:

- total de usuarios.
- total por role.
- total ativos/inativos.
- total solicitacoes por status.
- total banidos.
- nicknames ativos nao duplicados no SQL.
- solicitacoes pendentes preservam `nickname`, `cracha`, `setor`, `status`.

Severidade:

- usuario ausente: `critical`.
- role divergente: `high`.
- senha legada exposta em view segura: `critical`.
- indice nickname diferente mas dados centrais corretos: `medium`.

### Dashboard e avaliador

Fonte:

- `dashboardConfig/paineis`
- `dashboardConfig/avaliadorPedidos`
- `dashboardConfig/ocorrenciasCampos`
- `dashboardConfig/ocorrenciasAvaliadorSenha`

SQL:

- `dashboard_panels`
- `purchase_evaluations`
- `app_settings`

Checks:

- total paineis.
- total avaliacoes.
- amostra por codigo avaliado.
- configuracoes em `app_settings`.
- senha do avaliador nao aparece em texto puro.

### Contagens

Fonte:

- `contagens`
- `contagemRascunhos`
- `contagemAtual`
- `contagemStatusMaquinas`
- `contagemControle`

SQL:

- `counting_sessions`
- `counting_items`
- `counting_empty_checks`
- `counting_drafts`
- `counting_machine_status`
- `counting_control_events`

Checks:

- sessoes por data/usuario.
- itens contados por sessao.
- verificacoes vazias por sessao.
- rascunhos por uid.
- status por ciclo/maquina/usuario.
- divergencias calculadas batem quando saldo e contado existem.

Severidade:

- sessao finalizada ausente: `critical`.
- item contado ausente: `high`.
- rascunho ausente: `medium`, se houver corte planejado.
- presenca antiga ausente: `low`.

### Etiquetas

Fonte:

- `etiquetasGeradas`
- `rankingEtiquetas`
- fallback em `contagens/*/*/_etiquetas`

SQL:

- `label_print_jobs`
- `label_user_ranking`
- `v_label_user_ranking`

Checks:

- total eventos.
- total etiquetas por usuario.
- ranking recalculado bate com agregado ou explica diferenca.
- eventos fallback foram incorporados.

### Ocorrencias

Fonte:

- `ocorrencias`
- `chatGlobal/ocorrencias`

SQL:

- `occurrences`
- `occurrence_history`

Checks:

- total deduplicado por `id`.
- status e gravidade por amostra.
- historico por ocorrencia.
- tratativas/documentos preservados.
- origem `source_path` correta.

### Chat

Fonte:

- `chatRooms`
- `chatReadState`

SQL:

- `chat_rooms`
- `chat_messages`
- `chat_read_states`

Checks:

- salas esperadas existem.
- total mensagens por sala.
- amostra de mensagens por sala.
- read states por usuario/sala.
- senha de sala nao foi gravada em texto puro.
- `typing` ignorado ou marcado como transitorio.

### Automus

Fonte:

- `automus/releases`
- manifestos locais `version.json`/`latest.json`

SQL:

- `automus_releases`

Checks:

- release latest existe.
- versao, URL e notas batem.
- pacote ZIP nao foi gravado no SQL.

## Checksums

Cada dominio deve gerar dois tipos de checksum.

### Checksum de conjunto

Ordenar registros por chave estavel, normalizar JSON e calcular SHA-256.

Exemplo conceitual:

```text
sha256(join("\n", [
  canonical_json(record_1),
  canonical_json(record_2)
]))
```

### Checksum de amostra

Amostra deterministica:

- ordenar chaves;
- pegar primeiro, ultimo e N itens por hash modular;
- comparar campo a campo.

Isso evita relatorio gigante e ainda detecta divergencias estruturais.

## Relatorio

Resumo Markdown:

```text
# Integridade pos-migracao

Run: 2026-06-27_070000
Status: failed
Maior severidade: critical

## Cooperat
- Firebase codigos: 10125
- SQL codigos: 10125
- Firebase eventos: 212339
- SQL eventos: 212339
- Status: ok

## Estoque
- Status: failed
- Critical: 2 itens ativos ausentes
```

JSON:

```json
{
  "run_id": "2026-06-27_070000",
  "status": "failed",
  "max_severity": "critical",
  "domains": {
    "cooperat": {
      "status": "ok",
      "checks": []
    }
  }
}
```

Differences JSONL:

```json
{"domain":"inventory","severity":"critical","key":"12345","field":"item","message":"Item ativo ausente no SQL"}
```

## Portao de corte

Firebase so deve ir para somente leitura quando:

- `cooperat`, `inventory`, `users`, `dashboard`, `counting`, `occurrences` estiverem sem `critical` e sem `high`.
- divergencias `medium` tiverem issue/plano de correcao.
- seguranca validada: RLS ativo, views seguras sem campos sensiveis e API sem acesso superuser.
- backup final salvo e testado.

## Esqueleto de implementacao

```python
@dataclass
class CheckResult:
    domain: str
    severity: str
    key: str
    field: str
    message: str
    firebase_value: Any = None
    sql_value: Any = None


class IntegrityChecker:
    domain: str

    def load_raw(self, run_dir: Path) -> Any:
        ...

    def load_sql_summary(self, conn) -> dict:
        ...

    def compare_counts(self, raw, sql) -> list[CheckResult]:
        ...

    def compare_samples(self, raw, conn) -> list[CheckResult]:
        ...

    def run(self, run_dir: Path, conn) -> list[CheckResult]:
        return [
            *self.compare_counts(...),
            *self.compare_samples(...),
        ]
```

## Primeiro incremento implementavel

1. Implementar `integrity/cooperat.py`.
2. Comparar:
   - total codigos;
   - total eventos;
   - 50 codigos por amostra deterministica;
   - 200 eventos por amostra deterministica.
3. Gerar `integrity-summary.md`.
4. Falhar com exit code `1` se houver divergencia `high` ou `critical`.

## Resultado inicial

Primeiro verificador Cooperat executado em modo raw-only em `2026-06-29`:

```powershell
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe scripts\migration\integrity_check.py --domain cooperat --run-id initial_cooperat_dry_run --fail-on high
```

Resultado:

- `run_dir`: `_migration_runs/initial_cooperat_dry_run`
- modo: `raw-only`
- findings: `0`
- severidade maxima: `ok`
- raw codes: `10125`
- raw events: `212339`

Arquivos gerados:

- `_migration_runs/initial_cooperat_dry_run/reports/integrity-cooperat.json`
- `_migration_runs/initial_cooperat_dry_run/reports/integrity-cooperat.md`
- `_migration_runs/initial_cooperat_dry_run/reports/integrity-differences.jsonl`

## Criterio de pronto

- Verificador roda contra um export raw e o PostgreSQL.
- Gera Markdown, JSON e JSONL.
- Nao imprime secrets.
- Exit code respeita `--fail-on`.
- Pelo menos Cooperat e Estoque possuem checks completos antes do primeiro corte real.
