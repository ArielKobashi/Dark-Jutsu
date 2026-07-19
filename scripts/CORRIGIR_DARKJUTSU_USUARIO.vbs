Set shell = CreateObject("WScript.Shell")

scriptPath = "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\atualizar_usuario_guardiao_monitor_darkjutsu.ps1"
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File " & Chr(34) & scriptPath & Chr(34) & " -NoStatus"
code = shell.Run(command, 1, True)

If code = 0 Then
  MsgBox "Guardiao, monitor e Automus foram atualizados e iniciados para este usuario.", 64, "Dark-Jutsu corrigido"
Else
  MsgBox "A correcao terminou com codigo " & code & ". Verifique o log em %LOCALAPPDATA%\DarkJutsu\logs.", 48, "Dark-Jutsu"
End If
