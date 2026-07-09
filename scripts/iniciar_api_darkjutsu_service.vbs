Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

shareRoot = "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
logDir = "C:\DarkJutsu\logs"
If Not fso.FolderExists("C:\DarkJutsu") Then fso.CreateFolder("C:\DarkJutsu")
If Not fso.FolderExists(logDir) Then fso.CreateFolder(logDir)

userRoot = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\Desktop\Dark-Jutsu"
machineRoot = "C:\DarkJutsu\Dark-Jutsu"
root = ""

If fso.FileExists(userRoot & "\api\iniciar_api_servidor.bat") Then
  root = userRoot
ElseIf fso.FileExists(machineRoot & "\api\iniciar_api_servidor.bat") Then
  root = machineRoot
End If

If root = "" Then
  Set errFile = fso.OpenTextFile(logDir & "\api_runtime.log", 8, True)
  errFile.WriteLine Now & " api\iniciar_api_servidor.bat nao encontrado em " & userRoot & " nem " & machineRoot
  errFile.Close
  shell.Run "cmd /c """ & shareRoot & "\scripts\registrar_evento_servidor_darkjutsu.bat"" ""ERRO"" ""API"" ""Nao encontrou api\iniciar_api_servidor.bat no usuario nem em C:\DarkJutsu\Dark-Jutsu.""", 0, True
  WScript.Quit 1
End If

shell.CurrentDirectory = root
shell.Run "cmd /c """ & shareRoot & "\scripts\registrar_evento_servidor_darkjutsu.bat"" ""INFO"" ""API"" ""Iniciando API usando root: " & root & """", 0, True
cmd = "cmd /c ""cd /d """ & root & """ && api\iniciar_api_servidor.bat >> ""C:\DarkJutsu\logs\api_runtime.log"" 2>&1"""
shell.Run cmd, 0, False
