Dark-Jutsu - scripts padronizados do servidor

Use estes comandos daqui para frente:

instalar-tudo.bat
  Instala ou atualiza guardiao, monitor e autoatualizacao para o usuario atual.

instalar-monitor.bat
  Atualiza e reabre somente o icone do monitor.
  O monitor inclui o Infinity, que move o mouse 1px e retorna a cada 2m30s para manter a tela ativa.
  Para parar: clique com o botao direito no icone do monitor, escolha "Parar Infinity" e use a senha 123456789.

reiniciar-guardiao.bat
  Remove a tarefa antiga do guardiao, reinstala a rotina e cria fallback no Inicializar se a tarefa agendada for bloqueada.

testar-servidor.bat
  Mostra um diagnostico legivel do servidor principal e da reserva.

verificar-iniciar.bat
  Executa uma rodada do guardiao: se nenhum servidor estiver ativo, inicia este PC quando ele for principal/reserva.

tornar-principal.bat
  Faz este PC assumir a API local.

tornar-reserva.bat
  Para a API local e pausa a principal por alguns minutos para a reserva assumir.

parar-servidor-local.bat
  Para somente a API local deste PC.

Os aliases antigos foram removidos. Use o instalador unico para recriar inicializacao automatica.
