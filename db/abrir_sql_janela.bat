@echo off
setlocal EnableExtensions
title Controle Dark-Jutsu Servidor
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0abrir_sql_janela.ps1"
if errorlevel 1 pause
