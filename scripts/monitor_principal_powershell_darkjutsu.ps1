$ErrorActionPreference = "SilentlyContinue"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName Microsoft.VisualBasic

$createdNew = $false
$mutex = New-Object System.Threading.Mutex($true, "Global\DarkJutsuServerTrayMonitor", [ref]$createdNew)
if (-not $createdNew) {
  exit 0
}

$PrimaryIp = "192.168.5.44"
$ReserveIp = "192.168.5.38"
$Port = 8765
$ShareRoot = "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
$AppPath = Join-Path $ShareRoot "app\index.html"
$TestScript = Join-Path $ShareRoot "scripts\testar_servidor_darkjutsu.bat"
$GuardScript = Join-Path $ShareRoot "scripts\guardiao_servidor_tick_darkjutsu.bat"
$MakePrincipalScript = Join-Path $ShareRoot "scripts\tornar_principal_operacional_darkjutsu.bat"
$MakeReserveScript = Join-Path $ShareRoot "scripts\tornar_reserva_operacional_darkjutsu.bat"
$LogDir = "C:\DarkJutsu\logs"
$LogFile = Join-Path $LogDir "monitor_servidor.log"
$script:thisPcIsActiveServer = $false

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
    $result = Invoke-RestMethod -Uri "http://${ip}:${Port}/health" -TimeoutSec 2
    return ($result.ok -eq $true)
  } catch {
    return $false
  }
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
  Write-MonitorLog "Abrir Dark-Jutsu"
  Start-Process $AppPath
})
[void]$menu.Items.Add($openItem)

$testItem = New-Object System.Windows.Forms.ToolStripMenuItem
$testItem.Text = "Testar servidor"
$testItem.Add_Click({
  if (Confirm-Password "Testar servidor") {
    Write-MonitorLog "Teste manual solicitado"
    Start-Process "cmd.exe" -ArgumentList "/k title Dark-Jutsu - Teste do servidor & call `"$TestScript`""
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

$stopScript = Join-Path $ShareRoot "scripts\parar_api_darkjutsu.bat"
$closeItem = New-Object System.Windows.Forms.ToolStripMenuItem
$closeItem.Text = "Encerrar"
$closeItem.Add_Click({
  if (Confirm-Password "Encerrar servidor local") {
    Write-MonitorLog "Encerrar servidor local solicitado"
    Start-Process "cmd.exe" -WindowStyle Hidden -ArgumentList "/c call `"$stopScript`""
  }
})
[void]$menu.Items.Add($closeItem)

$notify.ContextMenuStrip = $menu
$notify.Add_DoubleClick({ Start-Process $AppPath })

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 15000

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
    $notify.Icon = $iconBlack
    $text = "Dark-Jutsu: nenhum servidor esta ligado"
    if ($localIp) {
      $assumeItem.Text = "Tornar este PC o Principal"
    }
  }

  $notify.Text = $text.Substring(0, [Math]::Min(63, $text.Length))
  $statusItem.Text = "Status: $text"
}

$timer.Add_Tick({ Update-Status })
$timer.Start()
Update-Status

[System.Windows.Forms.Application]::Run()

$notify.Visible = $false
$mutex.ReleaseMutex()
$mutex.Dispose()
