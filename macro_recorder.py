import argparse
import json
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from pynput import keyboard, mouse


@dataclass
class Event:
    dt: float
    kind: str
    data: Dict[str, Any]


def record(output_path: str):
    events: List[Event] = []
    start_time = None
    recording = {"on": False}

    def now():
        return time.perf_counter()

    def add_event(kind: str, data: Dict[str, Any]):
        nonlocal start_time
        if not recording["on"]:
            return
        if start_time is None:
            start_time = now()
        dt = now() - start_time
        events.append(Event(dt=dt, kind=kind, data=data))

    def on_press(key):
        if key == keyboard.Key.f9:
            recording["on"] = True
            add_event("meta", {"action": "start"})
            return
        if key == keyboard.Key.f10:
            recording["on"] = False
            add_event("meta", {"action": "stop"})
            return False
        if recording["on"]:
            try:
                add_event("key_press", {"key": key.char})
            except AttributeError:
                add_event("key_press", {"key": str(key)})

    def on_release(key):
        if recording["on"]:
            try:
                add_event("key_release", {"key": key.char})
            except AttributeError:
                add_event("key_release", {"key": str(key)})

    def on_move(x, y):
        add_event("mouse_move", {"x": x, "y": y})

    def on_click(x, y, button, pressed):
        add_event("mouse_click", {"x": x, "y": y, "button": str(button), "pressed": pressed})

    def on_scroll(x, y, dx, dy):
        add_event("mouse_scroll", {"x": x, "y": y, "dx": dx, "dy": dy})

    print("Pressione F9 para iniciar a gravacao e F10 para parar.")
    with keyboard.Listener(on_press=on_press, on_release=on_release) as kl, \
            mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll) as ml:
        kl.join()
        ml.stop()

    data = [asdict(e) for e in events if e.kind != "meta"]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Macro salva em: {output_path}")


def playback(input_path: str, speed: float = 1.0):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    kb = keyboard.Controller()
    ms = mouse.Controller()

    start = time.perf_counter()
    last_dt = 0.0

    print("Reproducao iniciada. Pressione ESC para abortar.")

    def abort_on_esc(key):
        if key == keyboard.Key.esc:
            return False

    with keyboard.Listener(on_press=abort_on_esc) as abort_listener:
        for e in data:
            dt = e["dt"] / speed
            time.sleep(max(0, dt - last_dt))
            last_dt = dt
            kind = e["kind"]
            d = e["data"]

            if kind == "mouse_move":
                ms.position = (d["x"], d["y"])
            elif kind == "mouse_click":
                btn = mouse.Button.left if "left" in d["button"] else mouse.Button.right
                ms.position = (d["x"], d["y"])
                if d["pressed"]:
                    ms.press(btn)
                else:
                    ms.release(btn)
            elif kind == "mouse_scroll":
                ms.scroll(d["dx"], d["dy"])
            elif kind == "key_press":
                k = d["key"]
                if k.startswith("Key."):
                    kb.press(getattr(keyboard.Key, k.split(".", 1)[1]))
                else:
                    kb.press(k)
            elif kind == "key_release":
                k = d["key"]
                if k.startswith("Key."):
                    kb.release(getattr(keyboard.Key, k.split(".", 1)[1]))
                else:
                    kb.release(k)

        abort_listener.stop()


def main():
    parser = argparse.ArgumentParser(description="Macro recorder/playback")
    sub = parser.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record")
    rec.add_argument("--out", default="macro.saldo.atual.json")

    play = sub.add_parser("play")
    play.add_argument("--in", dest="inp", default="macro.json")
    play.add_argument("--speed", type=float, default=1.0)

    args = parser.parse_args()
    if args.cmd == "record":
        record(args.out)
    else:
        playback(args.inp, speed=args.speed)


if __name__ == "__main__":
    main()
