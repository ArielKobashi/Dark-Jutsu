$ErrorActionPreference = "Stop"

$ShareRoot = "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
$ShareScripts = Join-Path $ShareRoot "scripts"
$LocalDir = Join-Path $env:LOCALAPPDATA "DarkJutsu\monitor"
$LogDir = "C:\DarkJutsu\logs"
$LogFile = Join-Path $LogDir "autoatualizacao_local.log"
$StateFile = Join-Path $LocalDir "versao_instalada_guardiao_monitor.txt"
$LockDir = Join-Path $LogDir "autoatualizacao_local.lock"
$Installer = Join-Path $ShareScripts "instalar_atualizar_guardiao_monitor_darkjutsu.bat"
$EventLogger = Join-Path $ShareScripts "registrar_evento_servidor_darkjutsu.bat"

$TrackedFiles = @(
  "instalar_atualizar_guardiao_monitor_darkjutsu.bat",
  "guardiao_servidor_tick_darkjutsu.bat",
  "atualizar_darkjutsu_do_github.bat",
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
  New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path $LogFile -Encoding UTF8 -Value "$stamp | $Message"
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

  if ([string]::IsNullOrWhiteSpace($localSignature)) {
    Set-Content -Path $StateFile -Encoding ASCII -Value $remoteSignature
    Write-Log "Versao-base registrada nesta maquina: $remoteSignature"
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
  Add-Content -Path $LogFile -Encoding UTF8 -Value ($output | ForEach-Object { "  $_" })

  if ($exitCode -ne 0) {
    Write-Log "FALHOU: instalador retornou codigo $exitCode."
    Write-Event "ERRO" "Autoatualizacao local falhou. Instalador retornou codigo $exitCode. Veja C:\DarkJutsu\logs\autoatualizacao_local.log."
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
