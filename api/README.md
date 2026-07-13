# API SQL local Dark-Jutsu

API HTTP inicial para consumir os dados migrados do PostgreSQL sem acessar Firebase Realtime Database direto no navegador.

## Iniciar

Com o PostgreSQL local ligado:

```powershell
api\iniciar_api.bat
```

Status/parada:

```powershell
api\status_api.bat
api\parar_api.bat
```

Ou diretamente:

```powershell
$env:DATABASE_URL="postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
$env:DARK_JUTSU_API_PORT="8765"
C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe api\dark_jutsu_api.py
```

## Autenticacao

A API valida dois tipos de autenticacao:

- Navegador: `POST /api/auth/login` retorna um token SQL local. `index.html`, `dashboard.html` e `label-editor.html` salvam esse token em `localStorage.darkJutsuSqlAuthToken` e enviam `Authorization: Bearer <token>`.
- Servico/script: `DARK_JUTSU_API_TOKEN`, quando definido, autoriza chamadas como `service`.

Variaveis:

```text
DARK_JUTSU_REQUIRE_AUTH=1
DARK_JUTSU_ALLOWED_ORIGINS=*
DARK_JUTSU_API_TOKEN=
DARK_JUTSU_AUTH_SECRET=
```

Para scripts, envie:

```text
Authorization: Bearer <token>
```

ou:

```text
X-API-Token: <token>
```

Com `DARK_JUTSU_REQUIRE_AUTH=1`, chamadas sem token SQL/servico recebem `401`.

Endpoints de auth:

```text
POST /api/auth/login
POST /api/auth/change-password
POST /api/auth/logout
GET /api/auth/me
```

## Endpoints iniciais

```text
GET /health
GET /api/me
GET /api/ops/status
GET /api/nicknames/{nickname}/status?badge=123
GET /api/inventory?limit=100&offset=0&q=texto
GET /api/inventory/{codigo}
POST /api/inventory/automus-update
GET /api/users?limit=100&offset=0
GET /api/users/{id}
PATCH /api/users/{id}
POST /api/users/{id}/ban
POST /api/users/{id}/reset-password
GET /api/signup-requests?limit=100
GET /api/signup-requests/{id}
POST /api/signup-requests
PATCH /api/signup-requests/{id}
POST /api/signup-requests/{id}/approve
GET /api/banned-users?limit=100
DELETE /api/banned-users/{id}
GET /api/dashboard
GET /api/dashboard/snapshot?limit=1000
PUT /api/dashboard/panels/{id}
PUT /api/dashboard/evaluations/{legacyKey}
DELETE /api/dashboard/evaluations/{legacyKey}
PUT /api/inventory/{codigo}/adjustment
GET /api/counting/sessions?limit=100
POST /api/counting/sessions
PATCH /api/counting/sessions/{sessionId}/user
GET /api/counting/history?limit=1000
GET /api/counting/sessions/{sessionId}/items?limit=500
GET /api/counting/drafts?limit=100
PUT /api/counting/drafts
DELETE /api/counting/drafts/{uid}
GET /api/counting/machine-status?limit=200
PUT /api/counting/machine-status
POST /api/counting/reset
GET /api/labels/jobs?limit=100
POST /api/labels/jobs
GET /api/settings/{key}
PUT /api/settings/{key}
GET /api/cooperat/history/{codigo}?limit=200
GET /api/occurrences?limit=100
POST /api/occurrences
PATCH /api/occurrences/{id}
GET /api/chat/rooms
GET /api/chat/rooms/{roomId}/password-status
GET /api/chat/rooms/{roomId}/messages?limit=100
POST /api/chat/rooms/{roomId}/messages
DELETE /api/chat/rooms/{roomId}/messages
PUT /api/chat/rooms/{roomId}/password
POST /api/chat/rooms/{roomId}/verify-password
GET /api/chat/read-state/{uid}
PUT /api/chat/read-state
GET /api/automus/releases/{channel}
PUT /api/automus/releases/{channel}
```

## Papel na migracao

Esta API agora concentra leitura, escrita e autenticacao SQL local para o frontend e Automus, sem depender do Firebase em tempo de execucao.

## Escritas iniciais

### Painel do dashboard

```http
PUT /api/dashboard/panels/maiores_faltas_em_entregas_parciais
Content-Type: application/json

{
  "limite": 10,
  "codigosOcultos": "2307000062",
  "atualizadoPor": "usuario"
}
```

### Avaliador de pedidos

```http
PUT /api/dashboard/evaluations/MzExMTAwMDQwMg
Content-Type: application/json

{
  "codigo": "3111000402",
  "decisao": "passivel",
  "statusManual": "aguardando_solicitacao",
  "observacao": "",
  "avaliadoEm": 1781672623617,
  "avaliadoPor": "usuario"
}
```

```http
GET /api/dashboard/snapshot?limit=1000
```

Retorna um pacote compativel com o `dashboard.html`: estoque em formato legado, `dashboardConfig/paineis`, `dashboardConfig/avaliadorPedidos`, contagens, etiquetas e ranking calculado a partir do SQL.

```http
PUT /api/inventory/0311000402/adjustment
Content-Type: application/json

{
  "legacy_key": "MDMxMTAwMDQwMg",
  "itemKey": "0311000402",
  "minimo": 2,
  "maximo": 8,
  "reposicao": 6,
  "atualizadoPor": "usuario"
}
```

Grava ajuste manual de limite em `inventory_adjustments`; o snapshot do dashboard mescla esses ajustes sobre o ultimo snapshot de estoque.

### Ocorrencias

