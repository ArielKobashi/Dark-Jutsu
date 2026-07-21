$ErrorActionPreference = "Continue"

$shareScripts = "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts"
$automusReleaseRoot = "\\fileserver\Almoxarifado\0800\automus"
$automusSignalFile = Join-Path $automusReleaseRoot "sinal_atualizacao.txt"
$localDir = Join-Path $env:LOCALAPPDATA "DarkJutsu\monitor"
$pythonDir = Join-Path $env:USERPROFILE "Desktop\aplicacoes code\WPy64-3.13.12.0\python"
$pythonw = Join-Path $pythonDir "pythonw.exe"
$logDir = Join-Path $env:LOCALAPPDATA "DarkJutsu\logs"
$logFile = Join-Path $logDir "watchdog_usuario.log"
$activeRuntimeFile = Join-Path $localDir "active_runtime.txt"
$automusSignalStateFile = Join-Path $localDir "automus_sinal_atualizacao_visto.txt"
$created = $false
$mutex = [Threading.Mutex]::new($true, "Local\DarkJutsuUserWatchdog", [ref]$created)
if (-not $created) { exit 0 }

New-Item -ItemType Directory -Path $localDir,$logDir -Force | Out-Null

function Write-WatchdogLog([string]$message) {
  Add-Content -LiteralPath $logFile -Encoding UTF8 -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $message"
}

function Get-ActiveRuntimeDir {
  try {
    if (Test-Path -LiteralPath $activeRuntimeFile) {
      $candidate = (Get-Content -LiteralPath $activeRuntimeFile -Raw).Trim()
      if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
  } catch {}
  return $localDir
}

function Sync-File([string]$name, [string]$targetDir) {
  $source = Join-Path $shareScripts $name
  $target = Join-Path $targetDir $name
  if (-not (Test-Path -LiteralPath $source)) { return $false }
  try {
    $copy = -not (Test-Path -LiteralPath $target)
    if (-not $copy) {
      $copy = (Get-Item $source).LastWriteTimeUtc -gt (Get-Item $target).LastWriteTimeUtc -or (Get-Item $source).Length -ne (Get-Item $target).Length
    }
    if ($copy) {
      Copy-Item -LiteralPath $source -Destination $target -Force
      Write-WatchdogLog "Atualizado: $name"
      return $true
    }
    return $false
  } catch {
    Write-WatchdogLog "Falha ao atualizar ${name}: $($_.Exception.Message)"
    return $false
  }
}

function Stop-ProcessesByPattern([string]$pattern) {
  try {
    Get-CimInstance Win32_Process -ErrorAction Stop |
      Where-Object {
        $_.CommandLine -and
        $_.CommandLine -match [regex]::Escape($pattern) -and
        $_.ProcessId -ne $PID
      } |
      ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        Write-WatchdogLog "Processo reiniciado por atualizacao: $pattern pid=$($_.ProcessId)"
      }
  } catch {
    Write-WatchdogLog "Falha ao reiniciar processo ${pattern}: $($_.Exception.Message)"
  }
}

function Process-Exists([string]$pattern) {
  if ($pattern -eq "guardiao_loop_python_darkjutsu.py") {
    $lockFile = Join-Path $logDir "guardiao_loop_python.lock"
    try {
      if (-not (Test-Path -LiteralPath $lockFile)) { return $false }
      $lockPid = [int](Get-Content -LiteralPath $lockFile -Raw).Trim()
      $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$lockPid" -ErrorAction Stop
      return [bool]($proc -and $proc.CommandLine -and $proc.CommandLine -match [regex]::Escape($pattern))
    } catch { return $false }
  }
  if ($pattern -eq "monitor_reserva_python_darkjutsu.py") {
    $lockFile = Join-Path $logDir "monitor_python.lock"
    try {
      if (Test-Path -LiteralPath $lockFile) {
        $lockPid = [int](Get-Content -LiteralPath $lockFile -Raw).Trim()
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$lockPid" -ErrorAction Stop
        if ($proc -and $proc.CommandLine -and $proc.CommandLine -match [regex]::Escape($pattern)) { return $true }
      }
    } catch {}
    $monitorMutex = $null
    try {
      $monitorMutex = [Threading.Mutex]::OpenExisting("Global\DarkJutsuMonitorReservaPython")
      return $true
    } catch { return $false }
    finally { if ($monitorMutex) { $monitorMutex.Dispose() } }
  }
  try {
    return [bool](Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object {
      $_.CommandLine -and $_.CommandLine -match [regex]::Escape($pattern)
    } | Select-Object -First 1)
  } catch { return $false }
}

