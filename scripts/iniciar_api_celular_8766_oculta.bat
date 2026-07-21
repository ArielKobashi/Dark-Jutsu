@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."
set "DATABASE_URL=postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
set "DARK_JUTSU_API_HOST=127.0.0.1"
set "DARK_JUTSU_API_PORT=8766"
set "DARK_JUTSU_ALLOWED_ORIGINS=*"
set "DARK_JUTSU_APP_WEB_ROOT=%ROOT%"
cd /d "%ROOT%"
call "%ROOT%\api\iniciar_api_servidor.bat" > "%ROOT%\data\api_8766_stdout.log" 2> "%ROOT%\data\api_8766_stderr.log"