```http
POST /api/occurrences
Content-Type: application/json

{
  "id": "ocorrencia_1783000000000_usuario",
  "criadoEm": 1783000000000,
  "data": "2026-07-01",
  "hora": "09:00",
  "operadorUid": "uid",
  "operadorNome": "usuario",
  "acusadoNome": "envolvido",
  "tipo": "Outro",
  "gravidade": "baixa",
  "descricao": "Descricao",
  "status": "aberta",
  "historico": {
    "criado": {
      "em": 1783000000000,
      "porUid": "uid",
      "porNome": "usuario",
      "acao": "criada"
    }
  }
}
```

### Chat

```http
POST /api/chat/rooms/publica/messages
Content-Type: application/json

{
  "uid": "uid",
  "nome": "usuario",
  "texto": "mensagem",
  "data": "09:30:00",
  "timestamp": 1783000200000,
  "sessionId": "sessao"
}
```

### Etiquetas

```http
POST /api/labels/jobs
Content-Type: application/json

{
  "usuario": "davi",
  "data": "2026-07-01",
  "timestamp": 1783000300000,
  "totalEtiquetas": 3,
  "totalCodigosInformados": 4,
  "porTamanho": {
    "5": 1,
    "7": 2,
    "10": 0,
    "15": 0
  },
  "teveNaoEncontrados": true
}
```

### Contagens

```http
GET /api/counting/history?limit=1000
```

Retorna `contagens` e `rascunhos` no formato compativel com os caminhos antigos do Firebase, reconstruidos a partir de `counting_sessions.raw_data` e `counting_drafts.raw_data`. Esse endpoint alimenta relatorios e historico de planilhas durante a transicao.

```http
POST /api/counting/sessions
Content-Type: application/json

{
  "usuario": "davi",
  "uid": "uid",
  "data": "2026-07-01",
  "timestamp": 1783000000000,
  "maquina": "M1",
  "itens": {
    "item_key": {
      "protheus": "123",
      "descricao": "Item",
      "saldoSistema": 5,
      "contado": 4
    }
  },
  "verificacoesVazio": {}
}
```

```http
PATCH /api/counting/sessions/{sessionId}/user
Content-Type: application/json

{
  "usuario": "novo_usuario",
  "corrigidoPor": "admin",
  "usuarioAnterior": "usuario_antigo"
}
```

Atualiza o dono de uma sessao historica de contagem no SQL e registra metadados de correcao em `raw_data`.

### Estoque Automus

```http
POST /api/inventory/automus-update
Content-Type: application/json

{
  "dados": [],
  "dadosMortos": [],
  "ajustesItens": {},
  "historicoSaldo": {},
  "movimentacoesMata185": {},
  "ultimaAtualizacao": 1783000000000,
  "atualizadoPor": "automus"
}
```

O endpoint substitui o inventario em uma transacao, grava `inventory_snapshots` e recarrega itens, enderecos, limites, ajustes, historico de saldo e movimentacoes MATA185.

```http
PUT /api/counting/drafts
Content-Type: application/json

{
  "usuario": "davi",
  "uid": "uid",
  "ciclo": "atual",
  "valores": {},
  "verificacoesVazio": {},
  "saldosSistema": {},
  "sessao": {}
}
```

```http
PUT /api/counting/machine-status
Content-Type: application/json

{
  "ciclo": "atual",
  "usuarioKey": "davi",
  "grupo": "M1",
  "usuario": "davi",
  "aberta": true,
  "contados": 10,
  "total": 20
}
```

```http
POST /api/counting/reset
Content-Type: application/json

{
  "resetAt": 1783000000000,
  "resetPor": "admin",
  "formatarContagem": true
}
```

### Configuracoes

```http
PUT /api/settings/label.config
Content-Type: application/json

{
  "value": {
    "layouts": {},
    "presets": {}
  }
}
```

### Automus release

```http
PUT /api/automus/releases/latest
Content-Type: application/json

{
  "version": "1.1.2",
  "packageUrl": "\\\\fileserver\\Almoxarifado\\0800\\automus\\Automus-v1.1.2.zip",
  "notes": ["Atualizacao"]
}
```

### Usuarios e cadastro

```http
PATCH /api/users/uid
Content-Type: application/json

{
  "nivel": "admin",
  "ativo": true
}
```

```http
POST /api/users/uid/ban
Content-Type: application/json

{
  "banidoEm": 1783000400000,
  "motivo": "administrativo"
}
```

```http
POST /api/users/uid/reset-password
Content-Type: application/json

{}
```

```http
POST /api/signup-requests/solicitacao_id/approve
Content-Type: application/json

{
  "uid": "uid_criado_no_firebase_auth",
  "nivel": "operador"
}
```

```http
PATCH /api/signup-requests/solicitacao_id
Content-Type: application/json

{
  "status": "recusado",
  "decididoEm": 1783000500000
}
```

```http
DELETE /api/banned-users/uid
```

```http
GET /api/chat/read-state/uid
```

Retorna `{ room_id: timestamp_ms }` para restaurar contadores de mensagens nao lidas sem ler `chatReadState` no Firebase.

```http
PUT /api/chat/read-state
Content-Type: application/json

{
  "user_id": "uid",
  "room_id": "publica",
  "timestamp": 1783000200000
}
```

```http
PATCH /api/occurrences/ocorrencia_1783000000000_usuario
Content-Type: application/json

{
  "status": "analisada",
  "atualizadoEm": 1783000060000,
  "atualizadoPor": "uid",
  "historico/status_1783000060000": {
    "em": 1783000060000,
    "porUid": "uid",
    "porNome": "usuario",
    "acao": "status",
    "valor": "analisada"
  }
}
```
