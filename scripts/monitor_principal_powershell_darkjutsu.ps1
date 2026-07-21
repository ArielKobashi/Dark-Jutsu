$ErrorActionPreference = "SilentlyContinue"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName Microsoft.VisualBasic
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class InfinityMouseInput {
  [DllImport("user32.dll")]
  public static extern void mouse_event(uint dwFlags, int dx, int dy, uint dwData, UIntPtr dwExtraInfo);
}
"@

$createdNew = $false
$mutex = New-Object System.Threading.Mutex($true, "Global\DarkJutsuServerTrayMonitor", [ref]$createdNew)
if (-not $createdNew) {
  exit 0
}

$PrimaryIp = "192.168.5.44"
$ReserveIp = "192.168.5.38"
$Port = 8765
$ShareRoot = "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
$TestScript = Join-Path $ShareRoot "scripts\testar_servidor_darkjutsu.bat"
$PanelScript = Join-Path $ShareRoot "scripts\abrir_painel_servidor_darkjutsu.bat"
$GuardScript = Join-Path $ShareRoot "scripts\guardiao_servidor_tick_darkjutsu.bat"
$MakePrincipalScript = Join-Path $ShareRoot "scripts\tornar_principal_operacional_darkjutsu.bat"
$MakeReserveScript = Join-Path $ShareRoot "scripts\tornar_reserva_operacional_darkjutsu.bat"
$LogDir = "C:\DarkJutsu\logs"
$LogFile = Join-Path $LogDir "monitor_servidor.log"
$script:thisPcIsActiveServer = $false
$script:InfinityEnabled = $true
$script:ServerOfflineSince = $null
$InfinityPassword = "123456789"
$OfflineGraceSeconds = 45

function Write-MonitorLog([string]$message) {
  try {
    if (-not (Test-Path -LiteralPath $LogDir)) {
      New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }
    $line = "{0:yyyy-MM-dd HH:mm:ss} | {1} | {2} | {3}" -f (Get-Date), $env:COMPUTERNAME, $env:USERNAME, $message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
  } catch {}
}

function Get-LocalServerIp {
  $ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -in @($PrimaryIp, $ReserveIp) } |
    Select-Object -ExpandProperty IPAddress -First 1
  return $ips
}

function Test-Health($ip) {
  try {
    $result = Invoke-RestMethod -Uri "http://${ip}:${Port}/health" -TimeoutSec 3
    return ($result.ok -eq $true)
  } catch {
    return $false
  }
}

function Get-DarkJutsuAppUrl {
  foreach ($ip in @($PrimaryIp, $ReserveIp, "127.0.0.1")) {
    if (Test-Health $ip) {
      return "http://${ip}:${Port}/app/index.html"
    }
  }
  return "http://${PrimaryIp}:${Port}/app/index.html"
}

function New-StatusIcon([System.Drawing.Color]$color, [string]$letter) {
  $bitmap = New-Object System.Drawing.Bitmap 64, 64
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
  $graphics.Clear([System.Drawing.Color]::Transparent)

  $brush = New-Object System.Drawing.SolidBrush $color
  $border = New-Object System.Drawing.Pen ([System.Drawing.Color]::White), 5
  $graphics.FillEllipse($brush, 6, 6, 52, 52)
  $graphics.DrawEllipse($border, 6, 6, 52, 52)

  $font = New-Object System.Drawing.Font "Segoe UI", 26, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Pixel)
  $textBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
  $format = New-Object System.Drawing.StringFormat
  $format.Alignment = [System.Drawing.StringAlignment]::Center
  $format.LineAlignment = [System.Drawing.StringAlignment]::Center
  $rect = New-Object System.Drawing.RectangleF 0, 0, 64, 60
  $graphics.DrawString($letter, $font, $textBrush, $rect, $format)

  $iconHandle = $bitmap.GetHicon()
  $icon = [System.Drawing.Icon]::FromHandle($iconHandle)
  $graphics.Dispose()
  $brush.Dispose()
  $border.Dispose()
  $font.Dispose()
  $textBrush.Dispose()
  $format.Dispose()
  return $icon
}

$iconGreen = New-StatusIcon ([System.Drawing.Color]::FromArgb(28, 161, 86)) "D"
$iconRed = New-StatusIcon ([System.Drawing.Color]::FromArgb(205, 45, 45)) "D"
$iconBlack = New-StatusIcon ([System.Drawing.Color]::FromArgb(20, 20, 20)) "D"

$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Text = "Dark-Jutsu: verificando servidor..."
$notify.Icon = $iconBlack
$notify.Visible = $true

function Confirm-Password([string]$actionName) {
  $password = [Microsoft.VisualBasic.Interaction]::InputBox(
    "Digite a senha para executar: $actionName",
    "Dark-Jutsu",
    ""
  )
  if ($password -eq "654321") {
    return $true
  }
  if ($password -ne "") {
    [System.Windows.Forms.MessageBox]::Show(
      "Senha incorreta.",
      "Dark-Jutsu",
      [System.Windows.Forms.MessageBoxButtons]::OK,
      [System.Windows.Forms.MessageBoxIcon]::Warning
    ) | Out-Null
  }
  return $false
}

