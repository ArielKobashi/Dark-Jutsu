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

Se `DARK_JUTSU_API_TOKEN` for definido, as chamadas precisam enviar:

```text
Authorization: Bearer <token>
```

ou:

```text
X-API-Token: <token>
```

## Endpoints iniciais

```text
GET /health
GET /api/inventory?limit=100&offset=0&q=texto
GET /api/inventory/{codigo}
GET /api/users?limit=100&offset=0
GET /api/signup-requests?limit=100
GET /api/banned-users?limit=100
GET /api/dashboard
PUT /api/dashboard/panels/{id}
PUT /api/dashboard/evaluations/{legacyKey}
GET /api/counting/sessions?limit=100
GET /api/counting/sessions/{sessionId}/items?limit=500
GET /api/counting/drafts?limit=100
GET /api/counting/machine-status?limit=200
GET /api/labels/jobs?limit=100
GET /api/settings/{key}
GET /api/cooperat/history/{codigo}?limit=200
GET /api/occurrences?limit=100
GET /api/chat/rooms
GET /api/chat/rooms/{roomId}/messages?limit=100
GET /api/automus/releases/{channel}
```

## Papel na migracao

Esta API ainda e uma ponte inicial. Ela permite trocar leituras do frontend e do Automus por SQL de forma controlada, antes de implementar escritas, validacao de Firebase Auth no backend e escrita dupla.

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
