$ErrorActionPreference = "Stop"

$ShareRoot = "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
$ShareScripts = Join-Path $ShareRoot "scripts"
$LocalDir = Join-Path $env:LOCALAPPDATA "DarkJutsu\monitor"
$PreferredLogDir = "C:\DarkJutsu\logs"
$FallbackLogDir = Join-Path $env:LOCALAPPDATA "DarkJutsu\logs"
$LogDir = $PreferredLogDir
try {
  New-Item -ItemType Directory -Force -Path $PreferredLogDir -ErrorAction Stop | Out-Null
} catch {
  $LogDir = $FallbackLogDir
}
$LogFile = Join-Path $LogDir "autoatualizacao_local.log"
$StateFile = Join-Path $LocalDir "versao_instalada_guardiao_monitor.txt"
$LockDir = Join-Path $LogDir "autoatualizacao_local.lock"
$Installer = Join-Path $ShareScripts "instalar_atualizar_guardiao_monitor_darkjutsu.bat"
$EventLogger = Join-Path $ShareScripts "registrar_evento_servidor_darkjutsu.bat"
$ForceReinstallFlag = Join-Path $ShareRoot "forcar-reinstalacao-guardiao-monitor.txt"
$ForceReinstallState = Join-Path $LocalDir "ultima_reinstalacao_forcada.txt"

$TrackedFiles = @(
  "instalar_atualizar_guardiao_monitor_darkjutsu.bat",
  "iniciar_automus_com_guardiao_darkjutsu.ps1",
  "iniciar_tunel_celular_darkjutsu.ps1",
  "guardiao_loop_python_darkjutsu.py",
  "servidor_eleicao_darkjutsu.py",
  "servidores_config.json",
  "guardiao_servidor_tick_darkjutsu.bat",
  "atualizar_darkjutsu_do_github.bat",
  "status_compartilhado_servidores_darkjutsu.py",
  "abrir_status_darkjutsu.py",
  "monitor_reserva_python_darkjutsu.py",
  "monitor_principal_powershell_darkjutsu.ps1",
  "iniciar_monitor_reserva_python_darkjutsu.bat",
  "iniciar_monitor_principal_powershell_oculto.vbs",
  "abrir_painel_servidor_darkjutsu.bat",
  "painel_servidor_darkjutsu.py",
  "corrigir_python_tkinter_darkjutsu.bat",
  "assumir_servidor_darkjutsu.bat",
  "parar_api_darkjutsu.bat",
  "registrar_evento_servidor_darkjutsu.bat",
  "limpar_log_72h_darkjutsu.py"
)

function Write-Log {
  param([string]$Message)
  try {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
  } catch {}

  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  $line = "$stamp | $Message"

  for ($i = 1; $i -le 8; $i++) {
    try {
      $stream = [System.IO.File]::Open($LogFile, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
      try {
        $writer = New-Object System.IO.StreamWriter($stream, [System.Text.Encoding]::UTF8)
        try {
          $writer.WriteLine($line)
          return
        } finally {
          $writer.Dispose()
        }
      } finally {
        $stream.Dispose()
      }
    } catch {
      Start-Sleep -Milliseconds (150 * $i)
    }
  }

  try {
    $fallback = Join-Path $env:TEMP "autoatualizacao_local_darkjutsu.log"
    Add-Content -Path $fallback -Encoding UTF8 -Value $line -ErrorAction SilentlyContinue
  } catch {}
}

function Append-LogLines {
  param([object[]]$Lines)
  foreach ($line in $Lines) {
    Write-Log ("  " + [string]$line)
  }
}

function Write-Event {
  param([string]$Level, [string]$Message)
  if (Test-Path $EventLogger) {
    & cmd.exe /c "`"$EventLogger`" `"$Level`" `"AUTOATUALIZACAO`" `"$Message`"" | Out-Null
  }
}

function Get-SharedSignature {
  $parts = New-Object System.Collections.Generic.List[string]
  foreach ($name in $TrackedFiles) {
    $path = Join-Path $ShareScripts $name
    if (-not (Test-Path $path)) {
      throw "Arquivo obrigatorio ausente no fileserver: $name"
    }
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
    $parts.Add("$name=$hash")
  }

  $text = ($parts | Sort-Object) -join "`n"
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text)
    return -join ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString("x2") })
  } finally {
    $sha.Dispose()
  }
}

New-Item -ItemType Directory -Force -Path $LocalDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

try {
  New-Item -ItemType Directory -Path $LockDir -ErrorAction Stop | Out-Null
} catch {
  exit 0
}

