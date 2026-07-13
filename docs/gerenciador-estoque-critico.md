# Gerenciador de Estoque Critico

Documento de regras e parametros para orientar a implementacao do gerenciador automatico de estoque critico do Dark Jutsu.

Este documento substitui a ideia do "sugestor de estoque minimo" por um motor controlado, auditavel e integrado ao avaliador. O motor nao deve agir como caixa preta: toda decisao precisa carregar dados usados, dados ignorados, regras aplicadas, confianca, explicacao e proxima acao.

## Objetivo

O gerenciador deve calcular politica de estoque por item:

- minimo
- maximo
- reposicao
- ponto de reposicao
- quantidade sugerida
- risco de ruptura
- risco de excesso
- confianca do calculo
- decisao operacional
- explicacao para o avaliador

O resultado deve alimentar o avaliador e, quando permitido pelas regras globais, aplicar limites automaticamente.

## Preceitos Fixos

1. Saldo inicial nao e parametro de aprendizado.
2. Saldo atual so serve para comparar contra a politica ja calculada.
3. Ajuste manual vence qualquer calculo automatico.
4. Decisao do avaliador vence sugestao automatica.
5. Aumento brusco nunca e aplicado sem revisao.
6. Reducao brusca nunca e aplicada sem revisao.
7. Item com pedido aberto nao deve gerar nova solicitacao automatica.
8. Item morto/inativo nao deve gerar reposicao.
9. Item sem dados suficientes nao deve receber minimo inventado.
10. Toda decisao deve ser explicavel e auditavel.
11. Entrada elevada fora do padrao nao deve inflar politica automaticamente.

## Fontes de Dados do Dark

### Fontes Primarias

| Fonte | Uso |
|---|---|
| `inventory_balance_history` / `historicoSaldo` | Saidas e entradas reais por delta. Usar `delta < 0` como consumo real. |
| `inventory_items` | Cadastro, saldo atual, armazem, endereco, origem atual dos limites. |
| `inventory_item_addresses` | Distribuicao por endereco/armazem e anomalias de enderecamento. |
| `inventory_adjustments` | Ajustes manuais de minimo/maximo/reposicao. |
| `purchase_evaluations` | Memoria do avaliador e status do kanban. |
| `pedidosCompra` / MATA110/MATA111/MATA112 | Solicitacao, pedido, recebimento, lead time e pedidos abertos. |
| `historico_cooperat_antigo` | Evidencia historica por codigo Cooperat, principalmente para item intermitente. |
| `movimentacoesMata185` | Movimentos/requisicoes. Enquanto estiver bruto, usar como evidencia fraca; quando normalizado, vira fonte primaria. |

### Fontes Permitidas Como Estado, Nao Aprendizado

| Fonte | Pode usar para | Nao pode usar para |
|---|---|---|
| Saldo atual | Saber se esta abaixo/acima da politica | Calcular demanda, minimo ou consumo |
| Saldo anterior da planilha de estoque minimo | Auditoria e comparacao visual | Inferir consumo automatico |
| Limite Cooperat existente | Fallback/controlador de origem | Provar consumo |

## Ordem de Autoridade

Quando houver conflito entre fontes, usar esta ordem:

1. `manual`: ajuste feito por usuario.
2. `avaliador`: decisao aprovada no avaliador.
3. `politica_item`: regra fixa por item/categoria.
4. `cooperat`: limite oficial/importado.
5. `motor_critico`: calculo automatico.
6. `sem_politica`: sem limite confiavel.

O motor automatico so pode substituir um nivel superior se houver acao explicita do usuario.

## Parametros Mutaveis Globais

Estes parametros devem ficar em tabela/configuracao, nao hardcoded.

