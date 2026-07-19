@echo off
setlocal
pushd "%~dp0" >nul 2>&1
if errorlevel 1 (
  echo Nao consegui acessar a pasta do Automus no servidor.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Get-Process -Name Automus -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0configurar_automus_servidor.ps1"
if errorlevel 1 (
  popd
  echo.
  echo Nao foi possivel atualizar o Automus neste computador.
  pause
  exit /b 1
)

popd
echo.
echo Automus atualizado/aberto pela versao central do servidor.
timeout /t 4 /nobreak >nul
exit /b 0
