$ErrorActionPreference = "Stop"

$releaseRoot = "\\fileserver\Almoxarifado\0800\automus"
$manifestPath = Join-Path $releaseRoot "latest.json"
$installRoot = Join-Path $env:LOCALAPPDATA "Automus\servidor"
$appDir = Join-Path $installRoot "app"
$versionPath = Join-Path $installRoot "installed-version.txt"
$systemLogDir = "C:\DarkJutsu\logs"
$userLogDir = Join-Path $env:LOCALAPPDATA "DarkJutsu\logs"
$logDir = if (Test-Path "C:\DarkJutsu\PostgreSQL\pgsql\bin\pg_ctl.exe") { $systemLogDir } else { $userLogDir }
$logPath = Join-Path $logDir "automus_guardiao.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path $installRoot | Out-Null

function Write-Log([string]$Message) {
    Add-Content -LiteralPath $logPath -Encoding UTF8 -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
}

try {
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        throw "Manifesto do Automus nao encontrado em $manifestPath"
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $version = [string]$manifest.version
    $packageName = [string]$manifest.package
    if ([string]::IsNullOrWhiteSpace($version) -or [string]::IsNullOrWhiteSpace($packageName)) {
        throw "Manifesto do Automus incompleto."
    }

    $exePath = Join-Path $appDir "Automus.exe"
    $installedVersion = if (Test-Path -LiteralPath $versionPath) {
        (Get-Content -LiteralPath $versionPath -Raw).Trim()
    } else { "" }

    if ($installedVersion -ne $version -or -not (Test-Path -LiteralPath $exePath)) {
        $packagePath = Join-Path $releaseRoot $packageName
        if (-not (Test-Path -LiteralPath $packagePath)) {
            throw "Pacote do Automus nao encontrado em $packagePath"
        }
        $stage = Join-Path $installRoot ("stage-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Force -Path $stage | Out-Null
        try {
            Expand-Archive -LiteralPath $packagePath -DestinationPath $stage -Force
            if (-not (Test-Path -LiteralPath (Join-Path $stage "Automus.exe"))) {
                throw "Pacote extraido sem Automus.exe."
            }
            if (Test-Path -LiteralPath $appDir) {
                Remove-Item -LiteralPath $appDir -Recurse -Force
            }
            Move-Item -LiteralPath $stage -Destination $appDir
            Set-Content -LiteralPath $versionPath -Encoding ASCII -NoNewline -Value $version
            Write-Log "Automus atualizado para $version."
        } finally {
            if (Test-Path -LiteralPath $stage) {
                Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }

    if (-not (Get-Process -Name "Automus" -ErrorAction SilentlyContinue)) {
        Start-Process -FilePath $exePath -ArgumentList "--background" -WorkingDirectory $appDir -WindowStyle Hidden
        Write-Log "Automus $version iniciado junto com o Guardiao."
    } else {
        Write-Log "Automus ja estava em execucao."
    }
    Start-Sleep -Seconds 4
    $startupDir = [Environment]::GetFolderPath("Startup")
    foreach ($legacyName in @(
        "Automus_Controlador_Atualizacoes.bat",
        "Automus_Atualizacoes.bat",
        "Automus.bat",
        "Dark-Jutsu Cluster Usuario.cmd"
    )) {
        $legacyPath = Join-Path $startupDir $legacyName
        if (Test-Path -LiteralPath $legacyPath) {
            Remove-Item -LiteralPath $legacyPath -Force -ErrorAction SilentlyContinue
            Write-Log "Inicializacao direta antiga removida: $legacyName"
        }
    }
} catch {
    Write-Log "ERRO: $($_.Exception.Message)"
    exit 1
}
