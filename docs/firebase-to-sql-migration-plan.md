# Planejamento: migracao do Firebase para SQL

## Contexto atual

O Dark-Jutsu usa Firebase Auth e Firebase Realtime Database diretamente no frontend. Os principais pontos encontrados no codigo sao:

- `estoqueGlobal`: base principal de estoque, ajustes manuais, historico de saldo e configuracoes de contagem/etiquetas.
- `usuarios`, `solicitacoesCadastro`, `usuariosBanidos` e indices de nickname: cadastro, permissoes e administracao.
- `contagens`, `contagemAtual`, `contagemRascunhos`, `contagemStatusMaquinas` e `contagemControle`: fluxo de contagem de estoque.
- `etiquetasGeradas` e `rankingEtiquetas`: historico e ranking de etiquetas.
- `dashboardConfig`: configuracoes do dashboard, avaliador de pedidos, campos de ocorrencias e senha do avaliador.
- `historicoComprasCooperat`: base historica grande, com cerca de 10.125 codigos e 212.339 eventos no JSON local.
- `ocorrencias`: abertura e tratativa de ocorrencias.
- `chatGlobal`, `chatRooms` e `chatReadState`: mensagens, salas, senhas e leitura.
- `automus/releases`: manifestos de atualizacao do Automus.

Como hoje o app grava no Firebase direto pelo navegador, a migracao para SQL precisa introduzir uma API backend. O navegador nao deve falar diretamente com o banco SQL.

## Decisao inicial recomendada

Usar PostgreSQL como banco principal.

Motivos:

- Bom suporte a dados relacionais e historicos grandes.
- `jsonb` ajuda a migrar partes mais flexiveis sem travar o projeto em uma modelagem perfeita no primeiro dia.
- Indices, views e consultas agregadas vao beneficiar dashboard, historico Cooperat, contagens e avaliador.
- E facil evoluir depois para filas, auditoria e relatorios.

Alternativa aceitavel para comeco local: SQLite. Mas para uso compartilhado, multiusuario e dashboard, PostgreSQL e a escolha mais segura.

## Arquitetura alvo

1. Frontend HTML/JS continua existindo, mas troca chamadas Firebase por chamadas HTTP.
2. Backend API passa a concentrar autenticacao, regras de permissao e persistencia.
3. SQL guarda dados normalizados onde houver consulta frequente.
4. SQL guarda JSON bruto temporariamente onde a estrutura ainda muda muito.
5. Firebase fica em modo leitura durante uma etapa de transicao, ate a comparacao bater.

Fluxo alvo:

```text
index.html / dashboard.html / label-editor.html
  -> API HTTP
    -> PostgreSQL
```

## Estrategia de migracao

### Fase 1: Inventario e backup

- Exportar um snapshot completo do Realtime Database em JSON.
- Guardar o arquivo bruto com data/hora e hash.
- Medir tamanho dos principais nos: `estoqueGlobal`, `contagens`, `historicoComprasCooperat`, `chatRooms`, `ocorrencias`.
- Congelar uma lista oficial de caminhos que serao migrados.

Entrega:

- `firebase-export-YYYYMMDD.json`
- relatorio de contagem por no
- lista de caminhos mapeados para tabelas

### Fase 2: Modelo SQL inicial

Criar tabelas centrais primeiro:

- `users`
- `signup_requests`
- `banned_users`
- `inventory_items`
- `inventory_adjustments`
- `inventory_balance_history`
- `inventory_snapshots`
- `counting_sessions`
- `counting_records`
- `counting_drafts`
- `label_print_jobs`
- `label_user_ranking`
- `dashboard_panels`
- `purchase_evaluations`
- `cooperat_purchase_codes`
- `cooperat_purchase_events`
- `occurrences`
- `chat_rooms`
- `chat_messages`
- `chat_read_states`
- `app_settings`
- `automus_releases`

Para nos muito flexiveis, usar `jsonb` inicialmente:

- configuracao visual de etiquetas
- progresso parcial de contagem
- payload bruto de registros antigos
- historico de snapshots do estoque

### Fase 3: API backend

Endpoints iniciais por area:

- `GET /api/me`
- `GET /api/inventory`
- `PATCH /api/inventory/items/:code/adjustments`
- `POST /api/inventory/import`
- `GET /api/users`
- `PATCH /api/users/:id`
- `POST /api/users/:id/ban`
- `POST /api/users/:id/reset-password`
- `GET /api/signup-requests`
- `PATCH /api/signup-requests/:id`
- `POST /api/signup-requests/:id/approve`
- `DELETE /api/banned-users/:id`
- `GET /api/counting/sessions`
- `POST /api/counting/records`
- `GET /api/dashboard`
- `PATCH /api/dashboard/panels/:id`
- `GET /api/cooperat/history/:code`
- `GET /api/occurrences`
- `POST /api/occurrences`
- `GET /api/chat/rooms/:room/messages`
- `POST /api/chat/rooms/:room/messages`

No primeiro ciclo, a API pode aceitar payloads parecidos com os atuais para reduzir alteracoes no frontend.

Status em 2026-07-01:

- API local ja cobre leituras principais, dashboard, ocorrencias, chat, etiquetas e administracao inicial de usuarios/cadastro/banidos.
- `index.html` e `dashboard.html` ja tentam SQL primeiro em varios fluxos administrativos e mantem Firebase como fallback de transicao.
- A aprovacao de cadastro ainda depende do Firebase Auth para criar o `uid`; depois disso o SQL recebe `POST /api/signup-requests/:id/approve`.
- Contagens agora tem escrita SQL inicial para sessoes finalizadas, rascunhos, status de maquinas e reset global.
- Relatorio e historico de planilhas de contagem agora usam `GET /api/counting/history` primeiro, com fallback Firebase.
- Correcao de usuario no historico de contagem agora tenta `PATCH /api/counting/sessions/{sessionId}/user` antes do fallback Firebase.
- O editor de etiquetas salva/carrega a configuracao compartilhada em `app_settings` via `PUT /api/settings/label.config`.
- O publicador do Automus tenta gravar o manifesto em `automus_releases` via `PUT /api/automus/releases/latest`.
- O estoque do Automus agora tem `POST /api/inventory/automus-update`, testado com o export completo em 2026-07-09, gravando snapshot e recarregando itens/enderecos/limites/historico em SQL.
- Os scripts `Automus/scripts/atualizacao/automus_update.py` e `scripts/atualizacao/automus_update.py` passaram a tentar escrita SQL antes do Firebase; `AUTOMUS_SQL_ONLY=1` corta o fallback quando o teste operacional for aprovado.

### Fase 4: Migração de dados

Criar scripts idempotentes:

1. `export_firebase.py`: baixa o JSON completo ou por caminho.
2. `inspect_firebase_export.py`: conta registros e valida campos esperados.
3. `migrate_firebase_to_sql.py`: carrega no SQL com upsert.
4. `compare_firebase_sql.py`: compara totais, amostras e checksums.

Ordem sugerida:

1. `usuarios`, `usuariosBanidos`, `solicitacoesCadastro`
2. `estoqueGlobal`
3. `historicoComprasCooperat`
4. `dashboardConfig`
5. `contagens` e contagem em andamento
6. `etiquetasGeradas` e `rankingEtiquetas`
7. `ocorrencias`
8. `chatRooms`, `chatGlobal`, `chatReadState`
9. `automus/releases`

### Fase 5: Transicao sem parada brusca

Opcoes:

- Leitura dupla: frontend/API le do SQL e compara amostras com Firebase.
- Escrita dupla temporaria: API grava SQL e Firebase por alguns dias.
- Corte unico: congelar escrita no Firebase, migrar, validar e virar a chave.

