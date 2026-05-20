# Atualizacao Automus

Estrutura consolidada da atualizacao automatica (sem interferir na sessao aberta do navegador):

- `automus_update.py`: rotina principal (Firebase + backup + validacoes).
- `automus_config.json`: credenciais locais (ignorado no git).
- `automus_config.json.example`: modelo de configuracao.
- `__main__.py`: entrada para execucao como modulo.
- `executar_automus.bat`: disparo manual direto do Automus.

Fluxo padrao (com macros):
1) `scripts/executar_tudo.py` roda macros `001..005`.
2) prepara `incluir.xlsx`, `Saldo Atual.xlsx`, `Saldo por Endereco.xlsx`.
3) chama `atualizacao.automus_update` para atualizar `estoqueGlobal`.

Compatibilidade:
- `scripts/automus_update.py` foi mantido como wrapper.
