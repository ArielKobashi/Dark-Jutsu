import ctypes
import importlib
import msvcrt
import os
import queue
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


# Evita carga duplicada quando o arquivo roda como script (__main__) e tambem
# e importado por nome de modulo em outros pontos (ex.: executar_tudo.py).
if __name__ == "__main__":
    sys.modules.setdefault("controladordeatualização", sys.modules[__name__])

try:
    from pynput import keyboard as pynput_keyboard, mouse as pynput_mouse  # type: ignore
except Exception:
    pynput_keyboard = None
    pynput_mouse = None


class StopRequested(RuntimeError):
    pass


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _ControlWindow:
    def __init__(self, state: "_SharedState"):
        self._state = state
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._attention_queue: "queue.Queue[bool]" = queue.Queue()
        self._minimize_queue: "queue.Queue[bool]" = queue.Queue()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="macro-control-window", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)

    def append(self, message: str):
        self._queue.put(message)

    def request_attention(self):
        self._attention_queue.put(True)

    def request_minimize(self):
        self._minimize_queue.put(True)

    def _run(self):
        try:
            import tkinter as tk
            import tkinter.font as tkfont
            from tkinter import scrolledtext
        except Exception:
            self._ready.set()
            return

        root = tk.Tk()
        root.title("Controles da Macro")
        root.geometry("600x420")
        root.resizable(False, False)

        buttons = tk.Frame(root)
        buttons.pack(fill="x", padx=8, pady=(8, 4))

        pause_btn = tk.Button(
            buttons,
            text="Pausar (F8 / P)",
            command=self._state.request_pause,
            width=20,
            height=2,
        )
        pause_btn.pack(side="left", padx=(0, 6))

        resume_btn = tk.Button(
            buttons,
            text="Retomar (F9 / R)",
            command=self._state.request_resume,
            width=20,
            height=2,
        )
        resume_btn.pack(side="left", padx=(0, 6))

        stop_btn = tk.Button(
            buttons,
            text="Parar (F10 / S)",
            command=self._state.request_stop,
            width=20,
            height=2,
        )
        stop_btn.pack(side="left")

        run_btn = tk.Button(
            buttons,
            text="Executar Tudo",
            command=self._state.run_executar_tudo,
            width=16,
            height=2,
        )
        run_btn.pack(side="left", padx=(6, 0))

        pixel_buttons = tk.Frame(root)
        pixel_buttons.pack(fill="x", padx=8, pady=(0, 4))

        pixel_on_btn = tk.Button(
            pixel_buttons,
            text="Ativar Identificador (Espaco captura)",
            command=self._state.activate_pixel_identifier,
            width=32,
            height=2,
        )
        pixel_on_btn.pack(side="left", padx=(0, 6))

        pixel_off_btn = tk.Button(
            pixel_buttons,
            text="Desativar Identificador",
            command=self._state.deactivate_pixel_identifier,
            width=24,
            height=2,
        )
        pixel_off_btn.pack(side="left")

        live_pixel_var = tk.StringVar(value="PIXEL AO VIVO | desativado")
        live_pixel_label = tk.Label(
            root,
            textvariable=live_pixel_var,
            anchor="w",
            justify="left",
        )
        live_pixel_label.pack(fill="x", padx=8, pady=(0, 4))

        log = scrolledtext.ScrolledText(root, wrap="word", height=18, state="disabled")
        log.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        try:
            current_font = tkfont.Font(font=log.cget("font"))
            # Tamanho compacto e legivel para as mensagens de status.
            current_font.configure(size=8, weight="bold")
            log.configure(font=current_font)
            live_font = tkfont.Font(font=live_pixel_label.cget("font"))
            live_font.configure(size=9, weight="bold")
            live_pixel_label.configure(font=live_font)
        except Exception:
            pass

        def on_close():
            # Fechar a janela principal deve interromper tudo imediatamente.
            self._state.request_stop_from_window_close()
            try:
                root.destroy()
            except Exception:
                pass
            os._exit(0)

        def bring_to_front():
            try:
                root.deiconify()
                root.lift()
                # Pulso de "sempre no topo" para garantir foco visual imediato.
                root.attributes("-topmost", True)
                root.after(350, lambda: root.attributes("-topmost", False))
                root.focus_force()
            except Exception:
                pass

        def pump():
            live_text = self._state.get_live_pixel_status_text()
            if live_text is None:
                live_pixel_var.set("PIXEL AO VIVO | desativado")
            else:
                live_pixel_var.set(live_text)

            while True:
                try:
                    self._minimize_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    root.iconify()
                except Exception:
                    pass

            while True:
                try:
                    self._attention_queue.get_nowait()
                except queue.Empty:
                    break
                bring_to_front()

            while True:
                try:
                    line = self._queue.get_nowait()
                except queue.Empty:
                    break
                log.configure(state="normal")
                log.insert("end", f"{line}\n{'-' * 80}\n")
                log.see("end")
                log.configure(state="disabled")
            root.after(40, pump)

        root.protocol("WM_DELETE_WINDOW", on_close)
        root.after(40, pump)
        self._ready.set()
        root.mainloop()


