# Automus

Esta pasta contem somente o controlador Automus e os arquivos necessarios para rodar ou gerar o executavel separado do projeto principal.

## Rodar em desenvolvimento

Use:

```bat
iniciar_automus.bat
```

O app sempre pede login ADM ao iniciar. As preferencias, historico, agendamentos e dados locais ficam dentro da propria pasta do Automus ou ao lado do executavel.

Se faltar alguma biblioteca Python, o `.bat` instala o que esta listado em `requirements.txt`.

## Gerar o executavel

Use:

```bat
gerar_exe.bat
```

O resultado fica em:

```text
dist\Automus.exe
```

Para passar para outro PC, copie somente `dist\Automus.exe`. No primeiro uso ele cria uma pasta `AutomusData` ao lado do executavel para guardar configuracoes, historico e arquivos baixados.

## Arquivos principais

- `scripts\controladordeatualizacao*.py`: interface e app em segundo plano.
- `scripts\executar_tudo.py`: fluxo principal de atualizacao.
- `scripts\atualizacao\automus_update.py`: envio e validacao dos dados no Firebase.
- `scripts\firebase_config.json`: configuracao Firebase usada pelo Automus sem depender do `index.html` do projeto principal.
- `downloads\`: planilhas base copiadas para o pacote isolado.
- `requirements.txt`: dependencias Python do Automus.