Recomendacao: para estoque e contagem, usar escrita dupla temporaria. Para historico Cooperat, corte unico e suficiente porque e uma base historica.

### Fase 6: Desligamento do Firebase Database

- Deixar Firebase Auth ativo ou migrar autenticacao depois.
- Bloquear escrita no Realtime Database.
- Manter backup final.
- Remover chaves Firebase do frontend quando a API estiver cobrindo tudo.

## Modelo inicial de tabelas

### Usuarios

```sql
create table users (
  id text primary key,
  nickname text not null unique,
  badge text,
  sector text,
  role text not null default 'user',
  active boolean not null default true,
  password_status text,
  created_at timestamptz,
  updated_at timestamptz,
  raw_data jsonb not null default '{}'::jsonb
);
```

### Estoque

```sql
create table inventory_items (
  code text primary key,
  description text,
  warehouse text,
  address text,
  unit text,
  balance numeric,
  min_qty numeric,
  max_qty numeric,
  reorder_qty numeric,
  status text,
  source text,
  updated_at timestamptz,
  raw_data jsonb not null default '{}'::jsonb
);

create table inventory_adjustments (
  id bigserial primary key,
  item_code text not null references inventory_items(code),
  min_qty numeric,
  max_qty numeric,
  reorder_qty numeric,
  reason text,
  updated_by text references users(id),
  updated_at timestamptz not null default now(),
  raw_data jsonb not null default '{}'::jsonb
);

create table inventory_balance_history (
  id bigserial primary key,
  item_code text not null references inventory_items(code),
  event_at timestamptz,
  previous_balance numeric,
  current_balance numeric,
  delta numeric,
  source text,
  raw_data jsonb not null default '{}'::jsonb
);
```

### Historico Cooperat

```sql
create table cooperat_purchase_codes (
  code text primary key,
  latest_description text,
  total_events integer not null default 0,
  total_purchase_qty numeric,
  total_requested_qty numeric,
  total_supplied_qty numeric,
  total_low_value numeric,
  first_date date,
  last_date date,
  avg_purchase_qty numeric,
  avg_requested_qty numeric,
  avg_supplied_qty numeric,
  avg_low_value numeric
);

create table cooperat_purchase_events (
  id bigserial primary key,
  code text not null references cooperat_purchase_codes(code),
  requisition text,
  event_date date,
  description text,
  unit text,
  requested_qty numeric,
  supplied_qty numeric,
  low_value numeric,
  purchase_qty numeric,
  source text,
  origin text,
  raw_data jsonb not null default '{}'::jsonb
);

create index cooperat_purchase_events_code_date_idx
  on cooperat_purchase_events (code, event_date desc);
```

## Pontos de atencao

- O Realtime Database aceita estrutura aninhada e chaves dinamicas; SQL precisa decidir chaves primarias antes da carga.
- O app atual usa autenticacao Firebase no cliente. Se Firebase Auth continuar, a API deve validar ID token do Firebase.
- Regras de seguranca do Firebase precisam virar regras no backend, nao no frontend.
- `contagemAtual` e `chatRooms/typing` tem comportamento de tempo real. Em SQL puro, isso precisa de polling, WebSocket, SSE ou Redis.
- `estoqueGlobal` parece ser atualizado em blocos pelo Automus; essa rotina precisa virar endpoint/worker para nao expor banco no cliente.
- Senhas de salas/chat e campos sensiveis devem ser revisados antes de ir para SQL.

## Seguranca de dados

Medidas implementadas no ambiente SQL:

- `db/init/002_security.sql` cria roles sem login: `dark_jutsu_readonly`, `dark_jutsu_app` e `dark_jutsu_service`.
- Row Level Security foi habilitado nas tabelas de negocio.
- Policies usam contexto de sessao com `app.user_id` e `app.role`.
- Views seguras foram criadas para evitar exposicao direta de campos sensiveis: `v_users_safe`, `v_signup_requests_safe`, `v_chat_rooms_safe`.
- Tabelas de auditoria foram criadas: `audit_events` e `security_events`.
- `chat_rooms` guarda `password_hash`, nao senha pura.
- `signup_requests.password_plain_legacy` existe apenas para acomodar legado durante a transicao e nao deve ser exposto pela API.

Como a API deve operar:

```sql
set local app.user_id = '<uid-do-usuario>';
set local app.role = 'op'; -- op, mod, admin ou service
```

Regras de acesso planejadas:

- `op`: leitura operacional, criar contagens, etiquetas, chat e ocorrencias proprias.
- `mod`: pode tratar ocorrencias, alterar dashboard/avaliador e operar rotinas compartilhadas.
- `admin`: administra usuarios, solicitacoes, bloqueios, configuracoes e relatorios sensiveis.
- `service`: usado por migradores, Automus e rotinas de carga. Deve ser restrito a servidores/scripts confiaveis.

Cuidados obrigatorios antes de producao:

- A API nao deve conectar no banco com owner/superuser, porque dono de tabela pode contornar RLS.
- Criar usuarios PostgreSQL de login separados e conceder apenas uma role operacional.
- Validar ID token do Firebase no backend enquanto Firebase Auth continuar ativo.
- Nao gravar senha de usuario em texto puro; migrar `senha`, `senhaAntiga` e `senhaReset` para flags/fluxo de reset seguro.
- Converter senhas de salas privadas para hash com salt.
- Guardar segredos em `.env`/secret manager, nunca em HTML ou arquivos versionados.
- Registrar em `audit_events` toda acao administrativa, importacao, update Automus, alteracao de ajuste e alteracao de usuario.
- Registrar em `security_events` falhas de login, permissao negada, importacao rejeitada e divergencia de checksum.
- Fazer backup antes de cada carga grande e manter hash do snapshot Firebase/SQL.
- Aplicar retencao para dados transitorios: typing, presenca de contagem e rascunhos antigos.
- Mascarar ou omitir campos sensiveis em dumps de suporte.

## Mapeamento de dados Firebase -> SQL

Para a matriz direta endereco Firebase -> arquivo raiz -> destino SQL/API, use tambem:

- [firebase-address-traceability.md](firebase-address-traceability.md)
- [firebase-to-sql-transfer-engine.md](firebase-to-sql-transfer-engine.md)
- [post-migration-integrity-checker.md](post-migration-integrity-checker.md)
- [sql-integration-gap-analysis.md](sql-integration-gap-analysis.md)

### Resumo por caminho

