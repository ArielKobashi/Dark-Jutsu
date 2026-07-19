@echo off
setlocal

set "ROOT=%~dp0"
set "POINTER=%ROOT%versao_atual.txt"

if not exist "%POINTER%" (
  echo ERRO: versao_atual.txt nao encontrado em %ROOT%
  pause
  exit /b 1
)

for /f "usebackq delims=" %%V in ("%POINTER%") do (
  set "VERSION=%%V"
  goto got_version
)

:got_version
if not defined VERSION (
  echo ERRO: versao_atual.txt esta vazio.
  pause
  exit /b 1
)

set "LAUNCHER=%ROOT%Aplicacao\%VERSION%\Reenviar_Ultimos_Dados_Automus.bat"
if not exist "%LAUNCHER%" (
  echo ERRO: reenvio nao encontrado para a versao %VERSION%.
  echo %LAUNCHER%
  pause
  exit /b 1
)

call "%LAUNCHER%"
exit /b %ERRORLEVEL%
