# Automus

Esta pasta contem somente o controlador Automus e os arquivos necessarios para gerar e publicar o executavel separado do projeto principal.

## Atualizar o Automus

Use:

```bat
atualizar_automus.bat
```

Ele abre uma interface para informar a nova versao, as notas e acompanhar o loading da publicacao. A interface atualiza `scripts\version.json`, fecha qualquer Automus aberto, gera o novo `Automus.exe`, cria o `.zip`, atualiza o `latest.json` e copia para a pasta de publicacao configurada.

Na tela:

```text
Nova versao: confira ou altere a versao sugerida
Notas da versao: escreva o que mudou
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
  "updateBaseUrl": "https://seu-servidor/automus/"
}
```

O `updateManifestUrl` e o endereco HTTP que o Automus instalado consulta. O `updateBaseUrl` e usado na hora de gerar o `latest.json`, para apontar para o `.zip` da versao nova.

O `.zip` deve ficar em um link HTTP/HTTPS, compartilhamento de rede Windows ou servidor interno acessivel pelos usuarios.

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
- `scripts\atualizacao\automus_update.py`: envio e validacao dos dados no SQL/API.
- `scripts\version.json`: versao exibida no titulo e usada nos pacotes de atualizacao.
- `scripts\preparar_release_automus.py`: assistente para atualizar versao, notas e gerar o pacote completo.
- `scripts\package_automus_release.py`: cria o `.zip` de atualizacao.
- `scripts\automus_self_update.py`: verifica, baixa e instala novas versoes do Automus.exe.
- `downloads\`: planilhas base copiadas para o pacote isolado.
- `requirements.txt`: dependencias Python do Automus.

## Ensaio do ambiente da macro

Depois do login, use **Testar ambiente da macro**. O ensaio nao clica nem
digita: ele confere resolucao, escala/DPI, localiza o TOTVS e ajusta sua janela
para `1366x768` na posicao `0,0`. O resultado tambem informa o tamanho real da
area cliente e se o TOTVS estava em foco. Nesta primeira fase o diagnostico nao
bloqueia as macros existentes.

Para abrir o navegador com o perfil separado e a geometria do ensaio, execute
`scripts\abrir_protheus_controlado.ps1`.

## Execucao centralizada pelo servidor

Ao publicar, o Automus envia a aplicacao descompactada para
`<publishDir>\Aplicacao\<versao>` e atualiza `versao_atual.txt`. As versoes sao
separadas para nao sobrescrever um executavel que esteja aberto pela rede.

Em cada computador, execute uma unica vez
`Configurar_Automus_neste_PC.bat`, diretamente na pasta publicada do servidor.
Ele cria somente o atalho da Area de Trabalho e a inicializacao automatica. O
programa e suas dependencias permanecem no servidor; configuracoes por usuario
continuam em `%APPDATA%\Automus`.

A inicializacao e registrada em `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`,
sem depender de permissao de escrita na pasta Startup e sem exigir administrador.