```json
{
  "usarSaldoInicialNoAprendizado": false,
  "modoAplicacao": "sombra",
  "confiancaMinimaParaAplicar": 0.85,
  "confiancaMinimaParaSugerir": 0.55,
  "eventosMinimosParaAplicar": 8,
  "eventosMinimosParaSugerir": 3,
  "janelaHistoricoDias": 730,
  "janelaHistoricoMinimaDias": 180,
  "leadTimePadraoDias": 30,
  "leadTimeMaximoDias": 120,
  "nivelServicoPadrao": 0.9,
  "aumentoAutomaticoMaximoPercentual": 0.5,
  "reducaoAutomaticaMaximaPercentual": 0.3,
  "multiplicadorAumentoRevisao": 3,
  "multiplicadorReducaoRevisao": 0.4,
  "bloquearComPedidoAberto": true,
  "bloquearItemMorto": true,
  "bloquearSemEnderecoValido": false,
  "bloquearSemHistorico": true,
  "tratarOutlierComoRevisao": true,
  "tratarEntradaElevadaComoPreventiva": true,
  "percentilOutlier": 0.95,
  "multiplicadorEntradaElevada": 3,
  "percentilEntradaElevada": 0.9,
  "maximoPorLoteMultiplicador": 3,
  "minimoNuncaMenorQue": 1
}
```

### Modos de Aplicacao

| Modo | Comportamento |
|---|---|
| `sombra` | Calcula e mostra, mas nao altera limites. |
| `sugestao` | Calcula e envia para avaliador. |
| `semi_auto` | Aplica somente baixo risco; medio/alto vai para avaliador. |
| `auto_controlado` | Aplica dentro das travas globais e registra auditoria. |

O modo inicial deve ser `sombra`.

## Parametros Mutaveis Por Item

Cada item pode ter politica propria:

```json
{
  "itemKey": "3101001141",
  "criticidade": "normal",
  "classeOperacional": "manutencao",
  "leadTimeManualDias": null,
  "nivelServico": 0.9,
  "loteMinimoCompra": null,
  "loteMultiplo": null,
  "minimoManualTravado": null,
  "maximoManualTravado": null,
  "reposicaoManualTravada": null,
  "permitirAjusteAutomatico": true,
  "permitirReducaoAutomatica": true,
  "permitirAumentoAutomatico": true,
  "observacaoRegra": ""
}
```

### Criticidade

| Criticidade | Efeito |
|---|---|
| `vital` | Aumenta nivel de servico, reduz tolerancia a ruptura, exige avaliacao se dados forem fracos. |
| `essencial` | Politica conservadora, alerta cedo. |
| `normal` | Politica padrao. |
| `baixo` | Reduz estoque de seguranca e evita excesso. |
| `obsoleto` | Bloqueia reposicao automatica. |

## Mecanismo de Calculo

### 1. Normalizar Identidade do Item

Chaves candidatas:

- `protheus_code`
- `protheus_key`
- `cooperat_code`
- `legacy_key`

O motor deve registrar quais chaves foram usadas.

### 2. Coletar Eventos Reais

Eventos de consumo:

- `inventory_balance_history.delta < 0`
- MATA185 normalizado com tipo de saida/requisicao encerrada
- historico Cooperat quando indicar requisicao/fornecimento/baixa operacional

Eventos de reposicao:

- `inventory_balance_history.delta > 0`
- MATA111 pedido
- MATA112 entrada/enderecamento
- MATA185 normalizado de entrada, quando disponivel

Nao considerar como consumo:

- saldo inicial
- saldo anterior da planilha de estoque minimo
- diferenca entre duas fotografias sem evento confirmado
- saldo por endereco isolado

### 2.1. Detectar Entrada Elevada Fora do Padrao

Algumas entradas aparecem maiores que o comportamento normal porque a compra veio a mais para preventiva, manutencao programada, oportunidade de compra, lote minimo de fornecedor ou regularizacao. Esse tipo de entrada nao pode virar minimo/maximo automaticamente.

O motor deve marcar uma entrada como `entrada_elevada_fora_padrao` quando qualquer regra abaixo for verdadeira:

```text
quantidade_entrada >= mediana_entradas * multiplicadorEntradaElevada
quantidade_entrada >= percentilEntradaElevada das entradas historicas
quantidade_entrada > max(mediana_consumo_evento * multiplicadorEntradaElevada, lote_reposicao_tipico * multiplicadorEntradaElevada)
```

Regras:

