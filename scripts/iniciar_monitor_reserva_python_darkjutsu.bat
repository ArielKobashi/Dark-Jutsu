@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "LOGDIR=C:\DarkJutsu\logs"
set "LAUNCH_LOG=%LOGDIR%\monitor_launcher.log"
set "LOCAL_DIR=%LOCALAPPDATA%\DarkJutsu\monitor"
set "LOCAL_SCRIPT=%LOCAL_DIR%\monitor_reserva_python_darkjutsu.py"
set "SHARE_SCRIPT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\monitor_reserva_python_darkjutsu.py"
set "PYTHONW_EXE="
set "PYTHON_EXE="

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
>>"%LAUNCH_LOG%" echo ==================================================
>>"%LAUNCH_LOG%" echo [%date% %time%] Launcher monitor reserva. Usuario=%USERNAME% Maquina=%COMPUTERNAME%
>>"%LAUNCH_LOG%" echo [%date% %time%] Limpando monitores antigos/duplicados antes de iniciar.
wmic process where "CommandLine like '%%monitor_servidor_darkjutsu_py.py%%' or CommandLine like '%%monitor_servidor_darkjutsu_py.bat%%' or CommandLine like '%%monitor_servidor_darkjutsu.ps1%%' or CommandLine like '%%monitor_principal_powershell_darkjutsu.ps1%%'" call terminate >> "%LAUNCH_LOG%" 2>&1
wmic process where "CommandLine like '%%monitor_reserva_python_darkjutsu.py%%'" call terminate >> "%LAUNCH_LOG%" 2>&1

if exist "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\pythonw.exe" if exist "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\Lib\encodings\__init__.py" set "PYTHONW_EXE=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\pythonw.exe"
if exist "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\python.exe" if exist "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\Lib\encodings\__init__.py" set "PYTHON_EXE=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\python.exe"

if not defined PYTHONW_EXE (
  for /d %%D in ("%USERPROFILE%\Desktop\aplica* code") do (
    if not defined PYTHONW_EXE if exist "%%~fD\WPy64-3.13.12.0\python\pythonw.exe" if exist "%%~fD\WPy64-3.13.12.0\python\Lib\encodings\__init__.py" set "PYTHONW_EXE=%%~fD\WPy64-3.13.12.0\python\pythonw.exe"
    if not defined PYTHON_EXE if exist "%%~fD\WPy64-3.13.12.0\python\python.exe" if exist "%%~fD\WPy64-3.13.12.0\python\Lib\encodings\__init__.py" set "PYTHON_EXE=%%~fD\WPy64-3.13.12.0\python\python.exe"
  )
)

if not defined PYTHONW_EXE if not defined PYTHON_EXE (
  >>"%LAUNCH_LOG%" echo [%date% %time%] FALHOU: Python portatil nao encontrado.
  echo Python portatil nao encontrado.
  exit /b 1
)

if exist "%LOCAL_SCRIPT%" (
  set "TARGET_SCRIPT=%LOCAL_SCRIPT%"
) else if exist "%SHARE_SCRIPT%" (
  set "TARGET_SCRIPT=%SHARE_SCRIPT%"
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
  >>"%LAUNCH_LOG%" echo [%date% %time%] Iniciando com pythonw=%PYTHONW_EXE%
  start "Dark-Jutsu Monitor Reserva" "%PYTHONW_EXE%" "%TARGET_SCRIPT%"
) else (
  >>"%LAUNCH_LOG%" echo [%date% %time%] Iniciando com python=%PYTHON_EXE%
  start "Dark-Jutsu Monitor Reserva" /min "%PYTHON_EXE%" "%TARGET_SCRIPT%" 1>>"%LAUNCH_LOG%" 2>>&1
)

exit /b 0
