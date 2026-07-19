@echo off
setlocal EnableExtensions

rem A restauracao recorrente foi desativada: ela causava avisos de seguranca
rem e conflita com a eleicao dinamica atual.
schtasks.exe /Delete /F /TN "Dark-Jutsu Restaurar Reserva" >nul 2>&1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0atualizar_usuario_guardiao_monitor_darkjutsu.ps1" -NoStatus
exit /b %errorlevel%
