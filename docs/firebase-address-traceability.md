# Rastreabilidade direta: enderecos Firebase -> arquivos raiz -> destinos SQL/API

Este arquivo e o indice operacional para atrelar cada endereco Firebase encontrado no codigo ao arquivo que usa esse endereco e ao destino previsto na migracao SQL.

Legenda:

- **R/W**: leitura e escrita.
- **R**: leitura.
- **W**: escrita.
- **RT**: leitura em tempo real/listener.
- **API alvo**: endpoint ou familia de endpoints que deve substituir o uso direto do Firebase.
- **SQL alvo**: tabela, view ou staging recomendado.

## Arquivos raiz que falam com Firebase

| Arquivo raiz | Tipo de uso Firebase | Observacao |
| --- | --- | --- |
| `index.html` | R/W/RT | Principal cliente Firebase: estoque, usuarios, cadastro, contagem, etiquetas, ocorrencias e chat. |
| `dashboard.html` | R/W | Dashboard e avaliador: le estoque, contagens, ranking, Cooperat e grava configuracoes/avaliacoes. |
| `label-editor.html` | R/W/RT | Editor de layout de etiquetas compartilhado. |
| `scripts/atualizacao/automus_update.py` | R/W via REST | Atualiza `estoqueGlobal` e backup remoto. |
| `Automus/scripts/atualizacao/automus_update.py` | R/W via REST | Versao empacotada/completa; atualiza `estoqueGlobal` em blocos e backup remoto. |
| `scripts/importar_historico_cooperat_firebase.py` | W via REST | Publica `historicoComprasCooperat`. Deve virar migrador SQL. |
| `scripts/controladordeatualizacao.py` | R via REST | Valida usuario/admin em `usuarios` para Automus local. |
| `Automus/scripts/controladordeatualizacao.py` | R via REST | Versao empacotada; valida usuario/admin e consulta manifesto Firebase. |
| `Automus/scripts/preparar_release_automus.py` | W via REST | Publica manifesto `automus/releases/latest`. |

## Matriz por endereco Firebase

### Estoque

| Endereco Firebase | Arquivo/linha raiz | Op | Vai para API alvo | Vai para SQL alvo | Observacao |
| --- | --- | --- | --- | --- | --- |
| `estoqueGlobal` | `index.html:11950`, `index.html:13175` | RT | `GET /api/inventory/snapshot` ou `GET /api/inventory` | `inventory_items`, `inventory_item_addresses`, `inventory_adjustments`, `inventory_balance_history`, `app_settings` | Listener principal do app. |
| `estoqueGlobal` | `index.html:1983`, `index.html:3681`, `index.html:3683`, `index.html:3752`, `index.html:3754` | W | `PATCH /api/inventory/snapshot` | mesmas tabelas de estoque + `inventory_snapshots` | Escritas amplas do frontend devem sumir e virar comandos da API. |
| `estoqueGlobal` | `dashboard.html:2794` | R | `GET /api/dashboard` ou `GET /api/inventory` | mesmas tabelas de estoque | Dashboard consome snapshot inteiro hoje. |
| `estoqueGlobal` | `scripts/atualizacao/automus_update.py:920`, `:922`, `:1058`, `:1061` | R/W | `POST /api/automus/inventory-update` | `inventory_*`, `inventory_snapshots` | Automus raiz le snapshot, calcula e faz PATCH. |
| `estoqueGlobal` | `Automus/scripts/atualizacao/automus_update.py:1412`, `:1414`, `:1589`, `:1592`, `:1600`, `:1603` | R/W | `POST /api/automus/inventory-update` | `inventory_*`, `inventory_snapshots` | Versao completa grava blocos `dados`, `dadosMortos`, `ajustesItens`, `historicoSaldo`, `movimentacoesMata185`. |
| `estoqueGlobal/dados` | `index.html:10567` | W | `PUT /api/inventory/items/import` | `inventory_items` | Importacao manual de dados mortos atualiza dados ativos tambem. |
| `estoqueGlobal/dadosMortos` | `index.html:10568` | W | `PUT /api/inventory/dead-items/import` | `inventory_items(is_dead=true)` | Itens mortos/inativos. |
| `estoqueGlobal/ultimaAtualizacao` | `index.html:10569` | W | `PATCH /api/inventory/metadata` | `inventory_snapshots`, `app_settings` | Metadado de snapshot. |
| `estoqueGlobal/atualizadoPor` | `index.html:10571` | W | `PATCH /api/inventory/metadata` | `inventory_snapshots.updated_by` | Auditoria simples. |
| `estoqueGlobal/configContagem` | `index.html:6587` | W | `PATCH /api/settings/counting-config` | `app_settings(key='counting.config')` | Configuracao compartilhada da contagem. |
| `estoqueGlobal/configuracoesEtiquetas` | `index.html:2709`, `label-editor.html:982`, `label-editor.html:1008`, `label-editor.html:1032` | R/W/RT | `GET/PATCH /api/settings/label-layout` | `app_settings(key='label.layout.shared')` ou `label_layout_configs` | Layout visual compartilhado do editor de etiquetas. |
| `estoqueGlobalBackups/automus_last` | `scripts/atualizacao/automus_update.py:1020`, `:1033`, `:1034`; `Automus/scripts/atualizacao/automus_update.py:1526`, `:1550`, `:1551` | R/W | `POST /api/inventory/snapshots` | `inventory_snapshots` | Backup remoto de rollback antes do update Automus. |

