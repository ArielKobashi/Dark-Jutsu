import time
import threading
import ctypes
from pathlib import Path
import msvcrt

try:
    from pynput import keyboard as pynput_keyboard  # type: ignore
except Exception:
    pynput_keyboard = None


class StopRequested(RuntimeError):
    pass


class ExecutionController:
    def __init__(self, use_listener: bool = True):
        self.paused = False
        self.stop_requested = False
        self._listener = None
        self._lock = threading.Lock()
        if use_listener and pynput_keyboard is not None:
            self._start_listener()

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
            self._set_paused(True)
        elif char == "r":
            self._set_paused(False)
        elif char == "s":
            self._set_stop()

    def wait_if_paused(self):
        while self.paused and not self.stop_requested:
            self.poll_keypress()
            time.sleep(0.1)

    def close(self):
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def _set_paused(self, paused: bool):
        with self._lock:
            if paused and not self.paused:
                self.paused = True
                print("Pausado. Teclas: F9 retoma, F10 para.")
            elif not paused and self.paused:
                self.paused = False
                print("Retomado.")

    def _set_stop(self):
        with self._lock:
            if not self.stop_requested:
                self.stop_requested = True
                print("Parada solicitada. Encerrando macro.")

    def _start_listener(self):
        def on_press(key):
            if key == pynput_keyboard.Key.f8:
                self._set_paused(True)
            elif key == pynput_keyboard.Key.f9:
                self._set_paused(False)
            elif key == pynput_keyboard.Key.f10:
                self._set_stop()

        self._listener = pynput_keyboard.Listener(on_press=on_press)
        self._listener.start()


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


def handle_custom_event(kind: str, data: dict, controller: ExecutionController) -> bool:
    if kind == "wait":
        seconds = float(data.get("seconds", 0))
        if seconds <= 0:
            return True
        if not sleep_with_controls(seconds, controller):
            raise StopRequested("Parada solicitada. Encerrando macro.")
        return True

    if kind in ("wait_pixel", "wait_not_pixel"):
        x = int(data["x"])
        y = int(data["y"])
        target = tuple(data["rgb"])
        tolerance = int(data.get("tolerance", 0))
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
            timeout,
            interval,
            should_match,
            controller,
            error_on_timeout,
            context,
        )
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
            raise StopRequested("Parada solicitada. Encerrando macro.")
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
            raise StopRequested("Parada solicitada. Encerrando macro.")
        current = _get_pixel_color(x, y)
        matches = _color_matches(current, target_rgb, tolerance)
        if matches == should_match:
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
