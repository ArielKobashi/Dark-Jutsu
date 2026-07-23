@echo off
setlocal EnableExtensions

set "PYROOT=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0"
set "PYDIR=%PYROOT%\python"

echo Dark-Jutsu - instalador rapido
echo Usuario: %USERNAME%
echo Maquina: %COMPUTERNAME%
echo.

if exist "%PYROOT%" (
  if not exist "%PYDIR%\python.exe" goto limpar_python
  if not exist "%PYDIR%\pythonw.exe" goto limpar_python
  if not exist "%PYDIR%\Lib\encodings\__init__.py" goto limpar_python
  goto instalar
)
goto instalar

:limpar_python
echo Python portable local parece incompleto. Limpando copia quebrada...
rmdir /s /q "%PYROOT%" 2>nul

:instalar
call "%~dp0instalar_atualizar_guardiao_monitor_darkjutsu.bat"
set "ERR=%ERRORLEVEL%"
echo.
if "%ERR%"=="0" (
  echo OK: instalacao concluida.
) else (
  echo ERRO: instalador terminou com codigo %ERR%.
)
pause
exit /b %ERR%
