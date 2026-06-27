param(
    [string]$Url = "https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/index.html",
    [string]$OutputDir = "",
    [int]$Port = 9222,
    [int]$MaxWheelSteps = 6000,
    [int]$WheelDelta = 1800,
    [int]$WheelDelayMs = 5,
    [int]$StopAfterSameScreen = 500
)

$ErrorActionPreference = "Stop"

if (-not $OutputDir) {
    $OutputDir = $PSScriptRoot
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Get-ChromePath {
    $paths = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($path in $paths) {
        if ($path -and (Test-Path $path)) { return $path }
    }
    throw "Chrome nao encontrado. Ajuste o caminho do Chrome no script."
}

function Send-CdpCommand {
    param(
        [System.Net.WebSockets.ClientWebSocket]$Socket,
        [int]$Id,
        [string]$Method,
        [hashtable]$Params = @{}
    )

    $payload = @{ id = $Id; method = $Method; params = $Params } | ConvertTo-Json -Depth 20 -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
    $Socket.SendAsync([ArraySegment[byte]]::new($bytes), [System.Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).GetAwaiter().GetResult()

    $buffer = New-Object byte[] 1048576
    while ($true) {
        $output = New-Object System.Collections.Generic.List[byte]
        do {
            $result = $Socket.ReceiveAsync([ArraySegment[byte]]::new($buffer), [Threading.CancellationToken]::None).GetAwaiter().GetResult()
            if ($result.Count -gt 0) {
                $output.AddRange([byte[]]($buffer[0..($result.Count - 1)]))
            }
        } while (-not $result.EndOfMessage)

        $message = [System.Text.Encoding]::UTF8.GetString($output.ToArray()) | ConvertFrom-Json
        if ($message.id -eq $Id) { return $message }
    }
}

try {
    $targets = Invoke-RestMethod "http://127.0.0.1:$Port/json" -TimeoutSec 2
} catch {
    throw "Chrome controlado nao encontrado na porta $Port. O verificador nao abre janela nova; abra o Protheus pelo fluxo do Automus/Chrome controlado e tente novamente."
}

$target = $targets |
    Where-Object { $_.type -eq "page" -and $_.url -like "*webapp/index.html*" } |
    Select-Object -First 1
if (-not $target) {
    $target = $targets | Where-Object { $_.type -eq "page" } | Select-Object -First 1
}
if (-not $target) {
    throw "Nenhuma aba do Chrome encontrada na porta $Port."
}

$js = @'
(() => {
  const alvo = 'br_azul_mdi.png';
  const encontrados = new Map();

  function todosElementos(root = document) {
    const lista = [...root.querySelectorAll('*')];
    for (const el of [...lista]) {
      if (el.shadowRoot) lista.push(...todosElementos(el.shadowRoot));
    }
    return lista;
  }

  function textoVisivel(el) {
    return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function sobrepoeVerticalmente(a, b) {
    return a.top < b.bottom && a.bottom > b.top;
  }

  function extrairNumeros(texto) {
    return (texto.match(/\d+/g) || []).map(n => n.trim()).filter(Boolean);
  }

  function acharAzul() {
    return todosElementos().filter(el =>
      el.classList &&
      el.classList.contains('image-cell') &&
      (el.style.backgroundImage || '').includes(alvo)
    );
  }

  function pegarChaveAoLado(el) {
    const azulRect = el.getBoundingClientRect();
    const linha = el.closest('tr, [role="row"], .row, .tr') || el.parentElement;
    const base = linha || document;
    const candidatos = [...base.querySelectorAll('*')]
      .map(item => ({ item, rect: item.getBoundingClientRect(), texto: textoVisivel(item) }))
      .filter(({ item, rect, texto }) =>
        item !== el &&
        texto &&
        rect.width > 0 &&
        rect.height > 0 &&
        rect.left >= azulRect.right - 2 &&
        sobrepoeVerticalmente(azulRect, rect)
      )
      .sort((a, b) => a.rect.left - b.rect.left);

    const numeros = [];
    for (const candidato of candidatos) {
      for (const numero of extrairNumeros(candidato.texto)) {
        if (numeros[numeros.length - 1] !== numero) numeros.push(numero);
      }
    }
    if (numeros.length < 2 && linha) {
      for (const numero of extrairNumeros(textoVisivel(linha))) {
        if (numeros[numeros.length - 1] !== numero) numeros.push(numero);
      }
    }
    return {
      sa: numeros[0] ? numeros[0].padStart(6, '0') : '',
      item: numeros[1] ? numeros[1].padStart(2, '0') : '',
    };
  }

  function registrarAzuis() {
    for (const azul of acharAzul()) {
      const chaveAoLado = pegarChaveAoLado(azul);
      const linha = azul.closest('tr, [role="row"], .row, .tr') || azul.parentElement;
      const textoLinha = textoVisivel(linha);
      const chave = `${chaveAoLado.sa};${chaveAoLado.item}`;
      const chaveFinal = chave !== ';' ? chave : `${textoLinha}-${encontrados.size}`;
      if (!encontrados.has(chaveFinal)) {
        encontrados.set(chaveFinal, { sa: chaveAoLado.sa, item: chaveAoLado.item, chave, textoLinha });
      }
      azul.style.outline = '4px solid #00aaff';
      azul.style.boxShadow = '0 0 16px #00aaff';
      if (linha) linha.style.outline = '2px solid #00aaff';
    }
  }

  function fingerprintTela() {
    return todosElementos()
      .filter(el => {
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && rect.top >= 250 && rect.top <= innerHeight - 20;
      })
      .map(textoVisivel)
      .filter(Boolean)
      .slice(0, 80)
      .join('|');
  }

  function resultado() {
    const lista = [...encontrados.values()];
    return {
      ok: lista.length > 0,
      mensagem: lista.length > 0 ? `${lista.length} elemento(s) azul(is) encontrado(s).` : 'Nenhum elemento azul encontrado ate o final da rolagem.',
      lista,
      fingerprint: fingerprintTela(),
      viewport: { width: innerWidth, height: innerHeight }
    };
  }

  window.__procurarAzul = { registrar: () => { registrarAzuis(); return resultado(); }, resultado };
})();
'@

$socket = [System.Net.WebSockets.ClientWebSocket]::new()
$socket.ConnectAsync([Uri]$target.webSocketDebuggerUrl, [Threading.CancellationToken]::None).GetAwaiter().GetResult()

try {
    Send-CdpCommand -Socket $socket -Id 1 -Method "Runtime.enable" | Out-Null
    Send-CdpCommand -Socket $socket -Id 2 -Method "Page.bringToFront" | Out-Null
    Send-CdpCommand -Socket $socket -Id 3 -Method "Runtime.evaluate" -Params @{ expression = $js; returnByValue = $true } | Out-Null

    $viewportResponse = Send-CdpCommand -Socket $socket -Id 4 -Method "Runtime.evaluate" -Params @{
        expression = "({ width: window.innerWidth, height: window.innerHeight })"
        returnByValue = $true
    }
    $viewport = $viewportResponse.result.result.value
    $mouseX = [Math]::Floor([double]$viewport.width / 2)
    $mouseY = [Math]::Floor([double]$viewport.height * 0.55)

    for ($i = 0; $i -lt 120; $i++) {
        Send-CdpCommand -Socket $socket -Id (100000 + $i) -Method "Input.dispatchMouseEvent" -Params @{
            type = "mouseWheel"; x = $mouseX; y = $mouseY; deltaX = 0; deltaY = -$WheelDelta
        } | Out-Null
        Start-Sleep -Milliseconds 5
    }

    $ultimoFingerprint = ""
    $parado = 0
    $resultado = $null
    for ($i = 0; $i -lt $MaxWheelSteps; $i++) {
        $scan = Send-CdpCommand -Socket $socket -Id (200000 + $i) -Method "Runtime.evaluate" -Params @{
            expression = "window.__procurarAzul.registrar()"
            returnByValue = $true
        }
        $resultado = $scan.result.result.value
        if ($resultado.fingerprint -eq $ultimoFingerprint) {
            $parado++
        } else {
            $parado = 0
            $ultimoFingerprint = $resultado.fingerprint
        }
        if ($parado -ge $StopAfterSameScreen -and $i -gt 1000) { break }
        Send-CdpCommand -Socket $socket -Id (300000 + $i) -Method "Input.dispatchMouseEvent" -Params @{
            type = "mouseWheel"; x = $mouseX; y = $mouseY; deltaX = 0; deltaY = $WheelDelta
        } | Out-Null
        Start-Sleep -Milliseconds $WheelDelayMs
    }

    $finalResponse = Send-CdpCommand -Socket $socket -Id 900000 -Method "Runtime.evaluate" -Params @{
        expression = "window.__procurarAzul.registrar()"
        returnByValue = $true
    }
    $resultado = $finalResponse.result.result.value
    $linhas = @()
    if ($resultado.lista) {
        foreach ($item in $resultado.lista) {
            if ($item.sa -and $item.item) {
                $linhas += "$($item.sa);$($item.item)"
            }
        }
    }

    $saida = Join-Path $OutputDir "lista-azuis.txt"
    $saidaCsv = Join-Path $OutputDir "lista-azuis-com-itens.csv"
    $linhas | Set-Content -Path $saida -Encoding UTF8
    @("Nr.S.A.;Item S.A.") + $linhas | Set-Content -Path $saidaCsv -Encoding UTF8
    Write-Host ("AZUL_RESULTADO encontrados={0} arquivo={1}" -f $linhas.Count, $saida)
} finally {
    $socket.Dispose()
}
