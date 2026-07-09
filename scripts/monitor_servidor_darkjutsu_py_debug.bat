@echo off
setlocal EnableExtensions

title Dark-Jutsu - Diagnostico do Monitor
echo ==================================================
echo Dark-Jutsu - Diagnostico do Monitor Python
echo Usuario: %USERNAME%
echo Maquina: %COMPUTERNAME%
echo ==================================================
echo.

set "SCRIPT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\monitor_servidor_darkjutsu_py.py"
set "LOCAL_SCRIPT=%USERPROFILE%\Desktop\Dark-Jutsu\scripts\monitor_servidor_darkjutsu_py.py"
set "PYTHON_EXE="

call :try_python "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\python.exe"
if not defined PYTHON_EXE call :try_python "%USERPROFILE%\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe"
if not defined PYTHON_EXE (
  for /d %%D in ("%USERPROFILE%\Desktop\aplica* code") do (
    if not defined PYTHON_EXE call :try_python "%%~fD\WPy64-3.13.12.0\python\python.exe"
  )
)

if not defined PYTHON_EXE (
  echo ERRO: Python portatil nao encontrado.
  echo Procurei em:
  echo %USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\python.exe
  echo %USERPROFILE%\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe
  echo.
  pause
  exit /b 1
)

echo Python encontrado:
echo %PYTHON_EXE%
echo.

set "PYTHON_HOME=%PYTHON_EXE:\python.exe=%"
set "PYTHON_HOME=%PYTHON_HOME:\pythonw.exe=%"
set "PYTHONHOME=%PYTHON_HOME%"
set "PYTHONPATH=%PYTHON_HOME%\Lib;%PYTHON_HOME%\Lib\site-packages"

if exist "%LOCAL_SCRIPT%" (
  echo Script usado:
  echo %LOCAL_SCRIPT%
  echo.
  "%PYTHON_EXE%" "%LOCAL_SCRIPT%"
) else if exist "%SCRIPT%" (
  echo AVISO: script local nao encontrado. Usando rede:
  echo %SCRIPT%
  echo.
  "%PYTHON_EXE%" "%SCRIPT%"
) else (
  echo ERRO: monitor_servidor_darkjutsu_py.py nao encontrado na rede nem local.
  echo Rede: %SCRIPT%
  echo Local: %LOCAL_SCRIPT%
  echo.
  pause
  exit /b 1
)

echo.
echo Monitor encerrou com codigo %errorlevel%.
pause
exit /b %errorlevel%

:try_python
if defined PYTHON_EXE exit /b 0
if exist "%~1" set "PYTHON_EXE=%~1"
exit /b 0
