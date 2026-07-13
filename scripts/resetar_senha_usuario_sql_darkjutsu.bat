@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."
set "PYTHON_EXE="

call :try_python "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\python.exe"
if not defined PYTHON_EXE (
  for /d %%D in ("%USERPROFILE%\Desktop\aplica* code") do (
    if not defined PYTHON_EXE call :try_python "%%~fD\WPy64-3.13.12.0\python\python.exe"
  )
)
if not defined PYTHON_EXE (
  echo ERRO: Python portatil valido nao encontrado.
  exit /b 1
)
if "%~1"=="" (
  echo Uso: resetar_senha_usuario_sql_darkjutsu.bat LOGIN
  exit /b 2
)
"%PYTHON_EXE%" "%ROOT%\scripts\resetar_senha_usuario_sql_darkjutsu.py" %*
exit /b %errorlevel%

:try_python
if defined PYTHON_EXE exit /b 0
set "CANDIDATE=%~1"
if not exist "%CANDIDATE%" exit /b 0
if not exist "%~dp1Lib\encodings\__init__.py" exit /b 0
if not exist "%~dp1Lib\site-packages\psycopg\__init__.py" exit /b 0
set "PYTHON_EXE=%CANDIDATE%"
exit /b 0