| Caminho Firebase | Formato atual | Destino SQL sugerido | Prioridade | Observacoes |
| --- | --- | --- | --- | --- |
| `estoqueGlobal` | objeto raiz com listas, mapas e metadados | varias tabelas de estoque + `app_settings` | P0 | Principal base do sistema. Hoje e lido por `index.html`, `dashboard.html` e atualizado pelo Automus. |
| `estoqueGlobal/dados` | array de itens ativos | `inventory_items`, `inventory_item_addresses` | P0 | Cada item tem codigos Protheus/Cooperat, descricao, saldo, endereco principal e lista de enderecos. |
| `estoqueGlobal/dadosMortos` | array de itens inativos/mortos | `inventory_items` com `is_dead=true` | P1 | Mesmo formato de item, mas pode usar `protheusKey="MORTO|codigo"`. |
| `estoqueGlobal/ajustesItens` | mapa por chave codificada | `inventory_adjustments` + campos atuais em `inventory_items` | P0 | Ajustes manuais vencem limites de planilha e sugestao automatica. |
| `estoqueGlobal/historicoSaldo` | mapa `itemKey -> eventos[]` | `inventory_balance_history` | P0 | Usado para consumo, sugestao de minimo/maximo e dashboard. |
| `estoqueGlobal/movimentacoesMata185` | objeto com lote atual e lotes | `inventory_movements` ou `inventory_mata185_batches` | P1 | Gerado pelo Automus quando existe `mata185.xlsx`. |
| `estoqueGlobal/configuracoesEtiquetas` | objeto de layout | `app_settings` ou `label_layout_configs` com `jsonb` | P2 | Compartilhado com `label-editor.html`. |
| `estoqueGlobal/configContagem` | objeto de configuracao | `app_settings` com `jsonb` | P1 | Configura o fluxo de contagem. |
| `estoqueGlobalBackups/automus_last` | backup bruto | `inventory_snapshots` | P1 | Importante para rollback. Pode guardar JSON bruto comprimido. |
| `usuarios` | mapa `uid -> usuario` | `users` | P0 | Permissao e perfil do app. |
| `solicitacoesCadastro` | mapa de solicitacoes | `signup_requests` | P1 | Cadastro pendente antes de criar usuario Auth. |
| `usuariosBanidos` | mapa `uid -> dados` | `banned_users` | P1 | Bloqueios e historico basico de banimento. |
| `nicknamesSimple`, `nicknamesAuth`, `nicknamesSolic`, `nicknamesSolicCracha` | indices auxiliares | indices SQL/constraints ou views | P2 | Em SQL viram `unique`, consultas e constraints, nao precisam migrar como tabelas principais. |
| `contagens` | `data -> usuario -> registro` | `counting_sessions`, `counting_items`, `counting_empty_checks`, `label_print_jobs` | P0 | Guarda contagens finalizadas e fallback de etiquetas em `_etiquetas`. |
| `contagemAtual` | `ciclo -> usuarios -> rascunho/progresso` | `counting_live_sessions` + `counting_drafts` | P1 | Dado vivo. Pode ficar em Redis/WebSocket depois; em SQL precisa TTL/limpeza. |
| `contagemRascunhos` | `uid -> rascunho` | `counting_drafts` | P1 | Backup remoto do rascunho local. |
| `contagemStatusMaquinas` | `ciclo -> maquina -> usuario -> status` | `counting_machine_status` | P1 | Presenca/progresso em tempo real. |
| `contagemControle/resetGlobal` | objeto de controle | `counting_control_events` | P1 | Evento administrativo para zerar ciclo. |
| `etiquetasGeradas` | `data -> usuario -> eventos` | `label_print_jobs` | P2 | Historico de geracao de etiquetas. |
| `rankingEtiquetas` | `usuario -> agregado` | view/materialized view ou `label_user_ranking` | P2 | Pode ser calculado por query a partir de eventos. |
| `dashboardConfig/paineis` | `painel -> config` | `dashboard_panels` | P1 | Limite e codigos ocultos por painel. |
| `dashboardConfig/avaliadorPedidos` | `codigoKey -> avaliacao` | `purchase_evaluations` | P0 | Base do avaliador/kanban de compras. |
| `dashboardConfig/ocorrenciasCampos` | objeto de listas | `app_settings` com `jsonb` | P2 | Configuracao de tipos, gravidades, status e setores. |
| `dashboardConfig/ocorrenciasAvaliadorSenha` | objeto com senha e auditoria | `app_settings` ou `occurrence_settings` | P2 | Revisar armazenamento, idealmente hash em vez de texto puro. |
| `historicoComprasCooperat` | objeto grande por codigo | `cooperat_purchase_codes`, `cooperat_purchase_events`, `cooperat_import_runs` | P0 | Base historica grande e boa candidata a piloto da migracao. |
| `ocorrencias` | `id -> ocorrencia` | `occurrences`, `occurrence_history` | P1 | Tem fallback legado em `chatGlobal/ocorrencias`. |
| `chatGlobal/ocorrencias` | fallback de ocorrencias | importar para `occurrences` com `source='fallback'` | P2 | Migrar somente se existir no export real. |
| `chatRooms` | salas, senhas, mensagens, digitacao | `chat_rooms`, `chat_messages`; typing fora do SQL ou tabela TTL | P2 | `typing` e tempo real pedem WebSocket/Redis/SSE. |
| `chatReadState` | `uid -> room -> timestamp` | `chat_read_states` | P2 | Simples e relacional. |
| `chatGlobal` | legado/misto | avaliar no export | P3 | Hoje aparece principalmente como fallback para ocorrencias. |
| `automus/releases` | manifests de atualizacao | `automus_releases` | P2 | Pequeno e administrativo. |

### Campos de estoque

Formato inferido de `estoqueGlobal/dados` e `dadosMortos`:

| Campo Firebase | Tipo | SQL sugerido | Observacao |
| --- | --- | --- | --- |
| `protheus` | texto | `inventory_items.protheus_code` | Codigo principal atual. |
| `protheusKey` | texto | `inventory_items.protheus_key` | Pode aparecer em mortos ou chaves especiais. |
| `cooperat` | texto | `inventory_items.cooperat_code` | Codigo antigo/Cooperat. |
| `descricao` | texto | `inventory_items.description` | Descricao do item. |
| `enderecoPrincipal` | texto | `inventory_items.primary_address` | Endereco selecionado para exibicao. |
| `armazemPrincipal` | texto | `inventory_items.primary_warehouse` | Armazem principal. |
| `saldo` | numero | `inventory_items.balance` | Soma dos enderecos validos quando disponivel. |
| `enderecos[]` | array | `inventory_item_addresses` | Campos internos: `endereco`, `armazem`, `saldo`, `origem`. |
| `comentarios[]` | array | `inventory_item_comments` ou `raw_data` | Nao apareceu como fluxo central; manter JSON inicialmente. |
| `morto` | booleano | `inventory_items.is_dead` | Separa ativos e mortos. |
| `minimo` | numero/null | `inventory_items.min_qty` | Pode vir de Cooperat, manual, automatico ou anterior. |
| `maximo` | numero/null | `inventory_items.max_qty` | Idem. |
| `reposicao` | numero/null | `inventory_items.reorder_qty` | Geralmente `maximo - minimo`, mas pode vir da planilha. |
| `minimoOrigem`, `maximoOrigem`, `reposicaoOrigem`, `limitesOrigem` | texto | `inventory_items.limit_source` e colunas auxiliares | Guardar tambem no `raw_data` para nao perder granularidade. |
| `limitesCooperat` | objeto | `inventory_item_cooperat_limits` ou `raw_data` | Campos: `minimo`, `maximo`, `reposicao`, `saldoAnterior`. |
| `sugestaoEstoque` | objeto | `inventory_item_suggestions` ou `raw_data` | Gerado pelo algoritmo automatico. |

Chave natural recomendada:

- `item_id`: surrogate key interno.
- `protheus_code`: unique parcial quando existir e nao for `MORTO`.
- `cooperat_code`: indice para busca e historico.
- `legacy_key`: guardar a chave antiga usada no Firebase para reconciliação.

### Campos de ajuste manual

`estoqueGlobal/ajustesItens/{ajusteKey}`:

| Campo | SQL sugerido |
| --- | --- |
| chave do mapa | `inventory_adjustments.legacy_key` |
| codigo decodificado quando possivel | `inventory_adjustments.item_code` |
| `minimo` | `min_qty` |
| `maximo` | `max_qty` |
| `atualizadoEm` | `updated_at` |
| `atualizadoPor` | `updated_by_name` ou FK para usuario quando resolver |
| payload completo | `raw_data` |

Regra de migracao: carregar o ultimo ajuste como estado atual no item e manter a linha em `inventory_adjustments` para auditoria.

### Campos de historico de saldo

