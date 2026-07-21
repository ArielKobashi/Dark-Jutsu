@echo off
setlocal EnableExtensions
if /I not "%~1"=="--hidden" (
  wscript.exe //B "%~dp0iniciar_api_celular_8766_oculta.vbs"
  exit
)
set "ROOT=%~dp0.."
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0iniciar_api_celular_8766_direta.ps1" -Root "%ROOT%" -Port 8766
