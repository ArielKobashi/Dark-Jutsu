# Analise de termino da integracao Firebase -> SQL

Data: 2026-07-01

Atualizacao 2026-07-11:

- `/api/me` agora retorna tambem o cadastro SQL do usuario autenticado, permitindo validacao de sessao SQL-first no frontend.
- `index.html` valida usuario por SQL antes de consultar `usuarios/{uid}` no Firebase.
- Listas administrativas de solicitacoes, usuarios e banidos usam polling SQL-first.
- Chat privado deixou de expor senha pura no frontend quando a API esta ativa: `password-status`, `verify-password` e `PUT password` usam hash no PostgreSQL.
- Admin consegue limpar mensagens da sala por `DELETE /api/chat/rooms/{roomId}/messages`.
- Configuracoes de ocorrencias (`occurrences.fields` e `occurrences.evaluator_password`) passaram para SQL-first via `app_settings`.
- Checagem publica de nickname entrou em `GET /api/nicknames/{nickname}/status`.
- Integridade raw-vs-SQL rerodada em 2026-07-11 para `users`, `dashboard`, `counting`, `occurrences`, `chat`, `automus`, `inventory` e `cooperat`: `0` findings em todos.
- Criado endpoint operacional `GET /api/ops/status`.
- Criado modo SQL-only inicial no frontend para bloquear wrappers RTDB globais.
- Criado auditor de dependencias Firebase restantes: `scripts/auditar_firebase_restante.py`; primeira execucao encontrou `719` ocorrencias, incluindo imports, fallbacks e chamadas diretas.
- Criados scripts de ensaio e restore:
  - `scripts/ensaio_sql_only_darkjutsu.bat`
  - `scripts/testar_restore_backup_postgres_darkjutsu.bat`
- Criado runbook de corte: `docs/sql-cutover-runbook.md`.
- `dashboard.html` agora depende de `GET /api/dashboard/snapshot` e dos endpoints SQL de painel/avaliacao/ajuste quando a API esta ativa; os fallbacks RTDB desses fluxos foram cortados.
- `label-editor.html` agora usa `/api/me` e `app_settings/label.config`; o listener RTDB de configuracao compartilhada foi removido.
- `index.html` deixou de cair para RTDB em validacao de sessao SQL, parte dos fluxos admin, ocorrencias, chat SQL e rascunho/presenca de contagem quando a API esta disponivel.
- Automus ganhou modo operacional `AUTOMUS_SQL_ONLY=1` com `DARK_JUTSU_API_TOKEN`: atualizacao, controlador e build pulam dependencias obrigatorias de Firebase no caminho SQL-only.

Atualizacao 2026-07-12:

- `index.html` deixou de importar SDK Firebase; o frontend principal usa autenticacao SQL local.
- Estoque inicial passou a vir de `/api/dashboard/snapshot`; atualizacao manual de estoque passou a usar `POST /api/inventory/automus-update`.
- Fluxos de admin/cadastro/usuarios/banidos, chat, read-state, typing, ocorrencias, contagem viva/rascunhos/reset global e download de release Automus foram fechados em SQL/API no `index.html`.
- Escritas diretas restantes de chat/cadastro/ocorrencias/estoque para RTDB foram removidas ou transformadas em falha fechada.
- `dashboard.html` e `label-editor.html` usam autenticacao SQL local, sem `databaseURL` do Realtime Database.
- Automus build/update/release passou a SQL-only por padrao; `Automus/scripts/firebase_config.json` foi removido.
- Controladores Automus agora exigem `DARK_JUTSU_API_TOKEN` e nao validam mais admin/mod no Realtime Database.
- Automus update raiz e empacotado nao fazem mais backup remoto, leitura ou escrita final no banco legado; a publicacao termina na API SQL.
- Importador historico direto para Realtime Database foi bloqueado e aponta para o motor SQL de migracao.
- Firebase Auth foi substituido por autenticacao SQL local na API e nos HTMLs principais.
- Auditoria estatica caiu para `0` achados nos alvos principais.
- API `/health` respondeu em `http://192.168.5.44:8765`; `127.0.0.1:8765` nao respondeu nesta rodada. `GET /api/ops/status` retornou `401` sem credencial administrativa, como esperado.

## Estado atual

Concluido:

