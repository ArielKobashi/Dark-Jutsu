@echo off
setlocal
cd /d "%~dp0"

set "GIT_EXE=C:\Users\davi.souza\AppData\Local\Programs\Git\cmd\git.exe"
if not exist "%GIT_EXE%" (
  set "GIT_EXE=C:\Users\davi.souza\AppData\Local\Programs\Git\mingw64\bin\git.exe"
)

if not exist "%GIT_EXE%" (
  echo Git nao encontrado.
  pause
  exit /b 1
)

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
set "MSG=auto commit %TS%"

echo.
echo Usando: %GIT_EXE%
echo Pasta: %cd%
echo Mensagem: %MSG%
echo.

"%GIT_EXE%" add -A
"%GIT_EXE%" commit -m "%MSG%"
"%GIT_EXE%" push

echo.
echo Finalizado.
pause

