@echo off
setlocal
cd /d "%~dp0"
where pyw >nul 2>nul && (
  pyw -3 "scripts\preparar_release_automus.py"
  exit /b %errorlevel%
)
where pythonw >nul 2>nul && (
  pythonw "scripts\preparar_release_automus.py"
  exit /b %errorlevel%
)
where py >nul 2>nul && (
  py -3 "scripts\preparar_release_automus.py"
  exit /b %errorlevel%
)
where python >nul 2>nul && (
  python "scripts\preparar_release_automus.py"
  exit /b %errorlevel%
)
echo Python nao encontrado. Instale o Python ou execute o publicador em um ambiente com Python.
pause
exit /b 1