- entrada elevada pode ajudar a identificar lote de compra, mas nao prova demanda recorrente.
- entrada elevada nao pode aumentar minimo automaticamente.
- entrada elevada nao pode aumentar maximo automaticamente sem avaliador.
- se a entrada elevada estiver ligada a pedido preventivo, marcar motivo `entrada_preventiva_possivel`.
- se houver consumo posterior confirmando a necessidade, a entrada deixa de ser tratada como outlier aos poucos.
- se o avaliador aprovar a entrada como novo padrao, gravar decisao em politica do item.

Efeito no calculo:

```text
entrada_elevada_fora_padrao:
  peso_demanda = 0
  peso_lote_reposicao = 0.3
  bloqueia_aplicacao_automatica = true se alterar minimo/maximo acima da trava
```

Observacao: essa regra vale para entradas/reposicoes. Para saidas elevadas, usar regra de outlier de consumo separada, porque saida alta pode representar ruptura operacional real.

### 3. Cortar Janela de Historico

Regra padrao:

- usar ultimos `janelaHistoricoDias`.
- se houver menos de `eventosMinimosParaSugerir`, ampliar para historico completo.
- eventos muito antigos entram com peso menor.

Peso sugerido:

```text
<= 365 dias: peso 1.00
366-730 dias: peso 0.70
731-1460 dias: peso 0.40
> 1460 dias: peso 0.20
```

### 4. Classificar Demanda

Calcular:

```text
eventos_consumo
quantidade_total_consumida
media_por_evento
mediana_por_evento
pico_por_evento
dias_entre_consumos
mediana_intervalo
demanda_media_diaria
demanda_media_mensal
coeficiente_variacao
```

Classificacao:

| Classe | Regra |
|---|---|
| `regular` | Intervalo mediano <= 45 dias e eventos suficientes. |
| `intermitente` | Intervalo mediano > 45 dias ou muitos periodos zerados. |
| `raro` | Menos de 3 eventos confiaveis. |
| `sem_dados` | Sem evento real. |

### 5. Calcular Lead Time

Preferencia:

1. MATA111 pedido -> MATA112 entrada.
2. Pedido em `pedidosCompra.temposRecebimento`.
3. Media por familia/grupo.
4. `leadTimePadraoDias`.

Calcular:

```text
lead_time_medio
lead_time_mediano
lead_time_p95
amostras_lead_time
```

Usar mediana como padrao, limitado por `leadTimeMaximoDias`.

### 6. Estoque de Seguranca

Para demanda regular:

```text
demanda_lead_time = demanda_media_diaria * lead_time_dias
estoque_seguranca = max(
  desvio_consumo_no_lead_time,
  demanda_lead_time * fator_variabilidade,
  pico_por_evento * fator_pico_regular
)
```

Para demanda intermitente:

```text
demanda_intermitente = mediana_por_evento / mediana_intervalo_dias
demanda_lead_time = demanda_intermitente * lead_time_dias
estoque_seguranca = max(
  mediana_por_evento,
  pico_por_evento * fator_pico_intermitente,
  demanda_lead_time
)
```

Fatores configuraveis:

```json
{
  "fatorVariabilidadeRegular": 0.8,
  "fatorPicoRegular": 0.25,
  "fatorPicoIntermitente": 0.4,
  "fatorVital": 1.4,
  "fatorEssencial": 1.15,
  "fatorBaixo": 0.75
}
```

### 7. Ponto de Reposicao

```text
ponto_reposicao = demanda_lead_time + estoque_seguranca
```

Arredondamento:

- sempre para cima.
- nunca menor que `minimoNuncaMenorQue`, se houver politica.

### 8. Lote de Reposicao

Base:

```text
lote_reposicao = max(
  mediana_quantidade_pedido,
  mediana_por_evento,
  ponto_reposicao * 0.75,
  lote_minimo_compra_do_item
)
```

Se houver `loteMultiplo`, arredondar para multiplo.

### 9. Minimo, Maximo e Reposicao

```text
minimo = ponto_reposicao
reposicao = lote_reposicao
maximo = minimo + reposicao
```

Observacao: `reposicao` deve continuar significando quantidade para voltar do minimo ao maximo.

### 10. Quantidade Sugerida Agora

O saldo atual entra somente aqui:

```text
quantidade_sugerida = maximo - saldo_atual
```

Aplicar:

