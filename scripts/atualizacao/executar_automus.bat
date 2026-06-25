@echo off
setlocal
cd /d "%~dp0\..\.."

set "SCRIPT_PATH=%cd%\scripts\atualizacao\automus_update.py"
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

if not defined PYTHON_EXE (
  echo Python nao encontrado.
  echo Este atalho e apenas para desenvolvimento. Em computadores sem Python, abra o Automus.exe.
  pause
  exit /b 1
)

"%PYTHON_EXE%" %PYTHON_ARGS% "%SCRIPT_PATH%" --config "%cd%\scripts\atualizacao\automus_config.json" --project-root "%cd%"

echo.
echo Finalizado.
pause
