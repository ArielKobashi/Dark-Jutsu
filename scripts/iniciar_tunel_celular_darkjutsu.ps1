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

  $psi = [System.Diagnostics.ProcessStartInfo]::new()
  $psi.FileName = $Cloudflared
  $psi.Arguments = "tunnel --url `"$Url`""
  $psi.WorkingDirectory = $Root
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.CreateNoWindow = $true

  $process = [System.Diagnostics.Process]::new()
  $process.StartInfo = $psi
  $script:currentUrl = ""

  $handler = {
    param($sender, $eventArgs)
    if (-not $eventArgs.Data) { return }
    Write-Host $eventArgs.Data
    $match = [regex]::Match($eventArgs.Data, "https://[a-z0-9-]+\.trycloudflare\.com")
    if ($match.Success) {
      $script:currentUrl = $match.Value
      Write-MobileState "online" $script:currentUrl "Tunnel ativo."
      Write-Host ""
      Write-Host "QR/Link atualizado no Dark-Jutsu: $script:currentUrl"
      Write-Host ""
    }
  }

  Register-ObjectEvent -InputObject $process -EventName OutputDataReceived -Action $handler | Out-Null
  Register-ObjectEvent -InputObject $process -EventName ErrorDataReceived -Action $handler | Out-Null

  [void]$process.Start()
  $process.BeginOutputReadLine()
  $process.BeginErrorReadLine()
  $process.WaitForExit()

  if ($script:currentUrl) {
    Write-MobileState "offline" $script:currentUrl "Tunnel encerrado."
  } else {
    Write-MobileState "offline" "" "Tunnel encerrado antes de gerar link."
  }

  if ($KeepAlive) {
    Write-Host "Tunnel caiu/fechou. Reiniciando em 5 segundos..."
    Start-Sleep -Seconds 5
  }
} while ($KeepAlive)
