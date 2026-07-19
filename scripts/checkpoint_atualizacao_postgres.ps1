param(
  [ValidateSet("antes", "depois")]
  [string]$Etapa = "antes",
  [string]$DatabaseUrl = "postgresql://postgres@127.0.0.1:5433/dark_jutsu",
  [string]$Saida = ""
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $Saida) { $Saida = Join-Path $Repo "_db_update_checkpoints" }
$Saida = [System.IO.Path]::GetFullPath($Saida)
$Ponteiro = Join-Path $Saida "checkpoint_atual.txt"

function Find-PgBin {
  $candidatos = @(
    $env:PG_BIN,
    "C:\DarkJutsu\PostgreSQL\pgsql\bin",
    (Join-Path $env:USERPROFILE "Desktop\aplicacoes code\pgsql\bin"),
    (Join-Path $env:USERPROFILE "Desktop\postgresql-18.4-2-windows-x64-binaries\pgsql\bin")
  ) | Where-Object { $_ }
  foreach ($dir in $candidatos) {
    if (Test-Path -LiteralPath (Join-Path $dir "psql.exe")) { return $dir }
  }
  $psql = Get-Command psql.exe -ErrorAction SilentlyContinue
  if ($psql) { return Split-Path -Parent $psql.Source }
  throw "psql.exe nao encontrado. Defina PG_BIN com a pasta bin do PostgreSQL."
}

function Parse-DatabaseUrl([string]$Url) {
  $uri = [Uri]$Url
  if ($uri.Scheme -notin @("postgres", "postgresql")) { throw "DATABASE_URL invalida." }
  $partes = $uri.UserInfo.Split(":", 2)
  $db = $uri.AbsolutePath.TrimStart("/")
  if (-not $db) { throw "Nome do banco ausente na DATABASE_URL." }
  return [pscustomobject]@{
    Host = $uri.Host; Port = $uri.Port; Database = $db
    User = [Uri]::UnescapeDataString($partes[0])
    Password = if ($partes.Count -gt 1) { [Uri]::UnescapeDataString($partes[1]) } else { "" }
  }
}

$PgBin = Find-PgBin
$Db = Parse-DatabaseUrl $DatabaseUrl
$Psql = Join-Path $PgBin "psql.exe"
$PgDump = Join-Path $PgBin "pg_dump.exe"
$PgRestore = Join-Path $PgBin "pg_restore.exe"
$env:PGPASSWORD = $Db.Password

function Invoke-Sql([string]$Sql) {
  $result = & $Psql -X -h $Db.Host -p $Db.Port -U $Db.User -d $Db.Database -v ON_ERROR_STOP=1 -Atc $Sql 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($result -join [Environment]::NewLine) }
  return @($result)
}

function Get-SchemaHash([string]$Path) {
  $normalizado = (Get-Content -LiteralPath $Path | Where-Object { $_ -notmatch '^\\(un)?restrict ' }) -join "`n"
  $bytes = [Text.Encoding]::UTF8.GetBytes($normalizado)
  $sha = [Security.Cryptography.SHA256]::Create()
  try { return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant() }
  finally { $sha.Dispose() }
}

function Capture-State([string]$Dir, [string]$Label) {
  New-Item -ItemType Directory -Force -Path $Dir | Out-Null
  $log = Join-Path $Dir "erros.log"
  try {
    $ready = & (Join-Path $PgBin "pg_isready.exe") -h $Db.Host -p $Db.Port -U $Db.User -d $Db.Database 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($ready -join " ") }

    $backup = Join-Path $Dir "dark_jutsu_$Label.backup"
    & $PgDump -h $Db.Host -p $Db.Port -U $Db.User -d $Db.Database -F c -f $backup 2>> $log
    if ($LASTEXITCODE -ne 0) { throw "pg_dump falhou; consulte $log" }
    & $PgRestore -l $backup | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Backup criado, mas a validacao pg_restore -l falhou." }

    $schema = Join-Path $Dir "schema.sql"
    & $PgDump -h $Db.Host -p $Db.Port -U $Db.User -d $Db.Database --schema-only --no-owner --no-privileges -f $schema 2>> $log
    if ($LASTEXITCODE -ne 0) { throw "Dump do schema falhou; consulte $log" }

    $tables = Invoke-Sql "select tablename from pg_tables where schemaname='public' order by tablename"
    $resumo = [ordered]@{}
    foreach ($table in $tables) {
      $safe = $table.Replace('"', '""')
      $canonical = Join-Path $Dir (".hash_" + $table + ".txt")
      $copySql = "COPY (SELECT to_jsonb(t)::text AS row_data FROM public.`"$safe`" t ORDER BY 1) TO STDOUT"
      & $Psql -X -h $Db.Host -p $Db.Port -U $Db.User -d $Db.Database -v ON_ERROR_STOP=1 -c $copySql 1> $canonical 2>> $log
      if ($LASTEXITCODE -ne 0) { throw "Falha ao assinar a tabela $table; consulte $log" }
      $countRows = @(Invoke-Sql "select count(*) from public.`"$safe`"")
      $count = $countRows[0]
      $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $canonical).Hash.ToLowerInvariant()
      Remove-Item -LiteralPath $canonical -Force
      $resumo[$table] = [ordered]@{ linhas = [int64]$count; sha256 = $hash }
    }

    $meta = [ordered]@{
      etapa = $Label
      capturado_em = (Get-Date).ToString("o")
      servidor_utc = (@(Invoke-Sql "select clock_timestamp()"))[0]
      banco = $Db.Database
      host = $Db.Host
      porta = $Db.Port
      versao = (@(Invoke-Sql "select version()"))[0]
      schema_sha256 = Get-SchemaHash $schema
      backup = [IO.Path]::GetFileName($backup)
      backup_bytes = (Get-Item -LiteralPath $backup).Length
      tabelas = $resumo
    }
    $meta | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Dir "estado.json") -Encoding utf8
    return $meta
  } catch {
    "[$((Get-Date).ToString('o'))] $($_.Exception.Message)" | Add-Content -LiteralPath $log -Encoding utf8
    throw
  }
}