class _SharedState:
    def __init__(self):
        self.paused = False
        self.stop_requested = False
        self.lock = threading.Lock()
        self.listener = None
        self.mouse_listener = None
        self.window: Optional[_ControlWindow] = None
        self.macro_name: Optional[str] = None
        self.total_events: int = 0
        self.prev_event_idx: int = 0
        self.next_event_idx: int = 1
        self.pixel_identifier_active = False
        self.last_pixel_capture_at = 0.0
        self.automation_running = False
        self.mouse_lock_enabled = False
        self.locked_mouse_pos: Optional[tuple] = None
        self._mouse_repositioning = False

    def ensure_window(self):
        if self.window is None:
            self.window = _ControlWindow(self)

    def _show_window_now(self):
        if self.window is not None:
            self.window.request_attention()

    def _minimize_window_now(self):
        if self.window is not None:
            self.window.request_minimize()

    def ensure_listener(self):
        if self.listener is not None or pynput_keyboard is None:
            return

        def on_press(key):
            if key == pynput_keyboard.Key.f8:
                self.request_pause()
            elif key == pynput_keyboard.Key.f9:
                self.request_resume()
            elif key == pynput_keyboard.Key.f10:
                self.request_stop()
            elif key == pynput_keyboard.Key.space:
                self.capture_pixel_snapshot()

        self.listener = pynput_keyboard.Listener(on_press=on_press)
        self.listener.start()

    def ensure_mouse_lock_listener(self):
        if self.mouse_listener is not None or pynput_mouse is None:
            return

        def on_move(x, y):
            with self.lock:
                if (
                    not self.mouse_lock_enabled
                    or self.paused
                    or self.stop_requested
                    or self.locked_mouse_pos is None
                    or self._mouse_repositioning
                ):
                    return
                target_x, target_y = self.locked_mouse_pos
                if int(x) == int(target_x) and int(y) == int(target_y):
                    return
                self._mouse_repositioning = True

            try:
                ctypes.windll.user32.SetCursorPos(int(target_x), int(target_y))
            finally:
                with self.lock:
                    self._mouse_repositioning = False

        self.mouse_listener = pynput_mouse.Listener(on_move=on_move)
        self.mouse_listener.start()

    def activate_mouse_lock(self):
        with self.lock:
            if self.mouse_lock_enabled:
                return
            self.mouse_lock_enabled = True
            self.locked_mouse_pos = _get_cursor_pos()
            self._mouse_repositioning = False
        self.ensure_mouse_lock_listener()

    def deactivate_mouse_lock(self):
        with self.lock:
            self.mouse_lock_enabled = False
            self.locked_mouse_pos = None
            self._mouse_repositioning = False

    def set_locked_mouse_position(self, x: int, y: int):
        with self.lock:
            if not self.mouse_lock_enabled:
                return
            self.locked_mouse_pos = (int(x), int(y))

    def set_macro_context(self, macro_name: str, total_events: int):
        with self.lock:
            self.macro_name = macro_name
            self.total_events = max(0, int(total_events))
            self.prev_event_idx = 0
            self.next_event_idx = 1
        self.activate_mouse_lock()

    def update_position(self, previous_idx: int, next_idx: int, total_events: Optional[int] = None):
        with self.lock:
            if total_events is not None:
                self.total_events = max(0, int(total_events))
            self.prev_event_idx = max(0, int(previous_idx))
            self.next_event_idx = max(1, int(next_idx))

    def clear_context(self):
        with self.lock:
            self.macro_name = None
            self.total_events = 0
            self.prev_event_idx = 0
            self.next_event_idx = 1

    def _digits(self) -> int:
        top = self.total_events if self.total_events > 0 else 9999
        return max(4, len(str(top)))

    def current_between_text(self) -> str:
        with self.lock:
            digits = self._digits()
            prev_txt = f"#{self.prev_event_idx:0{digits}d}"
            next_txt = f"#{self.next_event_idx:0{digits}d}"
            if self.macro_name:
                return f"entre {prev_txt} e {next_txt} ({self.macro_name})"
            return f"entre {prev_txt} e {next_txt}"

    def stop_message(self) -> str:
        return f"Parada solicitada. Encerrando macro. Posicao atual: {self.current_between_text()}."

    def request_pause(self):
        with self.lock:
            if self.paused:
                return
            self.paused = True
        self._show_window_now()
        emit_status(
            f"Pausado. Posicao atual: {self.current_between_text()}. "
            "Teclas: F9/R retoma, F10/S para."
        )

    def request_resume(self):
        with self.lock:
            if not self.paused:
                return
            self.paused = False
        self._minimize_window_now()
        emit_status("Retomado.")

    def request_stop(self):
        with self.lock:
            if self.stop_requested:
                return
            self.stop_requested = True
        self._show_window_now()
        emit_status(self.stop_message(), level="WARNING")

    def request_stop_from_window_close(self):
        with self.lock:
            already_stopped = self.stop_requested
            self.stop_requested = True
        if not already_stopped:
            emit_status(
                "Janela fechada. Parando macro e encerrando execucao imediatamente.",
                level="WARNING",
            )

    def _prepare_new_run(self):
        with self.lock:
            self.paused = False
            self.stop_requested = False
            self.prev_event_idx = 0
            self.next_event_idx = 1

    def run_executar_tudo(self):
        with self.lock:
            if self.automation_running:
                self._show_window_now()
                emit_status("Automacao ja esta em execucao.")
                return
            self.automation_running = True

        self._show_window_now()
        self._prepare_new_run()
        thread = threading.Thread(
            target=self._run_executar_tudo_worker,
            name="executar-tudo-worker",
            daemon=True,
        )
        thread.start()

    def _run_executar_tudo_worker(self):
        try:
            emit_status("Iniciando executar_tudo.py pelo controlador...")
            mod = importlib.import_module("executar_tudo")
            if not hasattr(mod, "main"):
                raise RuntimeError("executar_tudo.py nao possui funcao main().")
            mod.main()
        except Exception as exc:
            emit_status(f"Falha ao executar executar_tudo.py: {exc}", level="ERROR")
        finally:
            self.deactivate_mouse_lock()
            with self.lock:
                self.automation_running = False
            emit_status("Execucao do executar_tudo.py finalizada.")

    def activate_pixel_identifier(self):
        with self.lock:
            if self.pixel_identifier_active:
                return
            self.pixel_identifier_active = True
        self._show_window_now()
        emit_status(
            "Identificador de pixel ATIVADO. "
            "Pressione Espaco para capturar o pixel atual do cursor."
        )

    def deactivate_pixel_identifier(self):
        with self.lock:
            if not self.pixel_identifier_active:
                return
            self.pixel_identifier_active = False
        self._show_window_now()
        emit_status("Identificador de pixel DESATIVADO.")

    def capture_pixel_snapshot(self):
        with self.lock:
            if not self.pixel_identifier_active:
                return
            now = time.time()
            # evita repeticao excessiva por key repeat de sistema
            if (now - self.last_pixel_capture_at) < 0.15:
                return
            self.last_pixel_capture_at = now
        self._show_window_now()
        x, y = _get_cursor_pos()
        r, g, b = _get_pixel_color(x, y)
        emit_status(f"PIXEL | X:{x} Y:{y} RGB:({r},{g},{b}) HEX:#{r:02X}{g:02X}{b:02X}")

    def get_live_pixel_status_text(self) -> Optional[str]:
        with self.lock:
            active = self.pixel_identifier_active
        if not active:
            return None
        x, y = _get_cursor_pos()
        r, g, b = _get_pixel_color(x, y)
        return f"PIXEL AO VIVO | X:{x} Y:{y} RGB:({r},{g},{b}) HEX:#{r:02X}{g:02X}{b:02X}"