- se `saldo_atual > ponto_reposicao`: quantidade sugerida = 0.
- se ha pedido aberto: quantidade sugerida = 0 ou "aguardar pedido aberto".
- se quantidade sugerida menor que lote minimo: ajustar para lote minimo.

## Confianca do Calculo

Pontuacao de 0 a 1.

Componentes sugeridos:

```text
base = 0.20
+ ate 0.25 por quantidade de eventos
+ ate 0.15 por eventos recentes
+ ate 0.15 por lead time real
+ ate 0.10 por MATA111/MATA112 casados
+ ate 0.10 por historico Cooperat recente
+ ate 0.10 por consistencia baixa de outliers
- ate 0.20 por dados antigos
- ate 0.20 por outlier dominante
- ate 0.15 por divergencia entre fontes
```

Faixas:

| Confianca | Uso |
|---|---|
| `< 0.40` | Sem politica automatica. |
| `0.40 - 0.54` | Sugerir somente como evidencia fraca. |
| `0.55 - 0.84` | Enviar ao avaliador. |
| `>= 0.85` | Pode aplicar se passar pelas travas. |

## Regras de Trava

### Travas Que Bloqueiam Aplicacao Automatica

- origem atual e `manual`.
- item esta morto/inativo.
- item tem pedido aberto.
- item tem menos eventos que `eventosMinimosParaAplicar`.
- confianca menor que `confiancaMinimaParaAplicar`.
- sugestao aumenta minimo acima de `multiplicadorAumentoRevisao`.
- sugestao reduz minimo abaixo de `multiplicadorReducaoRevisao`.
- outlier domina mais de 50% da politica.
- entrada elevada fora do padrao aumenta minimo/maximo acima da trava.
- item sem codigo confiavel.
- item esta sem endereco valido e regra global bloqueia.

### Travas Que Enviam Para Avaliador

- aumento maior que limite automatico.
- reducao maior que limite automatico.
- divergencia forte entre Cooperat, MATA111 e historico real.
- demanda rara com item vital.
- historico antigo forte, mas sem movimento recente.
- pico historico relevante.
- entrada elevada possivelmente preventiva.
- saldo atual zerado com item essencial/vital.

## Decisoes Possiveis

| Decisao | Significado |
|---|---|
| `aplicar_politica` | Pode aplicar minimo/maximo/reposicao automaticamente. |
| `sugerir_politica` | Enviar para avaliador aprovar. |
| `critico_solicitar_agora` | Saldo atual abaixo do ponto de reposicao e sem pedido aberto. |
| `alto_solicitar` | Risco alto, mas nao emergencial. |
| `monitorar` | Nao solicitar agora, acompanhar. |
| `aguardar_pedido_aberto` | Ja existe fluxo de compra/entrada. |
| `revisar_politica` | Dados indicam mudanca sensivel. Precisa humano. |
| `dados_insuficientes` | Nao ha base para politica confiavel. |
| `nao_solicitar` | Nao ha necessidade operacional agora. |
| `excesso_estoque` | Saldo atual acima do maximo calculado. |
| `bloqueado_manual` | Item protegido por ajuste manual. |
| `bloqueado_obsoleto` | Item morto/obsoleto/inativo. |

## Strings de Explicacao

As strings devem ser montadas por codigos, nao por texto solto no meio do calculo. O motor retorna `reasonCodes`; a UI traduz.

### Codigos de Motivo

