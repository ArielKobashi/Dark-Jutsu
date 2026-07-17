param(
  [switch]$NoStatus
)

$ErrorActionPreference = "Continue"

$ShareRoot = "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
$Scripts = Join-Path $ShareRoot "scripts"
$LocalDir = Join-Path $env:LOCALAPPDATA "DarkJutsu\monitor"
$LogDir = Join-Path $env:LOCALAPPDATA "DarkJutsu\logs"
$LogFile = Join-Path $LogDir "atualizar_usuario_guardiao_monitor.log"
$PyDir = Join-Path $env:USERPROFILE "Desktop\aplicacoes code\WPy64-3.13.12.0\python"
$Python = Join-Path $PyDir "python.exe"
$PythonW = Join-Path $PyDir "pythonw.exe"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null

function Log($Message) {
  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  try {
    Add-Content -Path $LogFile -Encoding UTF8 -Value "$stamp | $Message"
  } catch {
    Start-Sleep -Milliseconds 200
    try { Add-Content -Path $LogFile -Encoding UTF8 -Value "$stamp | $Message" } catch {}
  }
  Write-Host $Message
}

function Copy-Required($Name) {
  $src = Join-Path $Scripts $Name
  $dst = Join-Path $LocalDir $Name
  try {
    Copy-Item $src $dst -Force
    Log "OK: copiado $Name"
    return $dst
  } catch {
    Log "ERRO: nao consegui copiar $Name - $($_.Exception.Message)"
    return $null
  }
}

function Has-Ip($Ip) {
  try {
    $text = ipconfig | Out-String
    return $text.Contains($Ip)
  } catch {
    return $false
  }
}

function Stop-OldProcesses {
  $patterns = @(
    "monitor_reserva_python_darkjutsu",
    "monitor_servidor_python_darkjutsu",
    "monitor_principal_powershell_darkjutsu",
    "guardiao_loop_python_darkjutsu",
    "guardiao_loop_compartilhado_darkjutsu"
  )
  try {
    Get-CimInstance Win32_Process |
      Where-Object {
        $cmd = $_.CommandLine
        if (-not $cmd) { return $false }
        foreach ($p in $patterns) {
          if ($cmd -match [regex]::Escape($p)) { return $true }
        }
        return $false
      } |
      ForEach-Object {
        Log "Encerrando processo antigo: $($_.ProcessId) $($_.Name)"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
      }
  } catch {
    Log "AVISO: nao consegui encerrar todos os processos antigos - $($_.Exception.Message)"
  }
}

