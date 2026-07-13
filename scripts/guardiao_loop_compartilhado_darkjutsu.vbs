Set shell = CreateObject("WScript.Shell")

shareScripts = "\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts"

Do
  shell.Run "cmd /c """ & shareScripts & "\verificar_atualizar_instalacao_local_darkjutsu.bat""", 0, True
  shell.Run "cmd /c """ & shareScripts & "\guardiao_servidor_tick_darkjutsu.bat""", 0, True
  shell.Run "cmd /c """ & shareScripts & "\atualizar_darkjutsu_do_github.bat""", 0, False
  WScript.Sleep 60000
Loop