_STATE = _SharedState()


_STATUS_LINE_PATTERN = re.compile(r"^\d{2}/\d{2} \d{2}:\d{2}:\d{2} \| [A-Z]+ \| ")
_LEGACY_STATUS_LINE_PATTERN = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) "
    r"(?P<time>\d{2}:\d{2}:\d{2}),\d{3} \| "
    r"(?P<level>[A-Z]+) \| "
    r"(?P<message>.*)$"
)


def _format_status_line(message: str, level: str = "INFO") -> str:
    legacy_match = _LEGACY_STATUS_LINE_PATTERN.match(message)
    if legacy_match:
        dt = datetime.strptime(
            f"{legacy_match.group('date')} {legacy_match.group('time')}",
            "%Y-%m-%d %H:%M:%S",
        )
        short_ts = dt.strftime("%d/%m %H:%M:%S")
        return f"{short_ts} | {legacy_match.group('level')} | {legacy_match.group('message')}"

    if _STATUS_LINE_PATTERN.match(message):
        return message
    timestamp = datetime.now().strftime("%d/%m %H:%M:%S")
    return f"{timestamp} | {level.upper()} | {message}"


def emit_status(message: str, to_console: bool = True, level: str = "INFO"):
    line = _format_status_line(str(message), level=level)
    if to_console:
        print(line)
    if _STATE.window is not None:
        _STATE.window.append(line)


