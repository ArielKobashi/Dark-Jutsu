(function(){
    function abrirDashboard(){
        window.location.href = "dashboard.html?armazem=04";
    }
    function abrirAvaliadorPedidos(){
        window.location.href = "dashboard.html?ambiente=avaliador&armazem=04&status=abaixo&limite=50";
    }

    function executarComando(valor){
        var comando = String(valor || "").toLowerCase().trim();
        if(["/avaliador", "avaliador", "pedidos", "/pedidos"].indexOf(comando) !== -1) return "avaliador";
        return ["/dashboard", "dashboard", "dash"].indexOf(comando) !== -1 ? "dashboard" : "";
    }

    window.abrirDashboard = window.abrirDashboard || abrirDashboard;
    window.abrirAvaliadorPedidos = window.abrirAvaliadorPedidos || abrirAvaliadorPedidos;
    window.executarComandoDashboardBusca = window.executarComandoDashboardBusca || function(valor){
        var destino = executarComando(valor);
        if(!destino) return false;
        var input = document.getElementById("searchInput");
        if(input) input.value = "";
        if(destino === "avaliador") abrirAvaliadorPedidos();
        else abrirDashboard();
        return true;
    };

    document.addEventListener("DOMContentLoaded", function(){
        var input = document.getElementById("searchInput");
        if(input){
            input.addEventListener("input", function(e){
                if(window.executarComandoDashboardBusca(input.value)){
                    e.stopImmediatePropagation();
                }
            });
        }

        document.addEventListener("keydown", function(e){
            if(e.ctrlKey && e.altKey && (e.key === "d" || e.key === "D")){
                e.preventDefault();
                abrirDashboard();
            }
        });
    });
})();