`estoqueGlobal/historicoSaldo/{itemKey}[]`:

| Campo esperado | SQL sugerido |
| --- | --- |
| chave do mapa | `item_legacy_key` |
| `timestamp` | `event_at` |
| `data` | `event_date_label` ou derivado |
| `saldoAnterior` | `previous_balance` |
| `saldoAtual` | `current_balance` |
| `delta` | `delta` |
| `tipo` | `event_type` |
| payload completo | `raw_data` |

Regra de migracao: se o item nao for encontrado por `protheus/protheusKey/cooperat`, manter `item_id` nulo e preencher `item_legacy_key` para reconciliar depois.

### Campos de contagem

Registro final em `contagens/{data}/{usuarioKey}/{pushId}`:

| Campo | SQL sugerido |
| --- | --- |
| `usuario` | `counting_sessions.user_name` |
| `uid` | `counting_sessions.user_id` |
| `data` | `counting_sessions.session_date` |
| `timestamp` | `counting_sessions.created_at` |
| `maquina` | `counting_sessions.machine` |
| `totalItens` | `counting_sessions.total_items` |
| `totalItensComQuantidade` | `counting_sessions.total_quantity_items` |
| `totalVerificacoesVazio` | `counting_sessions.total_empty_checks` |
| `itens` | `counting_items` |
| `verificacoesVazio` | `counting_empty_checks` |

Itens contados em `itens/{safeKey}`:

| Campo | SQL sugerido |
| --- | --- |
| `protheus` | `protheus_code` |
| `cooperat` | `cooperat_code` |
| `descricao` | `description` |
| `armazem` | `warehouse` |
| `endereco` | `address` |
| `saldoSistema` | `system_balance` |
| `reposicao` | `reorder_qty` |
| `contado` | `counted_qty` |

Verificacoes vazias em `verificacoesVazio/{safeKey}`:

| Campo | SQL sugerido |
| --- | --- |
| `endereco` | `address` |
| `armazem` | `warehouse` |
| `status` | `status` |
| `maquina` | `machine` |
| `secao` | `section` |
| `prateleira` | `shelf` |
| `caixa` | `box` |
| `descricao` | `description` |

Rascunhos em `contagemRascunhos/{uid}` e `contagemAtual/{ciclo}/usuarios/{usuario}`:

- `valores`, `verificacoesVazio`, `saldosSistema`: guardar em `counting_drafts` como `jsonb` inicialmente.
- `_progresso_itens`, `_progresso_grupos`, `_presenca`: guardar em tabelas de status se precisar manter tempo real no SQL; caso contrario mover para cache/Redis.
- `updatedAt`: usar para resolver conflitos entre local e remoto.

### Campos de historico Cooperat

Medição do arquivo local `data/historico_cooperat_antigo.json`:

- `totalCodigos`: 10.125
- `totalEventos`: 212.339
- eventos contados no arquivo: 212.339
- maior volume em um unico codigo: 3.822 eventos

Raiz:

- `geradoEm`
- `descricao`
- `regraQuantidade`
- `regraValor`
- `limiteEventosPorCodigo`
- `fontes`
- `totalCodigos`
- `totalEventos`
- `codigos`

Resumo por codigo:

- `codigo`
- `descricaoMaisRecente`
- `totalEventos`
- `totalQuantidadeCompra`
- `totalQuantidadeSolicitada`
- `totalQuantidadeFornecida`
- `totalValorBaixa`
- `primeiraData`
- `ultimaData`
- `mediaQuantidadeCompra`
- `mediaQuantidadeSolicitada`
- `mediaQuantidadeFornecida`
- `mediaValorBaixa`

Evento:

- `fonte`
- `origem`
- `requisicao`
- `data`
- `dataBr`
- `codigo`
- `descricao`
- `unidade`
- `qtdSolicitada`
- `qtdFornecida`
- `valorBaixa`
- `quantidadeCompra`

Recomendacao: migrar o Cooperat como primeiro piloto porque ele e grande, historico, tem JSON local para validar e nao depende de escrita concorrente diaria.

### Campos de usuarios e cadastro

`usuarios/{uid}`:

| Campo observado | SQL sugerido |
| --- | --- |
| chave `uid` | `users.id` |
| `nickname` | `users.nickname` |
| `cracha` | `users.badge` |
| `setor` | `users.sector` |
| `nivel` | `users.role` |
| `ativo` | `users.active` |
| `senha`, `senhaReset`, `senhaAntiga` | revisar; idealmente nao migrar senha em texto, manter somente flags seguras |
| `criadoEm` | `users.created_at` |

`solicitacoesCadastro/{id}`:

- `uid`, `nickname`, `senha`, `cracha`, `setor`, `status`, `duplicado`, `criadoEm`

Recomendacao: se Firebase Auth continuar, a API valida o token e usa `users.id = firebase uid`. Se migrar auth tambem, planejar etapa separada para senhas e reset.

### Campos do avaliador de pedidos

`dashboardConfig/avaliadorPedidos/{codigoKey}`:

| Campo | SQL sugerido |
| --- | --- |
| `codigo` | `purchase_evaluations.item_code` |
| `decisao` | `decision` |
| `statusManual` ou `statusKanban` | `kanban_status` |
| `observacao` | `note` |
| `avaliadoEm` | `evaluated_at` |
| `avaliadoPor` | `evaluated_by` |
| `atualizadoEm` | `updated_at` |
| `atualizadoPor` | `updated_by` |
| payload completo | `raw_data` |

### Campos de ocorrencias

`ocorrencias/{id}`:

| Campo | SQL sugerido |
| --- | --- |
| `id` | `occurrences.id` |
| `criadoEm` | `created_at` |
| `data`, `hora` | derivar de `created_at`, manter labels se necessario |
| `operadorUid`, `operadorNome`, `operadorCracha`, `operadorSetor` | colunas do operador |
| `acusadoNome`, `acusadoCracha`, `acusadoSetor` | colunas do envolvido |
| `tipo`, `gravidade`, `status` | colunas indexadas |
| `codigoItem`, `descricaoItem`, `quantidade` | dados do item |
| `descricao` | texto da ocorrencia |
| `responsavelUid`, `responsavelNome`, `responsavelCracha`, `responsavelSetor`, `responsavelAtribuidoEm` | dados de tratativa |
| `tratativaRealizada`, `tratativaAssinatura`, `tratativaEm`, `tratativaPorUid`, `tratativaPorNome` | dados de conclusao/tratativa |
| `documentoTratativa` | `jsonb` |
| `historico` | `occurrence_history` ou `jsonb` inicial |
| `_storagePath`/origem | `source_path` |

Regra: importar tanto `ocorrencias` quanto `chatGlobal/ocorrencias`, deduplicando por `id`.

### Campos de chat

`chatRooms/{roomId}`:

- `senha`: migrar para `chat_rooms.password_hash`; nao manter texto puro se possivel.
- `messages/{pushId}`: `nome`, `texto`, `data`, `timestamp`, `tipo`, `evento`, `sessionId`, `uid`.
- `typing/{uid}`: `nickname`, `cracha`, `ts`; dado transitorio, idealmente fora do SQL.

`chatReadState/{uid}/{roomId}`:

- timestamp da ultima leitura; mapear para `chat_read_states(user_id, room_id, last_seen_at)`.

### Campos de etiquetas

`etiquetasGeradas/{data}/{usuarioKey}/{pushId}`:

| Campo | SQL sugerido |
| --- | --- |
| `usuario` | `label_print_jobs.user_name` |
| `data` | `job_date` |
| `timestamp` | `created_at` |
| `totalEtiquetas` | `total_labels` |
| `totalCodigosInformados` | `total_codes_submitted` |
| `porTamanho` | `by_size jsonb` ou tabela filha |
| `teveNaoEncontrados` | `had_missing_codes` |

