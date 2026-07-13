@echo off
setlocal EnableExtensions

set "TOOLS_DIR=%LOCALAPPDATA%\DarkJutsu\cloudflared"
set "CLOUDFLARED=%TOOLS_DIR%\cloudflared.exe"
set "TUNNEL_TOKEN=%DARK_JUTSU_CLOUDFLARED_TOKEN%"

if "%TUNNEL_TOKEN%"=="" (
  echo FALHOU: DARK_JUTSU_CLOUDFLARED_TOKEN nao definido.
  echo.
  echo Crie um Tunnel no Cloudflare Zero Trust, adicione um Public Hostname protegido por Access,
  echo copie o token do conector e salve nesta maquina com:
  echo   setx DARK_JUTSU_CLOUDFLARED_TOKEN "TOKEN_DO_CLOUDFLARE"
  echo.
  echo Por seguranca este script nao cria quick tunnel publico.
  exit /b 1
)

if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%" 2>nul
if not exist "%TOOLS_DIR%" (
  echo FALHOU: nao consegui criar %TOOLS_DIR%
  exit /b 1
)

if not exist "%CLOUDFLARED%" (
  echo Baixando cloudflared sem instalacao administrativa...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%CLOUDFLARED%'" || exit /b 1
)

echo Iniciando Cloudflare Tunnel protegido pelo Zero Trust...
echo IMPORTANTE: este script nao abre porta no roteador e nao inicia quick tunnel.
"%CLOUDFLARED%" tunnel --no-autoupdate run --token "%TUNNEL_TOKEN%"
exit /b %errorlevel%
