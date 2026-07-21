const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const context = { window: {} };
vm.createContext(context);
vm.runInContext(fs.readFileSync("critical-stock-manager.js", "utf8"), context);
const manager = context.window.DarkCriticalStockManager;

function consumptionHistory(count, quantity = 5) {
    return Array.from({ length: count }, (_, index) => ({
        delta: -quantity,
        tipo: "saida",
        timestamp: Date.UTC(2026, 0, 1 + index * 30)
    }));
}

assert.equal(
    manager.calculateItemPolicy(
        { saldo: 0 },
        { history: [], purchaseOrder: { mediaPedido: 100 } }
    ),
    null,
    "compra sem historico de saida nao pode virar consumo"
);

const cooperat = {
    saldo: 0,
    minimo: 4,
    maximo: 10,
    reposicao: 6,
    limitesOrigem: "cooperat"
};
manager.applyPolicy(cooperat, {
    history: consumptionHistory(10),
    config: { modoAplicacao: "auto_controlado", confidenceToApply: 0.5, minEventsToApply: 3 }
});
assert.deepEqual(
    [cooperat.minimo, cooperat.maximo, cooperat.reposicao, cooperat.limitesOrigem],
    [4, 10, 6, "cooperat"],
    "a politica Cooperat e imutavel para o gerenciador"
);
assert.ok(cooperat.gerenciadorEstoqueCritico?.algoritmoVersao);

const shadow = { saldo: 0 };
manager.applyPolicy(shadow, { history: consumptionHistory(10) });
assert.equal(shadow.minimo, undefined, "modo sombra nao aplica limite");
assert.ok(shadow.gerenciadorEstoqueCritico?.algoritmoVersao);

const automatic = { saldo: 0 };
manager.applyPolicy(automatic, {
    history: consumptionHistory(10),
    config: { modoAplicacao: "auto_controlado", confidenceToApply: 0.5, minEventsToApply: 3 }
});
assert.ok(automatic.minimo > 0, "modo automatico aplica politica com evidencia suficiente");
assert.equal(automatic.limitesOrigem, "gerenciador_critico");

const legacy = {
    saldo: 2,
    minimo: 9,
    maximo: 20,
    reposicao: 11,
    limitesOrigem: "automatico",
    sugestaoEstoque: { fonte: "automus_antigo" }
};
manager.applyPolicy(legacy, { history: [] });
assert.equal(legacy.minimo, undefined, "politica automatica antiga deve ser removida");
assert.equal(legacy.sugestaoEstoque, undefined);

console.log("critical-stock-manager: 5 cenarios validados");

const dashboard = fs.readFileSync("dashboard.html", "utf8");
const moduleMatch = dashboard.match(/<script type="module">([\s\S]*?)<\/script>/);
assert.ok(moduleMatch, "script principal do dashboard deve existir");
new vm.SourceTextModule(moduleMatch[1], { context: vm.createContext({}) });
console.log("dashboard: sintaxe do modulo validada");
