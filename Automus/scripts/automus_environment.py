"""Pre-flight seguro do ambiente visual usado pelas macros do Automus.

Este modulo nao envia mouse ou teclado. Ele apenas inspeciona o Windows e,
quando solicitado, reposiciona a janela do TOTVS para a geometria de teste.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field


TOTVS_TITLE_TOKENS = ("totvs", "smartclient", "manufatura")


@dataclass(frozen=True)
class WindowTarget:
    x: int = 0
    y: int = 0
    width: int = 1366
    height: int = 768


@dataclass
class PreflightResult:
    ok: bool
    messages: list[str] = field(default_factory=list)
    window_found: bool = False
    window_corrected: bool = False

    def summary(self) -> str:
        prefix = "AMBIENTE OK" if self.ok else "AMBIENTE INCOMPLETO"
        return prefix + " | " + " | ".join(self.messages)


def enable_per_monitor_dpi_awareness() -> None:
    """Faz as coordenadas da macro representarem pixels fisicos reais."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _window_text(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    size = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(max(1, size + 1))
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def find_totvs_window() -> int | None:
    user32 = ctypes.windll.user32
    matches: list[tuple[int, int]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            title = _window_text(int(hwnd)).casefold()
            score = sum(1 for token in TOTVS_TITLE_TOKENS if token in title)
            if score:
                matches.append((score, int(hwnd)))
        return True

    user32.EnumWindows(callback, 0)
    return max(matches, default=(0, 0))[1] or None


def _rect(hwnd: int, client: bool = False) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    user32 = ctypes.windll.user32
    if client:
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        point = wintypes.POINT(rect.left, rect.top)
        user32.ClientToScreen(hwnd, ctypes.byref(point))
        return point.x, point.y, rect.right - rect.left, rect.bottom - rect.top
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def _dpi_percent(hwnd: int | None) -> int:
    user32 = ctypes.windll.user32
    try:
        dpi = user32.GetDpiForWindow(hwnd) if hwnd else user32.GetDpiForSystem()
        return round(int(dpi) * 100 / 96)
    except Exception:
        return 100


def run_preflight(target: WindowTarget = WindowTarget(), autocorrect: bool = True) -> PreflightResult:
    """Inspeciona resolucao, DPI e janela TOTVS sem gerar entrada do usuario."""
    enable_per_monitor_dpi_awareness()
    user32 = ctypes.windll.user32
    screen = (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    messages = [f"tela {screen[0]}x{screen[1]}"]
    ok = screen[0] >= target.width and screen[1] >= target.height

    hwnd = find_totvs_window()
    dpi = _dpi_percent(hwnd)
    messages.append(f"escala {dpi}%")
    ok = ok and dpi == 100
    if not hwnd:
        messages.append("janela TOTVS nao encontrada")
        return PreflightResult(False, messages)

    corrected = False
    outer = _rect(hwnd)
    expected = (target.x, target.y, target.width, target.height)
    if outer != expected and autocorrect:
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        corrected = bool(user32.SetWindowPos(
            hwnd, 0, target.x, target.y, target.width, target.height,
            SWP_NOZORDER | SWP_NOACTIVATE,
        ))
        outer = _rect(hwnd)

    client = _rect(hwnd, client=True)
    foreground = int(user32.GetForegroundWindow() or 0) == hwnd
    messages.extend([
        f"janela {outer[2]}x{outer[3]} em {outer[0]},{outer[1]}",
        f"area cliente {client[2]}x{client[3]}",
        "foco confirmado" if foreground else "TOTVS sem foco (teste nao altera foco)",
    ])
    if corrected:
        messages.append("posicao corrigida")
    ok = ok and outer == expected
    return PreflightResult(ok, messages, window_found=True, window_corrected=corrected)
