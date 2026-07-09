@echo off
setlocal EnableExtensions

set "SCRIPT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\monitor_servidor_darkjutsu_py.py"
set "LOCAL_SCRIPT=%USERPROFILE%\Desktop\Dark-Jutsu\scripts\monitor_servidor_darkjutsu_py.py"
set "PYTHON_EXE="

call :try_python "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\pythonw.exe"
if not defined PYTHON_EXE call :try_python "%USERPROFILE%\Desktop\aplicações code\WPy64-3.13.12.0\python\pythonw.exe"
if not defined PYTHON_EXE (
  for /d %%D in ("%USERPROFILE%\Desktop\aplica* code") do (
    if not defined PYTHON_EXE call :try_python "%%~fD\WPy64-3.13.12.0\python\pythonw.exe"
  )
)

if not defined PYTHON_EXE (
  echo Python portatil nao encontrado.
  exit /b 1
)

set "PYTHON_HOME=%PYTHON_EXE:\python.exe=%"
set "PYTHON_HOME=%PYTHON_HOME:\pythonw.exe=%"
set "PYTHONHOME=%PYTHON_HOME%"
set "PYTHONPATH=%PYTHON_HOME%\Lib;%PYTHON_HOME%\Lib\site-packages"

if exist "%LOCAL_SCRIPT%" (
  start "" "%PYTHON_EXE%" "%LOCAL_SCRIPT%"
) else if exist "%SCRIPT%" (
  start "" "%PYTHON_EXE%" "%SCRIPT%"
) else (
  echo monitor_servidor_darkjutsu_py.py nao encontrado.
  exit /b 1
)
exit /b 0

:try_python
if defined PYTHON_EXE exit /b 0
if exist "%~1" set "PYTHON_EXE=%~1"
exit /b 0
