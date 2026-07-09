@echo off
setlocal EnableExtensions

set "SCRIPT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\monitor_reserva_python_darkjutsu.py"
set "LOCAL_SCRIPT=%~dp0monitor_reserva_python_darkjutsu.py"
set "LOGDIR=C:\DarkJutsu\logs"
set "LAUNCH_LOG=%LOGDIR%\monitor_launcher.log"
set "PYTHONW_EXE="
set "PYTHON_EXE="

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
>>"%LAUNCH_LOG%" echo ==================================================
>>"%LAUNCH_LOG%" echo [%date% %time%] Iniciando launcher do monitor. Usuario=%USERNAME% Maquina=%COMPUTERNAME%

call :try_pythonw "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\pythonw.exe"
call :try_python "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\python.exe"
call :try_pythonw "%USERPROFILE%\Desktop\aplica????es code\WPy64-3.13.12.0\python\pythonw.exe"
call :try_python "%USERPROFILE%\Desktop\aplica????es code\WPy64-3.13.12.0\python\python.exe"

if not defined PYTHONW_EXE (
  for /d %%D in ("%USERPROFILE%\Desktop\aplica* code") do (
    if not defined PYTHONW_EXE call :try_pythonw "%%~fD\WPy64-3.13.12.0\python\pythonw.exe"
    if not defined PYTHON_EXE call :try_python "%%~fD\WPy64-3.13.12.0\python\python.exe"
  )
)

if not defined PYTHONW_EXE if not defined PYTHON_EXE (
  >>"%LAUNCH_LOG%" echo [%date% %time%] FALHOU: Python portatil nao encontrado.
  echo Python portatil nao encontrado.
  exit /b 1
)

if exist "%LOCAL_SCRIPT%" (
  set "TARGET_SCRIPT=%LOCAL_SCRIPT%"
) else if exist "%SCRIPT%" (
  set "TARGET_SCRIPT=%SCRIPT%"
) else (
  >>"%LAUNCH_LOG%" echo [%date% %time%] FALHOU: monitor_reserva_python_darkjutsu.py nao encontrado.
  echo monitor_reserva_python_darkjutsu.py nao encontrado.
  exit /b 1
)

if defined PYTHONW_EXE (
  set "PYTHON_HOME=%PYTHONW_EXE:\pythonw.exe=%"
) else (
  set "PYTHON_HOME=%PYTHON_EXE:\python.exe=%"
)
set "PYTHONHOME=%PYTHON_HOME%"
set "PYTHONPATH=%PYTHON_HOME%\Lib;%PYTHON_HOME%\Lib\site-packages"

>>"%LAUNCH_LOG%" echo [%date% %time%] PythonHome=%PYTHONHOME%
>>"%LAUNCH_LOG%" echo [%date% %time%] Script=%TARGET_SCRIPT%

if defined PYTHONW_EXE (
  >>"%LAUNCH_LOG%" echo [%date% %time%] Tentando pythonw=%PYTHONW_EXE%
  start "Dark-Jutsu Monitor" "%PYTHONW_EXE%" "%TARGET_SCRIPT%"
  timeout /t 3 /nobreak >nul
  wmic process where "CommandLine like '%%monitor_reserva_python_darkjutsu.py%%'" get ProcessId >nul 2>nul
  if not errorlevel 1 (
    >>"%LAUNCH_LOG%" echo [%date% %time%] Monitor iniciado com pythonw.
    exit /b 0
  )
)

if defined PYTHON_EXE (
  >>"%LAUNCH_LOG%" echo [%date% %time%] Tentando fallback python=%PYTHON_EXE%
  start "Dark-Jutsu Monitor" /min "%PYTHON_EXE%" "%TARGET_SCRIPT%" 1>>"%LAUNCH_LOG%" 2>>&1
  exit /b 0
)

exit /b 0

:try_pythonw
if defined PYTHONW_EXE exit /b 0
if not exist "%~1" exit /b 0
if not exist "%~dp1Lib\encodings\__init__.py" exit /b 0
set "PYTHONW_EXE=%~1"
exit /b 0

:try_python
if defined PYTHON_EXE exit /b 0
if not exist "%~1" exit /b 0
if not exist "%~dp1Lib\encodings\__init__.py" exit /b 0
set "PYTHON_EXE=%~1"
exit /b 0

