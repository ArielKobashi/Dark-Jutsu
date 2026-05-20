# Atualizacao Automus

Arquivos da rotina de atualizacao automatica (sem interferir na sessao do navegador):

- automus_update.py: envia planilhas para o Firebase com backup e validacoes.
- automus_config.json: credenciais locais (ignorado no git).
- automus_config.json.example: modelo de configuracao.

Fluxo:
1) executar_tudo.py roda macros 001..005
2) prepara incluir.xlsx / Saldo Atual.xlsx / Saldo por Endereco.xlsx
3) chama Automus para atualizar estoqueGlobal
