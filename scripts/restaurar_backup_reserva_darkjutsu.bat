@echo off
setlocal EnableExtensions

rem Compatibilidade com tarefas antigas: remove a chamada recorrente e converte
rem este disparo em uma unica ativacao silenciosa do Guardiao/monitor/watchdog.
schtasks.exe /Delete /F /TN "Dark-Jutsu Restaurar Reserva" >nul 2>&1
start "" /B powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\atualizar_usuario_guardiao_monitor_darkjutsu.ps1" -NoStatus
exit /b 0
