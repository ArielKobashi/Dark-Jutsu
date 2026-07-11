@echo off
setlocal EnableExtensions

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "PS1=%SHARE_ROOT%\scripts\verificar_atualizar_instalacao_local_darkjutsu.ps1"
set "LOGDIR=C:\DarkJutsu\logs"
set "LOGFILE=%LOGDIR%\autoatualizacao_local.log"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
if not exist "%PS1%" (
  >>"%LOGFILE%" echo [%date% %time%] ERRO: script PowerShell de autoatualizacao nao encontrado: %PS1%
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%" >> "%LOGFILE%" 2>&1
exit /b %errorlevel%
