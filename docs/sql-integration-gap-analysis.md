# Analise de termino da integracao Firebase -> SQL

Data: 2026-07-01

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
| Usuarios | `GET /api/users` | testado |
| Usuarios | `PATCH /api/users/{id}` | testado |
| Usuarios | `POST /api/users/{id}/ban` | testado |
| Usuarios | `POST /api/users/{id}/reset-password` | testado |
| Cadastro | `GET /api/signup-requests` | testado |
| Cadastro | `PATCH /api/signup-requests/{id}` | testado |
| Cadastro | `POST /api/signup-requests/{id}/approve` | testado |
| Banidos | `GET /api/banned-users` | implementado |
| Banidos | `DELETE /api/banned-users/{id}` | testado |
| Dashboard | `GET /api/dashboard` | implementado |
| Dashboard | `PUT /api/dashboard/panels/{id}` | testado |
| Dashboard | `PUT /api/dashboard/evaluations/{legacyKey}` | testado |
| Contagens | `GET /api/counting/sessions` | testado |
| Contagens | `POST /api/counting/sessions` | testado |
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
| Chat | `GET /api/chat/rooms/{roomId}/messages` | implementado |
| Chat | `POST /api/chat/rooms/{roomId}/messages` | testado |
| Chat | `PUT /api/chat/read-state` | testado |
| Automus | `GET /api/automus/releases/{channel}` | testado |
| Automus | `PUT /api/automus/releases/{channel}` | testado |

## O que ainda falta para terminar a integracao

### 1. Autenticacao real da API

Status: primeira versao implementada.

A API agora aceita `Authorization: Bearer <Firebase ID token>`, valida assinatura/issuer/audience do projeto `chat-fiasul`, localiza o usuario em `users`, bloqueia usuarios inativos/banidos e aplica `app.user_id`/`app.role` por requisicao. `DARK_JUTSU_API_TOKEN` continua existindo como token de servico para scripts locais.

Ainda falta para endurecer antes de producao:

- criar usuario PostgreSQL de login para a API que nao seja owner/superuser.
- definir `DARK_JUTSU_ALLOWED_ORIGINS` com a origem real do app em vez de `*`;
- revisar endpoints administrativos com checagens explicitas de papel alem das politicas SQL: primeira camada adicionada em 2026-07-03 para usuarios/cadastro/banidos, dashboard, settings, reset de contagem e publicacao Automus.

### 2. Endpoints de escrita

O banco ja tem tabelas, mas o frontend e o Automus ainda escrevem no Firebase. Para cortar o Firebase Database, precisa implementar estes grupos:

| Area atual Firebase | Escritas que faltam na API |
| --- | --- |
| `estoqueGlobal` | atualizar estoque pelo Automus, aplicar ajustes manuais, salvar `configContagem`, criar backup/snapshot |
| `dashboardConfig/paineis` | pronto na API inicial; falta trocar frontend |
| `dashboardConfig/avaliadorPedidos` | pronto na API inicial; falta trocar frontend |
| `usuarios` | admin inicial pronto: aprovar solicitacao, alterar nivel, ativar/desativar, banir e resetar status de senha tentam SQL antes do Firebase; falta login/API auth real e criacao publica |
| `solicitacoesCadastro` | aprovar/rejeitar pronto no admin; falta criar solicitacao publica e remover duplicadas via SQL |
| `usuariosBanidos` | banir/apagar banido pronto no admin; falta revisar fluxo final de reativacao/desbanimento apos corte Firebase |
| `nicknames*` | substituir por constraints/consultas SQL e endpoints de validacao |
| `contagens` | finalizacao de sessao pronta na API e frontend tenta SQL antes do Firebase; faltam leituras historicas totalmente por SQL e correcao/movimento de historico entre usuarios |
| `contagemAtual` | rascunho/progresso principal vai para SQL; falta tempo real por SSE/WebSocket para substituir `onValue` |
| `contagemRascunhos` | salvar/remover rascunhos pronto na API e frontend tenta SQL antes do Firebase |
| `contagemStatusMaquinas` | salvar status/progresso pronto na API e frontend tenta SQL antes do Firebase |
| `contagemControle/resetGlobal` | endpoint SQL implementado e frontend tenta SQL; teste destrutivo final deve ser feito em janela combinada |
| `etiquetasGeradas` | pronto na API inicial; frontend tenta SQL antes do fallback Firebase |
| `rankingEtiquetas` | substituir por query/view SQL; evento base ja vai para `label_print_jobs` |
| `ocorrencias` | pronto na API inicial para criar/atualizar/tratar com historico; falta validar autenticacao final |
| `dashboardConfig/ocorrenciasCampos` | salvar listas de campos |
| `dashboardConfig/ocorrenciasAvaliadorSenha` | trocar por hash/segredo controlado na API |
| `chatRooms/*/messages` | pronto na API inicial; frontend tenta SQL antes do fallback Firebase |
| `chatReadState` | pronto na API inicial; frontend tenta SQL antes do fallback Firebase |
| `chatRooms/*/typing` | substituir por dado transitorio via WebSocket/SSE/TTL |
| `chatRooms/*/senha` | criar/alterar senha com hash, nunca texto puro |
| `estoqueGlobal/configuracoesEtiquetas` | `label-editor.html` salva/carrega `label.config` no SQL primeiro; fallback Firebase mantido |
| `automus/releases/latest` | publicar manifest via API/SQL pronto; script de preparo tenta SQL automaticamente quando a API esta ativa |

### 3. Troca do frontend para API

Arquivos com chamadas Firebase ainda ativas:

- `index.html`
- `dashboard.html`
- `label-editor.html`

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

Arquivos principais ainda presos ao Firebase:

- `scripts/atualizacao/automus_update.py`
- `Automus/scripts/atualizacao/automus_update.py`
- `Automus/scripts/preparar_release_automus.py`
- `Automus/scripts/automus_self_update.py`
- `Automus/scripts/controladordeatualização.py`
- `scripts/controladordeatualização.py`

Falta:

- trocar leitura de `estoqueGlobal.json` por endpoint SQL/API;
- trocar PATCH/PUT de blocos do estoque por endpoint transacional;
- gravar backup em `inventory_snapshots`;
- publicar release em `automus_releases`;
- consultar update por `/api/automus/releases/latest`;
- manter compatibilidade com `latest.json`/arquivo local durante transicao.

### 5. Tempo real

Firebase hoje entrega `onValue` para chat, ocorrencias, usuarios, status de maquinas e estoque.

Opcoes para concluir:

- polling simples na primeira versao;
- SSE para atualizacoes leves;
- WebSocket para chat/typing/progresso vivo;
- Redis ou tabela TTL para dados transitorios.

Recomendacao inicial:

- polling para dashboard, ocorrencias e usuarios;
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
2. `POST /api/inventory/automus-update`
3. endpoints de criacao publica de cadastro e validacao de nickname
4. leituras historicas de contagem 100% SQL no frontend

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
