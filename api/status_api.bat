@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,State,OwningProcess"
pause