def push_status(message: str):
    emit_status(message, to_console=False)


class ModCommandApp:
    """
    App interno de comandos para controlar macro/janela sem acoplamento
    com interface externa.
    """

    def __init__(self):
        _STATE.ensure_window()
        _STATE.ensure_listener()

    def executar(self, comando: str) -> str:
        cmd = (comando or "").strip().lower()
        if not cmd:
            return self._help_text()

        if cmd in {"help", "ajuda", "comandos"}:
            return self._help_text()

        if cmd in {"pause", "pausar"}:
            _STATE.request_pause()
            return "OK: pausa solicitada."

        if cmd in {"resume", "retomar"}:
            _STATE.request_resume()
            return "OK: retomada solicitada."

        if cmd in {"stop", "parar"}:
            _STATE.request_stop()
            return "OK: parada solicitada."

        if cmd in {"pixel_on", "ativar_pixel", "identificador_on"}:
            _STATE.activate_pixel_identifier()
            return "OK: identificador de pixel ativado."

        if cmd in {"pixel_off", "desativar_pixel", "identificador_off"}:
            _STATE.deactivate_pixel_identifier()
            return "OK: identificador de pixel desativado."

        if cmd in {"pixel_capture", "capturar_pixel"}:
            _STATE.capture_pixel_snapshot()
            return "OK: captura de pixel solicitada."

        if cmd in {"run", "executar", "executar_tudo", "start"}:
            _STATE.run_executar_tudo()
            return "OK: executar_tudo iniciado."

        if cmd in {"status", "estado"}:
            with _STATE.lock:
                paused = _STATE.paused
                stop = _STATE.stop_requested
                pixel = _STATE.pixel_identifier_active
                running = _STATE.automation_running
            pos = _STATE.current_between_text()
            return (
                f"STATUS | pausado={paused} parar={stop} "
                f"pixel_ativo={pixel} executando={running} posicao={pos}"
            )

        return f"Comando desconhecido: {comando!r}. Use 'ajuda'."

    def _help_text(self) -> str:
        return (
            "Comandos internos (mod): "
            "pausar, retomar, parar, ativar_pixel, desativar_pixel, "
            "capturar_pixel, executar_tudo, status, ajuda"
        )