### Usuarios, cadastro e indices de nickname

| Endereco Firebase | Arquivo/linha raiz | Op | Vai para API alvo | Vai para SQL alvo | Observacao |
| --- | --- | --- | --- | --- | --- |
| `usuarios/{uid}` | `index.html:2186`, `index.html:2257`, `index.html:2305`, `index.html:11792` | R/W | `GET/PATCH/DELETE /api/users/:id` | `users` | Perfil e permissao do usuario. |
| `usuarios/{uid}/nivel` | `index.html:2271`, `index.html:11534`, `index.html:11585`, `index.html:11645` | R/W | `PATCH /api/users/:id/role` | `users.role` | Controle admin/mod/op. |
| `usuarios/{uid}/ativo` | `index.html:2309` | W | `PATCH /api/users/:id/status` | `users.active` | Reativacao. |
| `usuarios/{uid}/senha`, `usuarios/{uid}/senhaReset`, `usuarios/{uid}/senhaAntiga` | `index.html:2315`, `index.html:2316`, `index.html:11831`, `index.html:11834`, `index.html:11835` | W | `POST /api/users/:id/password-reset` | `users.password_status`, audit table | Nao migrar senha em texto; revisar com cuidado. |
| `usuarios` | `index.html:2394`, `index.html:2465`, `index.html:11543`, `dashboard.html` indireto via Auth | R/RT | `GET /api/users` | `users` | Listagem admin e reconstrucao de indices. |
| `usuarios/{uid}` | `scripts/controladordeatualizacao.py:122`, `Automus/scripts/controladordeatualizacao.py:247`, `:1534`, `:1605` | R | `POST /api/auth/validate-admin` ou `GET /api/me` | `users` | Validacao de permissao admin no Automus. |
| `solicitacoesCadastro` | `index.html:11190`, `index.html:11276`, `index.html:11377`, `index.html:11378` | R/W/RT | `GET/POST /api/signup-requests` | `signup_requests` | Solicitacoes pendentes de cadastro. |
| `solicitacoesCadastro/{id}` | `index.html:2151`, `:2205`, `:2237`, `:2244`, `:2466`, `:2497`, `:10599` | R/W | `GET/PATCH/DELETE /api/signup-requests/:id` | `signup_requests` | Aprovacao, recusa e migracao de setor. |
| `usuariosBanidos` | `index.html:2320`, `index.html:11605` | R/RT | `GET /api/banned-users` | `banned_users` | Lista admin e indices. |
| `usuariosBanidos/{uid}` | `index.html:2289`, `:2367`, `:2378`, `:11796` | R/W | `PUT/DELETE /api/banned-users/:id` | `banned_users` | Banimento/desbanimento. |
| `nicknamesSimple` | `index.html:10738`, `:11557` | R | `GET /api/users/nickname-availability` | indice unique em `users.nickname` | Nao precisa virar tabela principal. |
| `nicknamesSimple/{key}` | `index.html:11563`, `:11573`, `:11719` | W | `POST /api/users/rebuild-indexes` | constraints/views | Substituir por constraint e consulta SQL. |
| `nicknamesAuth` | `index.html:10744`, `:11348`, `:11617` | R | `GET /api/users/nickname-availability` | constraints/views | Indice auxiliar Firebase. |
| `nicknamesAuth/{key}` | `index.html:2171`, `:2198`, `:2297`, `:11623`, `:11633` | W | `POST /api/users/rebuild-indexes` | constraints/views | Substituir por SQL. |
| `nicknamesSolic` | `index.html:10746`, `:11488`, `:11672` | R/W | `GET /api/users/nickname-availability` | `signup_requests` + query | Contagem de solicitacoes pendentes por nickname. |
| `nicknamesSolic/{key}` | `index.html:11678`, `:11688` | W | `POST /api/signup-requests/reindex` | view/query | Nao migrar como entidade independente. |
| `nicknamesSolicCracha` | `index.html:11360`, `:11697` | R | `GET /api/signup-requests/duplicate-check` | `signup_requests(nickname,badge,status)` | Checagem nickname+cracha. |
| `nicknamesSolicCracha/{key}` | `index.html:11512`, `:11526`, `:11701`, `:11710` | W | `POST /api/signup-requests/reindex` | constraint/query | Substituir por SQL. |