function Get-AutomusUpdateSignal {
  try {
    if (Test-Path -LiteralPath $automusSignalFile) {
      return (Get-Content -LiteralPath $automusSignalFile -Raw -ErrorAction Stop).Trim()
    }
  } catch {
    Write-WatchdogLog "Aviso: nao foi possivel ler sinal do Automus: $($_.Exception.Message)"
  }
  return ""
}

function Get-LastSeenAutomusSignal {
  try {
    if (Test-Path -LiteralPath $automusSignalStateFile) {
      return (Get-Content -LiteralPath $automusSignalStateFile -Raw -ErrorAction Stop).Trim()
    }
  } catch {}
  return ""
}

function Set-LastSeenAutomusSignal([string]$signal) {
  try {
    Set-Content -LiteralPath $automusSignalStateFile -Encoding ASCII -NoNewline -Value $signal
  } catch {
    Write-WatchdogLog "Aviso: nao foi possivel salvar sinal visto do Automus: $($_.Exception.Message)"
  }
}

function Test-NeedsUpdate([string]$name, [string]$targetDir) {
  $source = Join-Path $shareScripts $name
  $target = Join-Path $targetDir $name
  if (-not (Test-Path -LiteralPath $source)) { return $false }
  if (-not (Test-Path -LiteralPath $target)) { return $true }
  try {
    return (Get-Item $source).LastWriteTimeUtc -gt (Get-Item $target).LastWriteTimeUtc -or (Get-Item $source).Length -ne (Get-Item $target).Length
  } catch {
    return $true
  }
}

function New-RuntimeDir {
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  $runtimeDir = Join-Path $localDir "runtime_$stamp"
  New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
  $ok = $true
  foreach ($name in @(
    "guardiao_loop_python_darkjutsu.py",
    "servidor_eleicao_darkjutsu.py",
    "servidores_config.json",
    "status_compartilhado_servidores_darkjutsu.py",
    "abrir_status_darkjutsu.py",
    "monitor_reserva_python_darkjutsu.py",
    "iniciar_automus_com_guardiao_darkjutsu.ps1",
    "iniciar_tunel_celular_darkjutsu.ps1",
    "watchdog_usuario_darkjutsu.ps1"
  )) {
    $source = Join-Path $shareScripts $name
    $target = Join-Path $runtimeDir $name
    if (-not (Test-Path -LiteralPath $source)) {
      Write-WatchdogLog "Runtime novo incompleto: fonte ausente $name"
      $ok = $false
      continue
    }
    try {
      Copy-Item -LiteralPath $source -Destination $target -Force -ErrorAction Stop
    } catch {
      Write-WatchdogLog "Runtime novo falhou ao copiar ${name}: $($_.Exception.Message)"
      $ok = $false
    }
  }
  if (-not $ok) { return $null }
  try {
    Set-Content -LiteralPath $activeRuntimeFile -Encoding ASCII -NoNewline -Value $runtimeDir
    Write-WatchdogLog "Runtime ativo trocado para $runtimeDir"
  } catch {
    Write-WatchdogLog "Aviso: nao foi possivel salvar runtime ativo $runtimeDir - $($_.Exception.Message)"
  }
  return $runtimeDir
}

