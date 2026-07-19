param(
    [switch]$ForceStart
)

$ErrorActionPreference = "Stop"

$releaseRoot = "\\fileserver\Almoxarifado\0800\automus"
$pointerPath = Join-Path $releaseRoot "versao_atual.txt"
$serverLauncher = Join-Path $releaseRoot "Iniciar_Automus_Servidor.vbs"
$logDir = Join-Path $env:LOCALAPPDATA "DarkJutsu\logs"
$logPath = Join-Path $logDir "automus_guardiao.log"
$serverStatusDir = Join-Path $releaseRoot "status"
$serverStatusPath = Join-Path $serverStatusDir ("guardiao_automus_{0}_{1}.json" -f $env:COMPUTERNAME, $env:USERNAME)
$stateDir = Join-Path $env:LOCALAPPDATA "Automus"
$versionState = Join-Path $stateDir "guardiao-versao-ativa.txt"

New-Item -ItemType Directory -Force -Path $logDir,$stateDir,$serverStatusDir | Out-Null

function Write-Log([string]$Message) {
    Add-Content -LiteralPath $logPath -Encoding UTF8 -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
}

function Write-ServerStatus([string]$Status, [string]$Message, [string]$Version = "", [string]$ExePath = "") {
    try {
        $payload = [ordered]@{
            updatedAt = (Get-Date -Format s)
            computer = $env:COMPUTERNAME
            user = $env:USERNAME
            status = $Status
            message = $Message
            version = $Version
            exePath = $ExePath
        }
        $payload | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $serverStatusPath -Encoding UTF8
    } catch {}
}

function Normalize-Path([string]$PathValue) {
    if ([string]::IsNullOrWhiteSpace($PathValue)) { return "" }
    try { return [IO.Path]::GetFullPath($PathValue).TrimEnd('\').ToLowerInvariant() }
    catch { return $PathValue.TrimEnd('\').ToLowerInvariant() }
}

try {
    Write-ServerStatus "checking" "Verificando Automus central."
    if (-not (Test-Path -LiteralPath $pointerPath)) {
        throw "Ponteiro central nao encontrado: $pointerPath"
    }
    $version = (Get-Content -LiteralPath $pointerPath -Raw).Trim()
    if ([string]::IsNullOrWhiteSpace($version)) {
        throw "Ponteiro central sem versao."
    }

    $appDir = Join-Path (Join-Path $releaseRoot "Aplicacao") $version
    $exePath = Join-Path $appDir "Automus.exe"
    if (-not (Test-Path -LiteralPath $exePath)) {
        throw "Versao $version ainda nao esta completa no servidor: $exePath"
    }

    $expectedExe = Normalize-Path $exePath
    $automusProcesses = @(Get-CimInstance Win32_Process -Filter "Name='Automus.exe'" -ErrorAction SilentlyContinue)
    $currentProcesses = @($automusProcesses | Where-Object {
        (Normalize-Path ([string]$_.ExecutablePath)) -eq $expectedExe
    })

    if ($currentProcesses.Count -gt 0 -and -not $ForceStart) {
        Set-Content -LiteralPath $versionState -Encoding ASCII -NoNewline -Value $version
        Write-ServerStatus "ok" "Automus ja estava na versao central." $version $exePath
        exit 0
    }

    if ($automusProcesses.Count -gt 0) {
        foreach ($proc in $automusProcesses) {
            try {
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
                Write-Log "Automus anterior encerrado para atualizar. PID=$($proc.ProcessId) Path=$($proc.ExecutablePath)"
            } catch {
                Write-Log "AVISO: falha ao encerrar PID=$($proc.ProcessId): $($_.Exception.Message)"
            }
        }
        Start-Sleep -Seconds 2
    }

    # A variavel faz o Automus manter a inicializacao apontando para o launcher
    # estavel do servidor, nunca para uma pasta de versao especifica.
    $env:AUTOMUS_SERVER_LAUNCHER = $serverLauncher
    Start-Process -FilePath $exePath -WorkingDirectory $appDir -ArgumentList "--background" -WindowStyle Hidden
    Set-Content -LiteralPath $versionState -Encoding ASCII -NoNewline -Value $version
    Write-Log "Automus central $version iniciado oculto. Origem=$exePath"
    Write-ServerStatus "started" "Automus central iniciado oculto." $version $exePath
} catch {
    Write-Log "ERRO ao verificar/atualizar Automus central: $($_.Exception.Message)"
    Write-ServerStatus "error" $_.Exception.Message
    exit 1
}
