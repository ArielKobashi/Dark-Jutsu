@echo off
setlocal EnableExtensions

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"

echo Instalando sincronizacao Dark-Jutsu nesta maquina...
echo.
echo Regra:
echo - se a API local estiver ativa, esta maquina gera backups a cada 5 minutos;
echo - se a API local estiver desligada, esta maquina restaura o backup mais recente a cada 5 minutos.
echo.

call "%SHARE_ROOT%\scripts\instalar_rotina_backup_principal_5min_darkjutsu.bat"
if errorlevel 1 echo AVISO: rotina de backup nao foi instalada como tarefa.

call "%SHARE_ROOT%\scripts\instalar_rotina_restore_reserva_5min_darkjutsu.bat"
if errorlevel 1 echo AVISO: rotina de restore nao foi instalada como tarefa.

echo.
echo Sincronizacao instalada com sucesso.
exit /b 0