mod_app = ModCommandApp()


def executar_comando_mod(comando: str) -> str:
    return mod_app.executar(comando)


def iniciar_controlador():
    emit_status(
        "Controlador iniciado. Use o botao 'Executar Tudo' ou o comando interno "
        "'executar_tudo'."
    )
    while True:
        time.sleep(0.5)


def validate_macro_comment_sequence(path: Path):
    """
    Garante que comentarios numerados das macros estejam em sequencia:
    # 0001, # 0002, # 0003...
    """
    if not path.exists():
        return

    pattern = re.compile(r"^\s*\(.*\),\s*#\s*(\d+)\b")
    expected = None
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = pattern.match(line)
        if not match:
            continue
        current = int(match.group(1))
        if expected is None:
            expected = current
            continue
        expected += 1
        if current != expected:
            raise RuntimeError(
                f"Comentarios fora de sequencia em {path.name}:{lineno}. "
                f"Esperado #{expected:04d}, encontrado #{current:04d}."
            )


class ExecutionController:
    def __init__(self, use_listener: bool = True):
        _STATE.ensure_window()
        if use_listener:
            _STATE.ensure_listener()

    @property
    def paused(self) -> bool:
        return _STATE.paused

    @property
    def stop_requested(self) -> bool:
        return _STATE.stop_requested

    def poll_keypress(self):
        if not msvcrt.kbhit():
            return
        key = msvcrt.getch()
        if not key:
            return
        try:
            char = key.decode("utf-8").lower()
        except UnicodeDecodeError:
            return
        if char == "p":
            _STATE.request_pause()
        elif char == "r":
            _STATE.request_resume()
        elif char == "s":
            _STATE.request_stop()
        elif char == " ":
            _STATE.capture_pixel_snapshot()

    def wait_if_paused(self):
        while self.paused and not self.stop_requested:
            self.poll_keypress()
            time.sleep(0.1)

    def set_macro_context(self, macro_name: str, total_events: int):
        _STATE.set_macro_context(macro_name, total_events)

    def update_event_position(self, previous_idx: int, next_idx: int, total_events: Optional[int] = None):
        _STATE.update_position(previous_idx, next_idx, total_events)

    def clear_macro_context(self):
        _STATE.clear_context()

    def set_locked_mouse_position(self, x: int, y: int):
        _STATE.set_locked_mouse_position(x, y)

    def get_stop_message(self) -> str:
        return _STATE.stop_message()

    def close(self):
        _STATE.deactivate_mouse_lock()
        _STATE.clear_context()


def sleep_with_controls(seconds, controller: ExecutionController) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        controller.poll_keypress()
        if controller.stop_requested:
            return False
        controller.wait_if_paused()
        if controller.stop_requested:
            return False
        remaining = end - time.time()
        time.sleep(0.05 if remaining > 0.05 else max(0.0, remaining))
    return True