### Contagem

| Endereco Firebase | Arquivo/linha raiz | Op | Vai para API alvo | Vai para SQL alvo | Observacao |
| --- | --- | --- | --- | --- | --- |
| `contagens` | `index.html:6026`, `:6133`, `:8106`, `:8579`, `dashboard.html:2799` | R/RT | `GET /api/counting/sessions` | `counting_sessions`, `counting_items`, `counting_empty_checks` | Historico e progresso geral. |
| `contagens/{data}/{usuario}` | `index.html:5680`, `:7844`, `:8255`, `:8550` | R/W | `GET/POST /api/counting/sessions` | mesmas tabelas | Registros finais por usuario/data. |
| `contagens/{data}/{usuario}/_etiquetas` | `index.html:3527` | W | `POST /api/labels/jobs` | `label_print_jobs(source='contagens_fallback')` | Fallback quando `etiquetasGeradas` bloqueia. |
| `contagens/{data}/{usuario}/{id}_corrigido` | `index.html:8552` | W | `POST /api/counting/sessions/:id/reassign` | `counting_sessions`, audit table | Correcao de usuario no historico. |
| `contagemRascunhos/{uid}` | `index.html:5202`, `:8107`, `:8580` | R/W | `GET/PUT /api/counting/drafts/me` | `counting_drafts` | Backup remoto do rascunho. |
| `contagemAtual/{ciclo}/usuarios/{usuario}/_rascunho_atual` | `index.html:5187`, `:5192`, `:8692` | R/W | `GET/PUT /api/counting/live/:cycle/draft` | `counting_drafts` ou cache TTL | Rascunho vivo por ciclo. |
| `contagemAtual/{ciclo}/usuarios/{usuario}/_progresso_itens` | `index.html:5486`, `:5555` | W | `PUT /api/counting/live/:cycle/progress-items` | `counting_draft_progress` ou cache | Progresso vivo. |
| `contagemAtual/{ciclo}/usuarios/{usuario}/_progresso_grupos` | `index.html:5487`, `:5556` | W | `PUT /api/counting/live/:cycle/progress-groups` | `counting_draft_progress` ou cache | Progresso por grupo. |
| `contagemAtual/{ciclo}/usuarios/{usuario}/_presenca` | `index.html:5488`, `:5517`, `:5524`, `:5557` | W | `PUT /api/counting/live/:cycle/presence` | `counting_machine_status` ou cache TTL | Presenca em tempo real. |
| `contagemStatusMaquinas` | `index.html:5789`, `:8693` | R/W | `GET/DELETE /api/counting/machine-status` | `counting_machine_status` | Status global por maquina. |
| `contagemStatusMaquinas/{ciclo}` | `index.html:5821` | RT | `GET/SSE /api/counting/live/:cycle/machine-status` | `counting_machine_status` ou cache | Ideal usar SSE/WebSocket. |
| `contagemStatusMaquinas/{ciclo}/{maquina}/{usuario}` | `index.html:5460` | W | `PUT /api/counting/live/:cycle/machines/:machine/users/:user` | `counting_machine_status` | Status individual. |
| `contagemControle/resetGlobal` | `index.html:5141`, `:5155`, `:8691` | R/W/RT | `GET/POST /api/counting/reset-events` | `counting_control_events` | Zerar ciclo. |