function Confirm-InfinityPassword([string]$actionName) {
  $password = [Microsoft.VisualBasic.Interaction]::InputBox(
    "Digite a senha do Infinity para executar: $actionName",
    "Infinity",
    ""
  )
  if ($password -eq $InfinityPassword) {
    return $true
  }
  if ($password -ne "") {
    [System.Windows.Forms.MessageBox]::Show(
      "Senha incorreta.",
      "Infinity",
      [System.Windows.Forms.MessageBoxButtons]::OK,
      [System.Windows.Forms.MessageBoxIcon]::Warning
    ) | Out-Null
  }
  return $false
}

function Invoke-InfinityNudge {
  if (-not $script:InfinityEnabled) {
    return
  }
  try {
    [InfinityMouseInput]::mouse_event(0x0001, 1, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [InfinityMouseInput]::mouse_event(0x0001, -1, 0, 0, [UIntPtr]::Zero)
    Write-MonitorLog "Infinity: mouse movido 1px e retornado"
  } catch {
    Write-MonitorLog "Infinity: falha ao mover mouse: $($_.Exception.Message)"
  }
}

function Show-Info([string]$message) {
  [System.Windows.Forms.MessageBox]::Show(
    $message,
    "Dark-Jutsu",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Information
  ) | Out-Null
}

$menu = New-Object System.Windows.Forms.ContextMenuStrip

$statusItem = New-Object System.Windows.Forms.ToolStripMenuItem
$statusItem.Text = "Status: verificando..."
$statusItem.Enabled = $false
[void]$menu.Items.Add($statusItem)

$openItem = New-Object System.Windows.Forms.ToolStripMenuItem
$openItem.Text = "Abrir Dark-Jutsu"
$openItem.Add_Click({
  $url = Get-DarkJutsuAppUrl
  Write-MonitorLog "Abrir Dark-Jutsu em $url"
  Start-Process $url
})
[void]$menu.Items.Add($openItem)

$testItem = New-Object System.Windows.Forms.ToolStripMenuItem
$testItem.Text = "Testar servidor"
$testItem.Add_Click({
  if (Confirm-Password "Testar servidor") {
    Write-MonitorLog "Teste manual solicitado"
    Start-Process "cmd.exe" -WindowStyle Hidden -ArgumentList "/c call `"$PanelScript`""
  }
})
[void]$menu.Items.Add($testItem)

$guardItem = New-Object System.Windows.Forms.ToolStripMenuItem
$guardItem.Text = "Verificar/iniciar agora"
$guardItem.Add_Click({
  if (Confirm-Password "Verificar/iniciar agora") {
    Write-MonitorLog "Verificar/iniciar agora solicitado"
    Start-Process "cmd.exe" -WindowStyle Hidden -ArgumentList "/c call `"$GuardScript`""
  }
})
[void]$menu.Items.Add($guardItem)

$assumeScript = Join-Path $ShareRoot "scripts\assumir_servidor_darkjutsu.bat"
$assumeItem = New-Object System.Windows.Forms.ToolStripMenuItem
$assumeItem.Text = "Tornar este PC o Principal"
$assumeItem.Add_Click({
  $localIp = Get-LocalServerIp
  if (-not $localIp) {
    [System.Windows.Forms.MessageBox]::Show(
      "Este computador nao esta configurado como principal nem reserva.",
      "Dark-Jutsu",
      [System.Windows.Forms.MessageBoxButtons]::OK,
      [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
    return
  }

  if ($script:thisPcIsActiveServer) {
    if (Confirm-Password "Tornar este PC o reserva") {
      Write-MonitorLog "Tornar este PC o reserva solicitado"
      Start-Process "cmd.exe" -WindowStyle Hidden -Wait -ArgumentList "/c call `"$MakeReserveScript`""
      Start-Sleep -Seconds 3
      Update-Status
      Show-Info "Este PC parou a API local e ficou pausado por ate 10 minutos. Se a reserva estiver ligada, ela deve assumir automaticamente em ate 1 minuto."
    }
  } else {
    if (Confirm-Password "Tornar este PC o Principal") {
      Write-MonitorLog "Tornar este PC o Principal solicitado"
      if ($localIp -eq $PrimaryIp) {
        Start-Process "cmd.exe" -WindowStyle Hidden -Wait -ArgumentList "/c call `"$assumeScript`""
      } else {
        Start-Process "cmd.exe" -WindowStyle Hidden -Wait -ArgumentList "/c call `"$MakePrincipalScript`""
      }
      Start-Sleep -Seconds 8
      Update-Status
      if (Test-Health $localIp) {
        Show-Info "Este PC assumiu como servidor ativo. A principal fixa foi pausada temporariamente para nao religar por cima."
      } else {
        Show-Info "O comando foi executado, mas a API deste PC ainda nao respondeu. Abra 'Testar servidor' para ver o motivo."
      }
    }
  }
})
[void]$menu.Items.Add($assumeItem)

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$infinityStatusItem = New-Object System.Windows.Forms.ToolStripMenuItem
$infinityStatusItem.Text = "Infinity: ativo (2m30s)"
$infinityStatusItem.Enabled = $false
[void]$menu.Items.Add($infinityStatusItem)

$infinityToggleItem = New-Object System.Windows.Forms.ToolStripMenuItem
$infinityToggleItem.Text = "Parar Infinity"
$infinityToggleItem.Add_Click({
  if ($script:InfinityEnabled) {
    if (Confirm-InfinityPassword "Parar Infinity") {
      $script:InfinityEnabled = $false
      $infinityStatusItem.Text = "Infinity: parado"
      $infinityToggleItem.Text = "Iniciar Infinity"
      Write-MonitorLog "Infinity parado pelo menu"
    }
  } else {
    $script:InfinityEnabled = $true
    $infinityStatusItem.Text = "Infinity: ativo (2m30s)"
    $infinityToggleItem.Text = "Parar Infinity"
    Write-MonitorLog "Infinity iniciado pelo menu"
  }
})
[void]$menu.Items.Add($infinityToggleItem)

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$stopScript = Join-Path $ShareRoot "scripts\parar_api_darkjutsu.bat"
$closeItem = New-Object System.Windows.Forms.ToolStripMenuItem
$closeItem.Text = "Encerrar"
$closeItem.Add_Click({
  if (Confirm-Password "Encerrar servidor local") {
    Write-MonitorLog "Encerrar servidor local solicitado"
    Start-Process "cmd.exe" -WindowStyle Hidden -ArgumentList "/c call `"$stopScript`" monitor_encerrar_menu"
  }
})
[void]$menu.Items.Add($closeItem)

$notify.ContextMenuStrip = $menu
$notify.Add_DoubleClick({
  $url = Get-DarkJutsuAppUrl
  Write-MonitorLog "Abrir Dark-Jutsu por duplo clique em $url"
  Start-Process $url
})

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 15000
$guardTimer = New-Object System.Windows.Forms.Timer
$guardTimer.Interval = 60000
$infinityTimer = New-Object System.Windows.Forms.Timer
$infinityTimer.Interval = 150000

function Update-Status {
  $localIp = Get-LocalServerIp
  $primaryOk = Test-Health $PrimaryIp
  $reserveOk = Test-Health $ReserveIp

  if (-not $localIp) {
    $assumeItem.Text = "Este PC nao e servidor"
    $assumeItem.Enabled = $false
  } else {
    $assumeItem.Enabled = $true
  }

  if ($primaryOk -or $reserveOk) {
    $script:ServerOfflineSince = $null
    $activeIp = if ($primaryOk) { $PrimaryIp } else { $ReserveIp }
    $activeName = if ($primaryOk) { "principal" } else { "reserva" }
    $script:thisPcIsActiveServer = ($localIp -eq $activeIp)

    if ($script:thisPcIsActiveServer) {
      $notify.Icon = $iconGreen
      $text = "Dark-Jutsu: este PC esta rodando o servidor ($activeName - $activeIp)"
      $assumeItem.Text = "Tornar este PC o reserva"
    } else {
      $notify.Icon = $iconRed
      $text = "Dark-Jutsu: servidor ativo em outro PC ($activeName - $activeIp)"
      $assumeItem.Text = "Tornar este PC o Principal"
    }
  } else {
    $script:thisPcIsActiveServer = $false
    if ($null -eq $script:ServerOfflineSince) {
      $script:ServerOfflineSince = Get-Date
    }
    $offlineSeconds = [int]((Get-Date) - $script:ServerOfflineSince).TotalSeconds
    if ($offlineSeconds -lt $OfflineGraceSeconds) {
      $notify.Icon = $iconBlack
      $text = "Dark-Jutsu: reconfirmando servidor (${offlineSeconds}s sem resposta)"
    } else {
      $notify.Icon = $iconRed
      $text = "Dark-Jutsu: nenhum servidor esta ligado"
    }
    if ($localIp) {
      $assumeItem.Text = "Tornar este PC o Principal"
    }
  }

  $notify.Text = $text.Substring(0, [Math]::Min(63, $text.Length))
  $statusItem.Text = "Status: $text"
}

$timer.Add_Tick({ Update-Status })
$timer.Start()
$guardTimer.Add_Tick({
  Write-MonitorLog "Tick automatico do monitor principal chamando guardiao"
  Start-Process "cmd.exe" -WindowStyle Hidden -ArgumentList "/c call `"$GuardScript`""
})
$guardTimer.Start()
$infinityTimer.Add_Tick({ Invoke-InfinityNudge })
$infinityTimer.Start()
Invoke-InfinityNudge
Update-Status

[System.Windows.Forms.Application]::Run()

$notify.Visible = $false
$mutex.ReleaseMutex()
$mutex.Dispose()
