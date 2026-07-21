Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
bat = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "iniciar_api_celular_8766_oculta.bat")
shell.Run "cmd.exe /d /c """ & bat & """ --hidden", 0, False