- PostgreSQL local portatil em `127.0.0.1:5433`.
- Schema SQL aplicado com seguranca/RLS/auditoria.
- Dados do export Firebase migrados para SQL com integridade `0` findings:
  - Cooperat
  - Estoque
  - Usuarios/solicitacoes/banidos
  - Dashboard/avaliador/configuracoes de ocorrencia
  - Contagens/etiquetas
  - Ocorrencias
  - Chat
  - Automus/releases
- API SQL local criada em `api/dark_jutsu_api.py`.
- Atalhos da API:
  - `api/iniciar_api.bat`
  - `api/status_api.bat`
  - `api/parar_api.bat`

## Endpoints ja existentes

| Area | Endpoint | Status |
| --- | --- | --- |
| Saude | `GET /health` | testado |
| Estoque | `GET /api/inventory` | testado |
| Estoque | `GET /api/inventory/{codigo}` | implementado |
| Estoque | `POST /api/inventory/automus-update` | testado com export completo |
| Usuarios | `GET /api/users` | testado |
| Usuarios | `PATCH /api/users/{id}` | testado |
| Usuarios | `POST /api/users/{id}/ban` | testado |
| Usuarios | `POST /api/users/{id}/reset-password` | testado |
| Cadastro | `GET /api/signup-requests` | testado |
| Cadastro | `POST /api/signup-requests` | implementado; publico, sem senha pura no SQL |
| Cadastro | `PATCH /api/signup-requests/{id}` | testado |
| Cadastro | `POST /api/signup-requests/{id}/approve` | testado |
| Nicknames | `GET /api/nicknames/{nickname}/status` | implementado e testado |
| Banidos | `GET /api/banned-users` | implementado |
| Banidos | `DELETE /api/banned-users/{id}` | testado |
| Dashboard | `GET /api/dashboard` | implementado |
| Dashboard | `GET /api/dashboard/snapshot` | implementado e testado; `dashboard.html` usa SQL como caminho obrigatorio quando a API esta ativa |
| Dashboard | `PUT /api/dashboard/panels/{id}` | testado |
| Dashboard | `PUT /api/dashboard/evaluations/{legacyKey}` | testado |
| Dashboard | `DELETE /api/dashboard/evaluations/{legacyKey}` | implementado |
| Estoque | `PUT /api/inventory/{codigo}/adjustment` | implementado; usado pelo dashboard para ajustes manuais |
| Contagens | `GET /api/counting/sessions` | testado |
| Contagens | `POST /api/counting/sessions` | testado |
| Contagens | `PATCH /api/counting/sessions/{sessionId}/user` | implementado; falta teste manual admin |
| Contagens | `GET /api/counting/history` | testado; alimenta relatorio/historico com formato legado |
| Contagens | `GET /api/counting/sessions/{sessionId}/items` | implementado |
| Contagens | `GET /api/counting/drafts` | implementado |
| Contagens | `PUT /api/counting/drafts` | testado |
| Contagens | `DELETE /api/counting/drafts/{uid}` | testado |
| Contagens | `GET /api/counting/machine-status` | implementado |
| Contagens | `PUT /api/counting/machine-status` | testado |
| Contagens | `POST /api/counting/reset` | implementado; nao disparado em teste real por ser destrutivo |
| Etiquetas | `GET /api/labels/jobs` | testado |
| Etiquetas | `POST /api/labels/jobs` | testado |
| Configuracoes | `GET /api/settings/{key}` | testado |
| Configuracoes | `PUT /api/settings/{key}` | testado |
| Cooperat | `GET /api/cooperat/history/{codigo}` | implementado |
| Ocorrencias | `GET /api/occurrences` | implementado |
| Ocorrencias | `POST /api/occurrences` | testado |
| Ocorrencias | `PATCH /api/occurrences/{id}` | testado |
| Chat | `GET /api/chat/rooms` | testado |
| Chat | `GET /api/chat/rooms/{roomId}/password-status` | implementado e testado |
| Chat | `GET /api/chat/rooms/{roomId}/messages` | implementado |
| Chat | `POST /api/chat/rooms/{roomId}/messages` | testado |
| Chat | `DELETE /api/chat/rooms/{roomId}/messages` | implementado; exige admin |
| Chat | `PUT /api/chat/rooms/{roomId}/password` | implementado; grava hash |
| Chat | `POST /api/chat/rooms/{roomId}/verify-password` | implementado e testado |
| Chat | `GET /api/chat/read-state/{uid}` | implementado e testado |
| Chat | `PUT /api/chat/read-state` | testado |
| Automus | `GET /api/automus/releases/{channel}` | testado |
| Automus | `PUT /api/automus/releases/{channel}` | testado |

