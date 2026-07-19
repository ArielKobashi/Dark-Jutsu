@echo off
setlocal EnableExtensions

rem Mantido apenas como compatibilidade com instalacoes antigas.
schtasks.exe /Delete /F /TN "Dark-Jutsu Restaurar Reserva" >nul 2>&1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0atualizar_usuario_guardiao_monitor_darkjutsu.ps1" -NoStatus
exit /b %errorlevel%
