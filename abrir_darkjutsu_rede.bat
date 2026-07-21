@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "API_PORT=8765"
set "PRIMARY_IP=192.168.5.44"
set "RESERVE_IP=192.168.5.38"
set "EXTRA_IP=192.168.5.41"

echo ==========================================
echo Dark-Jutsu - abrir pela rede
echo ==========================================
echo.
echo Procurando servidor ativo...
echo.

for %%I in ("%PRIMARY_IP%" "%RESERVE_IP%" "%EXTRA_IP%") do (
  set "IP=%%~I"
  if not "!IP!"=="" (
    echo Testando http://!IP!:%API_PORT% ...
    curl.exe -fsS --max-time 3 "http://!IP!:%API_PORT%/health" >nul 2>&1
    if "!errorlevel!"=="0" (
      set "URL=http://!IP!:%API_PORT%/"
      echo.
      echo Abrindo Dark-Jutsu:
      echo !URL!
      start "" "!URL!"
      exit /b 0
    )
  )
)

echo.
echo Nenhum servidor Dark-Jutsu respondeu agora.
echo Confira se o PC principal/reserva esta ligado e na mesma rede.
echo.
pause
exit /b 1
