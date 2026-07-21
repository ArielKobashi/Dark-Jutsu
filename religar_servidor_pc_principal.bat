@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "ROOT=%~dp0"
set "MAIN_API_PORT=8765"

echo ==========================================
echo Dark-Jutsu - religar servidor principal PC
echo ==========================================
echo.
echo Este modo e para os PCs.
echo Porta principal: %MAIN_API_PORT%
echo Celular/tunel usa outra porta: 8766
echo.

curl.exe -fsS --max-time 2 "http://127.0.0.1:%MAIN_API_PORT%/health" >nul 2>&1
if "%errorlevel%"=="0" (
  netstat -ano -p tcp | findstr /R /C:"0.0.0.0:%MAIN_API_PORT% .*LISTENING" >nul 2>&1
  if "!errorlevel!"=="0" (
    echo OK: servidor principal ja esta ativo em modo rede.
    exit /b 0
  )
  echo O servidor responde, mas esta preso em 127.0.0.1.
  echo Vou reiniciar a porta %MAIN_API_PORT% em modo rede.
)

for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":%MAIN_API_PORT% .*LISTENING"') do (
  echo Encerrando processo antigo da porta %MAIN_API_PORT%: %%P
  taskkill /PID %%P /F >nul 2>&1
)

set "DARK_JUTSU_API_HOST=0.0.0.0"
set "DARK_JUTSU_API_PORT=%MAIN_API_PORT%"
set "DARK_JUTSU_ALLOWED_ORIGINS=*"
start "Dark-Jutsu servidor principal" /min cmd /c call "%ROOT%api\iniciar_api_servidor.bat"

echo Aguardando servidor principal subir...
for /L %%N in (1,1,25) do (
  curl.exe -fsS --max-time 2 "http://127.0.0.1:%MAIN_API_PORT%/health" >nul 2>&1
  if "!errorlevel!"=="0" (
    netstat -ano -p tcp | findstr /R /C:"0.0.0.0:%MAIN_API_PORT% .*LISTENING" >nul 2>&1
    if "!errorlevel!"=="0" (
      echo OK: servidor principal ativo em modo rede na porta %MAIN_API_PORT%.
      exit /b 0
    )
  )
  timeout /t 1 /nobreak >nul
)

echo ERRO: nao consegui confirmar o servidor principal em modo rede.
echo Se aparecer "Acesso negado", abra este arquivo como administrador ou chame o Codex para religar.
exit /b 1
