@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "PY_SOURCE=%SHARE_ROOT%\instaladores\WPy64-3.13.12.0\python"
set "PY_TARGET=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python"
set "LOGDIR=C:\DarkJutsu\logs"
set "LOGFILE=%LOGDIR%\corrigir_python_tkinter.log"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
echo ==================================================
echo Dark-Jutsu - Correcao Tkinter Python portatil
echo Usuario: %USERNAME%
echo Maquina: %COMPUTERNAME%
echo ==================================================
>>"%LOGFILE%" echo ==================================================
>>"%LOGFILE%" echo [%date% %time%] Correcao Tkinter. Usuario=%USERNAME% Maquina=%COMPUTERNAME%

if not exist "%PY_SOURCE%\Lib\tkinter\__init__.py" (
  echo FALHOU: fonte Tkinter nao encontrada na rede.
  >>"%LOGFILE%" echo [%date% %time%] FALHOU: fonte Tkinter nao encontrada em %PY_SOURCE%.
  exit /b 1
)

if not exist "%PY_TARGET%\python.exe" (
  echo Python local nao existe. Copiando Python portatil completo...
  >>"%LOGFILE%" echo [%date% %time%] Python local ausente; copiando completo.
  robocopy "%SHARE_ROOT%\instaladores\WPy64-3.13.12.0" "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0" /E /R:2 /W:2 /NFL /NDL /NP >> "%LOGFILE%" 2>&1
  if errorlevel 8 (
    echo FALHOU: nao consegui copiar Python completo.
    exit /b 1
  )
)

echo Copiando Tkinter...
robocopy "%PY_SOURCE%\Lib\tkinter" "%PY_TARGET%\Lib\tkinter" /E /R:2 /W:2 /NFL /NDL /NP >> "%LOGFILE%" 2>&1
if errorlevel 8 exit /b 1

echo Copiando Tcl/Tk...
robocopy "%PY_SOURCE%\tcl" "%PY_TARGET%\tcl" /E /R:2 /W:2 /NFL /NDL /NP >> "%LOGFILE%" 2>&1
if errorlevel 8 exit /b 1

echo Copiando DLLs Tk...
copy /Y "%PY_SOURCE%\DLLs\_tkinter.pyd" "%PY_TARGET%\DLLs\_tkinter.pyd" >> "%LOGFILE%" 2>&1
copy /Y "%PY_SOURCE%\DLLs\tcl86t.dll" "%PY_TARGET%\DLLs\tcl86t.dll" >> "%LOGFILE%" 2>&1
copy /Y "%PY_SOURCE%\DLLs\tk86t.dll" "%PY_TARGET%\DLLs\tk86t.dll" >> "%LOGFILE%" 2>&1

set "PYTHONHOME=%PY_TARGET%"
set "PYTHONPATH=%PY_TARGET%\Lib;%PY_TARGET%\Lib\site-packages"
set "TCL_LIBRARY=%PY_TARGET%\tcl\tcl8.6"
set "TK_LIBRARY=%PY_TARGET%\tcl\tk8.6"
"%PY_TARGET%\python.exe" -c "import tkinter; root=tkinter.Tk(); root.withdraw(); root.destroy(); print('tkinter-ok')" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo FALHOU: Tkinter ainda nao carregou. Veja:
  echo %LOGFILE%
  exit /b 1
)

echo OK: Tkinter corrigido.
>>"%LOGFILE%" echo [%date% %time%] OK: Tkinter corrigido.
exit /b 0