### Etiquetas

| Endereco Firebase | Arquivo/linha raiz | Op | Vai para API alvo | Vai para SQL alvo | Observacao |
| --- | --- | --- | --- | --- | --- |
| `etiquetasGeradas/{data}/{usuario}` | `index.html:3524`, `dashboard.html:2800` | R/W | `GET/POST /api/labels/jobs` | `label_print_jobs` | Evento de geracao de etiquetas. |
| `rankingEtiquetas/{usuario}` | `index.html:3532`, `dashboard.html:2801` | R/W | `GET /api/labels/ranking` | view sobre `label_print_jobs` ou `label_user_ranking` | Preferir recalcular por query. |

### Dashboard e avaliador

| Endereco Firebase | Arquivo/linha raiz | Op | Vai para API alvo | Vai para SQL alvo | Observacao |
| --- | --- | --- | --- | --- | --- |
| `dashboardConfig/paineis/{id}` | `dashboard.html:836` | W | `PATCH /api/dashboard/panels/:id` | `dashboard_panels` | Limite e codigos ocultos. |
| `dashboardConfig/paineis` | `dashboard.html:2802` | R | `GET /api/dashboard/panels` | `dashboard_panels` | Config compartilhada do dashboard. |
| `dashboardConfig/avaliadorPedidos/{codigoKey}` | `dashboard.html:1841` | W | `PATCH /api/purchase-evaluations/:code` | `purchase_evaluations` | Decisao e status kanban. |
| `dashboardConfig/avaliadorPedidos` | `dashboard.html:2803` | R | `GET /api/purchase-evaluations` | `purchase_evaluations` | Dados do avaliador. |

### Historico Cooperat

| Endereco Firebase | Arquivo/linha raiz | Op | Vai para API alvo | Vai para SQL alvo | Observacao |
| --- | --- | --- | --- | --- | --- |
| `historicoComprasCooperat` | `dashboard.html:2804` | R | `GET /api/cooperat/history` ou `GET /api/cooperat/history/:code` | `cooperat_purchase_codes`, `cooperat_purchase_events` | Dashboard usa como base principal, com JSON local como fallback. |
| `historicoComprasCooperat` | `scripts/importar_historico_cooperat_firebase.py:17`, `:113` | W | `POST /api/admin/cooperat/import` | `cooperat_import_runs`, `cooperat_purchase_codes`, `cooperat_purchase_events` | Substituir script Firebase por migrador SQL. |

### Ocorrencias

| Endereco Firebase | Arquivo/linha raiz | Op | Vai para API alvo | Vai para SQL alvo | Observacao |
| --- | --- | --- | --- | --- | --- |
| `dashboardConfig/ocorrenciasCampos` | `index.html:12015`, `:12247`, `:12463` | R/W/RT | `GET/PATCH /api/settings/occurrence-fields` | `app_settings(key='occurrences.fields')` | Listas de tipos, gravidades, status, setores e tratadores. |
| `dashboardConfig/ocorrenciasAvaliadorSenha` | `index.html:12017`, `:12211` | R/W | `GET/PATCH /api/settings/occurrence-evaluator` | `app_settings` ou `occurrence_settings` | Ideal armazenar hash, nao senha pura. |
| `ocorrencias/{id}` | `index.html:12020`, `:12605`, `:12635`, `:12664`, `:12704`, `:12787` | R/W/RT | `GET/POST/PATCH /api/occurrences` | `occurrences`, `occurrence_history` | Caminho primario. |
| `chatGlobal/ocorrencias/{id}` | `index.html:12021`, `:12613`, `:12798` | R/W/RT | `GET/POST/PATCH /api/occurrences?source=fallback` | `occurrences(source_path='chatGlobal/ocorrencias')` | Fallback legado; deduplicar por `id`. |

