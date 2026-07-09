@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "SHARE_LOG_DIR=%SHARE_ROOT%\logs"
set "SHARE_LOG=%SHARE_LOG_DIR%\servidor_eventos_darkjutsu.txt"
set "LEVEL=%~1"
set "COMPONENT=%~2"
set "MESSAGE=%~3"
set "PYTHON_EXE="

if "%LEVEL%"=="" set "LEVEL=INFO"
if "%COMPONENT%"=="" set "COMPONENT=GERAL"
if "%MESSAGE%"=="" set "MESSAGE=%*"

if not exist "%SHARE_LOG_DIR%" mkdir "%SHARE_LOG_DIR%" 2>nul

set "STAMP="
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value 2^>nul ^| find "="') do set "DT=%%I"
if defined DT set "STAMP=%DT:~0,4%-%DT:~4,2%-%DT:~6,2% %DT:~8,2%:%DT:~10,2%:%DT:~12,2%"
if not defined STAMP set "STAMP=%date% %time%"

>>"%SHARE_LOG%" echo %STAMP% ^| %COMPUTERNAME% ^| %USERNAME% ^| %LEVEL% ^| %COMPONENT% ^| %MESSAGE%

call :try_python "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\python.exe"
if not defined PYTHON_EXE (
  for /d %%D in ("%USERPROFILE%\Desktop\aplica* code") do (
    if not defined PYTHON_EXE call :try_python "%%~fD\WPy64-3.13.12.0\python\python.exe"
  )
)
if not defined PYTHON_EXE call :try_python "%SHARE_ROOT%\instaladores\WPy64-3.13.12.0\python\python.exe"

if defined PYTHON_EXE (
  set "PY_HOME=%PYTHON_EXE:\python.exe=%"
  set "PYTHONHOME=%PY_HOME%"
  set "PYTHONPATH=%PY_HOME%\Lib;%PY_HOME%\Lib\site-packages"
  "%PYTHON_EXE%" "%SHARE_ROOT%\scripts\limpar_log_72h_darkjutsu.py" "%SHARE_LOG%" >nul 2>nul
)

exit /b 0

:try_python
if defined PYTHON_EXE exit /b 0
if not exist "%~1" exit /b 0
if not exist "%~dp1Lib\encodings\__init__.py" exit /b 0
set "PYTHON_EXE=%~1"
exit /b 0
