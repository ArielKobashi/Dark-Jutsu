Set shell = CreateObject("WScript.Shell")
shell.Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\monitor_principal_powershell_darkjutsu.ps1""", 0, False