`rankingEtiquetas/{usuarioKey}`:

- `usuario`, `totalEtiquetas`, `eventos`, `atualizadoEm`
- Preferencia: recalcular via query a partir de `label_print_jobs`.

### Campos de configuracao

Configuracoes pequenas podem ir para uma tabela comum:

```sql
create table app_settings (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz,
  updated_by text
);
```

Chaves candidatas:

- `label.layout.shared`
- `counting.config`
- `occurrences.fields`
- `occurrences.evaluator_password`
- `dashboard.panels.raw`

## Inventario arquivo por arquivo

Esta secao mapeia o repositorio por diretorio e arquivo, com o destino de cada item na migracao Firebase -> SQL.

Legenda:

- **Migrar dados**: arquivo contem dados que devem virar tabela/carga SQL.
- **Adaptar para API**: codigo hoje le/grava Firebase e deve passar a chamar backend.
- **Adaptar para SQL**: script hoje le/grava Firebase e deve falar com API/SQL.
- **Manter estatico**: asset/interface que nao vira dado SQL.
- **Ignorar gerado**: artefato de build/cache, fora da migracao.
- **Referencia**: documentacao, regras ou codigo antigo usado para conferir comportamento.

### Raiz do projeto

| Arquivo/diretorio | Papel atual | Acao | Destino na migracao |
| --- | --- | --- | --- |
| `.git/` | historico Git | Ignorar gerado | Nao entra na migracao de dados. |
| `.vscode/` | configuracao local de editor | Manter estatico | Sem destino SQL. |
| `assets/` | imagens de apoio/screenshot | Manter estatico | Sem destino SQL. |
| `Automus/` | pacote/app de automacao duplicado/empacotavel | Adaptar para SQL | Ver subsecao Automus. |
| `data/` | bases auxiliares e historico local | Migrar dados | Ver subsecao `data/`. |
| `docs/` | documentacao criada para a migracao | Referencia | Mantem plano e inventarios. |
| `downloads/` | planilhas fontes operacionais e assets de etiqueta | Migrar dados + manter estatico | Ver subsecao `downloads/`. |
| `scripts/` | automacao Python/PowerShell principal | Adaptar para SQL | Ver subsecao `scripts/`. |
| `tools/` | motores antigos de planilha | Referencia | Usar apenas se precisar comparar logica antiga. |
| `.gitignore` | regras de versionamento | Manter estatico | Sem destino SQL. |
| `README.md` | documentacao funcional | Referencia | Atualizar quando a API/SQL existir. |
| `index.html` | aplicacao principal; Auth, estoque, admin, contagem, etiquetas, ocorrencias e chat | Adaptar para API | Trocar Firebase client por cliente HTTP/API. Impacta quase todos os dominios. |
| `dashboard.html` | dashboard/avaliador; le estoque, contagens, etiquetas, dashboardConfig e Cooperat | Adaptar para API | `GET /api/dashboard`, `GET /api/inventory`, `GET /api/counting`, `GET /api/cooperat`, `PATCH /api/dashboard/*`. |
| `label-editor.html` | editor visual de layout de etiquetas; le/grava `estoqueGlobal/configuracoesEtiquetas` | Adaptar para API | `GET/PATCH /api/settings/label-layout`; tabela `app_settings` ou `label_layout_configs`. |
| `dashboard-nav.js` | atalhos/URLs do dashboard | Manter estatico | Sem destino SQL, talvez ajustar URLs se backend servir rotas. |
| `style.css` | estilos desktop | Manter estatico | Sem destino SQL. |
| `mobile.css` | estilos mobile | Manter estatico | Sem destino SQL. |
| `logo.png`, `logo-tab.png` | assets visuais | Manter estatico | Sem destino SQL. |
| `executar_tudo.bat` | atalho para automacao | Adaptar para SQL | Deve chamar scripts que enviam para API/SQL em vez de Firebase. |
| `push_rapido.bat` | atalho operacional | Referencia | Verificar funcao antes de migrar; sem dado SQL direto. |
| `firebase-rules-completas.json` | regras atuais do Realtime Database | Referencia | Converter regras para autorizacao no backend/API. |
| `firebase-rules-historico-compras.json` | regras do historico Cooperat | Referencia | Converter para permissao API/admin. |
| `dados.mortos.xlsx` | fonte de itens mortos/enderecos antigos | Migrar dados | Carga para `inventory_items(is_dead=true)` e/ou enriquecimento de enderecos. |
| `mata185.xlsx` | fonte de movimentacoes/requisicoes encerradas | Migrar dados | `inventory_movements` ou `inventory_mata185_events`. |
| `planilha complemento.xlsx` | planilha operacional auxiliar | Inventariar antes de migrar | Precisa identificar colunas; provavel fonte complementar de estoque/pedidos. |
| `planilha pedidos antigos COMPLETA.xlsx` | planilha historica grande de pedidos | Migrar dados se ainda usada | Provavel origem alternativa/complementar para `cooperat_purchase_events` ou historico de pedidos. |

### `data/`

| Arquivo | Papel atual | Acao | Destino na migracao |
| --- | --- | --- | --- |
| `data/historico_cooperat_antigo.json` | fallback local e fonte normalizada do historico Cooperat | Migrar dados P0 | `cooperat_import_runs`, `cooperat_purchase_codes`, `cooperat_purchase_events`. |
| `data/mata110.xlsx` | planilha auxiliar do dashboard/pedidos | Migrar dados P1 | `purchase_requests` ou staging `stg_mata110`, depois normalizar. |
| `data/mata111.xlsx` | historico novo de pedidos/compra | Migrar dados P1 | `purchase_orders` ou staging `stg_mata111`; usado para historico MATA111/MATA112. |
| `data/mata112.xlsx` | entradas/enderecamento | Migrar dados P1 | `purchase_receipts` ou staging `stg_mata112`. |
| `data/levantamento0706 antigo.xlsx` | levantamento antigo | Inventariar antes de migrar | Staging temporario ate identificar colunas e uso atual. |

Recomendacao para planilhas MATA: criar primeiro tabelas staging (`stg_mata110`, `stg_mata111`, `stg_mata112`) preservando linhas/colunas originais e depois views/tabelas normalizadas para o dashboard.

### `downloads/`

| Arquivo | Papel atual | Acao | Destino na migracao |
| --- | --- | --- | --- |
| `downloads/incluir.xlsx` | base MATA105 nativa usada no estoque e etiquetas | Migrar dados P0 | `inventory_items` via staging `stg_incluir`. |
| `downloads/Saldo Atual.xlsx` | saldo total por item | Migrar dados P0 | `inventory_balances` ou staging `stg_saldo_atual`; atualiza `inventory_items.balance`. |
| `downloads/Saldo por Endereco.xlsx` | saldo/endereco por item | Migrar dados P0 | `inventory_item_addresses`; atualiza `primary_address`. |
| `downloads/estoque_minimo.xlsx` | minimo, maximo, reposicao e saldo anterior Cooperat | Migrar dados P0 | `inventory_item_limits`, `inventory_items.min/max/reorder`, `limit_source='cooperat'`. |
| `downloads/mata112.xlsx` | copia operacional de MATA112 | Migrar dados P1 | Mesmo destino de `data/mata112.xlsx`; decidir fonte oficial para evitar duplicidade. |
| `downloads/etiquetas_logo.png` | asset para gerar etiquetas | Manter estatico | Servir como arquivo estatico. |
| `downloads/Oswald-Regular.ttf`, `downloads/Oswald-Bold.ttf` | fontes das etiquetas | Manter estatico | Servir como arquivo estatico. |

