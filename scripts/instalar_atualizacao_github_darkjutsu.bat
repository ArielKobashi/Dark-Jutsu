@echo off
setlocal EnableExtensions

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "SHARE_SCRIPTS=%SHARE_ROOT%\scripts"
set "LOCAL_DIR=%LOCALAPPDATA%\DarkJutsu\monitor"
set "LOGDIR=C:\DarkJutsu\logs"
set "LOGFILE=%LOGDIR%\instalar_atualizacao_github.log"
set "RUN_NAME=Dark-Jutsu Atualizacao GitHub"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
if not exist "%LOCAL_DIR%" mkdir "%LOCAL_DIR%" 2>nul

echo ==================================================
echo Dark-Jutsu - Instalador Atualizacao GitHub
echo Usuario: %USERNAME%
echo Maquina: %COMPUTERNAME%
echo ==================================================
echo.
>>"%LOGFILE%" echo ==================================================
>>"%LOGFILE%" echo [%date% %time%] Instalando atualizacao GitHub. Usuario=%USERNAME% Maquina=%COMPUTERNAME%

if not exist "%SHARE_SCRIPTS%\atualizar_darkjutsu_do_github.bat" (
  echo FALHOU: atualizador nao encontrado na rede.
  >>"%LOGFILE%" echo [%date% %time%] FALHOU: atualizador nao encontrado na rede.
  exit /b 1
)

copy /Y "%SHARE_SCRIPTS%\atualizar_darkjutsu_do_github.bat" "%LOCAL_DIR%\atualizar_darkjutsu_do_github.bat" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo FALHOU: nao consegui copiar atualizador local.
  >>"%LOGFILE%" echo [%date% %time%] FALHOU: copia local.
  exit /b 1
)

(
  echo Set shell = CreateObject("WScript.Shell"^)
  echo Do
  echo   shell.Run "cmd /c ""%LOCAL_DIR%\atualizar_darkjutsu_do_github.bat""", 0, True
  echo   WScript.Sleep 300000
  echo Loop
) > "%LOCAL_DIR%\atualizacao_github_loop.vbs"
if not exist "%LOCAL_DIR%\atualizacao_github_loop.vbs" (
  echo FALHOU: nao consegui criar loop local.
  >>"%LOGFILE%" echo [%date% %time%] FALHOU: loop local nao criado.
  exit /b 1
)

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%RUN_NAME%" /t REG_SZ /d "wscript.exe //B %LOCAL_DIR%\atualizacao_github_loop.vbs" /f >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo AVISO: Registro HKCU bloqueou inicializacao automatica.
  >>"%LOGFILE%" echo [%date% %time%] AVISO: Registro HKCU bloqueou Run.
) else (
  echo OK: Atualizacao GitHub instalada no login do usuario.
  >>"%LOGFILE%" echo [%date% %time%] OK: Run instalado.
)

wmic process where "CommandLine like '%%atualizacao_github_loop%%'" call terminate >> "%LOGFILE%" 2>&1
start "" wscript.exe //B "%LOCAL_DIR%\atualizacao_github_loop.vbs"

echo OK: Atualizador iniciado agora.
echo Log:
echo C:\DarkJutsu\logs\atualizacao_github.log
exit /b 0
