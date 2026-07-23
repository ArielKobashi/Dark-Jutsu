param(
    [string]$Url = "https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/index.html",
    [int]$Port = 9222
)

$ErrorActionPreference = "Stop"

function Get-ChromePath {
    $paths = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($path in $paths) {
        if ($path -and (Test-Path -LiteralPath $path)) { return $path }
    }
    throw "Chrome nao encontrado."
}

try {
    Invoke-RestMethod "http://127.0.0.1:$Port/json" -TimeoutSec 2 | Out-Null
    Write-Host "Chrome controlado ja esta ativo na porta $Port."
    exit 0
} catch {
    $chrome = Get-ChromePath
    $profileDir = Join-Path $env:LOCALAPPDATA "Automus\ChromeProtheusDebug"
    $windowWidth = if ($env:AUTOMUS_WINDOW_WIDTH) { [int]$env:AUTOMUS_WINDOW_WIDTH } else { 1366 }
    $windowHeight = if ($env:AUTOMUS_WINDOW_HEIGHT) { [int]$env:AUTOMUS_WINDOW_HEIGHT } else { 728 }
    New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
    Start-Process -FilePath $chrome -ArgumentList @(
        "--remote-debugging-port=$Port",
        "--user-data-dir=$profileDir",
        "--window-size=$windowWidth,$windowHeight",
        "--window-position=0,0",
        "--force-device-scale-factor=1",
        "--disable-session-crashed-bubble",
        "--no-first-run",
        "--new-window",
        $Url
    )
    Write-Host "Chrome controlado aberto na porta $Port. Faca login no Protheus nessa janela antes de iniciar a automacao."
}