try {
  Write-WatchdogLog "Watchdog iniciado. Usuario=$env:USERNAME Maquina=$env:COMPUTERNAME"
  $lastAutomusUpdateCheck = [datetime]::MinValue
  $lastSeenAutomusSignal = Get-LastSeenAutomusSignal
  while ($true) {
    $runtimeDir = Get-ActiveRuntimeDir
    $updatedFiles = @{}
    $needsRuntimeSwitch = (Test-NeedsUpdate "guardiao_loop_python_darkjutsu.py" $runtimeDir) -or (Test-NeedsUpdate "monitor_reserva_python_darkjutsu.py" $runtimeDir)
    if ($needsRuntimeSwitch -and (Split-Path $runtimeDir -Leaf) -like "runtime_*") {
      $newRuntime = New-RuntimeDir
      if ($newRuntime) {
        $runtimeDir = $newRuntime
        $updatedFiles["guardiao_loop_python_darkjutsu.py"] = $true
        $updatedFiles["monitor_reserva_python_darkjutsu.py"] = $true
      }
    }
    foreach ($name in @(
      "guardiao_loop_python_darkjutsu.py",
      "servidor_eleicao_darkjutsu.py",
      "servidores_config.json",
      "monitor_reserva_python_darkjutsu.py",
      "iniciar_automus_com_guardiao_darkjutsu.ps1",
      "iniciar_tunel_celular_darkjutsu.ps1"
    )) {
      if (Sync-File $name $runtimeDir) { $updatedFiles[$name] = $true }
    }

    if ($updatedFiles["guardiao_loop_python_darkjutsu.py"]) {
      Stop-ProcessesByPattern "guardiao_loop_python_darkjutsu.py"
      Start-Sleep -Seconds 1
    }
    if ($updatedFiles["monitor_reserva_python_darkjutsu.py"]) {
      Stop-ProcessesByPattern "monitor_reserva_python_darkjutsu.py"
      Start-Sleep -Seconds 1
    }

    if (Test-Path $pythonw) {
      if (-not (Process-Exists "guardiao_loop_python_darkjutsu.py")) {
        Start-Process $pythonw -ArgumentList "`"$(Join-Path $runtimeDir 'guardiao_loop_python_darkjutsu.py')`"" -WindowStyle Hidden
        Write-WatchdogLog "Guardiao reiniciado."
      }
      if (-not (Process-Exists "monitor_reserva_python_darkjutsu.py")) {
        Start-Process $pythonw -ArgumentList "`"$(Join-Path $runtimeDir 'monitor_reserva_python_darkjutsu.py')`"" -WindowStyle Hidden
        Write-WatchdogLog "Monitor reiniciado."
      }
    }

    $automusMissing = -not (Get-Process -Name Automus -ErrorAction SilentlyContinue)
    $currentAutomusSignal = Get-AutomusUpdateSignal
    $automusSignalReceived = -not [string]::IsNullOrWhiteSpace($currentAutomusSignal) -and $currentAutomusSignal -ne $lastSeenAutomusSignal
    $automusCheckDue = ((Get-Date) - $lastAutomusUpdateCheck).TotalSeconds -ge 300
    if ($automusMissing -or $automusSignalReceived -or $automusCheckDue) {
      $launcher = Join-Path $runtimeDir "iniciar_automus_com_guardiao_darkjutsu.ps1"
      if (Test-Path $launcher) {
        Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`"" -WindowStyle Hidden
        $lastAutomusUpdateCheck = Get-Date
        if ($automusSignalReceived) {
          $lastSeenAutomusSignal = $currentAutomusSignal
          Set-LastSeenAutomusSignal $currentAutomusSignal
        }
        $reason = if ($automusSignalReceived) { "sinal de atualizacao recebido: $currentAutomusSignal" } elseif ($automusMissing) { "processo ausente" } else { "intervalo de 5 minutos" }
        Write-WatchdogLog "Verificacao oculta do Automus acionada. Motivo=$reason."
      }
    }
    Start-Sleep -Seconds 15
  }
} finally {
  $mutex.ReleaseMutex()
  $mutex.Dispose()
}
