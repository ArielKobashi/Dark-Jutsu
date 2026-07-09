Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\Desktop\Dark-Jutsu"
logDir = "C:\DarkJutsu\logs"
If Not fso.FolderExists("C:\DarkJutsu") Then fso.CreateFolder("C:\DarkJutsu")
If Not fso.FolderExists(logDir) Then fso.CreateFolder(logDir)

If Not fso.FileExists(root & "\api\iniciar_api_servidor.bat") Then
  Set errFile = fso.OpenTextFile(logDir & "\api_runtime.log", 8, True)
  errFile.WriteLine Now & " api\iniciar_api_servidor.bat nao encontrado em " & root
  errFile.Close
  WScript.Quit 1
End If

shell.CurrentDirectory = root
cmd = "cmd /c ""cd /d """ & root & """ && api\iniciar_api_servidor.bat >> ""C:\DarkJutsu\logs\api_runtime.log"" 2>&1"""
shell.Run cmd, 0, False