try {
  if (-not (Test-Path $Installer)) {
    throw "Instalador compartilhado nao encontrado: $Installer"
  }

  $remoteSignature = Get-SharedSignature
  $localSignature = ""
  if (Test-Path $StateFile) {
    $localSignature = (Get-Content -Path $StateFile -TotalCount 1 -ErrorAction SilentlyContinue).Trim()
  }

  if (Test-Path $ForceReinstallFlag) {
    $flagText = Get-Content -Path $ForceReinstallFlag -Raw -ErrorAction SilentlyContinue
    $lastFlagText = ""
    if (Test-Path $ForceReinstallState) {
      $lastFlagText = Get-Content -Path $ForceReinstallState -Raw -ErrorAction SilentlyContinue
    }

    if ($flagText -ne $lastFlagText) {
    Write-Log "Reinstalacao forcada solicitada pelo fileserver. Conteudo=$flagText"
    Write-Event "INFO" "Reinstalacao forcada do guardiao/monitor solicitada pelo fileserver."

    $cmd = "pushd `"$ShareScripts`" && call `"$Installer`" && popd"
    $output = & cmd.exe /c $cmd 2>&1
    $exitCode = $LASTEXITCODE
    Append-LogLines $output

    if ($exitCode -ne 0) {
      Write-Log "FALHOU: reinstalacao forcada retornou codigo $exitCode."
      Write-Event "ERRO" "Reinstalacao forcada local falhou. Codigo=$exitCode. Veja $LogFile."
      exit $exitCode
    }

    Set-Content -Path $StateFile -Encoding ASCII -Value $remoteSignature
    Set-Content -Path $ForceReinstallState -Encoding UTF8 -Value $flagText
    Write-Log "OK: reinstalacao forcada aplicada. Versao=$remoteSignature"
    Write-Event "OK" "Reinstalacao forcada local aplicada com sucesso. Versao=$remoteSignature."
    exit 0
    }
  }

  if ([string]::IsNullOrWhiteSpace($localSignature)) {
    Write-Log "Primeira verificacao nesta maquina. Aplicando instalador antes de registrar versao. Remota=$remoteSignature"
    Write-Event "INFO" "Primeira verificacao local; aplicando instalador automaticamente para alinhar guardiao/monitor."

    $cmd = "pushd `"$ShareScripts`" && call `"$Installer`" && popd"
    $output = & cmd.exe /c $cmd 2>&1
    $exitCode = $LASTEXITCODE
    Append-LogLines $output

    if ($exitCode -ne 0) {
      Write-Log "FALHOU: instalador de primeira verificacao retornou codigo $exitCode."
      Write-Event "ERRO" "Autoatualizacao inicial falhou. Instalador retornou codigo $exitCode. Veja $LogFile."
      exit $exitCode
    }

    Set-Content -Path $StateFile -Encoding ASCII -Value $remoteSignature
    Write-Log "OK: primeira instalacao/atualizacao local aplicada. Versao=$remoteSignature"
    Write-Event "OK" "Primeira instalacao/atualizacao local aplicada com sucesso. Versao=$remoteSignature."
    exit 0
  }

  if ($remoteSignature -eq $localSignature) {
    exit 0
  }

  Write-Log "Versao nova detectada no fileserver. Local=$localSignature Remota=$remoteSignature"
  Write-Event "INFO" "Versao nova do guardiao/monitor detectada no fileserver; atualizando esta maquina."

  $cmd = "pushd `"$ShareScripts`" && call `"$Installer`" && popd"
  $output = & cmd.exe /c $cmd 2>&1
  $exitCode = $LASTEXITCODE
  Append-LogLines $output

  if ($exitCode -ne 0) {
    Write-Log "FALHOU: instalador retornou codigo $exitCode."
    Write-Event "ERRO" "Autoatualizacao local falhou. Instalador retornou codigo $exitCode. Veja $LogFile."
    exit $exitCode
  }

  Set-Content -Path $StateFile -Encoding ASCII -Value $remoteSignature
  Write-Log "OK: autoatualizacao local aplicada. Versao=$remoteSignature"
  Write-Event "OK" "Autoatualizacao local aplicada com sucesso. Versao=$remoteSignature."
  exit 0
} catch {
  Write-Log "ERRO: $($_.Exception.Message)"
  Write-Event "ERRO" "Autoatualizacao local encontrou erro: $($_.Exception.Message)"
  exit 1
} finally {
  Remove-Item -LiteralPath $LockDir -Force -Recurse -ErrorAction SilentlyContinue
}
