@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "VBS=%STARTUP%\Dark-Jutsu Celular Sem Admin.vbs"

if not exist "%STARTUP%" mkdir "%STARTUP%" 2>nul

>"%VBS%" echo Set shell = CreateObject("WScript.Shell")
>>"%VBS%" echo shell.Run """" ^& "%ROOT%iniciar_darkjutsu_celular_sem_admin.bat" ^& """", 1, False

echo Pronto: o modo celular vai iniciar junto com este usuario do Windows.
echo Link e QR Code aparecem no Dark-Jutsu quando o tunel estiver ativo.
pause
exit /b 0
