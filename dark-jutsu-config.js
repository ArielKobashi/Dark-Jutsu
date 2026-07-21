// Configuracao unica dos enderecos do Dark-Jutsu.
// Quando o servidor principal mudar, edite este arquivo.
(function(){
    const port = "8765";
    const principal = "192.168.5.44";
    const reservas = [
        "192.168.5.38"
    ];
    const extras = [
        "192.168.5.41"
    ];

    function hostUrl(host){
        return `http://${host}:${port}`;
    }

    window.DARK_JUTSU_CONFIG = {
        apiPort: port,
        apiPrincipalHost: principal,
        apiReservaHosts: reservas.slice(),
        apiExtraHosts: extras.slice(),
        apiPrincipalBaseUrl: hostUrl(principal),
        apiFallbackBaseUrls: [
            hostUrl(principal),
            ...reservas.map(hostUrl),
            ...extras.map(hostUrl)
        ]
    };

    window.DARK_JUTSU_API_BASE_URL = window.DARK_JUTSU_CONFIG.apiPrincipalBaseUrl;
})();