function Compare-State($Antes, $Depois, [string]$Dir) {
  $nomesAntes = @($Antes.tabelas.PSObject.Properties | Where-Object MemberType -eq 'NoteProperty' | ForEach-Object Name)
  $nomesDepois = @($Depois.tabelas.PSObject.Properties | Where-Object MemberType -eq 'NoteProperty' | ForEach-Object Name)
  $nomes = @($nomesAntes + $nomesDepois | Sort-Object -Unique)
  $itens = foreach ($nome in $nomes) {
    $a = $Antes.tabelas.$nome
    $d = $Depois.tabelas.$nome
    $status = if (-not $a) { "NOVA" } elseif (-not $d) { "REMOVIDA" } elseif ($a.sha256 -eq $d.sha256) { "NAO_MUDOU" } else { "MUDOU" }
    [pscustomobject]@{
      tabela=$nome; status=$status
      linhas_antes=if ($a) {$a.linhas} else {$null}
      linhas_depois=if ($d) {$d.linhas} else {$null}
      diferenca=if ($a -and $d) {[int64]$d.linhas-[int64]$a.linhas} else {$null}
      hash_antes=if ($a) {$a.sha256} else {$null}
      hash_depois=if ($d) {$d.sha256} else {$null}
    }
  }
  $itens | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Dir "comparacao.json") -Encoding utf8
  $schemaAntes = Get-SchemaHash (Join-Path $Dir 'schema.sql')
  $schemaDepois = Get-SchemaHash (Join-Path (Join-Path $Dir 'depois') 'schema.sql')
  $md = @("# Comparacao da atualizacao PostgreSQL", "", "- Antes: $($Antes.capturado_em)", "- Depois: $($Depois.capturado_em)", "- Schema: $(if ($schemaAntes -eq $schemaDepois) {'NAO_MUDOU'} else {'MUDOU'})", "", "| Tabela | Status | Antes | Depois | Diferenca |", "|---|---:|---:|---:|---:|")
  foreach ($i in $itens) { $md += "| $($i.tabela) | $($i.status) | $($i.linhas_antes) | $($i.linhas_depois) | $($i.diferenca) |" }
  $md | Set-Content -LiteralPath (Join-Path $Dir "RELATORIO.md") -Encoding utf8
  return $itens
}

New-Item -ItemType Directory -Force -Path $Saida | Out-Null
if ($Etapa -eq "antes") {
  $id = "postgres_" + (Get-Date -Format "yyyyMMdd_HHmmss")
  $dir = Join-Path $Saida $id
  $null = Capture-State $dir "antes"
  $id | Set-Content -LiteralPath $Ponteiro -Encoding ascii
  Write-Host "CHECKPOINT_ANTES_OK: $dir"
  Write-Host "Agora rode a atualizacao. Depois execute este script com -Etapa depois."
} else {
  if (-not (Test-Path -LiteralPath $Ponteiro)) { throw "Checkpoint anterior nao encontrado em $Ponteiro" }
  $id = (Get-Content -LiteralPath $Ponteiro -Raw).Trim()
  $dir = Join-Path $Saida $id
  $antes = Get-Content -LiteralPath (Join-Path $dir "estado.json") -Raw | ConvertFrom-Json
  $depoisDir = Join-Path $dir "depois"
  $depoisCapturado = Capture-State $depoisDir "depois"
  $depois = $depoisCapturado | ConvertTo-Json -Depth 8 | ConvertFrom-Json
  $comparacao = Compare-State $antes $depois $dir
  $mudou = @($comparacao | Where-Object status -eq "MUDOU").Count
  $igual = @($comparacao | Where-Object status -eq "NAO_MUDOU").Count
  Write-Host "CHECKPOINT_DEPOIS_OK: mudou=$mudou nao_mudou=$igual relatorio=$(Join-Path $dir 'RELATORIO.md')"
}
