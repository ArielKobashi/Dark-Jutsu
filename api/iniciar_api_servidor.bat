@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."

for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$desktop = Join-Path $env:USERPROFILE 'Desktop'; $preferred = @(Join-Path $desktop 'aplicacoes code'); $found = @((Get-ChildItem -LiteralPath $desktop -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'aplica* code' }).FullName); $candidates = @($preferred) + $found; foreach ($folder in $candidates) { $python = Join-Path $folder 'WPy64-3.13.12.0\python\python.exe'; $enc = Join-Path $folder 'WPy64-3.13.12.0\python\Lib\encodings\__init__.py'; $psy = Join-Path $folder 'WPy64-3.13.12.0\python\Lib\site-packages\psycopg\__init__.py'; if ((Test-Path -LiteralPath $python) -and (Test-Path -LiteralPath $enc) -and (Test-Path -LiteralPath $psy)) { Write-Output $python; break } }"`) do set "PYTHON_EXE=%%P"

if "%PYTHON_EXE%"=="" (
  echo Python portatil valido nao encontrado no Desktop.
  exit /b 1
)

if "%DATABASE_URL%"=="" set "DATABASE_URL=postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
if "%DARK_JUTSU_API_HOST%"=="" set "DARK_JUTSU_API_HOST=0.0.0.0"
if "%DARK_JUTSU_API_PORT%"=="" set "DARK_JUTSU_API_PORT=8765"

cd /d "%ROOT%"
echo Iniciando API SQL em http://%DARK_JUTSU_API_HOST%:%DARK_JUTSU_API_PORT%
"%PYTHON_EXE%" api\dark_jutsu_api.py
