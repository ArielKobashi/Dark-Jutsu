(function(){
    "use strict";

    const DEFAULT_CONFIG = {
        algorithmVersion: "critical_stock_v1_front_test",
        minEventsToSuggest: 3,
        minEventsToApply: 8,
        defaultLeadTimeDays: 30,
        maxLeadTimeDays: 120,
        confidenceToApply: 0.85,
        highIncreaseMultiplier: 3,
        highReductionMultiplier: 0.4,
        elevatedEntryMultiplier: 3,
        regularIntervalDays: 45,
        minStockFloor: 1
    };

    function numberValue(value){
        if(value === null || value === undefined || value === "") return null;
        if(typeof value === "number") return Number.isFinite(value) ? value : null;
        const normalized = String(value).trim().replace(/\./g, "").replace(",", ".");
        if(!normalized) return null;
        const parsed = Number(normalized);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function ceilPositive(value){
        const parsed = numberValue(value);
        if(parsed === null || parsed <= 0) return null;
        return Math.max(1, Math.ceil(parsed));
    }

    function average(values){
        return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
    }

    function median(values){
        if(!values.length) return null;
        const sorted = values.slice().sort((a, b) => a - b);
        const mid = Math.floor(sorted.length / 2);
        return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
    }

    function stddev(values){
        if(values.length < 2) return 0;
        const avg = average(values);
        return Math.sqrt(average(values.map(value => Math.pow(value - avg, 2))));
    }

    function percentile(values, ratio){
        if(!values.length) return null;
        const sorted = values.slice().sort((a, b) => a - b);
        const idx = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * ratio) - 1));
        return sorted[idx];
    }

    function eventsFromHistory(history){
        return (Array.isArray(history) ? history : [])
            .map(event => {
                const delta = numberValue(event?.delta);
                const timestamp = Number(event?.timestamp || 0);
                return {
                    delta,
                    quantity: delta === null ? null : Math.abs(delta),
                    timestamp: Number.isFinite(timestamp) ? timestamp : 0,
                    type: String(event?.tipo || event?.event_type || "").toLowerCase(),
                    raw: event
                };
            })
            .filter(event => event.delta !== null && event.quantity > 0);
    }

    function purchaseQuantities(purchaseOrder){
        const quantities = [
            purchaseOrder?.mediaPedido,
            purchaseOrder?.ultimoPedido?.quantidadeRecebida,
            purchaseOrder?.ultimoPedido?.quantidadePedida,
            purchaseOrder?.pedido?.quantidadePedida,
            purchaseOrder?.pedido?.quantidadeRecebida,
            purchaseOrder?.solicitacao?.quantidadeSolicitada,
            purchaseOrder?.solicitacao?.quantidadeEmPedido
        ].map(numberValue).filter(value => value !== null && value > 0);
        return quantities;
    }

    function leadTimeDays(purchaseOrder, config){
        const samples = Array.isArray(purchaseOrder?.temposRecebimento)
            ? purchaseOrder.temposRecebimento
                .map(item => numberValue(item?.dias))
                .filter(value => value !== null && value >= 0)
            : [];
        const lead = median(samples) ?? numberValue(purchaseOrder?.mediaDiasRecebimento) ?? config.defaultLeadTimeDays;
        return Math.min(config.maxLeadTimeDays, Math.max(1, lead));
    }

    function hasOpenPurchase(purchaseOrder){
        const status = String(purchaseOrder?.status || "").toLowerCase();
        if(!status || status === "sem") return false;
        if(["finalizado", "encerrado", "entregue"].includes(status)) return false;
        return !!(
            status.startsWith("aguardando") ||
            purchaseOrder?.solicitacao ||
            purchaseOrder?.pedido ||
            purchaseOrder?.entradaEndereco ||
            Number(purchaseOrder?.recebidoSemEntrada || 0) > 0
        );
    }

    function detectElevatedEntries(entries, demandQuantities, purchaseQty){
        const entryQuantities = entries.map(event => event.quantity).filter(value => value > 0);
        if(!entryQuantities.length) return { detected:false, maxEntry:0, threshold:null };
        const entryMedian = median(entryQuantities) || 0;
        const demandMedian = median(demandQuantities) || 0;
        const p90 = percentile(entryQuantities, 0.9) || 0;
        const base = Math.max(entryMedian, demandMedian, purchaseQty || 0, 1);
        const threshold = Math.max(base * DEFAULT_CONFIG.elevatedEntryMultiplier, p90);
        const maxEntry = Math.max(...entryQuantities);
        return {
            detected: maxEntry >= threshold && entryQuantities.length >= 3,
            maxEntry,
            threshold
        };
    }

    function calculateItemPolicy(item, options = {}){
        const config = { ...DEFAULT_CONFIG, ...(options.config || {}) };
        const historyEvents = eventsFromHistory(options.history);
        const consumption = historyEvents.filter(event => event.delta < 0);
        const entries = historyEvents.filter(event => event.delta > 0);
        const quantities = consumption.map(event => event.quantity).filter(value => value > 0);
        const purchaseOrder = options.purchaseOrder || null;
        const purchaseQtys = purchaseQuantities(purchaseOrder);
        const purchaseQty = median(purchaseQtys) || 0;
        const lead = leadTimeDays(purchaseOrder, config);
        const openPurchase = hasOpenPurchase(purchaseOrder);
        const reasonCodes = ["saldo_inicial_ignorado"];
        const locks = [];

        if(!quantities.length && purchaseQty > 0){
            quantities.push(purchaseQty);
            reasonCodes.push("lote_compra_recente");
        }

        if(quantities.length < config.minEventsToSuggest && !purchaseQty){
            return null;
        }

        const avg = average(quantities);
        const med = median(quantities) || avg || purchaseQty || 1;
        const peak = quantities.length ? Math.max(...quantities) : purchaseQty;
        const deviation = stddev(quantities);
        const timestamps = consumption
            .map(event => event.timestamp)
            .filter(Boolean)
            .sort((a, b) => a - b);
        const intervals = [];
        for(let i = 1; i < timestamps.length; i++){
            const days = (timestamps[i] - timestamps[i - 1]) / 86400000;
            if(days > 0) intervals.push(days);
        }
        const medianInterval = median(intervals);
        const demandClass = !quantities.length
            ? "sem_dados"
            : (medianInterval !== null && medianInterval <= config.regularIntervalDays && quantities.length >= config.minEventsToSuggest ? "regular" : "intermitente");
        const dailyDemand = demandClass === "regular"
            ? avg / Math.max(1, medianInterval || 30)
            : med / Math.max(1, medianInterval || config.defaultLeadTimeDays);
        const leadDemand = dailyDemand * lead;
        const safety = Math.max(
            med,
            leadDemand * 0.8,
            peak * (demandClass === "intermitente" ? 0.4 : 0.25),
            deviation
        );
        const point = ceilPositive(Math.max(leadDemand + safety, demandClass === "regular" ? avg : med, config.minStockFloor));
        if(point === null) return null;

        const elevatedEntry = detectElevatedEntries(entries, quantities, purchaseQty);
        if(elevatedEntry.detected){
            reasonCodes.push("entrada_elevada_fora_padrao", "entrada_preventiva_possivel");
            locks.push("entrada_elevada_fora_padrao");
        }

        const reorder = ceilPositive(Math.max(purchaseQty, med, point * 0.75)) || point;
        const max = Math.max(point + reorder, point + 1);
        const currentMin = numberValue(item?.minimo);
        const currentMax = numberValue(item?.maximo);
        const currentReorder = numberValue(item?.reposicao);
        const balance = numberValue(item?.saldo) ?? 0;
        const suggestedOrderQty = balance <= point ? Math.max(0, max - balance) : 0;
        const confidence = Math.min(0.95,
            0.2 +
            Math.min(0.25, quantities.length / 10 * 0.25) +
            (purchaseQty ? 0.15 : 0) +
            (Array.isArray(purchaseOrder?.temposRecebimento) && purchaseOrder.temposRecebimento.length ? 0.15 : 0) +
            (timestamps.length ? 0.1 : 0)
        );

        if(quantities.length >= config.minEventsToApply){
            reasonCodes.push("historico_consumo_forte");
        }else{
            reasonCodes.push("historico_consumo_fraco");
        }
        reasonCodes.push(demandClass === "regular" ? "demanda_regular" : "demanda_intermitente");
        reasonCodes.push(Array.isArray(purchaseOrder?.temposRecebimento) && purchaseOrder.temposRecebimento.length ? "lead_time_real" : "lead_time_padrao");
        reasonCodes.push(openPurchase ? "pedido_aberto_detectado" : "sem_pedido_aberto");
        if(balance <= point) reasonCodes.push("saldo_abaixo_ponto_reposicao");
        if(currentMin !== null && point > currentMin * config.highIncreaseMultiplier) locks.push("aumento_acima_limite");
        if(currentMin !== null && point < currentMin * config.highReductionMultiplier) locks.push("reducao_acima_limite");
        if(openPurchase) locks.push("pedido_aberto_detectado");
        if(confidence < config.confidenceToApply) locks.push("confianca_baixa");

        const decision = openPurchase
            ? "aguardar_pedido_aberto"
            : balance <= point
                ? (confidence >= 0.75 ? "critico_solicitar_agora" : "sugerir_politica")
                : balance > max
                    ? "excesso_estoque"
                    : "monitorar";

        return {
            minimo: point,
            maximo: max,
            reposicao: max - point,
            criterio: {
                algoritmoVersao: config.algorithmVersion,
                decisao: decision,
                confianca: confidence,
                demandaClasse: demandClass,
                eventosConsumo: quantities.length,
                consumoMedio: avg,
                consumoMediano: med,
                consumoPico: peak,
                desvioConsumo: deviation,
                intervaloMedianoDias: medianInterval,
                leadTimeDias: lead,
                pontoReposicao: point,
                minimoSugerido: point,
                maximoSugerido: max,
                reposicaoSugerida: max - point,
                quantidadeSugerida: suggestedOrderQty,
                pedidoAberto: openPurchase,
                entradaElevadaForaPadrao: elevatedEntry.detected,
                maiorEntrada: elevatedEntry.maxEntry,
                limiteEntradaElevada: elevatedEntry.threshold,
                minimoAtual: currentMin,
                maximoAtual: currentMax,
                reposicaoAtual: currentReorder,
                reasonCodes,
                travas: [...new Set(locks)],
                dadosIgnorados: ["saldo_inicial", "saldo_anterior_estoque_minimo"]
            }
        };
    }

    function protectedSource(item){
        const source = String(item?.limitesOrigem || item?.minimoOrigem || item?.maximoOrigem || item?.reposicaoOrigem || "").toLowerCase();
        return source.includes("manual") || source.includes("cooperat");
    }

    function applyPolicy(item, options = {}){
        if(!item) return item;
        const policy = calculateItemPolicy(item, options);
        delete item.sugestaoEstoqueLegada;
        if(!policy){
            if(item.limitesOrigem === "automatico" || item.limitesOrigem === "gerenciador_critico"){
                delete item.minimo;
                delete item.maximo;
                delete item.reposicao;
                delete item.minimoOrigem;
                delete item.maximoOrigem;
                delete item.reposicaoOrigem;
                delete item.limitesOrigem;
            }
            delete item.sugestaoEstoque;
            delete item.gerenciadorEstoqueCritico;
            return item;
        }

        item.gerenciadorEstoqueCritico = policy.criterio;
        item.sugestaoEstoque = policy.criterio;

        if(protectedSource(item)){
            policy.criterio.reasonCodes = [...new Set([...(policy.criterio.reasonCodes || []), "manual_ou_cooperat_tem_prioridade"])];
            return item;
        }

        const shouldApplyMin = item.minimo === undefined || item.minimo === null || item.minimo === "" || item.minimoOrigem === "automatico" || item.limitesOrigem === "automatico" || item.limitesOrigem === "gerenciador_critico";
        const shouldApplyMax = item.maximo === undefined || item.maximo === null || item.maximo === "" || item.maximoOrigem === "automatico" || item.limitesOrigem === "automatico" || item.limitesOrigem === "gerenciador_critico";
        if(shouldApplyMin){
            item.minimo = policy.minimo;
            item.minimoOrigem = "gerenciador_critico";
            item.limitesOrigem = item.limitesOrigem || "gerenciador_critico";
        }
        if(shouldApplyMax){
            item.maximo = policy.maximo;
            item.maximoOrigem = "gerenciador_critico";
            item.limitesOrigem = item.limitesOrigem || "gerenciador_critico";
        }
        item.reposicao = policy.reposicao;
        item.reposicaoOrigem = item.limitesOrigem || "gerenciador_critico";
        return item;
    }

    window.DarkCriticalStockManager = {
        DEFAULT_CONFIG,
        calculateItemPolicy,
        applyPolicy,
        numberValue,
        ceilPositive
    };
})();
