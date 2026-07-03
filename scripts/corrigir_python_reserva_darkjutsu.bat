@echo off
setlocal EnableExtensions

set "PY_SOURCE=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\instaladores\WPy64-3.13.12.0\python"
set "PY_TARGET=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python"

if not exist "%PY_SOURCE%\python.exe" (
    echo ERRO: Python de origem nao encontrado em %PY_SOURCE%.
    exit /b 1
)

if not exist "%PY_TARGET%\python.exe" (
    echo Python local nao encontrado. Copiando instalador completo...
    mkdir "%USERPROFILE%\Desktop\aplicacoes code" 2>nul
    xcopy "%PY_SOURCE%\.." "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\" /E /I /Y
)

echo Corrigindo bibliotecas Python locais...
robocopy "%PY_SOURCE%\Lib\urllib" "%PY_TARGET%\Lib\urllib" /E /R:2 /W:2 /NFL /NDL /NP
robocopy "%PY_SOURCE%\Lib\sysconfig" "%PY_TARGET%\Lib\sysconfig" /E /R:2 /W:2 /NFL /NDL /NP
robocopy "%PY_SOURCE%\Lib\zipfile" "%PY_TARGET%\Lib\zipfile" /E /R:2 /W:2 /NFL /NDL /NP
robocopy "%PY_SOURCE%\Lib\zoneinfo" "%PY_TARGET%\Lib\zoneinfo" /E /R:2 /W:2 /NFL /NDL /NP
robocopy "%PY_SOURCE%\Lib\site-packages\psycopg" "%PY_TARGET%\Lib\site-packages\psycopg" /E /R:2 /W:2 /NFL /NDL /NP
robocopy "%PY_SOURCE%\Lib\site-packages\psycopg_binary" "%PY_TARGET%\Lib\site-packages\psycopg_binary" /E /R:2 /W:2 /NFL /NDL /NP
robocopy "%PY_SOURCE%\Lib\site-packages\psycopg_binary.libs" "%PY_TARGET%\Lib\site-packages\psycopg_binary.libs" /E /R:2 /W:2 /NFL /NDL /NP
robocopy "%PY_SOURCE%\Lib\site-packages\_distutils_hack" "%PY_TARGET%\Lib\site-packages\_distutils_hack" /E /R:2 /W:2 /NFL /NDL /NP
robocopy "%PY_SOURCE%\Lib\site-packages\win32\lib" "%PY_TARGET%\Lib\site-packages\win32\lib" /E /R:2 /W:2 /NFL /NDL /NP

del "%PY_TARGET%\Lib\site-packages\pywin32.pth" >nul 2>&1
del "%PY_TARGET%\Lib\site-packages\sphinxcontrib_jsmath-1.0.1-py3.7-nspkg.pth" >nul 2>&1

"%PY_TARGET%\python.exe" -c "import urllib.parse, http.server, email.utils, zipfile, zoneinfo; import psycopg; print('python-ok')"
if errorlevel 1 exit /b 1

echo Python corrigido com sucesso.
exit /b 0
