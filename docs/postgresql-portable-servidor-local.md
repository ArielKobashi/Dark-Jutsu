# PostgreSQL portable como servidor local

Solucao provisoria para manter o PostgreSQL portable do Dark-Jutsu ativo na maquina compartilhada, sem depender de servico do Windows ou permissao de administrador.

## Arquitetura

- Binarios PostgreSQL: `C:\DarkJutsu\PostgreSQL\pgsql`
- Dados ativos: `C:\DarkJutsu\postgres-data`
- Logs: `C:\DarkJutsu\logs`
- Porta: `5433`
- Pasta de rede apenas para scripts, instaladores e backups: `\\fileserver\Almoxarifado\0800\servidor\dark-jutsu`

Nao use `Z:\` nem `\\fileserver` como `PGDATA` ativo. O PostgreSQL deve gravar os dados localmente para evitar lentidao, travamentos e risco de corrupcao.

## Scripts oficiais atuais

Os servidores usam o instalador unico e o guardiao ativo/passivo:

```text
scripts\instalar_atualizar_guardiao_monitor_darkjutsu.bat
scripts\guardiao_servidor_tick_darkjutsu.bat
scripts\assumir_servidor_darkjutsu.bat
scripts\iniciar_postgres_darkjutsu.bat
scripts\parar_postgres_darkjutsu.bat
scripts\iniciar_api_darkjutsu_service.vbs
```

O script de inicio:

- verifica se ha um processo escutando a porta `5433`;
- encerra sem erro se o PostgreSQL ja estiver ativo;
- valida `pg_ctl.exe` e `postgresql.conf`;
- inicia o PostgreSQL com `pg_ctl`;
- grava logs em `C:\DarkJutsu\logs`.

## Instalacao por usuario

Para cada usuario Windows da maquina compartilhada, execute uma vez:

```bat
cmd /c "pushd \\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts && call instalar_atualizar_guardiao_monitor_darkjutsu.bat && popd"
```

Esse comando instala monitor, guardiao e autoatualizacao. Nao use mais atalhos separados de PostgreSQL/API, porque eles podem gerar dois servidores ativos.

## Configuracao do PostgreSQL

Em `C:\DarkJutsu\postgres-data\postgresql.conf`, confirme:

```conf
port = 5433
listen_addresses = '*'
```

Em `C:\DarkJutsu\postgres-data\pg_hba.conf`, adicione uma faixa adequada para a rede da empresa:

```conf
host    all             all             192.168.0.0/16            md5
```

Ou, para uma sub-rede especifica:

```conf
host    all             all             192.168.5.0/24            md5
```

Depois de alterar esses arquivos, reinicie o PostgreSQL.

## Conexao do Dark-Jutsu

Na maquina compartilhada:

```text
DATABASE_URL=postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu
```

De outro computador na rede:

```text
DATABASE_URL=postgresql://dark_jutsu:dark_jutsu_dev@IP_DA_MAQUINA_COMPARTILHADA:5433/dark_jutsu
```

## Testes

```bat
C:\DarkJutsu\PostgreSQL\pgsql\bin\pg_ctl.exe -D C:\DarkJutsu\postgres-data -l C:\DarkJutsu\logs\postgres_runtime.log start
netstat -ano -p tcp | findstr /R /C:":5433 .*LISTENING"
C:\DarkJutsu\PostgreSQL\pgsql\bin\psql.exe -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu
\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\iniciar_postgres_darkjutsu.bat
```

Logs principais:

```text
C:\DarkJutsu\logs\postgres_startup.log
C:\DarkJutsu\logs\postgres_runtime.log
C:\DarkJutsu\logs\postgres_shutdown.log
```

## Backup

Use `pg_dump`. Nao copie `postgres-data` com o banco rodando.

```bat
C:\DarkJutsu\PostgreSQL\pgsql\bin\pg_dump.exe -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu -F c -f "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\backups\darkjutsu_backup.backup"
```

Esta solucao e provisoria. A solucao definitiva recomendada continua sendo pedir ao TI para instalar PostgreSQL no servidor local como servico do Windows, com backup e permissoes gerenciadas.
