@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."

for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$desktop = Join-Path $env:USERPROFILE 'Desktop'; $folder = Get-ChildItem -LiteralPath $desktop -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'aplica* code' } | Select-Object -First 1; if ($folder) { $python = Join-Path $folder.FullName 'WPy64-3.13.12.0\python\python.exe'; if (Test-Path -LiteralPath $python) { Write-Output $python } }"`) do set "PYTHON_EXE=%%P"

if "%PYTHON_EXE%"=="" (
  echo Python portatil nao encontrado no Desktop.
  echo Esperado: pasta "aplicacoes code" ou "aplicacoes code" com WPy64-3.13.12.0\python\python.exe.
  pause
  exit /b 1
)

if "%DATABASE_URL%"=="" set "DATABASE_URL=postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
if "%DARK_JUTSU_API_HOST%"=="" set "DARK_JUTSU_API_HOST=0.0.0.0"
if "%DARK_JUTSU_API_PORT%"=="" set "DARK_JUTSU_API_PORT=8765"

cd /d "%ROOT%"
echo Iniciando API SQL em http://%DARK_JUTSU_API_HOST%:%DARK_JUTSU_API_PORT%
"%PYTHON_EXE%" api\dark_jutsu_api.py
pause