function Write-StartupVbs($Name, $CommandLine) {
  $startup = [Environment]::GetFolderPath("Startup")
  if (-not $startup) {
    Log "AVISO: pasta Inicializar nao encontrada."
    return $false
  }
  $path = Join-Path $startup $Name
  $escaped = $CommandLine.Replace("""", """""")
  $content = "Set shell = CreateObject(""WScript.Shell"")`r`nshell.Run ""$escaped"", 0, False`r`n"
  try {
    Set-Content -Path $path -Encoding ASCII -Value $content -ErrorAction Stop
    Log "OK: inicializacao criada em $path"
    return $true
  } catch {
    Log "AVISO: nao consegui criar inicializacao fixa $path - $($_.Exception.Message)"
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $versioned = Join-Path $startup ($Name.Replace(".vbs", "_$stamp.vbs"))
    try {
      Set-Content -Path $versioned -Encoding ASCII -Value $content -ErrorAction Stop
      Log "OK: inicializacao criada em arquivo versionado $versioned"
      return $true
    } catch {
      Log "ERRO: pasta Inicializar bloqueou tambem arquivo versionado - $($_.Exception.Message)"
      return $false
    }
  }
}

Log "=================================================="
Log "Atualizando usuario Dark-Jutsu. Usuario=$env:USERNAME Maquina=$env:COMPUTERNAME"

if (-not (Test-Path $PythonW) -or -not (Test-Path $Python)) {
  $pySource = Join-Path $ShareRoot "instaladores\WPy64-3.13.12.0"
  $pyTarget = Split-Path $PyDir -Parent
  Log "Python portable ausente; copiando para o perfil deste usuario..."
  New-Item -ItemType Directory -Force -Path $pyTarget | Out-Null
  & robocopy $pySource $pyTarget /E /R:2 /W:2 /NFL /NDL /NP | Out-Null
  if ($LASTEXITCODE -ge 8 -or -not (Test-Path $PythonW) -or -not (Test-Path $Python)) {
    Log "ERRO: nao consegui preparar o Python portable em $PyDir"
    exit 1
  }
}

$role = "CANDIDATO"
$monitorPrefix = "monitor_reserva_python_darkjutsu"
Log "Papel detectado: $role"

Copy-Required "status_compartilhado_servidores_darkjutsu.py" | Out-Null
Copy-Required "abrir_status_darkjutsu.py" | Out-Null
Copy-Required "guardiao_loop_python_darkjutsu.py" | Out-Null
Copy-Required "servidor_eleicao_darkjutsu.py" | Out-Null
Copy-Required "servidores_config.json" | Out-Null
Copy-Required "iniciar_automus_com_guardiao_darkjutsu.ps1" | Out-Null

Stop-OldProcesses
Start-Sleep -Seconds 1

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$monitorLocal = Join-Path $LocalDir "$monitorPrefix`_$stamp.py"
try {
  Copy-Item (Join-Path $Scripts "monitor_reserva_python_darkjutsu.py") $monitorLocal -Force
  Log "OK: monitor atualizado em arquivo versionado: $monitorLocal"
} catch {
  Log "ERRO: nao consegui criar monitor versionado - $($_.Exception.Message)"
  exit 1
}

$guardianLocal = Join-Path $LocalDir "guardiao_loop_python_darkjutsu.py"
$statusLauncher = Join-Path $LocalDir "abrir_status_darkjutsu.py"
$automusLauncher = Join-Path $LocalDir "iniciar_automus_com_guardiao_darkjutsu.ps1"

$startupMonitorOk = Write-StartupVbs "Monitor Servidor Dark-Jutsu.vbs" "`"$PythonW`" `"$monitorLocal`""
$startupGuardianOk = Write-StartupVbs "Guardiao Servidor Dark-Jutsu.vbs" "`"$PythonW`" `"$guardianLocal`""
$startupAutomusOk = Write-StartupVbs "Automus com Guardiao Dark-Jutsu.vbs" "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$automusLauncher`""

try {
  New-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Force -ErrorAction Stop | Out-Null
  Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Dark-Jutsu Monitor Servidor" -Value "`"$PythonW`" `"$monitorLocal`"" -ErrorAction Stop
  Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Dark-Jutsu Guardiao Servidor" -Value "`"$PythonW`" `"$guardianLocal`"" -ErrorAction Stop
  Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Dark-Jutsu Automus" -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$automusLauncher`"" -ErrorAction Stop
  Log "OK: inicializacao tambem registrada em HKCU Run."
  $registryOk = $true
} catch {
  Log "AVISO: Registro HKCU Run bloqueado; usando pasta Inicializar. $($_.Exception.Message)"
  $registryOk = $false
}

Start-Process -FilePath $PythonW -ArgumentList "`"$monitorLocal`""
Start-Process -FilePath $PythonW -ArgumentList "`"$guardianLocal`""
Start-Process -FilePath powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$automusLauncher`""
Start-Sleep -Seconds 5

$procs = Get-CimInstance Win32_Process | Where-Object {
  $_.CommandLine -match "monitor_reserva_python_darkjutsu|monitor_servidor_python_darkjutsu|guardiao_loop_python_darkjutsu"
}
$monitorOk = $false
$guardianOk = $false
foreach ($p in $procs) {
  if ($p.CommandLine -match "monitor_reserva_python_darkjutsu|monitor_servidor_python_darkjutsu") { $monitorOk = $true }
  if ($p.CommandLine -match "guardiao_loop_python_darkjutsu") { $guardianOk = $true }
}

if ($monitorOk) { Log "OK: monitor rodando." } else { Log "ERRO: monitor nao apareceu nos processos." }
if ($guardianOk) { Log "OK: guardiao rodando." } else { Log "ERRO: guardiao nao apareceu nos processos." }

if ((-not $NoStatus) -and (Test-Path $statusLauncher)) {
  Log "Abrindo status final..."
  & $Python $statusLauncher
}

if ($monitorOk -and $guardianOk -and (($startupMonitorOk -and $startupGuardianOk -and $startupAutomusOk) -or $registryOk)) {
  Log "RESULTADO: OK"
  exit 0
}

Log "RESULTADO: ATENCAO"
if (-not (($startupMonitorOk -and $startupGuardianOk -and $startupAutomusOk) -or $registryOk)) {
  Log "ATENCAO: monitor/guardiao estao rodando agora, mas inicializacao automatica foi bloqueada pelo Windows."
}
exit 2
