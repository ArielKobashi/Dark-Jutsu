@echo off
setlocal
cd /d "%~dp0"

set "AUTOMUS_EXE=%cd%\Automus\dist\Automus\Automus.exe"
if not exist "%AUTOMUS_EXE%" set "AUTOMUS_EXE=%cd%\Automus\Automus.exe"
if not exist "%AUTOMUS_EXE%" set "AUTOMUS_EXE=%cd%\Automus.exe"

if exist "%AUTOMUS_EXE%" (
  echo Abrindo Automus...
  start "" "%AUTOMUS_EXE%"
  exit /b 0
)

set "SCRIPT_PATH=%cd%\Automus\scripts\executar_tudo.py"
set "PYTHON_EXE="
set "PYTHON_ARGS="
set "WPYTHON=C:\Users\jean.martimiano\Desktop\WPy64-3.13.12.0\python\python.exe"

if exist "%WPYTHON%" set "PYTHON_EXE=%WPYTHON%"

where py >nul 2>nul
if not defined PYTHON_EXE if not errorlevel 1 (
  set "PYTHON_EXE=py"
  set "PYTHON_ARGS=-3"
)

if not defined PYTHON_EXE (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    echo %%P | findstr /I "\\WindowsApps\\python.exe" >nul
    if errorlevel 1 if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
  )
)

if not exist "%SCRIPT_PATH%" (
  echo Script nao encontrado em:
  echo %SCRIPT_PATH%
  pause
  exit /b 1
)

if not defined PYTHON_EXE (
  echo Automus.exe nao encontrado e este computador nao tem Python.
  echo Baixe ou extraia o pacote Automus-v*.zip e abra o Automus.exe.
  pause
  exit /b 1
)

echo Executando automacao completa...
"%PYTHON_EXE%" %PYTHON_ARGS% "%SCRIPT_PATH%"

echo.
echo Execucao finalizada.
pause
