$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Desktop = [Environment]::GetFolderPath("Desktop")
$Python = Get-ChildItem -LiteralPath $Desktop -Directory |
    Where-Object { $_.Name -like "aplica* code" } |
    ForEach-Object { Join-Path $_.FullName "WPy64-3.13.12.0\python\python.exe" } |
    Where-Object {
        (Test-Path -LiteralPath $_) -and
        (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $_) "Lib\encodings"))
    } |
    Select-Object -First 1
$DatabaseUrl = "postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
$ApiUrl = "http://127.0.0.1:8765"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python nao encontrado em $Python"
}

Set-Location $Root
Remove-Item Env:\PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue

Write-Host "[1/4] Verificando API..."
$health = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 5
if ($health.ok -ne $true) {
    throw "API nao respondeu OK em $ApiUrl"
}

Write-Host "[2/4] Rodando auditoria Firebase restante..."
& $Python "scripts\auditar_firebase_restante.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[3/4] Compilando API..."
& $Python -m py_compile "api\dark_jutsu_api.py" "scripts\auditar_firebase_restante.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[4/4] Integridade rapida por dominio..."
$domains = @("users", "dashboard", "counting", "occurrences", "chat", "automus", "cooperat")
foreach ($domain in $domains) {
    $raw = "_migration_runs\reload_after_inventory_endpoint_${domain}_20260709\raw"
    $args = @(
        "scripts\migration\integrity_check.py",
        "--domain", $domain,
        "--run-id", "ensaio_sql_only_$domain",
        "--database-url", $DatabaseUrl,
        "--fail-on", "critical"
    )
    if (Test-Path -LiteralPath $raw) {
        $args += @("--raw", $raw)
    }
    & $Python @args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$inventoryRaw = "_migration_runs\reload_active_inventory_20260703\raw"
if (Test-Path -LiteralPath (Join-Path $inventoryRaw "estoqueGlobal.json")) {
    & $Python "scripts\migration\integrity_check.py" `
        "--domain" "inventory" `
        "--run-id" "ensaio_sql_only_inventory" `
        "--raw" $inventoryRaw `
        "--database-url" $DatabaseUrl `
        "--fail-on" "critical"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "AVISO: raw de inventory nao encontrado para integridade rapida."
}

Write-Host ""
Write-Host "Ensaio SQL-only concluido."
Write-Host "Auditoria: _migration_runs\firebase_audit_latest\firebase_audit.md"
Write-Host "Para testar no navegador: abra index.html?sqlOnly=1 ou defina localStorage.darkJutsuSqlOnly=1"
