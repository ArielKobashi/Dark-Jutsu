@echo off
setlocal EnableExtensions

set "SCRIPT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\restaurar_backup_darkjutsu_hidden.vbs"
set "TASK_NAME=Dark-Jutsu Restaurar Reserva"

schtasks /Delete /F /TN "%TASK_NAME%" >nul 2>&1
schtasks /Create /F /TN "%TASK_NAME%" /SC MINUTE /MO 5 /TR "wscript.exe //B \"%SCRIPT%\"" >nul 2>&1
if %errorlevel%==0 (
    echo Rotina instalada: reserva verifica backups a cada 5 minutos.
    exit /b 0
)

echo ERRO: nao foi possivel criar tarefa agendada de restore da reserva.
exit /b 1
