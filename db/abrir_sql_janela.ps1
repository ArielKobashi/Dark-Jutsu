$ErrorActionPreference = "Stop"

$DbDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $DbDir
$GuiScript = Join-Path $DbDir "postgres_server_gui.py"
$Desktop = Join-Path $env:USERPROFILE "Desktop"

$Python = Get-ChildItem -Path $Desktop -Recurse -Filter python.exe -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -like "*WPy64-3.13.12.0*python*python.exe" } |
  Select-Object -First 1 -ExpandProperty FullName

if (-not $Python) {
  throw "Nao encontrei o python.exe do WPy64-3.13.12.0 dentro do Desktop."
}

if (-not (Test-Path -LiteralPath $GuiScript)) {
  throw "Janela Python nao encontrada: $GuiScript"
}

Start-Process -FilePath $Python -ArgumentList "`"$GuiScript`"" -WorkingDirectory $RootDir
