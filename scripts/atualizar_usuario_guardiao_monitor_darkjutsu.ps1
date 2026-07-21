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
    Add-Content -Path $LogFile -Encoding UTF8 -Value "$stamp | $Message" -ErrorAction Stop
  } catch {
    Start-Sleep -Milliseconds 200
    try { Add-Content -Path $LogFile -Encoding UTF8 -Value "$stamp | $Message" -ErrorAction Stop } catch {}
  }
  Write-Host $Message
}

function Copy-Required($Name) {
  $src = Join-Path $Scripts $Name
  $dst = Join-Path $LocalDir $Name
  try {
    Copy-Item $src $dst -Force -ErrorAction Stop
    Log "OK: copiado $Name"
    return $dst
  } catch {
    Log "ERRO: nao consegui copiar $Name - $($_.Exception.Message)"
    return $null
  }
}

function Copy-ToRuntime($Name, $RuntimeDir) {
  $src = Join-Path $Scripts $Name
  $dst = Join-Path $RuntimeDir $Name
  try {
    Copy-Item $src $dst -Force -ErrorAction Stop
    Log "OK: runtime recebeu $Name"
    return $dst
  } catch {
    Log "ERRO: runtime nao recebeu $Name - $($_.Exception.Message)"
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

function Test-ProcessHandle($Process) {
  if (-not $Process) { return $false }
  try {
    $Process.Refresh()
    return -not $Process.HasExited
  } catch {
    return $false
  }
}

function Test-GuardianLock {
  $lockFile = Join-Path $LogDir "guardiao_loop_python.lock"
  try {
    if (-not (Test-Path -LiteralPath $lockFile)) { return $false }
    $lockPid = [int](Get-Content -LiteralPath $lockFile -Raw).Trim()
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$lockPid" -ErrorAction Stop
    return [bool]($proc -and $proc.CommandLine -and $proc.CommandLine -match "guardiao_loop_python_darkjutsu.py")
  } catch {
    return $false
  }
}

function Test-MonitorMutex {
  $lockFile = Join-Path $LogDir "monitor_python.lock"
  try {
    if (Test-Path -LiteralPath $lockFile) {
      $lockPid = [int](Get-Content -LiteralPath $lockFile -Raw).Trim()
      $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$lockPid" -ErrorAction Stop
      if ($proc -and $proc.CommandLine -and $proc.CommandLine -match "monitor_reserva_python_darkjutsu.py") { return $true }
    }
  } catch {}
  $mutex = $null
  try {
    $mutex = [Threading.Mutex]::OpenExisting("Global\DarkJutsuMonitorReservaPython")
    return $true
  } catch {
    return $false
  } finally {
    if ($mutex) { $mutex.Dispose() }
  }
}

function Stop-OldProcesses {
  $currentPid = $PID
  $parentPid = $null
  try {
    $selfProc = Get-CimInstance Win32_Process -Filter "ProcessId=$currentPid" -ErrorAction Stop
    $parentPid = $selfProc.ParentProcessId
  } catch {}
  $patterns = @(
    "monitor_reserva_python_darkjutsu",
    "monitor_servidor_python_darkjutsu",
    "monitor_principal_powershell_darkjutsu",
    "guardiao_loop_python_darkjutsu",
    "guardiao_loop_compartilhado_darkjutsu",
    "watchdog_usuario_darkjutsu"
  )
  try {
    Get-CimInstance Win32_Process |
      Where-Object {
        if ($_.ProcessId -eq $currentPid -or ($parentPid -and $_.ProcessId -eq $parentPid)) { return $false }
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

function Write-StartupVbs($Name, $CommandLine, [bool]$AllowVersionedFallback = $true) {
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
    if (-not $AllowVersionedFallback) {
      return $false
    }
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

Stop-OldProcesses
Start-Sleep -Seconds 1

$role = "CANDIDATO"
$monitorPrefix = "monitor_reserva_python_darkjutsu"
Log "Papel detectado: $role"

Copy-Required "status_compartilhado_servidores_darkjutsu.py" | Out-Null
Copy-Required "abrir_status_darkjutsu.py" | Out-Null
Copy-Required "servidores_config.json" | Out-Null

& schtasks.exe /Delete /F /TN "Dark-Jutsu Restaurar Reserva" 2>$null | Out-Null
Log "OK: tarefa antiga de restauracao recorrente removida."

$startupDir = [Environment]::GetFolderPath("Startup")
foreach ($legacyName in @(
  "Automus_Controlador_Atualizacoes.bat",
  "Automus_Atualizacoes.bat",
  "Automus.bat",
  "Dark-Jutsu Cluster Usuario.cmd",
  "Restaurar Reserva Dark-Jutsu.vbs",
  "Restaurar Reserva Dark-Jutsu.lnk"
)) {
  $legacyPath = Join-Path $startupDir $legacyName
  if (Test-Path -LiteralPath $legacyPath) {
    Remove-Item -LiteralPath $legacyPath -Force -ErrorAction SilentlyContinue
    Log "OK: inicializacao direta antiga removida: $legacyName"
  }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runtimeDir = Join-Path $LocalDir "runtime_$stamp"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

$runtimeOk = $true
foreach ($runtimeName in @(
  "status_compartilhado_servidores_darkjutsu.py",
  "abrir_status_darkjutsu.py",
  "guardiao_loop_python_darkjutsu.py",
  "servidor_eleicao_darkjutsu.py",
  "servidores_config.json",
  "monitor_reserva_python_darkjutsu.py",
  "iniciar_automus_com_guardiao_darkjutsu.ps1",
  "iniciar_tunel_celular_darkjutsu.ps1",
  "watchdog_usuario_darkjutsu.ps1"
)) {
  if (-not (Copy-ToRuntime $runtimeName $runtimeDir)) { $runtimeOk = $false }
}

if (-not $runtimeOk) {
  Log "ERRO: runtime novo ficou incompleto em $runtimeDir"
  exit 1
}

try {
  Set-Content -LiteralPath (Join-Path $LocalDir "active_runtime.txt") -Encoding ASCII -Value $runtimeDir -ErrorAction Stop
  Log "OK: runtime ativo apontando para $runtimeDir"
} catch {
  Log "AVISO: nao consegui gravar active_runtime.txt - $($_.Exception.Message)"
}

$monitorLocal = Join-Path $runtimeDir "monitor_reserva_python_darkjutsu.py"
$guardianLocal = Join-Path $runtimeDir "guardiao_loop_python_darkjutsu.py"
$statusLauncher = Join-Path $runtimeDir "abrir_status_darkjutsu.py"
$automusLauncher = Join-Path $runtimeDir "iniciar_automus_com_guardiao_darkjutsu.ps1"
$watchdogLocal = Join-Path $runtimeDir "watchdog_usuario_darkjutsu.ps1"

try {
  New-Item -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Force -ErrorAction Stop | Out-Null
  Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Dark-Jutsu Monitor Servidor" -Value "`"$PythonW`" `"$monitorLocal`"" -ErrorAction Stop
  Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Dark-Jutsu Guardiao Servidor" -Value "`"$PythonW`" `"$guardianLocal`"" -ErrorAction Stop
  Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Dark-Jutsu Automus" -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$automusLauncher`"" -ErrorAction Stop
  Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Dark-Jutsu Watchdog" -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watchdogLocal`"" -ErrorAction Stop
  Log "OK: inicializacao tambem registrada em HKCU Run."
  $registryOk = $true
} catch {
  Log "AVISO: Registro HKCU Run bloqueado; usando pasta Inicializar. $($_.Exception.Message)"
  $registryOk = $false
}

$allowVersionedFallback = -not $registryOk
$startupMonitorOk = Write-StartupVbs "Monitor Servidor Dark-Jutsu.vbs" "`"$PythonW`" `"$monitorLocal`"" $allowVersionedFallback
$startupGuardianOk = Write-StartupVbs "Guardiao Servidor Dark-Jutsu.vbs" "`"$PythonW`" `"$guardianLocal`"" $allowVersionedFallback
$startupAutomusOk = Write-StartupVbs "Automus com Guardiao Dark-Jutsu.vbs" "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$automusLauncher`"" $allowVersionedFallback
$startupWatchdogOk = Write-StartupVbs "Watchdog Usuario Dark-Jutsu.vbs" "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watchdogLocal`"" $allowVersionedFallback

if ($registryOk) {
  foreach ($pattern in @(
    "Monitor Servidor Dark-Jutsu_*.vbs",
    "Guardiao Servidor Dark-Jutsu_*.vbs",
    "Automus com Guardiao Dark-Jutsu_*.vbs",
    "Watchdog Usuario Dark-Jutsu_*.vbs"
  )) {
    Get-ChildItem -LiteralPath $startupDir -Filter $pattern -ErrorAction SilentlyContinue |
      ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
      }
  }
  Log "OK: atalhos versionados antigos removidos; HKCU Run e o caminho principal."
}

$monitorProcess = Start-Process -FilePath $PythonW -ArgumentList "`"$monitorLocal`"" -PassThru
$guardianProcess = Start-Process -FilePath $PythonW -ArgumentList "`"$guardianLocal`"" -PassThru
Start-Process -FilePath powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$automusLauncher`""
Start-Process -FilePath powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watchdogLocal`""
Start-Sleep -Seconds 5

$monitorOk = (Test-ProcessHandle $monitorProcess) -or (Test-MonitorMutex)
$guardianOk = (Test-ProcessHandle $guardianProcess) -or (Test-GuardianLock)

if ($monitorOk) { Log "OK: monitor rodando." } else { Log "ERRO: monitor nao apareceu nos processos." }
if ($guardianOk) { Log "OK: guardiao rodando." } else { Log "ERRO: guardiao nao apareceu nos processos." }

if ((-not $NoStatus) -and (Test-Path $statusLauncher)) {
  Log "Abrindo status final..."
  & $Python $statusLauncher
}

if ($monitorOk -and $guardianOk -and (($startupMonitorOk -and $startupGuardianOk -and $startupAutomusOk -and $startupWatchdogOk) -or $registryOk)) {
  Log "RESULTADO: OK"
  exit 0
}

Log "RESULTADO: ATENCAO"
if (-not (($startupMonitorOk -and $startupGuardianOk -and $startupAutomusOk -and $startupWatchdogOk) -or $registryOk)) {
  Log "ATENCAO: monitor/guardiao estao rodando agora, mas inicializacao automatica foi bloqueada pelo Windows."
}
exit 2
