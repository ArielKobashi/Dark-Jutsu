from pathlib import Path

from pynput import keyboard, mouse  # type: ignore

from controladordeatualização import ExecutionController, StopRequested, sleep_with_controls

# Macro 6: envio das 3 planilhas e clique em "Atualizar Banco".
# Ajuste os pontos abaixo se o layout/tamanho de tela mudar.
BTN_INCLUIR = (130, 157)
BTN_SALDO_ATUAL = (130, 205)
BTN_SALDO_ENDERECO = (130, 252)
BTN_ATUALIZAR_BANCO = (130, 318)

# Campo "Nome:" do dialogo de arquivo.
DIALOG_NAME_FIELD = (210, 610)

# Se True, envia Alt+Tab uma vez no inicio para trocar para o navegador.
ACTIVATE_DARK_JUTSU_WITH_ALT_TAB = True


def _check_stop(controller: ExecutionController):
    controller.poll_keypress()
    controller.wait_if_paused()
    if controller.stop_requested:
        controller.close()
        raise StopRequested(controller.get_stop_message())


def _sleep(seconds: float, controller: ExecutionController):
    if seconds <= 0:
        return
    if not sleep_with_controls(seconds, controller):
        controller.close()
        raise StopRequested(controller.get_stop_message())


def _click(m: mouse.Controller, controller: ExecutionController, x: int, y: int):
    _check_stop(controller)
    controller.set_locked_mouse_position(x, y)
    m.position = (x, y)
    m.press(mouse.Button.left)
    m.release(mouse.Button.left)


def _press_combo(k: keyboard.Controller, *keys):
    for key in keys:
        k.press(key)
    for key in reversed(keys):
        k.release(key)


def _type_path_on_dialog(k: keyboard.Controller, controller: ExecutionController, file_path: Path):
    _check_stop(controller)
    # Seleciona todo o valor atual do campo "Nome:".
    _press_combo(k, keyboard.Key.ctrl, "a")
    _sleep(0.08, controller)
    k.type(str(file_path))
    _sleep(0.08, controller)
    k.press(keyboard.Key.enter)
    k.release(keyboard.Key.enter)


def _resolve_target_file(base: Path, filename: str) -> Path:
    candidates = [
        base.parent / "downloads" / filename,
        Path.home() / "Desktop" / filename,
        Path.home() / "Downloads" / filename,
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    raise FileNotFoundError(f"Arquivo nao encontrado para envio: {filename}")


def _attach_file(
    m: mouse.Controller,
    k: keyboard.Controller,
    controller: ExecutionController,
    button_xy: tuple[int, int],
    file_path: Path,
):
    _click(m, controller, button_xy[0], button_xy[1])   # abre seletor de arquivo
    _sleep(0.9, controller)
    _click(m, controller, DIALOG_NAME_FIELD[0], DIALOG_NAME_FIELD[1])  # foca campo Nome:
    _sleep(0.15, controller)
    _type_path_on_dialog(k, controller, file_path)      # envia caminho completo + Enter
    _sleep(1.2, controller)


def play():
    m = mouse.Controller()
    k = keyboard.Controller()
    controller = ExecutionController()
    controller.set_macro_context(__name__, 6)

    try:
        base = Path(__file__).resolve().parent

        incluir = _resolve_target_file(base, "incluir.xlsx")
        saldo_atual = _resolve_target_file(base, "Saldo Atual.xlsx")
        saldo_endereco = _resolve_target_file(base, "Saldo por Endereco.xlsx")

        if ACTIVATE_DARK_JUTSU_WITH_ALT_TAB:
            _check_stop(controller)
            k.press(keyboard.Key.alt_l)
            k.press(keyboard.Key.tab)
            k.release(keyboard.Key.tab)
            k.release(keyboard.Key.alt_l)
            _sleep(0.8, controller)

        _attach_file(m, k, controller, BTN_INCLUIR, incluir)
        _attach_file(m, k, controller, BTN_SALDO_ATUAL, saldo_atual)
        _attach_file(m, k, controller, BTN_SALDO_ENDERECO, saldo_endereco)

        # Dispara atualização final no banco.
        _click(m, controller, BTN_ATUALIZAR_BANCO[0], BTN_ATUALIZAR_BANCO[1])
        _sleep(2.0, controller)
    finally:
        controller.close()


if __name__ == "__main__":
    play()
