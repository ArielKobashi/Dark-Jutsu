Set shell = CreateObject("WScript.Shell")
updater = "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\atualizar_usuario_guardiao_monitor_darkjutsu.ps1"

shell.Run "schtasks.exe /Delete /F /TN ""Dark-Jutsu Restaurar Reserva""", 0, True
repairCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & updater & Chr(34) & " -NoStatus"
shell.Run repairCommand, 0, True