```json
{
  "saldo_abaixo_ponto_reposicao": "Saldo atual abaixo do ponto de reposicao calculado.",
  "saldo_acima_maximo": "Saldo atual acima do maximo calculado.",
  "sem_pedido_aberto": "Nao ha pedido ou solicitacao aberta para este item.",
  "pedido_aberto_detectado": "Existe pedido, solicitacao ou entrada em andamento.",
  "historico_consumo_forte": "Historico de consumo/requisicao suficiente para politica automatica.",
  "historico_consumo_fraco": "Historico pequeno; calculo exige revisao.",
  "demanda_intermitente": "Demanda intermitente detectada; politica usa intervalo entre consumos.",
  "demanda_regular": "Demanda regular detectada; politica usa media e lead time.",
  "lead_time_real": "Lead time calculado por pedidos e entradas reais.",
  "lead_time_padrao": "Lead time padrao usado por falta de amostras confiaveis.",
  "lote_compra_recente": "Lote de reposicao baseado em pedidos recentes.",
  "outlier_detectado": "Pico historico detectado; aplicacao automatica bloqueada.",
  "entrada_elevada_fora_padrao": "Entrada elevada fora do padrao detectada; nao foi usada para inflar minimo automaticamente.",
  "entrada_preventiva_possivel": "Entrada pode ter vindo maior por preventiva, lote minimo ou compra programada.",
  "aumento_acima_limite": "Aumento sugerido acima da trava global; requer avaliador.",
  "reducao_acima_limite": "Reducao sugerida acima da trava global; requer avaliador.",
  "manual_tem_prioridade": "Limite manual existente tem prioridade sobre o motor.",
  "avaliador_tem_prioridade": "Decisao anterior do avaliador tem prioridade.",
  "cooperat_usado_fallback": "Limite Cooperat usado como referencia/fallback.",
  "saldo_inicial_ignorado": "Saldo inicial e saldo anterior nao foram usados no aprendizado.",
  "item_morto_bloqueado": "Item morto/inativo nao gera reposicao.",
  "codigo_inconsistente": "Codigo do item nao permitiu cruzamento confiavel entre fontes.",
  "dados_insuficientes": "Dados insuficientes para politica automatica confiavel."
}
```

### Templates de Explicacao Para Avaliador

```text
Politica sugerida: minimo {minimo}, maximo {maximo}, reposicao {reposicao}. Base: {eventosConsumo} evento(s), lead time {leadTimeDias} dia(s), confianca {confiancaPercentual}%.
```

```text
Solicitar agora: saldo atual {saldoAtual} abaixo do ponto de reposicao {pontoReposicao}. Quantidade sugerida: {quantidadeSugerida}.
```

```text
Aguardar: ja existe fluxo aberto ({statusPedido}). O motor nao cria nova sugestao enquanto o pedido estiver em andamento.
```

```text
Revisar politica: a sugestao altera o minimo de {minimoAtual} para {minimoSugerido}, acima da trava configurada. Requer aprovacao no avaliador.
```

```text
Entrada elevada ignorada no aprendizado: houve entrada de {quantidadeEntrada} unidade(s), acima do padrao historico. Ela pode indicar preventiva ou lote especial, entao nao aumentou o minimo automaticamente.
```

```text
Sem politica automatica: foram encontrados apenas {eventosConsumo} evento(s) confiavel(is), abaixo do minimo configurado.
```

```text
Protegido por ajuste manual: o motor calculou {minimoSugerido}/{maximoSugerido}/{reposicaoSugerida}, mas manteve {minimoAtual}/{maximoAtual}/{reposicaoAtual}.
```

## Saida Padrao do Motor

```json
{
  "itemKey": "3101001141",
  "codigoProtheus": "3101001141",
  "codigoCooperat": "124881",
  "algoritmoVersao": "critical_stock_v1",
  "modoAplicacao": "sombra",
  "autoridadeAplicada": "motor_critico",
  "politicaAtual": {
    "minimo": 5,
    "maximo": 15,
    "reposicao": 10,
    "origem": "cooperat"
  },
  "politicaSugerida": {
    "minimo": 9,
    "maximo": 19,
    "reposicao": 10,
    "pontoReposicao": 9
  },
  "estadoAtual": {
    "saldoAtual": 2,
    "pedidoAberto": false,
    "statusPedido": "sem"
  },
  "metricas": {
    "eventosConsumo": 246,
    "demandaClasse": "regular",
    "leadTimeDias": 6,
    "leadTimeAmostras": 4,
    "medianaConsumoEvento": 1,
    "picoConsumoEvento": 15,
    "quantidadeSugerida": 17,
    "riscoRuptura": 0.88,
    "riscoExcesso": 0.12,
    "confianca": 0.9
  },
  "decisao": "critico_solicitar_agora",
  "aplicavelAutomaticamente": false,
  "reasonCodes": [
    "saldo_abaixo_ponto_reposicao",
    "historico_consumo_forte",
    "lead_time_real",
    "sem_pedido_aberto",
    "saldo_inicial_ignorado"
  ],
  "travas": [],
  "dadosIgnorados": [
    "saldo_inicial",
    "saldo_anterior_estoque_minimo"
  ]
}
```

