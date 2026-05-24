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

## Gerar pacote de atualizacao

O jeito mais simples e usar:

```bat
atualizar_automus.bat
```

Ele pergunta a nova versao, as notas da versao, atualiza `scripts\version.json`, gera o novo `Automus.exe`, cria o `.zip`, atualiza o `latest.json` e abre a pasta `releases`.

Se voce preencher uma pasta local de publicacao no assistente, ele tambem copia automaticamente para essa pasta:

```text
latest.json
Automus-vVERSAO.zip
```

Para ativar atualizacao automatica nos computadores dos usuarios, publique o conteudo da pasta `releases` em algum endereco HTTP/HTTPS e preencha:

```json
{
  "updateManifestUrl": "https://seu-servidor/automus/latest.json",
  "updateBaseUrl": "https://seu-servidor/automus/"
}
```

O `updateManifestUrl` e o endereco que o Automus instalado consulta. O `updateBaseUrl` e usado na hora de gerar o `latest.json`, para apontar para o `.zip` da versao nova.

Depois use:

```bat
gerar_pacote_atualizacao.bat
```

Esse comando ainda existe para gerar o pacote direto a partir do `scripts\version.json`. O pacote fica em:

```text
releases\Automus-vVERSAO.zip
```

Esse `.zip` leva o `Automus.exe`, o manifesto `latest.json` e a versao usada. Para atualizar outro PC, feche o Automus antigo, substitua o `Automus.exe` pelo novo e abra novamente. A pasta `AutomusData` do outro PC deve permanecer no lugar para manter preferencias, historico e agendamentos.

Com `updateManifestUrl` configurado, o Automus verifica automaticamente depois do login ADM. Se houver versao nova, o app baixa o pacote, confere o SHA256, fecha, troca o executavel e abre novamente. A `AutomusData` nao e alterada. O botao `Verificar update` continua disponivel para conferir manualmente.

## Arquivos principais

- `scripts\controladordeatualizacao*.py`: interface e app em segundo plano.
- `scripts\executar_tudo.py`: fluxo principal de atualizacao.
- `scripts\atualizacao\automus_update.py`: envio e validacao dos dados no Firebase.
- `scripts\firebase_config.json`: configuracao Firebase usada pelo Automus sem depender do `index.html` do projeto principal.
- `scripts\version.json`: versao exibida no titulo e usada nos pacotes de atualizacao.
- `scripts\preparar_release_automus.py`: assistente para atualizar versao, notas e gerar o pacote completo.
- `scripts\package_automus_release.py`: cria o `.zip` de atualizacao.
- `scripts\automus_self_update.py`: verifica, baixa e instala novas versoes do Automus.exe.
- `downloads\`: planilhas base copiadas para o pacote isolado.
- `requirements.txt`: dependencias Python do Automus.
