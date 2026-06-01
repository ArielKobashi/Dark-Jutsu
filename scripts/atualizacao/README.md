# Atualizacao Automus

Estrutura consolidada da atualizacao automatica (sem interferir na sessao aberta do navegador):

- `automus_update.py`: rotina principal (Firebase + backup + validacoes).
- `automus_config.json`: credenciais locais (ignorado no git).
- `automus_config.enc.json`: credenciais criptografadas geradas no build do exe.
- `automus_config.json.example`: modelo de configuracao.
- `__main__.py`: entrada para execucao como modulo.
- `executar_automus.bat`: disparo manual direto do Automus.

Fluxo padrao (com macros):
1) `scripts/executar_tudo.py` roda macros `001..005`.
2) prepara `incluir.xlsx`, `Saldo Atual.xlsx`, `Saldo por Endereco.xlsx`.
3) se existir, também prepara `estoque_minimo.xlsx` para enriquecer mínimo/máximo/reposição.
4) chama `atualizacao.automus_update` para atualizar `estoqueGlobal`.

Compatibilidade:
- `scripts/automus_update.py` foi mantido como wrapper.

Build do exe:
- O `build_automus_exe.py` le `automus_config.json` local e grava `automus_config.enc.json` apenas na area de stage do pacote.
- O exe nao leva a senha em texto puro, mas consegue renovar a sessao Firebase quando o token ADM expirar.