## O que ainda falta para terminar a integracao

### 1. Autenticacao real da API

Status: implementado em SQL local.

A API agora aceita `Authorization: Bearer <token SQL local>`, emitido por `POST /api/auth/login`, localiza o usuario em `users`, bloqueia usuarios inativos/banidos e aplica `app.user_id`/`app.role` por requisicao. `DARK_JUTSU_API_TOKEN` continua existindo como token de servico para scripts locais.

Ainda falta para endurecer antes de producao:

- criar usuario PostgreSQL de login para a API que nao seja owner/superuser.
- definir `DARK_JUTSU_ALLOWED_ORIGINS` com a origem real do app em vez de `*`;
- revisar endpoints administrativos com checagens explicitas de papel alem das politicas SQL: primeira camada adicionada em 2026-07-03 para usuarios/cadastro/banidos, dashboard, settings, reset de contagem e publicacao Automus.

### 2. Endpoints de escrita

O banco ja tem tabelas, mas o frontend e o Automus ainda escrevem no Firebase. Para cortar o Firebase Database, precisa implementar estes grupos:

| Area atual Firebase | Escritas que faltam na API |
| --- | --- |
| `estoqueGlobal` | Automus update transacional pronto em `POST /api/inventory/automus-update`; ajustes manuais do dashboard usam SQL; falta validar fluxo real do Automus com `AUTOMUS_SQL_ONLY=1` |
| `dashboardConfig/paineis` | frontend do dashboard usa SQL quando a API esta ativa |
| `dashboardConfig/avaliadorPedidos` | frontend do dashboard usa SQL para salvar/remover quando a API esta ativa |
| `usuarios` | admin, lista administrativa, alteracao de nivel, ativar/desativar, banir e resetar status de senha usam SQL/API; usuarios sem senha migrada exigem reset SQL |
| `solicitacoesCadastro` | lista admin, criacao publica e aprovacao usam SQL/API; senha da solicitacao fica hasheada ate aprovacao |
| `usuariosBanidos` | banir/apagar banido pronto no admin; falta revisar fluxo final de reativacao/desbanimento apos corte Firebase |
| `nicknames*` | endpoint publico de status implementado; falta trocar todos os indices auxiliares Firebase por consultas SQL |
| `contagens` | finalizacao, relatorio/historico/reaplicacao e correcao de usuario tentam SQL antes do Firebase; falta validar correcao no fluxo admin real e substituir tempo real |
| `contagemAtual` | rascunho/progresso principal vai para SQL; falta tempo real por SSE/WebSocket para substituir `onValue` |
| `contagemRascunhos` | salvar/remover rascunhos pronto na API e frontend tenta SQL antes do Firebase |
| `contagemStatusMaquinas` | salvar status/progresso pronto na API e frontend tenta SQL antes do Firebase |
| `contagemControle/resetGlobal` | endpoint SQL implementado e frontend tenta SQL; teste destrutivo final deve ser feito em janela combinada |
| `etiquetasGeradas` | pronto na API inicial; frontend tenta SQL antes do fallback Firebase |
| `rankingEtiquetas` | substituir por query/view SQL; evento base ja vai para `label_print_jobs` |
| `ocorrencias` | pronto na API inicial para criar/atualizar/tratar com historico; frontend agora tenta polling SQL antes dos listeners Firebase; falta validar autenticacao final |
| `dashboardConfig/ocorrenciasCampos` | SQL-first via `app_settings/occurrences.fields` |
| `dashboardConfig/ocorrenciasAvaliadorSenha` | SQL-first via `app_settings/occurrences.evaluator_password`; proximo endurecimento e hash/segredo server-side |
| `chatRooms/*/messages` | frontend agora tenta polling SQL antes do listener Firebase e envio SQL nao publica mais no Firebase quando bem-sucedido |
| `chatReadState` | leitura e escrita SQL-only no frontend principal |
| `chatRooms/*/typing` | Firebase removido no frontend principal; estado fica local ate entrar WebSocket/SSE/TTL |
| `chatRooms/*/senha` | implementado em SQL com hash e verificacao server-side; fallback Firebase ainda existe para contingencia |
| `estoqueGlobal/configuracoesEtiquetas` | `label-editor.html` salva/carrega `label.config` no SQL; listener/fallback RTDB removido dessa tela |
| `automus/releases/latest` | publicar manifest via API/SQL pronto; script de preparo tenta SQL automaticamente quando a API esta ativa |

