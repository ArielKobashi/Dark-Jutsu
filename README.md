# Dark-Jutsu

Sistema web local para consulta de estoque, chat interno, administracao de usuarios, automacao de atualizacao e geracao de etiquetas Fiasul.

## Estrutura

- `index.html` - aplicacao principal SQL-first, tabela de estoque, chat, painel admin, relatorios, contagem, editor de limites e gerador de etiquetas.
- `dashboard.html` - dashboard de estoque com filtros por parametros de URL.
- `label-editor.html` - mini editor visual para simular e ajustar a formatacao das etiquetas.
- `dashboard-nav.js` - atalhos e comandos para abrir o dashboard, por padrao no armazem 04.
- `style.css` - estilos desktop da aplicacao.
- `mobile.css` - ajustes responsivos/mobile.
- `data/` - planilhas auxiliares usadas pela aplicacao e pelo dashboard:
  - `mata110.xlsx`
  - `mata111.xlsx`
  - `mata112.xlsx`
  - `levantamento0706 antigo.xlsx`
- `downloads/` - planilhas e assets usados pelo sistema:
  - `incluir.xlsx` - base mata105 nativa usada no estoque e nas etiquetas.
  - `Saldo Atual.xlsx`
  - `Saldo por Endereco.xlsx`
  - `estoque_minimo.xlsx`
  - `etiquetas_logo.png`
  - `Oswald-Regular.ttf`
  - `Oswald-Bold.ttf`
- `assets/screenshots/` - capturas de tela de apoio e diagnostico.
- `scripts/` - automacao Python, macros e atualizador Automus.
- `tools/planilhas/` - motores e utilitarios antigos de tratamento de planilhas, mantidos fora da raiz.

## Funcionalidades principais

- Consulta e filtro de itens de estoque.
- Filtro de saldo fora da faixa minima/maxima.
- Captura de itens pelo modo magnet.
- Relatorio imprimivel dos itens selecionados.
- Tela de contagem de estoque por maquina/endereco, limitada aos armazens 04 e 05, com rascunho local, botoes rapidos, divergencias e exportacao XLSX.
- Indicador flutuante de progresso da contagem na tela principal: fica recolhido como um ponto pulsante e abre ao passar o mouse.
- Historico de contagens com download individual da planilha XLSX de cada sessao.
- Dashboard abre inicialmente filtrado no armazem 04 e mostra o progresso geral da contagem.
- Avaliador de pedidos no dashboard (`ambiente=avaliador`) para revisar itens abaixo do minimo do armazem 04, registrar a decisao uma unica vez e acompanhar os itens passíveis em kanban ate entrega.
- Historico de pedidos por item com quantidade pedida, quantidade recebida e dias entre pedido e recebimento usando MATA111/MATA112.
- Modal de perfil do item com saldo, endereco, minimo, maximo e reposicao.
- Edicao item a item de minimo e maximo dentro do modal.
- Reposicao calculada como quantidade para voltar do minimo ao maximo; sugestoes automaticas usam consumo, pedido medio e saldo das planilhas.
- Ajustes manuais persistidos no PostgreSQL via API, preservados apos atualizacoes.
- Chat por salas com:
  - sala publica com blur ate abrir;
  - salas privadas com blur e senha dentro do proprio chat;
  - mensagens de entrada/saida de sala;
  - contador de nao lidas ignorando mensagens de sistema;
  - estado de leitura por usuario;
  - indicador de digitacao.
- Painel administrativo para solicitacoes, usuarios, niveis e banidos.
- Gerador de etiquetas Fiasul integrado:
  - usa a mata105 nativa (`downloads/incluir.xlsx`);
  - tamanhos `5cm`, `7cm`, `10cm` e `15cm`;
  - cada tamanho guarda sua propria lista de codigos;
  - possui editor visual simples (`label-editor.html`) com arrastar, redimensionar, guias e exportacao de JSON de layout;
  - download unico `etiquetas.zip`;
  - quando o navegador permite, reutiliza/substitui o mesmo `etiquetas.zip` durante a sessao;
  - registra historico e ranking de etiquetas no PostgreSQL;
  - pastas internas `5cm`, `7cm`, `10cm`, `15cm`;
  - lixeira para limpar a lista do tamanho atual.

## Automacao

