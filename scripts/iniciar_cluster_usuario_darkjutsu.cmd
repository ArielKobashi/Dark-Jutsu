@echo off
setlocal
set "PYTHONW=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\pythonw.exe"
set "PYTHON=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\python.exe"
set "MONITOR=%LOCALAPPDATA%\DarkJutsu\monitor"
if exist "%PYTHONW%" (
  start "" /min "%PYTHONW%" "%MONITOR%\guardiao_loop_python_darkjutsu.py"
  start "" /min "%PYTHONW%" "%MONITOR%\monitor_reserva_python_darkjutsu.py"
) else (
  start "" /min "%PYTHON%" "%MONITOR%\guardiao_loop_python_darkjutsu.py"
  start "" /min "%PYTHON%" "%MONITOR%\monitor_reserva_python_darkjutsu.py"
)
start "" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%MONITOR%\iniciar_automus_com_guardiao_darkjutsu.ps1"
exit /b 0
