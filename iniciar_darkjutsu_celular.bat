@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"

echo ==========================================
echo Dark-Jutsu - acesso pelo celular na rede
echo ==========================================
echo.
echo 1. Deixe o computador e o celular na mesma rede Wi-Fi.
echo 2. Abra no celular um dos enderecos abaixo:
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -ExpandProperty IPAddress -Unique; if (-not $ips) { Write-Host '   Nao encontrei IP de rede. Confira o Wi-Fi/Ethernet deste PC.' } else { foreach ($ip in $ips) { Write-Host ('   http://' + $ip + ':8765') } }"

echo.
echo Se o celular nao abrir, execute como administrador:
echo   scripts\liberar_firewall_darkjutsu.bat
echo.

curl.exe -fsS --max-time 2 "http://127.0.0.1:8765/health" >nul 2>&1
if "%errorlevel%"=="0" (
  echo Dark-Jutsu ja esta respondendo neste PC. Pode abrir o endereco acima no celular.
  call :testar_endereco_rede
  echo.
  pause
  exit /b 0
)

echo Iniciando banco local, se existir...
if exist "%ROOT%db\postgres-server.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%db\postgres-server.ps1" start
  if not "%errorlevel%"=="0" (
    echo.
    echo Aviso: nao consegui iniciar o PostgreSQL local.
    echo Vou tentar iniciar/conferir a API mesmo assim.
  )
)

echo.
echo Iniciando Dark-Jutsu em modo rede...
set "DARK_JUTSU_API_HOST=0.0.0.0"
set "DARK_JUTSU_ALLOWED_ORIGINS=*"
call "%ROOT%api\iniciar_api.bat"

exit /b %errorlevel%

:testar_endereco_rede
for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -ExpandProperty IPAddress -First 1; if ($ip) { Write-Output $ip }"`) do set "LAN_IP=%%I"
if "%LAN_IP%"=="" exit /b 0
curl.exe -fsS --max-time 2 "http://%LAN_IP%:8765/health" >nul 2>&1
if not "%errorlevel%"=="0" (
  echo.
  echo Aviso: o endereco de rede ainda nao respondeu neste PC.
  echo Execute scripts\liberar_firewall_darkjutsu.bat e aceite a permissao de administrador.
)
exit /b 0
