@echo off
setlocal EnableExtensions

set "SCRIPTS_DIR=%~dp0.."
pushd "%SCRIPTS_DIR%" || exit /b 1

call instalar_atualizar_guardiao_monitor_darkjutsu.bat
call instalar_sincronizacao_5min_darkjutsu.bat

popd
exit /b 0