Os scripts Python ficam em `scripts/`.

- `scripts/controladordeatualizacao.py` - controlador principal da automacao.
- `scripts/executar_tudo.py` - executa a sequencia de macros.
- `scripts/macro_001.py` a `scripts/macro_006.py` - macros gravadas.
- `scripts/macro_gravador.py` - gravador de macros.
- `scripts/identificador_de_pixel.py` - utilitario de leitura de pixel.
- `scripts/totvs_news_reference.json` e `scripts/totvs_news_reference.png` - referencia do detector TOTVS.
- `scripts/atualizacao/automus_update.py` - atualizacao do estoque no SQL/API sem depender do navegador.
- `scripts/atualizacao/automus_config.json` - configuracao local legada do Automus, mantida apenas para compatibilidade.
- Logs e caches (`*.log`, `__pycache__/`, `*.pyc`) sao artefatos gerados e ficam fora do versionamento.

## Regras de Estoque

### Origem de minimo, maximo e reposicao

A prioridade dos limites e:

1. Ajuste manual salvo no perfil do item (`estoqueGlobal/ajustesItens`).
2. Valores validos da planilha `estoque_minimo.xlsx`.
3. Sugestao automatica do sistema.
4. Valor anterior ja salvo, quando a planilha de estoque minimo nao foi carregada.

Zero, vazio ou valor invalido em minimo/maximo/reposicao e tratado como "sem limite". Quando a planilha `estoque_minimo.xlsx` traz a linha do item, mas minimo/maximo/reposicao estao zerados, o sistema usa o `SALDO ANTERIOR` apenas como pista de consumo; ele nao vira minimo automaticamente.

### Sugestao automatica

A sugestao automatica usa metodologia de ponto de pedido:

- `reposicao` e a quantidade para voltar do minimo ao maximo (`maximo - minimo`), nao a media entre minimo e maximo.
- O consumo estimado considera historico de saidas do item, pico recente de saida, queda entre `SALDO ANTERIOR` e saldo atual, e pedido medio anterior quando existir.
- Quando existe pedido de compra anterior, a media recebida vira referencia de lote de reposicao. O minimo sugerido por compra usa cerca de 35% desse lote como estoque de seguranca, sem transformar o lote inteiro em minimo.
- Exemplo: pedido medio anterior de 100 pecas, sem outro consumo melhor, sugere minimo perto de 35, maximo perto de 135 e reposicao perto de 100.
- Ajustes manuais sempre vencem a sugestao automatica e sao preservados nas proximas atualizacoes.

### Filtros de faixa

O botao `!` na coluna Saldo alterna em tres estados:

1. Normal: mostra a tabela completa.
2. Fora da faixa: mostra itens abaixo do minimo ou acima do maximo, ocultando os itens dentro da faixa.
3. Fora da faixa sem pedido: mostra apenas os itens fora da faixa que ainda nao tem pedido/solicitacao ativa. Neste modo o botao muda para `P` e fica laranja.

## Modos de Atualizacao Automus

No painel admin do Dark-Jutsu existem tres acoes:

- Atualizar nivel 1: roda macros 001-005 e envia mata105/mata225/mata226.
- Atualizar nivel 2: roda macros 007-009 e envia dados de pedido, compra e enderecamento.
- Atualizar os dois: executa nivel 1, envia, depois executa nivel 2 e envia.

## Dashboard

Abra `dashboard.html` para uma visao resumida do estoque. A pagina usa a sessao SQL local e aceita os mesmos logins do sistema.

Parametros de URL:

- `status`: `fora`, `abaixo`, `acima`, `ok`, `sem-faixa` ou `todos`. Padrao: `fora`.
- `semSolicitacao=1`: mostra apenas itens sem solicitacao/pedido ativo.
- `itens=COD1,COD2`: limita o dashboard a codigos especificos.
- `origem`: filtra por origem dos limites, como `cooperat`, `manual`, `automatico` ou `anterior`.
- `limite`: quantidade maxima de linhas, de 1 a 500. Padrao: 80.
- `ordenar`: `reposicao`, `saldo`, `descricao` ou `codigo`. Padrao: `reposicao`.
- `direcao`: `asc` ou `desc`. Padrao: `desc`.
- `titulo`: titulo exibido no topo.

Exemplo:

