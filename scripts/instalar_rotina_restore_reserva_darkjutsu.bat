@echo off
setlocal EnableExtensions

set "SCRIPT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\restaurar_backup_reserva_darkjutsu.bat"
set "TASK_NAME=Dark-Jutsu Restaurar Reserva"

schtasks /Create /F /TN "%TASK_NAME%" /SC MINUTE /MO 5 /TR "\"%SCRIPT%\"" >nul 2>&1
if %errorlevel%==0 (
    echo Rotina instalada: reserva verifica backups a cada 5 minutos.
    exit /b 0
)

echo Nao foi possivel criar tarefa agendada. Criando atalho no Inicializar como fallback.
set "SHORTCUT_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Restaurar Reserva Dark-Jutsu.lnk"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath='%SCRIPT%'; $s.WorkingDirectory='\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts'; $s.WindowStyle=7; $s.Save()"
exit /b %errorlevel%
