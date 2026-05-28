# Dark-Jutsu

Sistema web local para consulta de estoque, chat interno, administracao de usuarios, automacao de atualizacao e geracao de etiquetas Fiasul.

## Estrutura

- `index.html` - aplicacao principal, Firebase, tabela de estoque, chat, painel admin, relatorios, contagem, editor de limites e gerador de etiquetas.
- `style.css` - estilos desktop da aplicacao.
- `mobile.css` - ajustes responsivos/mobile.
- `downloads/` - planilhas e assets usados pelo sistema:
  - `incluir.xlsx` - base mata105 nativa usada no estoque e nas etiquetas.
  - `Saldo Atual.xlsx`
  - `Saldo por Endereco.xlsx`
  - `estoque_minimo.xlsx`
  - `etiquetas_logo.png`
  - `Oswald-Regular.ttf`
  - `Oswald-Bold.ttf`
- `scripts/` - automacao Python, macros e atualizador Automus.

## Funcionalidades principais

- Consulta e filtro de itens de estoque.
- Filtro de saldo fora da faixa minima/maxima.
- Captura de itens pelo modo magnet.
- Relatorio imprimivel dos itens selecionados.
- Tela de contagem de estoque por maquina/endereco, limitada aos armazens 04 e 05, com rascunho local, botoes rapidos, divergencias e exportacao XLSX.
- Modal de perfil do item com saldo, endereco, minimo, maximo e reposicao.
- Edicao item a item de minimo e maximo dentro do modal.
- Reposicao calculada como quantidade para voltar do minimo ao maximo; sugestoes automaticas usam consumo, pedido medio e saldo das planilhas.
- Ajustes manuais persistidos em `estoqueGlobal/ajustesItens`, preservados apos atualizacoes.
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
  - download unico `etiquetas.zip`;
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
- `scripts/atualizacao/automus_update.py` - atualizacao do Firebase sem depender do navegador.
- `scripts/atualizacao/automus_config.json` - credenciais/configuracao local do Automus.
- `scripts/executar_tudo.log` - log gerado pela automacao.

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

## Firebase

O app usa Firebase Auth e Realtime Database.

Pontos importantes das regras:

- `estoqueGlobal` deve permitir leitura para usuarios ativos.
- Escrita em `estoqueGlobal` continua restrita a admin ou ao email tecnico autorizado.
- `chatReadState/$uid` precisa permitir leitura/escrita apenas para o proprio usuario.
- `chatRooms/$room/typing/$uid` precisa permitir escrita apenas para o proprio usuario.
- `chatRooms/$room/messages` precisa permitir leitura/escrita para usuarios autenticados.
- `contagens` precisa permitir leitura/escrita para usuarios autenticados para salvar e consultar contagens.

## Etiquetas

O gerador integrado replica os moldes do app Python mais recente:

- renderizacao em 300 DPI;
- escala interna 2x;
- fonte Oswald;
- logo Fiasul;
- codigo novo, descricao e `COOPERAT:` posicionados por molde;
- `COOPERAT:` sempre aparece, mesmo sem codigo antigo.

Observacao: o navegador gera PNGs via Canvas, enquanto o app `.exe` usa Pillow. As medidas, textos e regras foram espelhadas, mas pode haver pequena diferenca visual de antialiasing entre Canvas e Pillow.

## Observacoes de manutencao

- Evite editar arquivos gerados em `__pycache__/`.
- Mantenha os assets das etiquetas em `downloads/`.
- A mata105 nativa das etiquetas e do estoque e `downloads/incluir.xlsx`.
- Ajustes manuais de minimo/maximo devem ser mantidos em `estoqueGlobal/ajustesItens`, nao apenas dentro de `dados`.
