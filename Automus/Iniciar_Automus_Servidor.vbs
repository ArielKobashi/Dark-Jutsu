Option Explicit

Dim fso, shell, root, pointer, version, appDir, exePath
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
pointer = fso.BuildPath(root, "versao_atual.txt")

If Not fso.FileExists(pointer) Then
    MsgBox "Automus: versao_atual.txt nao foi encontrado no servidor.", 16, "Automus"
    WScript.Quit 1
End If

version = Trim(fso.OpenTextFile(pointer, 1, False).ReadAll)
appDir = fso.BuildPath(fso.BuildPath(root, "Aplicacao"), version)
exePath = fso.BuildPath(appDir, "Automus.exe")

If Not fso.FileExists(exePath) Then
    MsgBox "Automus nao encontrado no servidor: " & exePath, 16, "Automus"
    WScript.Quit 2
End If

' O Automus usa esta variavel para manter o atalho de inicializacao apontando
' ao launcher estavel, e nao a uma versao especifica.
shell.Environment("PROCESS")("AUTOMUS_SERVER_LAUNCHER") = WScript.ScriptFullName
shell.CurrentDirectory = appDir
shell.Run Chr(34) & exePath & Chr(34) & " --background", 0, False
