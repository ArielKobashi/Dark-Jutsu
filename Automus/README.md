# Automus

Esta pasta contem somente o controlador Automus e os arquivos necessarios para gerar e publicar o executavel separado do projeto principal.

## Atualizar o Automus

Use:

```bat
atualizar_automus.bat
```

Ele abre uma interface para informar a nova versao, as notas, login ADM do Firebase e acompanhar o loading da publicacao. A interface atualiza `scripts\version.json`, fecha qualquer Automus aberto, gera o novo `Automus.exe`, cria o `.zip`, atualiza o `latest.json`, copia para a pasta de publicacao configurada e pode enviar o manifesto para o Firebase.

Na tela:

```text
Nova versao: confira ou altere a versao sugerida
Notas da versao: escreva o que mudou
Enviar manifesto para Firebase: deixe marcado
Login ADM Firebase: seu login ADM
Senha ADM Firebase: sua senha ADM
ENVIAR ATUALIZACAO: clique para iniciar
```

Antes de compilar, o assistente fecha automaticamente qualquer `Automus.exe` aberto para evitar erro de permissao no `dist\Automus.exe`.

O executavel gerado usa `C:\Users\Public\AutomusRuntimeTemp` como pasta fixa de extracao do PyInstaller, evitando falhas de DLL em `_MEI...` dentro do Temp do usuario.

Se voce preencher uma pasta local de publicacao no assistente, ele tambem copia automaticamente para essa pasta:

```text
latest.json
Automus-vVERSAO.zip
```

Para ativar atualizacao automatica nos computadores dos usuarios, preencha:

```json
{
  "updateManifestUrl": "https://seu-servidor/automus/latest.json",
  "updateManifestFirebasePath": "automus/releases/latest",
  "updateBaseUrl": "https://seu-servidor/automus/"
}
```

O `updateManifestUrl` e o endereco HTTP que o Automus instalado consulta. Se preferir Firebase, use `updateManifestFirebasePath`: depois do login ADM, o Automus le esse caminho no Realtime Database. O `updateBaseUrl` e usado na hora de gerar o `latest.json`, para apontar para o `.zip` da versao nova.

No Firebase, grave o conteudo de `releases\latest.json` no caminho escolhido, por exemplo:

```text
automus/releases/latest
```

O `.zip` nao deve ficar dentro do Realtime Database. Hospede o arquivo em um link HTTP/HTTPS, como Firebase Storage, Firebase Hosting, Google Drive com link direto, servidor interno ou GitHub Releases, e deixe esse link no campo `packageUrl` do manifesto. O assistente `atualizar_automus.bat` pode enviar o `latest.json` para o Firebase depois de gerar a release.

Tambem pode usar um caminho de rede Windows para o pacote, por exemplo:

```json
{
  "updateBaseUrl": "\\\\fileserver\\Almoxarifado\\0800\\automus",
  "publishDir": "\\\\fileserver\\Almoxarifado\\0800\\automus"
}
```

Nesse caso, o assistente copia o `.zip` para essa pasta e o Automus dos usuarios baixa/copias dali. Os computadores precisam ter acesso a esse compartilhamento de rede.

O pacote fica em:

```text
releases\Automus-vVERSAO.zip
```

Esse `.zip` leva o `Automus.exe`, o manifesto `latest.json` e a versao usada.

Com `updateManifestUrl` configurado, o Automus verifica automaticamente depois do login ADM. Se houver versao nova, o app baixa o pacote, confere o SHA256, fecha, troca o executavel e abre novamente. Os complementos ficam em `%APPDATA%\Automus\complemento`, sem criar `AutomusData` ao lado do exe. O botao `Verificar update` continua disponivel para conferir manualmente.

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