## Integracao Com Avaliador

O avaliador deve usar o motor como fonte de triagem, nao recalcular politica no browser.

### Fila do Avaliador

Ordenacao sugerida:

```text
risco_ruptura desc
criticidade desc
dias_abaixo_ponto desc
deficit_reposicao desc
confianca desc
```

### Acoes do Avaliador

| Acao | Efeito |
|---|---|
| `aprovar_politica` | Grava politica sugerida como decisao do avaliador. |
| `aplicar_manual` | Cria ajuste manual e trava item. |
| `solicitar_reposicao` | Marca como passivel/solicitar e entra no kanban. |
| `adiar` | Nao solicita agora; reavaliar depois. |
| `nao_solicitar` | Bloqueia sugestao ate novo evento relevante. |
| `marcar_outlier` | Remove evento/pico do calculo futuro ou reduz peso. |
| `alterar_criticidade` | Atualiza politica do item. |

## Persistencia Recomendada

### `critical_stock_policies`

Guarda parametros por item.

Campos:

- `id`
- `item_id`
- `item_legacy_key`
- `criticidade`
- `nivel_servico`
- `lead_time_manual_dias`
- `lote_minimo_compra`
- `lote_multiplo`
- `permitir_ajuste_automatico`
- `permitir_reducao_automatica`
- `permitir_aumento_automatico`
- `raw_data`
- `updated_at`
- `updated_by`

### `critical_stock_assessments`

Guarda cada calculo.

Campos:

- `id`
- `item_id`
- `item_legacy_key`
- `algorithm_version`
- `calculated_at`
- `mode`
- `decision`
- `confidence`
- `risk_stockout`
- `risk_excess`
- `current_min_qty`
- `current_max_qty`
- `current_reorder_qty`
- `suggested_min_qty`
- `suggested_max_qty`
- `suggested_reorder_qty`
- `suggested_order_qty`
- `authority_applied`
- `reason_codes`
- `locks`
- `raw_metrics`
- `raw_data`

### `critical_stock_decision_events`

Guarda acoes humanas e aplicacoes automaticas.

Campos:

- `id`
- `assessment_id`
- `item_id`
- `action`
- `previous_policy`
- `new_policy`
- `reason`
- `created_at`
- `created_by`
- `raw_data`

## Endpoints Recomendados

```http
GET /api/inventory/critical-stock/assessments?limit=100&status=critico
GET /api/inventory/{codigo}/critical-stock
POST /api/inventory/critical-stock/recalculate
PUT /api/inventory/{codigo}/critical-stock/policy
POST /api/inventory/{codigo}/critical-stock/decision
```

## Regras de Backtest

Antes de aplicar em producao:

1. Rodar em modo `sombra`.
2. Comparar politica atual vs politica sugerida.
3. Medir quantos itens seriam:
   - aumentados
   - reduzidos
   - enviados ao avaliador
   - bloqueados por dados insuficientes
   - bloqueados por pedido aberto
4. Separar top 50 maiores aumentos para revisao.
5. Separar top 50 maiores reducoes para revisao.
6. Confirmar que nenhum item manual foi alterado.
7. Confirmar que saldo inicial nao apareceu em metricas de demanda.

## Checklist Antes de Codar

- [ ] Criar configuracao global do motor.
- [ ] Criar parametros por item.
- [ ] Criar funcao pura de calculo sem dependencia de DOM/browser.
- [ ] Criar persistencia de assessment.
- [ ] Criar endpoint de recalculo em modo sombra.
- [ ] Adaptar dashboard para consumir assessment.
- [ ] Remover calculo duplicado de minimo do front somente depois de validar.
- [ ] Criar backtest com relatorio de impacto.
- [ ] Criar logs de auditoria.
- [ ] Criar migracao SQL das novas tabelas.

## Regra Final

O gerenciador nao deve "mandar comprar". Ele deve:

1. calcular politica;
2. explicar o calculo;
3. respeitar travas;
4. enviar duvidas ao avaliador;
5. registrar tudo.

Compra, mudanca agressiva de politica e excecao operacional continuam passando pelo controle humano.
