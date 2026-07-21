@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "TOOLS_DIR=%LOCALAPPDATA%\DarkJutsu\cloudflared"
set "CLOUDFLARED=%TOOLS_DIR%\cloudflared.exe"

echo ==========================================
echo Dark-Jutsu - celular sem administrador
echo ==========================================
echo.
echo Este modo usa um tunel gratuito temporario.
echo Nao precisa ser administrador e nao abre porta no roteador.
echo.

curl.exe -fsS --max-time 2 "http://127.0.0.1:8765/health" >nul 2>&1
if not "%errorlevel%"=="0" (
  echo Dark-Jutsu ainda nao esta respondendo neste PC.
  echo Vou tentar iniciar a API local primeiro...
  echo.
  set "DARK_JUTSU_API_HOST=127.0.0.1"
  set "DARK_JUTSU_ALLOWED_ORIGINS=*"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath 'cmd.exe' -ArgumentList '/c','\"%ROOT%api\iniciar_api_servidor.bat\"'"
  echo Aguardando a API subir...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(25); do { try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8765/health' -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } } while ((Get-Date) -lt $deadline); exit 1"
  if not "%errorlevel%"=="0" (
    echo.
    echo Nao consegui confirmar a API local.
    echo Abra api\iniciar_api_servidor.bat e depois rode este arquivo de novo.
    pause
    exit /b 1
  )
)

curl.exe -fsS --max-time 2 "http://127.0.0.1:8765/style.css" 2>nul | findstr /C:"body" >nul 2>&1
if not "%errorlevel%"=="0" (
  echo.
  echo A API local esta ativa, mas os arquivos visuais ainda nao estao saindo corretamente.
  echo Vou tentar reiniciar a API para carregar a correcao.
  for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":8765 .*LISTENING"') do taskkill /PID %%P /F >nul 2>&1
  set "DARK_JUTSU_API_HOST=127.0.0.1"
  set "DARK_JUTSU_ALLOWED_ORIGINS=*"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath 'cmd.exe' -ArgumentList '/c','\"%ROOT%api\iniciar_api_servidor.bat\"'"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(25); do { try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8765/style.css' -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } } while ((Get-Date) -lt $deadline); exit 1"
)

curl.exe -fsS --max-time 2 "http://127.0.0.1:8765/api/mobile-link" >nul 2>&1
if not "%errorlevel%"=="0" (
  echo.
  echo A API local esta ativa, mas ainda nao tem o recurso de QR Code.
  echo Vou reiniciar a API para carregar a versao nova.
  for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":8765 .*LISTENING"') do taskkill /PID %%P /F >nul 2>&1
  set "DARK_JUTSU_API_HOST=127.0.0.1"
  set "DARK_JUTSU_ALLOWED_ORIGINS=*"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath 'cmd.exe' -ArgumentList '/c','\"%ROOT%api\iniciar_api_servidor.bat\"'"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(25); do { try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8765/api/mobile-link' -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } } while ((Get-Date) -lt $deadline); exit 1"
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
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\iniciar_tunel_celular_darkjutsu.ps1" -Cloudflared "%CLOUDFLARED%" -Root "%ROOT%" -KeepAlive
pause
exit /b %errorlevel%