def _executar_evento_estilo_macro(mouse_controller, controller: ExecutionController, kind: str, data: dict):
    controller.poll_keypress()
    controller.wait_if_paused()
    if controller.stop_requested:
        raise StopRequested(controller.get_stop_message())

    if kind == "move":
        controller.set_locked_mouse_position(int(data["x"]), int(data["y"]))
        mouse_controller.position = (int(data["x"]), int(data["y"]))
        return

    if kind == "click":
        controller.set_locked_mouse_position(int(data["x"]), int(data["y"]))
        mouse_controller.position = (int(data["x"]), int(data["y"]))
        button = pynput_mouse.Button.left
        if data.get("pressed", False):
            mouse_controller.press(button)
            hold_ms = int(data.get("hold_ms", 0))
            if hold_ms > 0:
                time.sleep(hold_ms / 1000.0)
        else:
            mouse_controller.release(button)
        return


def _varrer_retangulo_e_clicar(mouse_controller, controller: ExecutionController, data: dict):
    x_min = int(data["x_min"])
    x_max = int(data["x_max"])
    y_min = int(data["y_min"])
    y_max = int(data["y_max"])
    click_delay = float(data.get("click_delay", 1.0))
    step_delay = float(data.get("step_delay", 0.004))
    follow_cursor = bool(data.get("follow_cursor", True))
    control_check_interval = max(1, int(data.get("control_check_interval", 64)))
    blocked = {tuple(rgb) for rgb in data.get("blocked_rgb", [])}
    context = data.get("label") or "scan_click_rectangle"

    emit_status(
        f"{context}: iniciando varredura de x={x_min}..{x_max}, y={y_min}..{y_max} de baixo para cima.",
        level="INFO",
    )

    scan_count = 0
    for y in range(y_max, y_min - 1, -1):
        for x in range(x_min, x_max + 1):
            if scan_count % control_check_interval == 0:
                controller.poll_keypress()
                controller.wait_if_paused()
                if controller.stop_requested:
                    raise StopRequested(controller.get_stop_message())

            if follow_cursor:
                controller.set_locked_mouse_position(x, y)
                mouse_controller.position = (x, y)

            current = _get_pixel_color(x, y)
            if current not in blocked:
                controller.set_locked_mouse_position(x, y)
                mouse_controller.position = (x, y)
                mouse_controller.press(pynput_mouse.Button.left)
                mouse_controller.release(pynput_mouse.Button.left)
                if click_delay > 0:
                    if not sleep_with_controls(click_delay, controller):
                        raise StopRequested(controller.get_stop_message())

            if follow_cursor and step_delay > 0:
                if not sleep_with_controls(step_delay, controller):
                    raise StopRequested(controller.get_stop_message())
            scan_count += 1

    emit_status(f"{context}: varredura concluida.", level="INFO")


