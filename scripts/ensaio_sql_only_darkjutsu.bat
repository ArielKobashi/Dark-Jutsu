@echo off
setlocal EnableExtensions

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ensaio_sql_only_darkjutsu.ps1"
exit /b %errorlevel%
