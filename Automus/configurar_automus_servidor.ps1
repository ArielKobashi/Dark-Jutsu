$ErrorActionPreference = "Stop"

$ServerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerLauncher = Join-Path $ServerRoot "Iniciar_Automus_Servidor.vbs"
if (-not (Test-Path -LiteralPath $ServerLauncher)) {
    throw "Launcher do servidor nao encontrado: $ServerLauncher"
}

# HKCU Run evita depender da pasta Startup, que pode ser protegida por politica
# corporativa. O registro pertence somente ao usuario e nao exige administrador.
$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$WscriptExe = Join-Path $env:WINDIR "System32\wscript.exe"
$RunCommand = '"' + $WscriptExe + '" "' + $ServerLauncher + '"'
New-Item -Path $RunKey -Force | Out-Null
Set-ItemProperty -LiteralPath $RunKey -Name "AutomusServidor" -Value $RunCommand -Type String

$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "Automus.lnk"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "$env:WINDIR\System32\wscript.exe"
$Shortcut.Arguments = '"' + $ServerLauncher + '"'
$Shortcut.WorkingDirectory = $ServerRoot
$Shortcut.Description = "Automus centralizado no servidor"
$Shortcut.Save()

Start-Process -FilePath "$env:WINDIR\System32\wscript.exe" -ArgumentList ('"' + $ServerLauncher + '"')

Write-Host "Inicializacao automatica registrada no usuario atual (HKCU Run)."
Write-Host "Atalho: $ShortcutPath"
Write-Host "Aplicacao executada diretamente de: $ServerRoot"
