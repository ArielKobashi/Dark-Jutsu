param(
  [ValidateSet("start", "stop", "restart", "status", "check")]
  [string]$Action = "status"
)

$ErrorActionPreference = "Stop"

$DbDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $DbDir
$DataDir = Join-Path $DbDir "data"
$LogFile = Join-Path $DbDir "postgres.log"
$PgHome = if ($env:PGSQL_HOME) { $env:PGSQL_HOME } else { "C:\Users\Davi.souza\Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql" }
$PgBin = Join-Path $PgHome "bin"
$PgCtl = Join-Path $PgBin "pg_ctl.exe"
$PgIsReady = Join-Path $PgBin "pg_isready.exe"
$Psql = Join-Path $PgBin "psql.exe"
$Port = 5433

function Assert-PostgresBinaries {
  foreach ($exe in @($PgCtl, $PgIsReady, $Psql)) {
    if (-not (Test-Path -LiteralPath $exe)) {
      throw "Executavel PostgreSQL nao encontrado: $exe. Ajuste PGSQL_HOME ou confira a pasta dos binarios."
    }
  }
}

function Assert-Cluster {
  $pgVersion = Join-Path $DataDir "PG_VERSION"
  if (-not (Test-Path -LiteralPath $pgVersion)) {
    throw "Cluster PostgreSQL nao encontrado em $DataDir. Rode a configuracao inicial descrita em db\README.md."
  }
}

function Get-ServerStatus {
  & $PgCtl -D $DataDir status
  return $LASTEXITCODE
}

function Start-Server {
  Assert-PostgresBinaries
  Assert-Cluster
  & $PgIsReady -h 127.0.0.1 -p $Port -U postgres *> $null
  if ($LASTEXITCODE -eq 0) {
    Write-Host "PostgreSQL ja esta ativo em 127.0.0.1:$Port"
    return
  }
  & $PgCtl -D $DataDir -l $LogFile start
  & $PgIsReady -h 127.0.0.1 -p $Port -U postgres
  Write-Host "DATABASE_URL=postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:$Port/dark_jutsu"
}

function Stop-Server {
  Assert-PostgresBinaries
  Assert-Cluster
  & $PgIsReady -h 127.0.0.1 -p $Port -U postgres *> $null
  if ($LASTEXITCODE -ne 0) {
    Write-Host "PostgreSQL ja esta parado."
    return
  }
  & $PgCtl -D $DataDir stop -m fast
}

function Check-Database {
  Assert-PostgresBinaries
  & $Psql -h 127.0.0.1 -p $Port -U dark_jutsu -d dark_jutsu -f (Join-Path $DbDir "check.sql")
}

switch ($Action) {
  "start" { Start-Server }
  "stop" { Stop-Server }
  "restart" {
    Stop-Server
    Start-Server
  }
  "status" {
    Assert-PostgresBinaries
    Assert-Cluster
    Get-ServerStatus | Out-Null
    & $PgIsReady -h 127.0.0.1 -p $Port -U postgres
  }
  "check" { Check-Database }
}
