@echo off
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ports = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue; if (-not $ports) { Write-Host 'API nao esta ouvindo na porta 8765.'; exit 0 }; foreach ($p in $ports) { Write-Host ('Encerrando PID ' + $p.OwningProcess); Stop-Process -Id $p.OwningProcess -Force }"
pause
