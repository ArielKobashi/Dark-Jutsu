@echo off
setlocal EnableExtensions

set "SCRIPT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\backup_postgres_darkjutsu_hidden.vbs"
set "TASK_NAME=Dark-Jutsu Backup PostgreSQL Principal"

schtasks /Delete /F /TN "%TASK_NAME%" >nul 2>&1
schtasks /Create /F /TN "%TASK_NAME%" /SC MINUTE /MO 5 /TR "wscript.exe //B \"%SCRIPT%\"" >nul 2>&1
if %errorlevel%==0 (
    echo Rotina instalada: backup a cada 5 minutos.
    exit /b 0
)

echo ERRO: nao foi possivel criar tarefa agendada de backup.
exit /b 1