### Chat

| Endereco Firebase | Arquivo/linha raiz | Op | Vai para API alvo | Vai para SQL alvo | Observacao |
| --- | --- | --- | --- | --- | --- |
| `chatRooms/{room}/messages` | `index.html:13255`, `:13522`, `:13907`, `:13908` | R/W/RT | `GET/POST /api/chat/rooms/:room/messages` + SSE/WebSocket | `chat_messages` | Mensagens por sala. |
| `chatRooms/{room}/senha` | `index.html:13615`, `:13878` | R/W | `GET/PATCH /api/chat/rooms/:room/password` | `chat_rooms.password_hash` | Migrar para hash. |
| `chatRooms/{room}/typing/{uid}` | `index.html:13783`, `:13789` | W/RT | `PUT/DELETE /api/chat/rooms/:room/typing/me` | cache TTL, nao SQL principal | Dado transitorio; usar Redis/SSE/WebSocket. |
| `chatReadState/{uid}` | `index.html:13373` | R | `GET /api/chat/read-state/me` | `chat_read_states` | Estado de leitura por usuario. |
| `chatReadState/{uid}/{room}` | `index.html:13364` | W | `PUT /api/chat/rooms/:room/read-state` | `chat_read_states` | Ultima leitura por sala. |

### Automus releases

| Endereco Firebase | Arquivo/linha raiz | Op | Vai para API alvo | Vai para SQL alvo | Observacao |
| --- | --- | --- | --- | --- | --- |
| `automus/releases/latest` ou `version.json.updateManifestFirebasePath` | `Automus/scripts/preparar_release_automus.py:86`, `:212`; `Automus/scripts/controladordeatualizacao.py:1758` | R/W | `GET/PUT /api/automus/releases/latest` | `automus_releases` | Manifesto pode ficar tambem como arquivo HTTP; ZIP nao deve ir para SQL. |

## Arquivos destino recomendados para a proxima etapa

Criar estes arquivos quando iniciar implementacao:

| Arquivo destino novo | Conteudo |
| --- | --- |
| `scripts/migration/export_firebase.py` | Exporta snapshot Firebase por caminho para JSON bruto. |
| `scripts/migration/inspect_firebase_export.py` | Mede registros, chaves e inconsistencias por endereco. |
| `scripts/migration/migrate_cooperat_to_sql.py` | Carga piloto de `historicoComprasCooperat` para SQL. |
| `scripts/migration/migrate_inventory_to_sql.py` | Carga de `estoqueGlobal` e planilhas para SQL. |
| `scripts/migration/compare_firebase_sql.py` | Compara totais/checksums Firebase x SQL. |
| `backend/` ou `api/` | API que substitui acesso direto Firebase no navegador. |
| `db/schema.sql` ou migracoes ORM | Schema das tabelas listadas no plano. |

## Ordem de substituicao por endereco

1. `historicoComprasCooperat`: migrar primeiro como piloto SQL.
2. `estoqueGlobal`: migrar leitura do dashboard para API, depois escrita Automus.
3. `dashboardConfig/avaliadorPedidos`: migrar junto com dashboard.
4. `contagens`: migrar historico finalizado; depois rascunho/presenca.
5. `usuarios` e `solicitacoesCadastro`: migrar regras para API, mantendo Firebase Auth se necessario.
6. `ocorrencias`: migrar caminho primario e fallback.
7. `etiquetasGeradas` e `rankingEtiquetas`: migrar eventos e gerar ranking por query.
8. `chatRooms` e `chatReadState`: migrar por ultimo por depender de tempo real.
9. `automus/releases`: adaptar quando Automus ja estiver usando API.