### 3. Troca do frontend para API

Arquivos com Firebase ainda ativo:

- `index.html`, `dashboard.html` e `label-editor.html` usam auth SQL local e nao carregam SDK Firebase.
- Scripts Automus/controlador/importador nao mantem mais caminho operacional de Realtime Database; ferramentas em `scripts/migration` continuam apenas para export/delta final.

Falta criar uma camada JS de dados, por exemplo `api-client.js`, e substituir por etapas:

1. Leituras simples:
   - estoque;
   - dashboard;
   - users/admin;
   - ocorrencias;
   - chat historico;
   - Automus release.
2. Escritas administrativas:
   - dashboard panels;
   - avaliador;
   - ocorrencias;
   - usuarios/cadastro admin: primeira versao implementada.
3. Escritas operacionais:
   - contagens: primeira versao de escrita implementada;
   - etiquetas;
   - chat;
   - estoque/Automus.

### 4. Adaptacao do Automus

Arquivos principais revisados nesta etapa:

- `scripts/atualizacao/automus_update.py`
- `Automus/scripts/atualizacao/automus_update.py`
- `Automus/scripts/preparar_release_automus.py`
- `Automus/scripts/automus_self_update.py`
- `Automus/scripts/controladordeatualização.py`
- `scripts/controladordeatualização.py`

Status:

- leitura de `estoqueGlobal.json` foi removida do fluxo operacional Automus SQL-only;
- PATCH/PUT de blocos do estoque foram removidos do fluxo operacional; publicacao usa endpoint transacional SQL;
- gravar backup em `inventory_snapshots`: pronto no endpoint SQL;
- publicar release em `automus_releases`;
- consultar update por URL/API/local; fallback por manifest no Realtime Database foi removido do controlador;
- manter compatibilidade com `latest.json`/arquivo local durante transicao.

### 5. Tempo real

Firebase hoje entrega `onValue` para chat, ocorrencias, usuarios, status de maquinas e estoque.

Opcoes para concluir:

- polling simples na primeira versao;
- SSE para atualizacoes leves;
- WebSocket para chat/typing/progresso vivo;
- Redis ou tabela TTL para dados transitorios.

Recomendacao inicial:

- polling para dashboard, ocorrencias, mensagens de chat, usuarios e contagem viva iniciado no frontend principal;
- WebSocket/SSE depois para chat e contagem viva;
- nao persistir `typing` como dado historico definitivo.

### 6. Corte controlado

Antes de desligar escrita no Firebase:

1. Rodar nova exportacao final do Firebase.
2. Reexecutar migradores idempotentes.
3. Rodar integridade todos os dominios.
4. Ativar API em modo leitura.
5. Migrar um fluxo de escrita pequeno primeiro, como dashboard/avaliador.
6. Rodar escrita dupla em estoque/contagem se necessario.
7. Congelar Firebase Database.
8. Fazer delta final e comparar.
9. Remover chaves Firebase Database do frontend.

## Proxima implementacao recomendada

Fluxos de escrita de menor risco ja implementados:

1. `PUT /api/dashboard/panels/{id}`: implementado e testado.
2. `PUT /api/dashboard/evaluations/{legacyKey}`: implementado e testado.
3. `POST /api/occurrences`: implementado e testado.
4. `PATCH /api/occurrences/{id}`: implementado e testado.
5. `POST /api/chat/rooms/{roomId}/messages`: implementado e testado.
6. `POST /api/labels/jobs`: implementado e testado.
7. Endpoints admin de usuarios/cadastro/banidos: implementados e testados.

Proximos fluxos grandes:

1. `POST /api/counting/sessions`
2. `POST /api/inventory/automus-update`: implementado e testado; falta teste com Automus real e ativar `AUTOMUS_SQL_ONLY=1` apos validacao
3. endpoints de criacao publica de cadastro e validacao de nickname
4. validar correcao/movimento de historico de contagem no fluxo admin real

## Como ajudar a descobrir o restante

O jeito mais rapido e listar os fluxos reais usados no dia a dia e testar um por um:

- aprovar um cadastro;
- banir/desbanir usuario;
- mudar nivel de usuario;
- salvar painel do dashboard;
- avaliar pedido;
- abrir/tratar ocorrencia;
- enviar mensagem no chat;
- fazer contagem;
- gerar etiqueta;
- rodar Automus completo;
- preparar/publicar release Automus.

Cada fluxo testado vira um endpoint e uma substituicao direta no frontend/script.
