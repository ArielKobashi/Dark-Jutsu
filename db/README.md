# Banco SQL do Dark-Jutsu

Ambiente local PostgreSQL para suportar a migracao Firebase -> SQL.

## Subir

```powershell
Copy-Item .env.example .env
docker compose up -d
```

Adminer:

```text
http://localhost:8080
Sistema: PostgreSQL
Servidor: postgres
Usuario: dark_jutsu
Senha: dark_jutsu_dev
Base: dark_jutsu
```

## Validar

```powershell
docker compose ps
docker compose exec postgres psql -U dark_jutsu -d dark_jutsu -c "\dt"
docker compose exec postgres psql -U dark_jutsu -d dark_jutsu -f /db/check.sql
```

Se preferir pelo PowerShell local, rode o `psql` apontando para `db/check.sql` depois de instalar o cliente PostgreSQL.

## Seguranca

O arquivo `db/init/002_security.sql` cria:

- roles PostgreSQL sem login: `dark_jutsu_readonly`, `dark_jutsu_app`, `dark_jutsu_service`;
- Row Level Security nas tabelas de dados;
- views seguras para usuarios, solicitacoes e salas de chat;
- tabelas de auditoria: `audit_events` e `security_events`;
- funcoes `app_user_id()`, `app_role()`, `app_is_admin()` e `app_is_staff()`.

A API deve abrir transacoes definindo o contexto do usuario:

```sql
set local app.user_id = 'firebase-uid-ou-user-id';
set local app.role = 'op'; -- op, mod, admin ou service
```

Para tarefas de migracao/Automus, usar `app.role = 'service'`.

Em producao, use usuarios PostgreSQL com login separados do dono do schema e conceda a eles uma das roles criadas. O dono das tabelas pode contornar RLS, entao a API nao deve conectar com o owner/superuser.

## Recriar do zero

Use somente em ambiente local/dev:

```powershell
docker compose down -v
docker compose up -d
```

O schema inicial fica em `db/init/001_schema.sql` e roda automaticamente quando o volume PostgreSQL ainda nao existe.
