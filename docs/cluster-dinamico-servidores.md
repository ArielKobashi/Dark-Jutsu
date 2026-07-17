# Cluster dinamico de servidores Dark-Jutsu

Todos os PCs que recebem o instalador do Guardiao sao candidatos equivalentes. Apenas um mantem a API gravavel. A preferencia fica em `scripts/servidores_config.json`, sem papeis fixos por IP.

## Prioridade

Numero menor significa maior prioridade. Um PC nao listado participa com `defaultPriority` quando `autoDiscover` estiver ativo.

```json
{
  "autoDiscover": true,
  "defaultPriority": 1000,
  "candidates": [
    {"computer": "ALMOX-PC03", "priority": 10, "enabled": true},
    {"computer": "ALMOX-PC01", "priority": 20, "enabled": true}
  ]
}
```

Para trocar a preferencia, altere os numeros. Para retirar temporariamente um candidato, use `"enabled": false`.

## Eleicao

Cada Guardiao publica heartbeat em `status/nodes/NOME.json`. Um candidato e elegivel quando esta habilitado, publicou heartbeat recente e possui PostgreSQL local pronto.

O vencedor grava `status/leader_lease.json`. O lease tem expiracao e `epoch`. Um lock no fileserver serializa a eleicao. Se o fileserver ficar indisponivel, nenhum candidato novo assume e o Guardiao deixa de considerar a si mesmo lider, evitando dois gravadores.

Quando o preferencial retorna, precisa permanecer pronto durante `preferredReturnGraceSeconds` antes de reassumir. Isso evita alternancias durante oscilacoes.

## Banco de dados

O cluster continua com um unico PostgreSQL gravavel por vez. Cada candidato precisa manter sua copia local atualizada pelas rotinas existentes de backup e restauracao. O lease evita duas APIs ativas, mas nao substitui replicacao. A perda maxima de dados depende da frequencia do backup/restore.

## Instalacao

Execute o mesmo instalador em qualquer PC candidato:

```cmd
cmd /c "pushd \\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts && call instalar_atualizar_guardiao_monitor_darkjutsu.bat && popd"
```

O instalador nao exige mais IP principal ou reserva. Ele instala o monitor Python, o Guardiao dinamico e o modulo de eleicao.

## Arquivos operacionais

- Configuracao: `scripts/servidores_config.json`
- Heartbeats: `status/nodes/*.json`
- Lease: `status/leader_lease.json`
- Lock temporario: `status/leader-election.lock`
- Status detalhado: `status/nodes-detail/*.json`

## Migracao segura

1. Publicar os scripts no fileserver.
2. Executar o instalador em cada candidato, um por vez.
3. Confirmar todos no status dinamico.
4. Confirmar um unico lease e uma unica API respondendo.
5. Somente depois executar o teste de queda controlado.
