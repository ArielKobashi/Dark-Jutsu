param(
  [string]$Root = "",
  [int]$Port = 8766
)

$ErrorActionPreference = "Stop"

if (-not $Root) {
  $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$Root = (Resolve-Path $Root).Path

try {
  Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2 | Out-Null
  return
} catch {}

function Test-PythonCandidate([string]$Path) {
  if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $false }
  $base = Split-Path -Parent $Path
  return (
    (Test-Path -LiteralPath (Join-Path $base "Lib\encodings\__init__.py")) -and
    (Test-Path -LiteralPath (Join-Path $base "Lib\site-packages\psycopg\__init__.py"))
  )
}

$pythonExe = ""
$desktop = Join-Path $env:USERPROFILE "Desktop"
$candidates = @(
  (Join-Path $desktop "aplicacoes code\WPy64-3.13.12.0\python\python.exe")
)
if (Test-Path -LiteralPath $desktop) {
  Get-ChildItem -LiteralPath $desktop -Directory -Filter "aplica* code" -ErrorAction SilentlyContinue | ForEach-Object {
    $candidates += (Join-Path $_.FullName "WPy64-3.13.12.0\python\python.exe")
  }
}

foreach ($candidate in $candidates) {
  if (Test-PythonCandidate $candidate) {
    $pythonExe = $candidate
    break
  }
}

if (-not $pythonExe) {
  throw "Python portatil valido nao encontrado no Desktop."
}

$env:DATABASE_URL = "postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
$env:DARK_JUTSU_API_HOST = "127.0.0.1"
$env:DARK_JUTSU_API_PORT = [string]$Port
$env:DARK_JUTSU_ALLOWED_ORIGINS = "*"
$env:DARK_JUTSU_APP_WEB_ROOT = $Root

Start-Process `
  -WindowStyle Hidden `
  -FilePath $pythonExe `
  -ArgumentList "api\dark_jutsu_api.py" `
  -WorkingDirectory $Root
