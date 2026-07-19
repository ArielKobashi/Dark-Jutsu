Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

pythonw = shell.ExpandEnvironmentStrings("%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\pythonw.exe")
python = shell.ExpandEnvironmentStrings("%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\python.exe")
monitor = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\DarkJutsu\monitor")

If fso.FileExists(pythonw) Then
  shell.Run Chr(34) & pythonw & Chr(34) & " " & Chr(34) & monitor & "\guardiao_loop_python_darkjutsu.py" & Chr(34), 0, False
  shell.Run Chr(34) & pythonw & Chr(34) & " " & Chr(34) & monitor & "\monitor_reserva_python_darkjutsu.py" & Chr(34), 0, False
ElseIf fso.FileExists(python) Then
  shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & monitor & "\guardiao_loop_python_darkjutsu.py" & Chr(34), 0, False
  shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & monitor & "\monitor_reserva_python_darkjutsu.py" & Chr(34), 0, False
End If

automusLauncher = monitor & "\iniciar_automus_com_guardiao_darkjutsu.ps1"
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & automusLauncher & Chr(34), 0, False

watchdog = monitor & "\watchdog_usuario_darkjutsu.ps1"
If fso.FileExists(watchdog) Then
  shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & watchdog & Chr(34), 0, False
End If
