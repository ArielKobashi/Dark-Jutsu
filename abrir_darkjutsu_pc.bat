@echo off
setlocal
set "URL=http://127.0.0.1:8765/?apiBase=http%%3A%%2F%%2F127.0.0.1%%3A8765"
echo Abrindo Dark-Jutsu no PC:
echo %URL%
start "" "%URL%"