def handle_custom_event(kind: str, data: dict, controller: ExecutionController) -> bool:
    if kind == "wait":
        seconds = float(data.get("seconds", 0))
        if seconds <= 0:
            return True
        if not sleep_with_controls(seconds, controller):
            raise StopRequested(controller.get_stop_message())
        return True

    if kind in ("wait_pixel", "wait_not_pixel"):
        x = int(data["x"])
        y = int(data["y"])
        target = tuple(data["rgb"])
        tolerance = int(data.get("tolerance", 0))
        search_radius = int(data.get("search_radius", 0))
        search_mode = str(data.get("search_mode", "")).strip().lower()
        center_rgb = tuple(data["center_rgb"]) if "center_rgb" in data else None
        center_tolerance = int(data.get("center_tolerance", tolerance))
        timeout = float(data.get("timeout", 0))
        interval = float(data.get("interval", 0.2))
        error_on_timeout = bool(data.get("error_on_timeout", False))
        context = data.get("label") or data.get("_event_index")
        should_match = kind == "wait_pixel"
        _wait_for_pixel(
            x,
            y,
            target,
            tolerance,
            search_radius,
            search_mode,
            center_rgb,
            center_tolerance,
            timeout,
            interval,
            should_match,
            controller,
            error_on_timeout,
            context,
        )
        return True

    if kind == "pixel_branch_sequence":
        wait_before_check = float(data.get("wait_before_check", 0))
        if wait_before_check > 0 and not sleep_with_controls(wait_before_check, controller):
            raise StopRequested(controller.get_stop_message())

        context = data.get("label") or data.get("_event_index") or "pixel_branch_sequence"
        x = int(data["x"])
        y = int(data["y"])
        blocked = {tuple(rgb) for rgb in data.get("blocked_rgb", [])}
        emit_status(
            f"{context}: iniciando checagem do pixel em ({x},{y}).",
            level="INFO",
        )
        current = _get_pixel_color(x, y)
        emit_status(
            f"{context}: pixel em ({x},{y}) = RGB{current} HEX:#{current[0]:02X}{current[1]:02X}{current[2]:02X}.",
            level="INFO",
        )
        if current in blocked:
            emit_status(
                f"{context}: pixel igual a uma das cores informadas, pulando a sequencia.",
                level="INFO",
            )
            return True

        mouse_controller = pynput_mouse.Controller() if pynput_mouse is not None else None
        if mouse_controller is None:
            return True

        emit_status(
            f"{context}: pixel diferente das cores informadas, executando sequencia.",
            level="INFO",
        )
        last = 0.0
        macro_like_events = data.get("macro_like_events", [])
        for idx, (t, event_kind, event_data) in enumerate(macro_like_events, start=1):
            wait = float(t) - last
            if wait > 0 and not sleep_with_controls(wait, controller):
                raise StopRequested(controller.get_stop_message())
            last = float(t)
            emit_status(
                f"{context}: executando evento {idx}/{len(macro_like_events)} apos espera de {wait:.2f}s.",
                level="INFO",
            )
            emit_status(
                f"{context}: evento {idx}/{len(macro_like_events)} -> {event_kind} {event_data}.",
                level="INFO",
            )
            _executar_evento_estilo_macro(mouse_controller, controller, event_kind, event_data)

        emit_status(f"{context}: sequencia concluida.", level="INFO")
        return True

    if kind == "scan_click_rectangle":
        mouse_controller = pynput_mouse.Controller() if pynput_mouse is not None else None
        if mouse_controller is None:
            return True
        _varrer_retangulo_e_clicar(mouse_controller, controller, data)
        return True

    if kind == "wait_file":
        path = Path(data["path"])
        timeout = float(data.get("timeout", 0))
        interval = float(data.get("interval", 0.5))
        _wait_for_file(path, timeout, interval, controller)
        return True

    return False


def _wait_for_file(path: Path, timeout: float, interval: float, controller: ExecutionController):
    start = time.time()
    while True:
        controller.poll_keypress()
        controller.wait_if_paused()
        if controller.stop_requested:
            raise StopRequested(controller.get_stop_message())
        if path.exists():
            return
        if timeout > 0 and (time.time() - start) >= timeout:
            return
        time.sleep(interval)


