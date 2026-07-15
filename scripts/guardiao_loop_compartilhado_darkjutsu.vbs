On Error Resume Next

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

shareScripts = "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts"
shareRoot = "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
cmdExe = "C:\Windows\SysWOW64\cmd.exe"
logFile = "C:\DarkJutsu\logs\guardiao_loop_compartilhado.log"

Sub Log(msg)
  On Error Resume Next
  If Not fso.FolderExists("C:\DarkJutsu\logs") Then fso.CreateFolder("C:\DarkJutsu\logs")
  Set fh = fso.OpenTextFile(logFile, 8, True)
  fh.WriteLine Now & " | " & msg
  fh.Close
End Sub

Sub RunHidden(command)
  On Error Resume Next
  Err.Clear
  rc = shell.Run(command, 0, True)
  If Err.Number <> 0 Then
    Log "ERRO ao executar: " & command & " | " & Err.Number & " | " & Err.Description
    Err.Clear
  ElseIf rc <> 0 Then
    Log "Comando retornou codigo " & rc & ": " & command
  End If
End Sub

Log "Guardiao loop iniciado. Usuario=" & shell.ExpandEnvironmentStrings("%USERNAME%") & " Maquina=" & shell.ExpandEnvironmentStrings("%COMPUTERNAME%")

Do
  RunHidden """" & cmdExe & """ /c """ & shareScripts & "\verificar_atualizar_instalacao_local_darkjutsu.bat"""
  If fso.FileExists(shareRoot & "\forcar-reinstalacao-guardiao-monitor.txt") Then
    RunHidden """" & cmdExe & """ /c """ & shareScripts & "\reiniciar_monitor_python_darkjutsu.bat"""
  End If
  RunHidden """" & cmdExe & """ /c """ & shareScripts & "\publicar_status_servidor_darkjutsu.bat"""
  RunHidden """" & cmdExe & """ /c """ & shareScripts & "\guardiao_servidor_tick_darkjutsu.bat"""
  WScript.Sleep 60000
Loop
