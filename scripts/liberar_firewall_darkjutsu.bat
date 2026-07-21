@echo off
setlocal EnableExtensions

net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo Solicitando permissao de administrador para liberar o acesso do celular...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b 0
)

netsh advfirewall firewall show rule name="Dark-Jutsu API 8765" >nul 2>&1
if "%errorlevel%"=="0" (
  echo Regra de firewall ja existe: Dark-Jutsu API 8765
) else (
  netsh advfirewall firewall add rule name="Dark-Jutsu API 8765" dir=in action=allow protocol=TCP localport=8765 profile=any
)

echo.
echo Porta 8765 liberada no Firewall do Windows.
echo Agora teste no celular:
echo   http://192.168.5.41:8765
pause
exit /b 0
