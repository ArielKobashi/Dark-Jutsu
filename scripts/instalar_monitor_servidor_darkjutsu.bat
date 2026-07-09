@echo off
setlocal EnableExtensions

set "SCRIPT_UNC=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\monitor_servidor_darkjutsu_hidden.vbs"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_NAME=Monitor Servidor Dark-Jutsu.lnk"
set "SHORTCUT_PATH=%STARTUP%\%SHORTCUT_NAME%"
set "FALLBACK_CMD=%STARTUP%\Monitor Servidor Dark-Jutsu.cmd"

if not exist "%SCRIPT_UNC%" (
    echo ERRO: script nao encontrado em:
    echo %SCRIPT_UNC%
    exit /b 1
)

echo Encerrando monitor antigo, se estiver aberto...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$self=$PID; Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $self -and $_.CommandLine -match 'monitor_servidor_darkjutsu\\.ps1|monitor_servidor_darkjutsu_hidden\\.vbs' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }" >nul 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath='wscript.exe'; $s.Arguments='//B ""%SCRIPT_UNC%""'; $s.WorkingDirectory='\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts'; $s.WindowStyle=7; $s.Save()"

if %errorlevel%==0 (
    echo Atalho do monitor criado em:
    echo %SHORTCUT_PATH%
    echo.
    echo Iniciando monitor agora...
    wscript.exe //B "%SCRIPT_UNC%"
    exit /b 0
)

echo AVISO: nao foi possivel criar o atalho .lnk do monitor.
echo Criando fallback .cmd no Inicializar...
(
    echo @echo off
    echo wscript.exe //B "%SCRIPT_UNC%"
) > "%FALLBACK_CMD%" 2>nul

if exist "%FALLBACK_CMD%" (
    echo Fallback criado em:
    echo %FALLBACK_CMD%
) else (
    echo AVISO: tambem nao foi possivel criar fallback no Inicializar.
    echo Criando fallback por tarefa agendada ao fazer logon...
    schtasks /Delete /F /TN "Dark-Jutsu Monitor Servidor" >nul 2>nul
    schtasks /Create /F /TN "Dark-Jutsu Monitor Servidor" /SC ONLOGON /TR "wscript.exe //B \"%SCRIPT_UNC%\"" >nul 2>nul
    if %errorlevel%==0 (
        echo Fallback criado por tarefa agendada ao fazer logon:
        echo Dark-Jutsu Monitor Servidor
    ) else (
        echo AVISO: tambem nao foi possivel criar tarefa agendada do monitor.
    )
    echo Criando fallback no Registro do usuario...
    reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "Dark-Jutsu Monitor Servidor" /t REG_SZ /d "wscript.exe //B \"%SCRIPT_UNC%\"" /f >nul 2>nul
    if %errorlevel%==0 (
        echo Fallback criado no Registro do usuario:
        echo HKCU\Software\Microsoft\Windows\CurrentVersion\Run\Dark-Jutsu Monitor Servidor
    ) else (
        echo AVISO: tambem nao foi possivel criar fallback no Registro.
    )
)

echo.
echo Tentando iniciar o monitor mesmo assim...
wscript.exe //B "%SCRIPT_UNC%"
echo Se o icone aparecer, o monitor esta funcionando nesta sessao.
echo Para inicializacao automatica, rode este CMD como o proprio usuario do Windows.
exit /b 0
