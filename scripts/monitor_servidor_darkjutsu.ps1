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
$GuardScript = Join-Path $ShareRoot "scripts\iniciar_servidor_se_necessario_darkjutsu.bat"

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

$menu = New-Object System.Windows.Forms.ContextMenuStrip

$statusItem = New-Object System.Windows.Forms.ToolStripMenuItem
$statusItem.Text = "Status: verificando..."
$statusItem.Enabled = $false
[void]$menu.Items.Add($statusItem)

$openItem = New-Object System.Windows.Forms.ToolStripMenuItem
$openItem.Text = "Abrir sistema"
$openItem.Add_Click({
  if (Confirm-Password "Abrir sistema") {
    Start-Process $AppPath
  }
})
[void]$menu.Items.Add($openItem)

$testItem = New-Object System.Windows.Forms.ToolStripMenuItem
$testItem.Text = "Testar servidor"
$testItem.Add_Click({
  if (Confirm-Password "Testar servidor") {
    Start-Process "cmd.exe" -ArgumentList "/c call `"$TestScript`""
  }
})
[void]$menu.Items.Add($testItem)

$guardItem = New-Object System.Windows.Forms.ToolStripMenuItem
$guardItem.Text = "Verificar/iniciar agora"
$guardItem.Add_Click({
  if (Confirm-Password "Verificar/iniciar agora") {
    Start-Process "cmd.exe" -WindowStyle Hidden -ArgumentList "/c call `"$GuardScript`""
  }
})
[void]$menu.Items.Add($guardItem)

$assumeScript = Join-Path $ShareRoot "scripts\assumir_servidor_darkjutsu.bat"
$assumeItem = New-Object System.Windows.Forms.ToolStripMenuItem
$assumeItem.Text = "Tornar este PC o servidor"
$assumeItem.Add_Click({
  if (Confirm-Password "Tornar este PC o servidor") {
    Start-Process "cmd.exe" -WindowStyle Hidden -ArgumentList "/c call `"$assumeScript`""
  }
})
[void]$menu.Items.Add($assumeItem)

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$stopScript = Join-Path $ShareRoot "scripts\parar_api_darkjutsu.bat"
$closeItem = New-Object System.Windows.Forms.ToolStripMenuItem
$closeItem.Text = "Encerrar"
$closeItem.Add_Click({
  if (Confirm-Password "Encerrar servidor local") {
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

  if ($primaryOk -or $reserveOk) {
    $activeIp = if ($primaryOk) { $PrimaryIp } else { $ReserveIp }
    $activeName = if ($primaryOk) { "principal" } else { "reserva" }

    if ($localIp -eq $activeIp) {
      $notify.Icon = $iconGreen
      $text = "Dark-Jutsu: este PC esta rodando o servidor ($activeName - $activeIp)"
    } else {
      $notify.Icon = $iconRed
      $text = "Dark-Jutsu: servidor ativo em outro PC ($activeName - $activeIp)"
    }
  } else {
    $notify.Icon = $iconBlack
    $text = "Dark-Jutsu: nenhum servidor esta ligado"
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
