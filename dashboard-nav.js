(function(){
    function abrirDashboard(){
        window.location.href = "dashboard.html";
    }

    function executarComando(valor){
        var comando = String(valor || "").toLowerCase().trim();
        return ["/dashboard", "dashboard", "dash"].indexOf(comando) !== -1;
    }

    window.abrirDashboard = window.abrirDashboard || abrirDashboard;
    window.executarComandoDashboardBusca = window.executarComandoDashboardBusca || function(valor){
        if(!executarComando(valor)) return false;
        var input = document.getElementById("searchInput");
        if(input) input.value = "";
        abrirDashboard();
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
