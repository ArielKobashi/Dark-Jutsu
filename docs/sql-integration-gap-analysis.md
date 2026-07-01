# Analise de termino da integracao Firebase -> SQL

Data: 2026-06-30

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
| Cadastro | `GET /api/signup-requests` | testado |
| Banidos | `GET /api/banned-users` | implementado |
| Dashboard | `GET /api/dashboard` | implementado |
| Dashboard | `PUT /api/dashboard/panels/{id}` | testado |
| Dashboard | `PUT /api/dashboard/evaluations/{legacyKey}` | testado |
| Contagens | `GET /api/counting/sessions` | testado |
| Contagens | `GET /api/counting/sessions/{sessionId}/items` | implementado |
| Contagens | `GET /api/counting/drafts` | implementado |
| Contagens | `GET /api/counting/machine-status` | implementado |
| Etiquetas | `GET /api/labels/jobs` | testado |
| Configuracoes | `GET /api/settings/{key}` | testado |
| Cooperat | `GET /api/cooperat/history/{codigo}` | implementado |
| Ocorrencias | `GET /api/occurrences` | implementado |
| Chat | `GET /api/chat/rooms` | testado |
| Chat | `GET /api/chat/rooms/{roomId}/messages` | implementado |
| Automus | `GET /api/automus/releases/{channel}` | testado |

## O que ainda falta para terminar a integracao

### 1. Autenticacao real da API

Hoje a API aceita `DARK_JUTSU_API_TOKEN` opcional e usa `app.role='service'` no SQL. Isso serve para desenvolvimento local, mas nao para producao.

Falta:

- validar Firebase ID token no backend enquanto Firebase Auth continuar ativo;
- carregar `users.role`, `users.active` e `banned_users` a partir do SQL;
- aplicar `app.user_id` e `app.role` por requisicao;
- restringir CORS para a origem real do app;
- criar usuario PostgreSQL de login para a API que nao seja owner/superuser.

### 2. Endpoints de escrita

O banco ja tem tabelas, mas o frontend e o Automus ainda escrevem no Firebase. Para cortar o Firebase Database, precisa implementar estes grupos:

| Area atual Firebase | Escritas que faltam na API |
| --- | --- |
| `estoqueGlobal` | atualizar estoque pelo Automus, aplicar ajustes manuais, salvar `configContagem`, criar backup/snapshot |
| `dashboardConfig/paineis` | pronto na API inicial; falta trocar frontend |
| `dashboardConfig/avaliadorPedidos` | pronto na API inicial; falta trocar frontend |
| `usuarios` | aprovar solicitacao, alterar nivel, ativar/desativar, resetar status de senha |
| `solicitacoesCadastro` | criar solicitacao, aprovar, rejeitar, remover duplicadas |
| `usuariosBanidos` | banir/desbanir |
| `nicknames*` | substituir por constraints/consultas SQL e endpoints de validacao |
| `contagens` | criar sessao, gravar itens contados, verificacoes vazias e sessoes importadas |
| `contagemAtual` | salvar progresso vivo ou substituir por WebSocket/SSE/TTL |
| `contagemRascunhos` | salvar/remover rascunhos |
| `contagemStatusMaquinas` | salvar status/progresso por maquina |
| `contagemControle/resetGlobal` | registrar evento administrativo de reset |
| `etiquetasGeradas` | registrar job de etiqueta |
| `rankingEtiquetas` | recalcular via SQL/view em vez de transacao Firebase |
| `ocorrencias` | criar, atribuir, atualizar status, tratar, anexar historico |
| `dashboardConfig/ocorrenciasCampos` | salvar listas de campos |
| `dashboardConfig/ocorrenciasAvaliadorSenha` | trocar por hash/segredo controlado na API |
| `chatRooms/*/messages` | enviar mensagem |
| `chatReadState` | atualizar leitura |
| `chatRooms/*/typing` | substituir por dado transitorio via WebSocket/SSE/TTL |
| `chatRooms/*/senha` | criar/alterar senha com hash, nunca texto puro |
| `estoqueGlobal/configuracoesEtiquetas` | salvar configuracao do editor de etiquetas |
| `automus/releases/latest` | publicar manifest de release via API/SQL |

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
   - usuarios.
3. Escritas operacionais:
   - contagens;
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

Comecar pelos endpoints de escrita de menor risco:

1. `PUT /api/dashboard/panels/{id}`: implementado e testado.
2. `PUT /api/dashboard/evaluations/{legacyKey}`: implementado e testado.
3. `POST /api/occurrences`
4. `PATCH /api/occurrences/{id}`
5. `POST /api/chat/rooms/{roomId}/messages`

Depois ir para os fluxos grandes:

1. `POST /api/counting/sessions`
2. `POST /api/labels/jobs`
3. `POST /api/inventory/automus-update`

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