### `assets/`

| Arquivo/diretorio | Papel atual | Acao | Destino na migracao |
| --- | --- | --- | --- |
| `assets/screenshots/desktop_capture.png` | screenshot de apoio | Manter estatico | Sem destino SQL. |
| `assets/screenshots/desktop_capture_after_focus.png` | screenshot de apoio | Manter estatico | Sem destino SQL. |

### `scripts/`

| Arquivo/diretorio | Papel atual | Acao | Destino na migracao |
| --- | --- | --- | --- |
| `scripts/atualizacao/` | modulo de atualizacao Automus sem navegador | Adaptar para SQL | Ver subsecao `scripts/atualizacao`. |
| `scripts/automus_update.py` | wrapper do update Automus | Adaptar para SQL | Deve chamar rotina nova de envio API/SQL. |
| `scripts/executar_tudo.py` | orquestra macros e chama envio ao Firebase | Adaptar para SQL P0 | Trocar `run_automus_update` para enviar a API/SQL. |
| `scripts/controladordeatualização.py` | app/controlador local, login admin e automacao | Adaptar para API P1 | Validar admin pela API; remover leituras diretas `usuarios/{uid}` do Firebase. |
| `scripts/build_automus_exe.py` | empacota Automus e injeta config Firebase | Adaptar P2 | Passar a embutir `API_BASE_URL`/config backend, nao `firebase_config`. |
| `scripts/importar_historico_cooperat_firebase.py` | envia JSON Cooperat para Firebase | Substituir por migrador SQL P0 | Novo script `migrate_cooperat_to_sql.py`. |
| `scripts/gerar_historico_cooperat_txt.py` | gera JSON Cooperat a partir de TXT | Manter/adaptar | Pode gerar carga para `cooperat_*`; ideal emitir CSV/SQL/staging. |
| `scripts/azul_encerradas.py` | verifica requisicoes encerradas antes do envio | Adaptar para SQL P1 | Gravar resultado em `inventory_movements`/`purchase_flow_events`. |
| `scripts/procurar_azul.ps1` | apoio para detectar itens azuis/encerrados | Referencia/adaptar se ainda usado | Sem SQL direto; pode alimentar `mata185`/movimentos. |
| `scripts/abrir_protheus_controlado.ps1` | abre Protheus controlado | Manter estatico | Sem destino SQL. |
| `scripts/macro_001.py` ... `scripts/macro_006.py`, `scripts/macro_012.py`, `scripts/macro_013.py` | macros de extracao/operacao | Manter/adaptar | Nao gravam SQL diretamente; produzem planilhas que viram staging. |
| `scripts/macro_gravador.py` | gravador de macros | Manter estatico | Sem destino SQL. |
| `scripts/identificador_de_pixel.py` | utilitario visual | Manter estatico | Sem destino SQL. |
| `scripts/totvs_news_reference.json`, `.png` | referencia para detector TOTVS | Manter estatico | Sem destino SQL. |

### `scripts/atualizacao/`

| Arquivo | Papel atual | Acao | Destino na migracao |
| --- | --- | --- | --- |
| `scripts/atualizacao/automus_update.py` | rotina principal que le planilhas, baixa `estoqueGlobal`, gera payload, faz backup e PATCH no Firebase | Adaptar para SQL P0 | Separar em: parser de planilhas, servico de reconciliacao, writer API/SQL, snapshot/rollback. |
| `scripts/atualizacao/automus_crypto.py` | criptografia da config Automus/Firebase | Adaptar P2 | Reusar para credenciais da API se necessario. |
| `scripts/atualizacao/automus_config.json` | config local real | Nao documentar conteudo | Migrar para config local da API; nao versionar segredo. |
| `scripts/atualizacao/automus_config.json.example` | exemplo de config Firebase | Adaptar | Exemplo deve usar `apiBaseUrl`/credencial API. |
| `scripts/atualizacao/__main__.py`, `__init__.py` | entrada de modulo | Adaptar | Apontar para novo fluxo SQL. |
| `scripts/atualizacao/README.md` | documentacao do update Firebase | Atualizar | Documentar update via API/SQL e rollback SQL. |
| `scripts/atualizacao/executar_automus.bat` | atalho local | Adaptar | Chamar novo update. |

### `Automus/`

`Automus/` repete e empacota grande parte de `scripts/`, com downloads proprios e release. Deve ser tratado como segundo consumidor da mesma migracao.

| Arquivo/diretorio | Papel atual | Acao | Destino na migracao |
| --- | --- | --- | --- |
| `Automus/build/`, `Automus/dist/` | artefatos PyInstaller/build | Ignorar gerado | Nao migrar; regenerar depois da adaptacao. |
| `Automus/downloads/incluir.xlsx` | copia de fonte estoque | Migrar dados se for fonte oficial | Preferir uma fonte oficial; evitar duplicar com `downloads/incluir.xlsx`. |
| `Automus/downloads/Saldo Atual.xlsx` | copia de saldo | Migrar dados se for fonte oficial | Mesmo staging de saldo. |
| `Automus/downloads/Saldo por Endereco.xlsx` | copia de enderecos | Migrar dados se for fonte oficial | Mesmo staging de enderecos. |
| `Automus/downloads/estoque_minimo.xlsx` | copia de limites | Migrar dados se for fonte oficial | Mesmo destino de limites. |
| `Automus/releases/` | pacotes/manifestos de release | Manter estatico + migrar manifesto | Manifesto pode ir para `automus_releases`; ZIP fica arquivo/HTTP, nao SQL. |
| `Automus/README.md` | documentacao de release/update Firebase | Atualizar | Documentar update via API/SQL. |
| `Automus/requirements.txt` | dependencias Python | Adaptar | Adicionar driver/API client se necessario. |
| `Automus/Abrir_Automus.bat`, `Automus/atualizar_automus.bat` | atalhos | Adaptar se chamarem config Firebase | Sem SQL direto. |
| `Automus/scripts/firebase_config.json` | config Firebase embutida | Remover/substituir | Trocar por config de API; nao expor segredo no cliente. |
| `Automus/scripts/version.json` | versao e manifesto de update | Adaptar | Campo `updateManifestFirebasePath` vira endpoint API ou URL estatico. |
| `Automus/scripts/preparar_release_automus.py` | prepara release e publica manifesto no Firebase | Adaptar P2 | Publicar manifesto em API/SQL ou arquivo HTTP. |
| `Automus/scripts/package_automus_release.py` | empacota release | Manter/adaptar | Sem SQL direto. |
| `Automus/scripts/build_automus_exe.py` | build exe com config Firebase | Adaptar P2 | Embutir API config. |
| `Automus/scripts/automus_self_update.py` | auto update | Adaptar P2 | Consultar endpoint/URL SQL-backed, nao Firebase. |
| `Automus/scripts/automus_update.py` | wrapper | Adaptar | Chamar rotina nova. |
| `Automus/scripts/executar_tudo.py` | orquestrador completo | Adaptar P0 | Igual `scripts/executar_tudo.py`. |
| `Automus/scripts/controladordeatualização.py` | controlador completo | Adaptar P1 | Igual controlador raiz, mas versao empacotada. |
| `Automus/scripts/azul_encerradas.py` | verificacao de encerradas | Adaptar P1 | Igual raiz. |
| `Automus/scripts/macro_001.py` ... `macro_013.py` | macros completas | Manter/adaptar | Produzem planilhas/staging; nao devem saber do SQL. |
| `Automus/scripts/macro_gravador.py`, `macro_gravador.py.py` | gravador/duplicata | Manter/limpar depois | Sem SQL direto. |
| `Automus/scripts/procurar_azul.ps1`, `abrir_protheus_controlado.ps1`, `identificador_de_pixel.py` | utilitarios | Manter | Sem SQL direto. |
| `Automus/scripts/totvs_news_reference.*` | referencias visuais | Manter estatico | Sem SQL direto. |
| `Automus/scripts/atualizacao/automus_update.py` | versao mais completa da rotina Firebase, com envio em blocos | Adaptar para SQL P0 | Provavel base principal para refatorar writer SQL/API. |
| `Automus/scripts/atualizacao/automus_crypto.py` | crypto config | Adaptar | Reusar se houver credencial local. |
| `Automus/scripts/atualizacao/automus_config.json.example` | exemplo config Firebase | Adaptar | Usar API. |
| `Automus/scripts/atualizacao/README.md`, `__main__.py`, `__init__.py` | docs/entrada | Atualizar/adaptar | Novo fluxo. |

