@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"

echo Reiniciando monitor visual Dark-Jutsu...
echo.
echo Se o icone preto antigo continuar perto do relogio, encerre o processo
echo "Windows PowerShell" antigo pelo Gerenciador de Tarefas e rode este arquivo de novo.
echo.

start "Monitor Dark-Jutsu" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\monitor_principal_powershell_darkjutsu.ps1"
exit /b 0