def _wait_for_pixel(
    x: int,
    y: int,
    target_rgb: tuple,
    tolerance: int,
    search_radius: int,
    search_mode: str,
    center_rgb,
    center_tolerance: int,
    timeout: float,
    interval: float,
    should_match: bool,
    controller: ExecutionController,
    error_on_timeout: bool,
    context,
):
    start = time.time()
    while True:
        controller.poll_keypress()
        controller.wait_if_paused()
        if controller.stop_requested:
            raise StopRequested(controller.get_stop_message())
        if search_mode == "quadrants":
            current, match_pos = _find_pixel_in_quadrant_centers(target_rgb, tolerance)
            matches = current is not None
        elif search_mode == "quadrants_plus_center":
            current, match_pos = _find_pixel_in_quadrants_plus_center(
                target_rgb,
                tolerance,
                center_rgb,
                center_tolerance,
            )
            matches = current is not None
        elif search_radius > 0:
            current, match_pos = _find_pixel_within_radius(x, y, target_rgb, tolerance, search_radius)
            matches = current is not None
        else:
            current = _get_pixel_color(x, y)
            match_pos = (x, y)
            matches = _color_matches(current, target_rgb, tolerance)
        if matches == should_match:
            if matches and search_radius > 0 and match_pos is not None:
                controller.set_locked_mouse_position(match_pos[0], match_pos[1])
            return
        if timeout > 0 and (time.time() - start) >= timeout:
            if error_on_timeout:
                ctx = f" Contexto: {context}." if context else ""
                raise RuntimeError(
                    f"Timeout esperando pixel ({x},{y}) ficar "
                    f"{target_rgb} (tolerancia {tolerance}) em {timeout:.1f}s."
                    f"{ctx}"
                )
            return
        time.sleep(interval)


def _get_screen_size() -> tuple[int, int]:
    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))


def _find_pixel_in_quadrant_centers(target_rgb: tuple, tolerance: int):
    width, height = _get_screen_size()
    centers = [
        (width // 4, height // 4),
        ((width * 3) // 4, height // 4),
        (width // 4, (height * 3) // 4),
        ((width * 3) // 4, (height * 3) // 4),
    ]
    for point in centers:
        current = _get_pixel_color(point[0], point[1])
        if _color_matches(current, target_rgb, tolerance):
            return current, point
    return None, None


def _find_pixel_in_quadrants_plus_center(target_rgb: tuple, tolerance: int, center_rgb, center_tolerance: int):
    current, point = _find_pixel_in_quadrant_centers(target_rgb, tolerance)
    if current is not None:
        return current, point

    if center_rgb is None:
        return None, None

    width, height = _get_screen_size()
    center_point = (width // 2, height // 2)
    current = _get_pixel_color(center_point[0], center_point[1])
    if _color_matches(current, tuple(center_rgb), center_tolerance):
        return current, center_point
    return None, None


def _find_pixel_within_radius(
    center_x: int,
    center_y: int,
    target_rgb: tuple,
    tolerance: int,
    radius: int,
):
    for dy in range(-radius, radius + 1):
        y = center_y + dy
        for dx in range(-radius, radius + 1):
            x = center_x + dx
            current = _get_pixel_color(x, y)
            if _color_matches(current, target_rgb, tolerance):
                return current, (x, y)
    return None, None


def _color_matches(current_rgb: tuple, target_rgb: tuple, tolerance: int) -> bool:
    return (
        abs(current_rgb[0] - target_rgb[0]) <= tolerance
        and abs(current_rgb[1] - target_rgb[1]) <= tolerance
        and abs(current_rgb[2] - target_rgb[2]) <= tolerance
    )


def _get_pixel_color(x: int, y: int) -> tuple:
    hdc = ctypes.windll.user32.GetDC(0)
    color = ctypes.windll.gdi32.GetPixel(hdc, x, y)
    ctypes.windll.user32.ReleaseDC(0, hdc)
    if color == -1:
        return (0, 0, 0)
    r = color & 0xFF
    g = (color >> 8) & 0xFF
    b = (color >> 16) & 0xFF
    return (r, g, b)


def _get_cursor_pos() -> tuple:
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def get_pixel_color(x: int, y: int) -> tuple:
    return _get_pixel_color(x, y)


def pixel_matches(x: int, y: int, target_rgb: tuple, tolerance: int = 0) -> bool:
    return _color_matches(_get_pixel_color(x, y), target_rgb, tolerance)


if __name__ == "__main__":
    try:
        iniciar_controlador()
    except KeyboardInterrupt:
        pass
