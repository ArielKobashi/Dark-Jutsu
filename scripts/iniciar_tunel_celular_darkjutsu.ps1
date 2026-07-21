param(
  [Parameter(Mandatory = $true)]
  [string]$Cloudflared,
  [Parameter(Mandatory = $true)]
  [string]$Root,
  [string]$Url = "http://127.0.0.1:8765",
  [switch]$KeepAlive
)

$ErrorActionPreference = "Stop"
$Root = $Root.Trim().Trim('"')
if ($Root -match '^(.*)"\s+-KeepAlive$') {
  $Root = $Matches[1].Trim().Trim('"')
  $KeepAlive = $true
}
$stateDir = Join-Path $Root "data"
$stateFile = Join-Path $stateDir "mobile_tunnel_url.json"
$logFile = Join-Path $stateDir "mobile_tunnel_cloudflared.log"
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

function Write-MobileState([string]$status, [string]$publicUrl = "", [string]$message = "") {
  $payload = [ordered]@{
    ok = ($status -eq "online")
    status = $status
    url = $publicUrl
    message = $message
    updatedAt = (Get-Date).ToUniversalTime().ToString("o")
  }
  $payload | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $stateFile -Encoding UTF8
}

do {
  Write-MobileState "starting" "" "Iniciando tunnel para celular."

  Get-CimInstance Win32_Process -Filter "Name = 'cloudflared.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
      $_.CommandLine -and
      $_.CommandLine -match "--url" -and
      $_.CommandLine -match "127\.0\.0\.1:(8765|8766)"
    } |
    ForEach-Object {
      try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}
    }
  Set-Content -LiteralPath $logFile -Value "" -Encoding UTF8

  $process = Start-Process -FilePath $Cloudflared -ArgumentList @(
    "tunnel",
    "--no-autoupdate",
    "--logfile", $logFile,
    "--loglevel", "info",
    "--protocol", "http2",
    "--url", $Url
  ) -WorkingDirectory $Root -WindowStyle Hidden -PassThru
  $currentUrl = ""
  $deadline = (Get-Date).AddSeconds(45)
  while (-not $process.HasExited) {
    if (Test-Path -LiteralPath $logFile) {
      $text = Get-Content -LiteralPath $logFile -Raw -ErrorAction SilentlyContinue
      $matches = [regex]::Matches(
        $text,
        '"message":"\|\s+(https://[a-z0-9-]+\.trycloudflare\.com)\s+\|"'
      )
      if ($matches.Count -gt 0) {
        $currentUrl = $matches[$matches.Count - 1].Groups[1].Value
        Write-MobileState "online" $currentUrl "Tunnel ativo."
        Write-Host ""
        Write-Host "QR/Link atualizado no Dark-Jutsu: $currentUrl"
        Write-Host ""
        break
      }
    }
    if ((Get-Date) -gt $deadline) {
      Write-MobileState "starting" "" "Tunnel ainda iniciando; confira $logFile."
      $deadline = (Get-Date).AddSeconds(45)
    }
    Start-Sleep -Seconds 1
  }

  if ($process.HasExited -and -not $currentUrl) {
    $tail = ""
    if (Test-Path -LiteralPath $logFile) {
      $tail = ((Get-Content -LiteralPath $logFile -Tail 12 -ErrorAction SilentlyContinue) -join " ")
    }
    if (-not $tail) { $tail = "Cloudflared encerrou sem escrever detalhes no log." }
    Write-MobileState "offline" "" "Tunnel falhou antes de gerar link. $tail"
  } elseif ($currentUrl -and -not $KeepAlive) {
    return
  } elseif (-not $process.HasExited) {
    $process.WaitForExit()
  }

  if ($currentUrl) {
    Write-MobileState "offline" $currentUrl "Tunnel encerrado."
  } elseif (-not $process.HasExited) {
    Write-MobileState "offline" "" "Tunnel encerrado antes de gerar link. Confira data\mobile_tunnel_cloudflared.log."
  }

  if ($KeepAlive) {
    Write-Host "Tunnel caiu/fechou. Reiniciando em 5 segundos..."
    Start-Sleep -Seconds 5
  }
} while ($KeepAlive)
