# Banco SQL do Dark-Jutsu

Ambiente local PostgreSQL para suportar a migracao Firebase -> SQL.

## Subir

### Opcao A: PostgreSQL local portatil

Ambiente validado em `2026-06-29` usando os binarios em:

```text
C:\Users\Davi.souza\Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql
```

Uso diario:

Interface em janela Python:

```powershell
db\abrir_sql_janela.bat
```

Na janela, use os botoes `Iniciar`, `Parar`, `Reiniciar`, `Status` e `Verificar`.
O `.bat` chama `db\abrir_sql_janela.ps1`, que localiza automaticamente o Python portatil `WPy64-3.13.12.0`.

Atalhos diretos:

```powershell
db\iniciar_sql.bat
db\parar_sql.bat
db\status_sql.bat
db\verificar_sql.bat
```

Ou pelo PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File db\postgres-server.ps1 start
powershell -NoProfile -ExecutionPolicy Bypass -File db\postgres-server.ps1 stop
powershell -NoProfile -ExecutionPolicy Bypass -File db\postgres-server.ps1 restart
powershell -NoProfile -ExecutionPolicy Bypass -File db\postgres-server.ps1 status
powershell -NoProfile -ExecutionPolicy Bypass -File db\postgres-server.ps1 check
```

Inicializar o cluster local do projeto:

```powershell
& 'C:\Users\Davi.souza\Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql\bin\initdb.exe' -D 'C:\Users\Davi.souza\Desktop\Dark-Jutsu\db\data' -U postgres --auth=trust --encoding=UTF8
Add-Content -Path 'C:\Users\Davi.souza\Desktop\Dark-Jutsu\db\data\postgresql.conf' -Value "`nport = 5433`nlisten_addresses = '127.0.0.1'`n"
& 'C:\Users\Davi.souza\Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql\bin\pg_ctl.exe' -D 'C:\Users\Davi.souza\Desktop\Dark-Jutsu\db\data' -l 'C:\Users\Davi.souza\Desktop\Dark-Jutsu\db\postgres.log' start
```

Criar login/base local:

```powershell
$psql='C:\Users\Davi.souza\Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql\bin\psql.exe'
& $psql -h 127.0.0.1 -p 5433 -U postgres -d postgres -c "do `$`$ begin if not exists (select 1 from pg_roles where rolname = 'dark_jutsu') then create role dark_jutsu login password 'dark_jutsu_dev'; end if; end `$`$;"
& 'C:\Users\Davi.souza\Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql\bin\createdb.exe' -h 127.0.0.1 -p 5433 -U postgres -O dark_jutsu dark_jutsu
```

Aplicar schema e seguranca:

```powershell
$psql='C:\Users\Davi.souza\Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql\bin\psql.exe'
& $psql -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu -v ON_ERROR_STOP=1 -f db\init\001_schema.sql
& $psql -h 127.0.0.1 -p 5433 -U postgres -d dark_jutsu -v ON_ERROR_STOP=1 -c "do `$`$ begin if not exists (select 1 from pg_roles where rolname = 'dark_jutsu_readonly') then create role dark_jutsu_readonly nologin; end if; if not exists (select 1 from pg_roles where rolname = 'dark_jutsu_app') then create role dark_jutsu_app nologin; end if; if not exists (select 1 from pg_roles where rolname = 'dark_jutsu_service') then create role dark_jutsu_service nologin; end if; end `$`$;"
& $psql -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu -v ON_ERROR_STOP=1 -f db\init\002_security.sql
```

Validar:

```powershell
& 'C:\Users\Davi.souza\Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql\bin\pg_isready.exe' -h 127.0.0.1 -p 5433 -U postgres
& 'C:\Users\Davi.souza\Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql\bin\psql.exe' -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu -f db\check.sql
```

String local:

```text
postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu
```

### Opcao B: Docker

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