### `tools/planilhas/`

| Arquivo | Papel atual | Acao | Destino na migracao |
| --- | --- | --- | --- |
| `motor_automacao_planilha.py` | motor antigo de tratamento | Referencia | Comparar regras antigas se houver divergencia na carga SQL. |
| `motor_automacao_planilha_saldo_corrigido.py` | variacao de saldo | Referencia | Sem destino SQL direto. |
| `motor_automacao_planilha_saldo_e_10170.py` | variacao especifica | Referencia | Sem destino SQL direto. |
| `motor_automacao_planilha_sem_controlador.py` | variacao sem controlador | Referencia | Sem destino SQL direto. |

### `docs/`

| Arquivo | Papel atual | Acao | Destino na migracao |
| --- | --- | --- | --- |
| `docs/firebase-to-sql-migration-plan.md` | plano e inventario da migracao | Manter e evoluir | Documento guia. |

## Destinos SQL consolidados

Esta e a lista consolidada de destinos que aparecem no inventario:

Ambiente local criado para estes destinos:

- `docker-compose.yml`: PostgreSQL 16 + Adminer.
- `.env.example`: variaveis locais do banco.
- `db/init/001_schema.sql`: schema inicial com tabelas, indices, triggers, staging e view de ranking.
- `db/init/002_security.sql`: roles, RLS, policies, views seguras e auditoria.
- `db/check.sql`: consulta de verificacao do schema.
- `db/README.md`: comandos para subir, validar e recriar o banco.

| Destino | Recebe dados de |
| --- | --- |
| `users` | `usuarios`, Auth Firebase validado pela API |
| `signup_requests` | `solicitacoesCadastro` |
| `banned_users` | `usuariosBanidos` |
| `inventory_items` | `estoqueGlobal/dados`, `estoqueGlobal/dadosMortos`, `downloads/incluir.xlsx` |
| `inventory_item_addresses` | `enderecos[]`, `Saldo por Endereco.xlsx`, `dados.mortos.xlsx` |
| `inventory_item_limits` | `estoque_minimo.xlsx`, `limitesCooperat`, ajustes manuais |
| `inventory_adjustments` | `estoqueGlobal/ajustesItens` |
| `inventory_balance_history` | `estoqueGlobal/historicoSaldo` |
| `inventory_movements` / `inventory_mata185_events` | `mata185.xlsx`, `movimentacoesMata185`, `azul_encerradas.py` |
| `inventory_snapshots` | `estoqueGlobalBackups/automus_last`, backups locais do Automus |
| `counting_sessions` | `contagens/{data}/{usuario}/{pushId}` |
| `counting_items` | `contagens/*/*/*/itens` |
| `counting_empty_checks` | `contagens/*/*/*/verificacoesVazio` |
| `counting_drafts` | `contagemRascunhos`, `contagemAtual/*/usuarios/*/_rascunho_atual` |
| `counting_machine_status` | `contagemStatusMaquinas` |
| `counting_control_events` | `contagemControle/resetGlobal` |
| `label_print_jobs` | `etiquetasGeradas`, `contagens/*/*/_etiquetas` |
| `label_user_ranking` ou view | `rankingEtiquetas` |
| `dashboard_panels` | `dashboardConfig/paineis` |
| `purchase_evaluations` | `dashboardConfig/avaliadorPedidos` |
| `cooperat_import_runs` | metadados de `historico_cooperat_antigo.json` |
| `cooperat_purchase_codes` | `historicoComprasCooperat/codigos` |
| `cooperat_purchase_events` | `historicoComprasCooperat/codigos/*/eventos` |
| `occurrences` | `ocorrencias`, `chatGlobal/ocorrencias` |
| `occurrence_history` | `ocorrencias/*/historico` |
| `chat_rooms` | `chatRooms/*/senha` e metadados das salas |
| `chat_messages` | `chatRooms/*/messages` |
| `chat_read_states` | `chatReadState` |
| `app_settings` | `estoqueGlobal/configuracoesEtiquetas`, `estoqueGlobal/configContagem`, `dashboardConfig/ocorrenciasCampos`, `dashboardConfig/ocorrenciasAvaliadorSenha` |
| `automus_releases` | `automus/releases`, `Automus/releases`, `version.json/latest.json` |
| `stg_*` | planilhas brutas antes da normalizacao |

## Proximas tarefas sugeridas

1. Escolher banco alvo: PostgreSQL local, servidor interno ou cloud.
2. Exportar um snapshot real do Firebase.
3. Rodar inventario de tamanho e formatos dos principais nos.
4. Fechar a primeira versao do schema.
5. Criar backend minimo com login e `GET /api/inventory`.
6. Migrar `historicoComprasCooperat` como piloto, por ser grande e mais facil de validar.
7. Migrar `estoqueGlobal` e adaptar dashboard para ler da API.
8. Migrar escritas criticas: ajustes, contagens e avaliador.

Ordem recomendada para implementar o motor:

1. Criar `scripts/migration/` com configuracao, cliente Firebase REST e cliente SQL.
2. Implementar primeiro o dominio `cooperat` em modo `dry-run`.
3. Persistir `cooperat_import_runs`, `cooperat_purchase_codes` e `cooperat_purchase_events`.
4. Adicionar validacao automatica de totais/checksums.
5. Repetir o padrao para `inventory`, depois `users`, `dashboard`, `counting`, `occurrences`, `labels`, `chat` e `automus`.
6. Implementar o verificador de integridade pos-migracao antes de qualquer corte de leitura/escrita.

Status da etapa inicial:

- `scripts/migration/` criado.
- Dominio `cooperat` implementado para `inspect`/`dry-run`.
- Dry-run `initial_cooperat_dry_run` executado com sucesso em `2026-06-29`.
- Totais validados: `10125` codigos e `212339` eventos.
- Verificador de integridade Cooperat executado em modo raw-only, com `0` findings.
- Cliente REST do Firebase criado em `scripts/migration/firebase_client.py`.
- Extrator de snapshot criado em `scripts/migration/extract_firebase.py`.
- Dominio `inventory` criado para inventariar `estoqueGlobal` em modo `inspect`/`dry-run`.
- `run_transfer.py` agora aceita `--domain cooperat` e `--domain inventory`.
- PostgreSQL local portatil iniciado em `127.0.0.1:5433`, usando `C:\Users\Davi.souza\Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql`.
- Schema SQL aplicado com sucesso: `36` tabelas, migrations `001_schema` e `002_security`, `63` policies RLS.
- Driver `psycopg` instalado no Python portatil informado.
- Cooperat aplicado no SQL local com sucesso no run `cooperat_apply_local_initial`.
- Integridade Cooperat raw-vs-SQL executada com `0` findings.
- Proximo passo tecnico: exportar `estoqueGlobal` real do Firebase e rodar `inspect --domain inventory`.

