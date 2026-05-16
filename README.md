# Dark-Jutsu

Este projeto ficou organizado em duas partes:

- `index.html`, `style.css`, `mobile.css` e as imagens do tema ficam na raiz.
- `scripts/` concentra tudo que e Python e tudo que pertence ao bloco de atualizacao/automacao.

## Estrutura

- `scripts/controladordeatualização.py` - controlador principal da automacao.
- `scripts/executar_tudo.py` - executa a sequencia de macros.
- `scripts/macro_001.py` a `scripts/macro_005.py` - macros gravadas.
- `scripts/macro_gravador.py` - gravador de macros.
- `scripts/identificador_de_pixel.py` - utilitario de leitura de pixel.
- `scripts/totvs_news_reference.json` e `scripts/totvs_news_reference.png` - referencia do detector TOTVS.
- `scripts/executar_tudo.log` - log gerado pela automacao.

Ordem atual de execucao em `executar_tudo.py`:

1. `macro_001`
2. `macro_002`
3. `macro_003`
4. `macro_004`

## Como executar

Rode os scripts a partir da pasta `scripts/` ou informe o caminho completo, por exemplo:

```powershell
python .\scripts\executar_tudo.py
python .\scripts\executar_tudo.py macro_001.py
python .\scripts\executar_tudo.py macro_002.py
python .\scripts\executar_tudo.py macro_003.py
python .\scripts\executar_tudo.py macro_004.py
python .\scripts\executar_tudo.py macro_005.py
python .\scripts\macro_gravador.py
python .\scripts\identificador_de_pixel.py
```

Na interface do controlador, voce tambem encontra:

- uma janela flutuante com a macro atual e os botões de pausa/parada
- botões para executar cada macro separadamente

## Observacao

Os arquivos Python continuam usando importacao entre arquivos vizinhos, entao a pasta `scripts/` deve permanecer junta aos arquivos de apoio que ela usa.