```text
dashboard.html?status=fora&semSolicitacao=1&limite=50&ordenar=reposicao&direcao=desc
```

### Avaliador de pedidos

Abra:

```text
dashboard.html?ambiente=avaliador&armazem=04&status=abaixo&limite=50
```

O avaliador lista itens abaixo do minimo ainda nao avaliados, mostra historico recente de pedidos por item, prazo medio de recebimento, quantidade media comprada e dias desde o ultimo pedido. A decisao fica salva no PostgreSQL via API. Itens marcados como passíveis entram no kanban de acompanhamento; itens marcados como minimo incorreto, reposicao incorreta ou nao solicitar ficam separados como avaliados fora do fluxo de compra.

O historico antigo do Cooperat fica separado visualmente do historico novo MATA111/MATA112. Ele usa:

- `Qtd.Solicitada` como quantidade comprada.
- `Vlr Baixa` como valor unitario da peca.
- PostgreSQL como base principal.
- `data/historico_cooperat_antigo.json` apenas como fallback/arquivo historico local.

## Como executar scripts

Use o Python instalado via WindowsApps, se `python` nao estiver no PATH:

```powershell
C:\Users\davi.souza\AppData\Local\Microsoft\WindowsApps\python.exe .\scripts\executar_tudo.py
C:\Users\davi.souza\AppData\Local\Microsoft\WindowsApps\python.exe .\scripts\executar_tudo.py macro_001.py
C:\Users\davi.souza\AppData\Local\Microsoft\WindowsApps\python.exe .\scripts\executar_tudo.py macro_002.py
C:\Users\davi.souza\AppData\Local\Microsoft\WindowsApps\python.exe .\scripts\executar_tudo.py macro_003.py
C:\Users\davi.souza\AppData\Local\Microsoft\WindowsApps\python.exe .\scripts\executar_tudo.py macro_004.py
C:\Users\davi.souza\AppData\Local\Microsoft\WindowsApps\python.exe .\scripts\executar_tudo.py macro_005.py
C:\Users\davi.souza\AppData\Local\Microsoft\WindowsApps\python.exe .\scripts\executar_tudo.py macro_006.py
```

Ou, se `python` estiver disponivel no PATH:

```powershell
python .\scripts\executar_tudo.py
python .\scripts\macro_gravador.py
python .\scripts\identificador_de_pixel.py
```

## Banco SQL

O app usa PostgreSQL local via `api/dark_jutsu_api.py`. A autenticacao, estoque, chat, contagens, ocorrencias, dashboard e etiquetas passam pela API SQL.

## Etiquetas

O gerador integrado replica os moldes do app Python mais recente:

- renderizacao em 300 DPI;
- escala interna 2x;
- fonte Oswald;
- logo Fiasul;
- codigo novo, descricao e `COOPERAT:` posicionados por molde;
- `COOPERAT:` sempre aparece, mesmo sem codigo antigo.

Observacao: o navegador gera PNGs via Canvas, enquanto o app `.exe` usa Pillow. As medidas, textos e regras foram espelhadas, mas pode haver pequena diferenca visual de antialiasing entre Canvas e Pillow.

## Servidor Local, API e Guardiao

O Dark-Jutsu roda como sistema local na rede privada. O app fica no servidor de arquivos e a API SQL fica ativa em apenas um dos computadores de servidor por vez.

### Acesso pelo celular sem assinatura paga

Para usar no celular sem contratar hospedagem, mantenha o PC servidor e o celular na mesma rede Wi-Fi e execute:

```bat
iniciar_darkjutsu_celular.bat
```

O script mostra um ou mais enderecos no formato:

```text
http://IP_DO_PC:8765
```

Abra esse endereco no navegador do celular. A propria API tambem serve o `index.html`, `dashboard.html`, `medidores.html` e arquivos publicos do app, entao nao precisa instalar servidor web separado.

Se o celular estiver na mesma rede e mesmo assim nao abrir, libere a porta no Firewall do Windows executando como administrador:

```bat
scripts\liberar_firewall_darkjutsu.bat
```

Se voce nao tiver permissao de administrador, use o modo por tunel temporario gratuito:

```bat
iniciar_darkjutsu_celular_sem_admin.bat
```