Resultado Cooperat no SQL local:

| Item | Valor |
| --- | --- |
| Run | `cooperat_apply_local_initial` |
| Import run SQL | `a608e8ba-a9c5-4298-b629-9bba5178b6d2` |
| Hash fonte | `ca708c12ff4c3852541baac824ac2a5f1bb3acdd131ffdbfeeb6374676521744` |
| Codigos SQL | `10125` |
| Eventos SQL | `212339` |
| Integridade | `raw-vs-sql`, `0` findings |

Resultado do primeiro export Firebase real:

- Arquivo fonte: `C:\Users\Davi.souza\Desktop\chat-fiasul-default-rtdb-export.json`
- Tamanho aproximado: `48 MB`
- Run de inventario: `firebase_inventory_export_20260629`
- Hash fonte: `13d5e3882ea394a8e4c28cc7533919ef54546b9d9d2b772a71c8ad86ca9b622e`
- `estoqueGlobal/dados`: `7681` itens ativos
- `estoqueGlobal/dadosMortos`: `131` itens mortos
- `estoqueGlobal/ajustesItens`: `3` ajustes
- `estoqueGlobal/historicoSaldo`: `1256` chaves, `5562` eventos
- `estoqueGlobal/movimentacoesMata185`: `4` chaves
- `estoqueGlobal/configContagem`: presente
- `estoqueGlobal/configuracoesEtiquetas`: nao encontrado dentro de `estoqueGlobal` neste export
- `estoqueGlobal/ultimaAtualizacao`: `1782537018879`
- `estoqueGlobal/atualizadoPor`: `atualizado automaticamente via Automus`
- Carga SQL executada no run `inventory_apply_local_initial`
- Snapshot SQL: `bb45cb90-a26f-4ff2-8f76-ab740e04c6ee`
- `inventory_items`: `7681` ativos, `131` mortos, `7812` total
- `inventory_item_addresses`: `44548` enderecos
- `inventory_item_limits`: `6191` limites Cooperat
- `inventory_adjustments`: `3` ajustes
- `inventory_balance_history`: `5562` eventos
- `inventory_movements`: `1` snapshot raw de `movimentacoesMata185`
- Integridade inventory raw-vs-SQL: `0` findings

Nos principais encontrados no export completo:

| Caminho raiz | Medida inicial |
| --- | --- |
| `automus` | `1` chave |
| `chatGlobal` | `100` chaves |
| `chatReadState` | `6` usuarios/chaves |
| `chatRooms` | `3` salas/chaves |
| `contagemAtual` | `1` chave |
| `contagemRascunhos` | `1` chave |
| `contagemStatusMaquinas` | `1` chave |
| `contagens` | `15` datas/chaves |
| `dashboardConfig` | `3` chaves |
| `estoqueGlobal` | `13` chaves |
| `estoqueGlobalBackups` | `1` chave |
| `historicoComprasCooperat` | `9` chaves |
| `nicknames`, `nicknamesAuth`, `nicknamesSimple` | `1`, `37`, `25` chaves |
| `ocorrencias` | `7` chaves |
| `solicitacoesCadastro` | `30` chaves |
| `solicitaçõesCadastro` | `17` chaves, caminho legado/acento a reconciliar |
| `usuarios` | `25` usuarios/chaves |
| `usuariosBanidos` | `12` usuarios/chaves |

Resultado da carga de usuarios no SQL local:

- Run: `users_apply_local_initial`
- `users`: `25`
- `signup_requests`: `47`
- `banned_users`: `12`
- `solicitacoesCadastro`: `30`
- `solicitaçõesCadastro`: `17`, caminho legado/acento preservado em `raw_data.source_path`
- `signup_requests.password_plain_legacy`: `0` registros preenchidos
- Senhas legadas em `raw_data`: sanitizadas como `[redacted]`
- Integridade users raw-vs-SQL: `0` findings

Resultado da carga de dashboard/avaliador no SQL local:

- Run: `dashboard_apply_local_initial`
- `dashboard_panels`: `5`
- `purchase_evaluations`: `11`
- `app_settings`: `1`
- Configuracao carregada em `app_settings`: `occurrences.fields`
- Integridade dashboard raw-vs-SQL: `0` findings

Resultado da carga de contagens/etiquetas no SQL local:

- Run: `counting_apply_local_initial`
- `counting_sessions`: `20`
- `counting_items`: `3557`
- `counting_empty_checks`: `410`
- `counting_drafts`: `1`
- `counting_machine_status`: `16`
- `label_print_jobs`: `20`
- `label_user_ranking`: `0`, ausente no export
- `etiquetasGeradas`: ausente no export; eventos de etiqueta vieram de `contagens/*/*/_etiquetas`
- `rankingEtiquetas`: ausente no export
- Integridade counting raw-vs-SQL: `0` findings

Resultado da carga de ocorrencias no SQL local:

- Run: `occurrences_apply_local_initial`
- `occurrences`: `7`
- `occurrence_history`: `11`
- `chatGlobal/ocorrencias`: `0`, ausente no export
- Integridade occurrences raw-vs-SQL: `0` findings

Resultado da carga de chat no SQL local:

- Run: `chat_apply_local_initial`
- `chat_rooms`: `4`, incluindo a sala sintetica `chatGlobal` para mensagens legadas
- `chat_messages`: `227`
- `chat_read_states`: `14`
- salas privadas com senha migrada para hash: `2`
- mensagens legadas de `chatGlobal`: `100`
- senhas em texto aberto em `chat_rooms.raw_data`: `0`
- Integridade chat raw-vs-SQL: `0` findings

Resultado da carga Automus no SQL local:

- Run: `automus_apply_local_initial`
- `automus_releases`: `1`
- canal carregado: `latest`
- versao: `1.1.1`
- manifesto com `sha256`: `1`
- Integridade Automus raw-vs-SQL: `0` findings

Resultado da primeira API SQL local:

- Arquivo: `api/dark_jutsu_api.py`
- Atalho de inicio: `api/iniciar_api.bat`
- Atalho de status: `api/status_api.bat`
- Atalho de parada: `api/parar_api.bat`
- URL local: `http://127.0.0.1:8765`
- Endpoints iniciais testados: `/health`, `/api/inventory`, `/api/chat/rooms`, `/api/automus/releases/latest`
- Endpoints de leitura ampliados: usuarios, solicitacoes, banidos, contagens, etiquetas e configuracoes
- Primeiras escritas SQL implementadas e testadas: `PUT /api/dashboard/panels/{id}` e `PUT /api/dashboard/evaluations/{legacyKey}`
- Escritas de ocorrencias implementadas e testadas: `POST /api/occurrences` e `PATCH /api/occurrences/{id}`
- Escritas de chat implementadas e testadas: `POST /api/chat/rooms/{roomId}/messages` e `PUT /api/chat/read-state`
- Escrita de etiquetas implementada e testada: `POST /api/labels/jobs`
- Papel: ponte inicial para substituir leituras Firebase por leituras SQL antes das escritas e da autenticacao final.

Comandos da proxima etapa:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe api\dark_jutsu_api.py
```

## Criterios de sucesso

- Totais migrados batem com o Firebase para cada no.
- Dashboard carrega do SQL com desempenho igual ou melhor.
- Atualizacao Automus grava no SQL sem perda de ajustes manuais.
- Usuarios comuns nao conseguem acessar dados administrativos pela API.
- Existe rollback documentado: restaurar leitura Firebase ou restaurar backup SQL.
