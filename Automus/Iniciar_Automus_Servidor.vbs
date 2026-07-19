Option Explicit

Dim fso, shell, network, root, pointer, version, appDir, exePath
Dim logDir, statusDir, logPath, statusPath, machine, userName
Dim attempts, foundExe, launchCommand
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
Set network = CreateObject("WScript.Network")

root = fso.GetParentFolderName(WScript.ScriptFullName)
pointer = fso.BuildPath(root, "versao_atual.txt")
logDir = fso.BuildPath(root, "logs")
statusDir = fso.BuildPath(root, "status")
machine = network.ComputerName
userName = network.UserName
logPath = fso.BuildPath(logDir, "automus_launcher.log")
statusPath = fso.BuildPath(statusDir, "automus_" & machine & "_" & userName & ".txt")

Sub EnsureFolder(path)
    On Error Resume Next
    If Not fso.FolderExists(path) Then fso.CreateFolder(path)
    On Error GoTo 0
End Sub

Sub WriteLauncherLog(message)
    Dim line, file
    line = Now & " | " & machine & "\" & userName & " | " & message
    EnsureFolder logDir
    EnsureFolder statusDir
    On Error Resume Next
    Set file = fso.OpenTextFile(logPath, 8, True)
    file.WriteLine line
    file.Close
    Set file = fso.OpenTextFile(statusPath, 2, True)
    file.WriteLine line
    file.Close
    On Error GoTo 0
End Sub

WriteLauncherLog "START root=" & root

If Not fso.FileExists(pointer) Then
    WriteLauncherLog "ERRO pointer ausente: " & pointer
    MsgBox "Automus: versao_atual.txt nao foi encontrado no servidor.", 16, "Automus"
    WScript.Quit 1
End If

version = fso.OpenTextFile(pointer, 1, False).ReadAll
version = Replace(version, vbCr, "")
version = Replace(version, vbLf, "")
version = Trim(version)
appDir = fso.BuildPath(fso.BuildPath(root, "Aplicacao"), version)
exePath = fso.BuildPath(appDir, "Automus.exe")
WriteLauncherLog "VERSAO=" & version & " appDir=" & appDir & " exe=" & exePath

foundExe = False
For attempts = 1 To 8
    If fso.FileExists(exePath) Then
        foundExe = True
        Exit For
    End If
    WriteLauncherLog "AGUARDANDO exe tentativa=" & attempts & " existeAppDir=" & CStr(fso.FolderExists(appDir))
    WScript.Sleep 1500
Next

If Not foundExe Then
    WriteLauncherLog "ERRO exe ausente depois das tentativas: " & exePath
    MsgBox "Automus nao encontrado no servidor: " & exePath, 16, "Automus"
    WScript.Quit 2
End If

' O Automus usa esta variavel para manter o atalho de inicializacao apontando
' ao launcher estavel, e nao a uma versao especifica.
shell.Environment("PROCESS")("AUTOMUS_SERVER_LAUNCHER") = WScript.ScriptFullName
shell.CurrentDirectory = appDir
launchCommand = Chr(34) & exePath & Chr(34) & " --background"
WriteLauncherLog "OK iniciando: " & launchCommand
shell.Run launchCommand, 0, False
