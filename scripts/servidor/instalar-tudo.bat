@echo off
setlocal EnableExtensions

set "SCRIPTS_DIR=%~dp0.."
pushd "%SCRIPTS_DIR%" || exit /b 1

call instalar_atalho_servidor_guardiao_darkjutsu.bat
call instalar_guardiao_continuo_darkjutsu.bat
call instalar_monitor_servidor_darkjutsu.bat
call instalar_sincronizacao_5min_darkjutsu.bat

popd
exit /b 0
