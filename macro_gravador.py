import time
from pathlib import Path

from pynput import keyboard, mouse  # type: ignore


RECORD_HOTKEY = keyboard.Key.f8
STOP_HOTKEY = keyboard.Key.f9
OUTPUT_PREFIX = "macro_"
OUTPUT_SUFFIX = ".py"

state = {
    "recording": False,
    "events": [],
    "start": 0.0,
}


def _now() -> float:
    return time.time()


def _rel_time() -> float:
    return _now() - state["start"]


def _key_to_data(key) -> str:
    if hasattr(key, "char") and key.char:
        return key.char
    if hasattr(key, "name") and key.name:
        return f"Key.{key.name}"
    return str(key)


def _next_macro_path() -> Path:
    base_dir = Path(__file__).resolve().parent
    existing = sorted(base_dir.glob(f"{OUTPUT_PREFIX}[0-9][0-9][0-9]{OUTPUT_SUFFIX}"))
    if not existing:
        return base_dir / f"{OUTPUT_PREFIX}001{OUTPUT_SUFFIX}"
    last = existing[-1].stem
    try:
        num = int(last.replace(OUTPUT_PREFIX, ""))
    except ValueError:
        num = 0
    return base_dir / f"{OUTPUT_PREFIX}{num + 1:03d}{OUTPUT_SUFFIX}"


def _write_macro(path: Path, events: list):
    header = [
        "import time",
        "from pynput import mouse, keyboard  # type: ignore",
        "",
        f"events = {events!r}",
        "",
        "def _parse_button(name):",
        "    try:",
        "        return getattr(mouse.Button, name)",
        "    except Exception:",
        "        return mouse.Button.left",
        "",
        "def _parse_key(value):",
        "    if not value:",
        "        return None",
        "    if isinstance(value, str) and value.startswith('Key.'):",
        "        name = value.split('.', 1)[1]",
        "        return getattr(keyboard.Key, name, value)",
        "    return value",
        "",
        "def play():",
        "    m = mouse.Controller()",
        "    k = keyboard.Controller()",
        "    last = 0.0",
        "    for t, kind, data in events:",
        "        wait = t - last",
        "        if wait > 0:",
        "            time.sleep(wait)",
        "        last = t",
        "        if kind == 'move':",
        "            m.position = (data['x'], data['y'])",
        "        elif kind == 'click':",
        "            m.position = (data['x'], data['y'])",
        "            btn = _parse_button(data['button'])",
        "            if data['pressed']:",
        "                m.press(btn)",
        "            else:",
        "                m.release(btn)",
        "        elif kind == 'scroll':",
        "            m.position = (data['x'], data['y'])",
        "            m.scroll(data['dx'], data['dy'])",
        "        elif kind == 'key_down':",
        "            key = _parse_key(data.get('key'))",
        "            if key is not None:",
        "                k.press(key)",
        "        elif kind == 'key_up':",
        "            key = _parse_key(data.get('key'))",
        "            if key is not None:",
        "                k.release(key)",
        "",
        "if __name__ == '__main__':",
        "    play()",
        "",
    ]
    path.write_text("\n".join(header), encoding="utf-8")


def _start_recording():
    state["recording"] = True
    state["events"] = []
    state["start"] = _now()
    print("Gravacao iniciada. Pressione F8 novamente para parar e salvar.")


def _stop_recording():
    state["recording"] = False
    out = _next_macro_path()
    _write_macro(out, state["events"])
    print(f"Gravacao salva em: {out}")


def _on_move(x, y):
    if state["recording"]:
        state["events"].append((_rel_time(), "move", {"x": x, "y": y}))


def _on_click(x, y, button, pressed):
    if state["recording"]:
        btn = button.name if hasattr(button, "name") else str(button)
        state["events"].append(
            (_rel_time(), "click", {"x": x, "y": y, "button": btn, "pressed": pressed})
        )


def _on_scroll(x, y, dx, dy):
    if state["recording"]:
        state["events"].append((_rel_time(), "scroll", {"x": x, "y": y, "dx": dx, "dy": dy}))


def _on_press(key):
    if key == STOP_HOTKEY:
        print("Encerrando gravador.")
        raise SystemExit(0)
    if key == RECORD_HOTKEY:
        if not state["recording"]:
            _start_recording()
        else:
            _stop_recording()
        return
    if state["recording"]:
        state["events"].append((_rel_time(), "key_down", {"key": _key_to_data(key)}))


def _on_release(key):
    if key == RECORD_HOTKEY:
        return
    if state["recording"]:
        state["events"].append((_rel_time(), "key_up", {"key": _key_to_data(key)}))


def main():
    print("Gravador de macros ativo.")
    print("F8 inicia a gravacao e F8 novamente para salvar.")
    with mouse.Listener(on_move=_on_move, on_click=_on_click, on_scroll=_on_scroll) as ml:
        with keyboard.Listener(on_press=_on_press, on_release=_on_release) as kl:
            kl.join()
            ml.stop()


if __name__ == "__main__":
    main()
