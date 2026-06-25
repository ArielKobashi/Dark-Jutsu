@echo off
setlocal
cd /d "%~dp0"

set "AUTOMUS_EXE=%cd%\Automus.exe"
if not exist "%AUTOMUS_EXE%" set "AUTOMUS_EXE=%cd%\dist\Automus\Automus.exe"
if not exist "%AUTOMUS_EXE%" set "AUTOMUS_EXE=%cd%\..\Automus.exe"

if exist "%AUTOMUS_EXE%" (
  start "" "%AUTOMUS_EXE%"
  exit /b 0
)

echo Automus.exe nao encontrado.
echo Extraia o pacote Automus-v*.zip inteiro e abra novamente por este arquivo.
echo.
echo Este launcher nao precisa de Python, mas o Automus.exe precisa estar na mesma pasta.
pause
exit /b 1
