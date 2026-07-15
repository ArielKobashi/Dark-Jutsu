import os
import runpy
import sys
import traceback


SHARE_STATUS = r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\status_compartilhado_servidores_darkjutsu.py"


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    local_status = os.path.join(base, "status_compartilhado_servidores_darkjutsu.py")
    status_script = local_status if os.path.exists(local_status) else SHARE_STATUS
    print("")
    print("Abrindo status Dark-Jutsu...")
    print("")
    try:
        sys.argv = [status_script]
        runpy.run_path(status_script, run_name="__main__")
    except Exception:
        print("")
        print("ERRO ao abrir status Dark-Jutsu:")
        traceback.print_exc()
    print("")
    try:
        input("Pressione ENTER para fechar...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