Quando aparecer uma URL `https://...trycloudflare.com`, abra essa URL no celular. Esse modo nao abre porta no roteador e nao altera o Firewall, mas depende de internet no PC e o link muda a cada execucao. O proprio Dark-Jutsu mostra o link atual e um QR Code na tela de login e no botao `Celular`.

O modo celular usa uma API separada em `127.0.0.1:8766`, deixando a API normal do servidor em `8765` livre para o monitor e para a rede interna.

Para iniciar o modo celular automaticamente ao entrar neste usuario do Windows, execute uma vez:

```bat
ativar_celular_ao_ligar_darkjutsu.bat
```

Sem permissao de administrador, o link gratuito do `trycloudflare.com` nao e fixo. Para ter sempre o mesmo endereco externo, use um tunnel nomeado/protegido em uma conta Cloudflare conforme `scripts\iniciar_cloudflare_tunnel_darkjutsu.bat`.

Para acesso fora da rede da empresa/casa sem abrir porta no roteador, use um tunel gratuito/protegido conforme `scripts\iniciar_cloudflare_tunnel_darkjutsu.bat`. Evite publicar o sistema em tunel publico sem controle de acesso.

### Candidatos e prioridade

- Todo PC instalado pode hospedar a API e funciona como candidato.
- O arquivo `scripts/servidores_config.json` define a prioridade; o menor numero vence.
- `ALMOX-PC03` tem prioridade preferencial, seguido por `ALMOX-PC01` e `ALMOX-EPI`.
- API SQL: `http://IP_DO_SERVIDOR:8765/health`.
- PostgreSQL local do servidor ativo: porta `5433`.
- Pacote compartilhado: `\\fileserver\Almoxarifado\0800\servidor\dark-jutsu`.

### Regra de failover

- Cada candidato publica um heartbeat compartilhado com disponibilidade, IP e saude local.
- Uma eleicao protegida por trava escolhe o candidato elegivel de maior prioridade e publica uma concessao (`lease`) curta.
- Se o lider cair ou deixar de renovar, o proximo candidato disponivel assume.
- Quando o candidato preferencial volta estavel, ele reassume apos o periodo de seguranca configurado.
- Somente o dono da `lease` mantem a API local ligada, reduzindo o risco de dois servidores ativos.

Os detalhes operacionais e de migracao estao em `docs/cluster-dinamico-servidores.md`.

### Comando unico de instalacao ou atualizacao

Rode no usuario Windows que deve ver o icone do servidor:

```cmd
cmd /c "pushd \\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts && call instalar_atualizar_guardiao_monitor_darkjutsu.bat && popd"
```

O instalador registra qualquer PC como candidato, instala o mesmo guardiao/monitor e usa a prioridade do arquivo compartilhado.

### Icone do servidor

- Verde: este PC esta servindo a API.
- Vermelho: outro PC esta servindo a API.
- Preto: nenhuma API respondeu naquele momento.

O botao `Abrir Dark-Jutsu` nao pede senha. Os comandos de controle pedem a senha operacional `654321`.

### Logs importantes

- Log local do guardiao: `C:\DarkJutsu\logs\servidor_guardiao.log`.
- Log local do monitor: `C:\DarkJutsu\logs\monitor_servidor.log`, `monitor_python.log` ou `monitor_launcher.log`.
- Log local da API: `C:\DarkJutsu\logs\api_runtime.log`.
- Log local do instalador: `C:\DarkJutsu\logs\instalador_guardiao_monitor.log`.
- Log compartilhado de eventos: `\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\logs\servidor_eventos_darkjutsu.txt`.

O log compartilhado registra heartbeats, lider eleito, epoca da eleicao, health checks e trocas de lideranca.

### Teste rapido

```cmd
python scripts/status_compartilhado_servidores_darkjutsu.py
```

Resultado esperado: exatamente um candidato aparece como lider saudavel; os demais ficam prontos, mas com a API local parada.

## Observacoes de manutencao

- Evite editar arquivos gerados em `__pycache__/`.
- Mantenha os assets das etiquetas em `downloads/`.
- A mata105 nativa das etiquetas e do estoque e `downloads/incluir.xlsx`.
- Ajustes manuais de minimo/maximo devem ser mantidos em `estoqueGlobal/ajustesItens`, nao apenas dentro de `dados`.
