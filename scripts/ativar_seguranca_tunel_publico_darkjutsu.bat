@echo off
setlocal EnableExtensions

set "APP_ROOT=C:\DarkJutsu\Dark-Jutsu"
set "ENV_DIR=%APP_ROOT%\_local_secrets"
set "ENV_FILE=%ENV_DIR%\sql_auth_runtime.env"
set "ALLOWED=%~1"

if "%ALLOWED%"=="" (
  echo FALHOU: informe as origens HTTPS permitidas separadas por virgula.
  echo.
  echo Exemplo:
  echo   %~nx0 https://seuusuario.github.io,https://dark.seudominio.com
  echo.
  echo Nao use * em modo publico.
  exit /b 1
)

echo %ALLOWED% | findstr /I /C:"*" >nul 2>&1
if not errorlevel 1 (
  echo FALHOU: origem * bloqueada em modo publico.
  exit /b 1
)

if not exist "%ENV_DIR%" mkdir "%ENV_DIR%" 2>nul
if not exist "%ENV_DIR%" (
  echo FALHOU: nao consegui criar %ENV_DIR%
  exit /b 1
)

if exist "%ENV_FILE%" copy /Y "%ENV_FILE%" "%ENV_FILE%.bak" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$path='%ENV_FILE%';" ^
  "$lines=@();" ^
  "if(Test-Path -LiteralPath $path){ $lines=Get-Content -LiteralPath $path }" ^
  "$drop='DARK_JUTSU_PUBLIC_TUNNEL_MODE','DARK_JUTSU_ALLOWED_ORIGINS','DARK_JUTSU_LOGIN_RATE_LIMIT_MAX','DARK_JUTSU_LOGIN_RATE_LIMIT_WINDOW_SECONDS';" ^
  "$next=$lines | Where-Object { $line=$_; $matched=$false; foreach($key in $drop){ if($line -like ($key + '=*')){ $matched=$true; break } }; -not $matched };" ^
  "$next += 'DARK_JUTSU_PUBLIC_TUNNEL_MODE=1';" ^
  "$next += 'DARK_JUTSU_ALLOWED_ORIGINS=%ALLOWED%';" ^
  "$next += 'DARK_JUTSU_LOGIN_RATE_LIMIT_MAX=6';" ^
  "$next += 'DARK_JUTSU_LOGIN_RATE_LIMIT_WINDOW_SECONDS=900';" ^
  "Set-Content -LiteralPath $path -Encoding ASCII -Value $next"

if errorlevel 1 (
  echo FALHOU: nao consegui gravar %ENV_FILE%
  exit /b 1
)

echo OK: modo tunel publico ativado com origens restritas:
echo   %ALLOWED%
echo.
echo Reinicie a API Dark-Jutsu para aplicar.
exit /b 0
