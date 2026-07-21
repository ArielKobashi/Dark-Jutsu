@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "ROOT=%~dp0"
set "ROOT_DIR=%ROOT:~0,-1%"
set "TOOLS_DIR=%LOCALAPPDATA%\DarkJutsu\cloudflared"
set "CLOUDFLARED=%TOOLS_DIR%\cloudflared.exe"
set "MAIN_API_PORT=8765"
set "MOBILE_API_PORT=8766"

echo ==========================================
echo Dark-Jutsu - celular sem administrador
echo ==========================================
echo.
echo Este modo usa um tunel gratuito temporario.
echo Nao precisa ser administrador e nao abre porta no roteador.
echo.
echo Servidor principal do PC: porta %MAIN_API_PORT%
curl.exe -fsS --max-time 2 "http://127.0.0.1:%MAIN_API_PORT%/health" >nul 2>&1
if "%errorlevel%"=="0" (
  netstat -ano -p tcp | findstr /R /C:"0.0.0.0:%MAIN_API_PORT% .*LISTENING" >nul 2>&1
  if "!errorlevel!"=="0" (
    echo OK: servidor principal esta ativo em modo rede na porta %MAIN_API_PORT%.
  ) else (
    echo AVISO: servidor principal responde localmente, mas nao esta em modo rede.
    echo Se os PCs ficarem pretos, execute: religar_servidor_pc_principal.bat
  )
) else (
  echo AVISO: servidor principal do PC nao respondeu na porta %MAIN_API_PORT%.
  echo Vou tentar ligar o servidor principal separado antes do modo celular.
  call "%ROOT%religar_servidor_pc_principal.bat"
)
echo.

curl.exe -fsS --max-time 2 "http://127.0.0.1:%MOBILE_API_PORT%/health" >nul 2>&1
if not "%errorlevel%"=="0" (
  echo API do celular ainda nao esta respondendo neste PC.
  echo Vou iniciar uma API separada em http://127.0.0.1:%MOBILE_API_PORT% ...
  echo.
  set "DARK_JUTSU_API_HOST=127.0.0.1"
  set "DARK_JUTSU_API_PORT=%MOBILE_API_PORT%"
  set "DARK_JUTSU_ALLOWED_ORIGINS=*"
  set "DARK_JUTSU_APP_WEB_ROOT=%ROOT_DIR%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath 'cmd.exe' -ArgumentList '/c','\"%ROOT%api\iniciar_api_servidor.bat\"'"
  echo Aguardando a API subir...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(25); do { try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%MOBILE_API_PORT%/health' -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } } while ((Get-Date) -lt $deadline); exit 1"
  if not "%errorlevel%"=="0" (
    echo.
    echo Nao consegui confirmar a API do celular.
    echo Abra api\iniciar_api_servidor.bat e depois rode este arquivo de novo.
    pause
    exit /b 1
  )
)

curl.exe -fsS --max-time 2 "http://127.0.0.1:%MOBILE_API_PORT%/style.css" 2>nul | findstr /C:"body" >nul 2>&1
if "%errorlevel%"=="0" (
  curl.exe -fsS --max-time 2 "http://127.0.0.1:%MOBILE_API_PORT%/mobile.css" 2>nul | findstr /C:"Mobile overrides" >nul 2>&1
)
if not "%errorlevel%"=="0" (
  echo.
  echo A API do celular esta ativa, mas os arquivos visuais/mobile ainda nao estao saindo corretamente.
  echo Vou tentar reiniciar somente a API do celular.
  for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":%MOBILE_API_PORT% .*LISTENING"') do taskkill /PID %%P /F >nul 2>&1
  set "DARK_JUTSU_API_HOST=127.0.0.1"
  set "DARK_JUTSU_API_PORT=%MOBILE_API_PORT%"
  set "DARK_JUTSU_ALLOWED_ORIGINS=*"
  set "DARK_JUTSU_APP_WEB_ROOT=%ROOT_DIR%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath 'cmd.exe' -ArgumentList '/c','\"%ROOT%api\iniciar_api_servidor.bat\"'"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(25); do { try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%MOBILE_API_PORT%/style.css' -TimeoutSec 2 | Out-Null; Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%MOBILE_API_PORT%/mobile.css' -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } } while ((Get-Date) -lt $deadline); exit 1"
)

curl.exe -fsS --max-time 2 "http://127.0.0.1:%MOBILE_API_PORT%/api/mobile-link" >nul 2>&1
if not "%errorlevel%"=="0" (
  echo.
  echo A API do celular esta ativa, mas ainda nao tem o recurso de QR Code.
  echo Vou reiniciar somente a API do celular para carregar a versao nova.
  for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":%MOBILE_API_PORT% .*LISTENING"') do taskkill /PID %%P /F >nul 2>&1
  set "DARK_JUTSU_API_HOST=127.0.0.1"
  set "DARK_JUTSU_API_PORT=%MOBILE_API_PORT%"
  set "DARK_JUTSU_ALLOWED_ORIGINS=*"
  set "DARK_JUTSU_APP_WEB_ROOT=%ROOT_DIR%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath 'cmd.exe' -ArgumentList '/c','\"%ROOT%api\iniciar_api_servidor.bat\"'"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(25); do { try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:%MOBILE_API_PORT%/api/mobile-link' -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } } while ((Get-Date) -lt $deadline); exit 1"
)

if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%" 2>nul
if not exist "%CLOUDFLARED%" (
  echo Baixando cloudflared na pasta do usuario...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%CLOUDFLARED%'"
  if not "%errorlevel%"=="0" (
    echo.
    echo Nao consegui baixar o cloudflared automaticamente.
    echo Se a empresa bloquear downloads, baixe cloudflared.exe em outro lugar e coloque em:
    echo   %CLOUDFLARED%
    pause
    exit /b 1
  )
)

echo.
echo Quando aparecer uma URL parecida com https://algo.trycloudflare.com,
echo abra essa URL no navegador do celular.
echo.
echo IMPORTANTE: o link fica ativo so enquanto esta janela estiver aberta.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\iniciar_tunel_celular_darkjutsu.ps1" -Cloudflared "%CLOUDFLARED%" -Root "%ROOT_DIR%" -Url "http://127.0.0.1:%MOBILE_API_PORT%" -KeepAlive
pause
exit /b %errorlevel%
