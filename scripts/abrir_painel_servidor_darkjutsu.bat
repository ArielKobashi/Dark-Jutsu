@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT=%~dp0painel_servidor_darkjutsu.py"
set "PYTHON_EXE="
set "PYTHONW_EXE="
set "LOGDIR=C:\DarkJutsu\logs"
set "LAUNCH_LOG=%LOGDIR%\painel_launcher.log"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
>>"%LAUNCH_LOG%" echo ==================================================
>>"%LAUNCH_LOG%" echo [%date% %time%] Abrindo painel. Usuario=%USERNAME% Maquina=%COMPUTERNAME%
>>"%LAUNCH_LOG%" echo [%date% %time%] Script esperado=%SCRIPT%

if exist "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\python.exe" if exist "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\Lib\encodings\__init__.py" set "PYTHON_EXE=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\python.exe"
if exist "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\pythonw.exe" if exist "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\Lib\encodings\__init__.py" set "PYTHONW_EXE=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\pythonw.exe"

if not defined PYTHON_EXE (
  for /d %%D in ("%USERPROFILE%\Desktop\aplica* code") do (
    if not defined PYTHON_EXE if exist "%%~fD\WPy64-3.13.12.0\python\python.exe" if exist "%%~fD\WPy64-3.13.12.0\python\Lib\encodings\__init__.py" set "PYTHON_EXE=%%~fD\WPy64-3.13.12.0\python\python.exe"
    if not defined PYTHONW_EXE if exist "%%~fD\WPy64-3.13.12.0\python\pythonw.exe" if exist "%%~fD\WPy64-3.13.12.0\python\Lib\encodings\__init__.py" set "PYTHONW_EXE=%%~fD\WPy64-3.13.12.0\python\pythonw.exe"
  )
)

if not defined PYTHON_EXE if exist "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\instaladores\WPy64-3.13.12.0\python\python.exe" if exist "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\instaladores\WPy64-3.13.12.0\python\Lib\encodings\__init__.py" set "PYTHON_EXE=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\instaladores\WPy64-3.13.12.0\python\python.exe"
if not defined PYTHONW_EXE if exist "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\instaladores\WPy64-3.13.12.0\python\pythonw.exe" if exist "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\instaladores\WPy64-3.13.12.0\python\Lib\encodings\__init__.py" set "PYTHONW_EXE=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\instaladores\WPy64-3.13.12.0\python\pythonw.exe"

if not defined PYTHON_EXE if defined PYTHONW_EXE set "PYTHON_EXE=%PYTHONW_EXE%"
if not defined PYTHON_EXE (
  >>"%LAUNCH_LOG%" echo [%date% %time%] FALHOU: Python portatil nao encontrado.
  echo Python portatil nao encontrado.
  pause
  exit /b 1
)

if not exist "%SCRIPT%" (
  >>"%LAUNCH_LOG%" echo [%date% %time%] FALHOU: painel_servidor_darkjutsu.py nao encontrado.
  echo painel_servidor_darkjutsu.py nao encontrado:
  echo %SCRIPT%
  pause
  exit /b 1
)

set "PY_HOME=%PYTHON_EXE:\pythonw.exe=%"
set "PY_HOME=%PY_HOME:\python.exe=%"
set "PYTHONHOME=%PY_HOME%"
set "PYTHONPATH=%PY_HOME%\Lib;%PY_HOME%\Lib\site-packages"

>>"%LAUNCH_LOG%" echo [%date% %time%] Python=%PYTHON_EXE%
>>"%LAUNCH_LOG%" echo [%date% %time%] PythonHome=%PYTHONHOME%
echo [%date% %time%] Iniciando processo do painel... >> "%LAUNCH_LOG%"
start "Dark-Jutsu Painel" /min cmd /c ""%PYTHON_EXE%" "%SCRIPT%" 1>>"%LAUNCH_LOG%" 2>>&1"
>>"%LAUNCH_LOG%" echo [%date% %time%] Comando enviado ao Windows.
exit /b 0
