import argparse
import importlib.util
import sys
import threading
import time
from pathlib import Path


def safe_import_pynput():
    try:
        from pynput import keyboard, mouse  # type: ignore
        return keyboard, mouse
    except Exception:
        print("Erro: o pacote 'pynput' nao esta instalado.")
        print("Instale com: pip install pynput")
        sys.exit(1)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Grava uma macro e gera um arquivo .py para reproduzir."
    )
    parser.add_argument(
        "--out",
        default="macro_reproduzir.py",
        help="Arquivo .py de saida (macro reproduzida)",
    )
    parser.add_argument(
        "--start-delay",
        type=float,
        default=3.0,
        help="Segundos de espera antes de iniciar a reproducao",
    )
    parser.add_argument(
        "--min-move-interval",
        type=float,
        default=0.05,
        help="Intervalo minimo (s) para registrar movimentos do mouse",
    )
    parser.add_argument(
        "--open-entrar",
        action="store_true",
        help="Abrir o Protheus usando entrar.protheus1.py antes de gravar",
    )
    parser.add_argument("--entrar-url", default="", help="URL para o entrar.protheus1.py")
    parser.add_argument("--entrar-user", default="", help="Usuario para o entrar.protheus1.py")
    parser.add_argument("--entrar-password", default="", help="Senha para o entrar.protheus1.py")
    parser.add_argument("--entrar-env", default="", help="Ambiente para o entrar.protheus1.py")
    parser.add_argument("--entrar-manual", action="store_true", help="Login manual")
    parser.add_argument("--entrar-headless", action="store_true", help="Rodar headless")
    parser.add_argument("--entrar-timeout", type=int, default=0, help="Timeout do login (s)")
    return parser


def serialize_key(key):
    data = {"key": None, "char": None, "vk": None}
    try:
        # Key (especial)
        if str(key).startswith("Key."):
            data["key"] = str(key)
        else:
            # KeyCode
            data["char"] = getattr(key, "char", None)
            data["vk"] = getattr(key, "vk", None)
    except Exception:
        data["key"] = str(key)
    return data


def serialize_button(button):
    name = str(button)
    # mouse.Button.left -> 'Button.left'
    if "Button." in name:
        return name.split("Button.", 1)[1]
    return name


def generate_playback_py(events, output_path: Path, start_delay: float):
    header = """import time
from pynput import mouse, keyboard


events = """
    footer = f"""


def _parse_key(data):
    key_name = data.get("key")
    if key_name and key_name.startswith("Key."):
        name = key_name.split(".", 1)[1]
        return getattr(keyboard.Key, name, None)
    char = data.get("char")
    if char:
        return char
    vk = data.get("vk")
    if vk is not None:
        return keyboard.KeyCode.from_vk(vk)
    return None


def _parse_button(name):
    return getattr(mouse.Button, name, mouse.Button.left)


def play():
    m = mouse.Controller()
    k = keyboard.Controller()
    last = 0.0
    for t, kind, data in events:
        wait = t - last
        if wait > 0:
            time.sleep(wait)
        last = t
        if kind == "move":
            m.position = (data["x"], data["y"])
        elif kind == "click":
            m.position = (data["x"], data["y"])
            btn = _parse_button(data["button"])
            if data["pressed"]:
                m.press(btn)
            else:
                m.release(btn)
        elif kind == "scroll":
            m.position = (data["x"], data["y"])
            m.scroll(data["dx"], data["dy"])
        elif kind == "key_down":
            key = _parse_key(data)
            if key is not None:
                k.press(key)
        elif kind == "key_up":
            key = _parse_key(data)
            if key is not None:
                k.release(key)


if __name__ == "__main__":
    print("Iniciando em {start_delay:.1f}s... deixe o foco na janela correta.")
    time.sleep({start_delay})
    play()
"""
    output_path.write_text(header + repr(events) + footer, encoding="utf-8")


def main() -> int:
    keyboard, mouse = safe_import_pynput()
    args = build_parser().parse_args()

    output_path = Path(args.out).expanduser().resolve()
    events = []
    p = browser = None
    recording = {"active": False}
    stop_event = threading.Event()
    start_time = {"value": None}
    last_move = {"t": 0.0}
    dragging = {"count": 0}

    def now():
        return time.perf_counter()

    def add_event(kind, data):
        if not recording["active"]:
            return
        t = now() - start_time["value"]
        events.append((t, kind, data))

    def on_press(key):
        if key == keyboard.Key.f9 and not recording["active"]:
            recording["active"] = True
            start_time["value"] = now()
            print("Gravacao iniciada.")
            return
        if key == keyboard.Key.f10 and recording["active"]:
            print("Gravacao finalizada.")
            stop_event.set()
            return False
        if recording["active"] and key not in (keyboard.Key.f9, keyboard.Key.f10):
            add_event("key_down", serialize_key(key))

    def on_release(key):
        if recording["active"] and key not in (keyboard.Key.f9, keyboard.Key.f10):
            add_event("key_up", serialize_key(key))

    def on_move(x, y):
        if not recording["active"]:
            return
        t = now()
        if dragging["count"] > 0 or (t - last_move["t"]) >= args.min_move_interval:
            last_move["t"] = t
            add_event("move", {"x": x, "y": y})

    def on_click(x, y, button, pressed):
        if not recording["active"]:
            return
        if pressed:
            dragging["count"] += 1
        else:
            dragging["count"] = max(0, dragging["count"] - 1)
        add_event(
            "click",
            {"x": x, "y": y, "button": serialize_button(button), "pressed": pressed},
        )

    def on_scroll(x, y, dx, dy):
        if not recording["active"]:
            return
        add_event("scroll", {"x": x, "y": y, "dx": dx, "dy": dy})

    if args.open_entrar:
        entrar_path = Path(__file__).with_name("entrar.protheus1.py")
        if not entrar_path.exists():
            print(f"Nao encontrei {entrar_path}")
            return 1
        try:
            spec = importlib.util.spec_from_file_location("entrar_protheus1", entrar_path)
            if spec is None or spec.loader is None:
                print("Falha ao carregar entrar.protheus1.py.")
                return 1
            entrar = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(entrar)

            entrar_args = []
            if args.entrar_url:
                entrar_args += ["--url", args.entrar_url]
            if args.entrar_user:
                entrar_args += ["--user", args.entrar_user]
            if args.entrar_password:
                entrar_args += ["--password", args.entrar_password]
            if args.entrar_env:
                entrar_args += ["--env", args.entrar_env]
            if args.entrar_manual:
                entrar_args += ["--manual"]
            if args.entrar_headless:
                entrar_args += ["--headless"]
            if args.entrar_timeout and args.entrar_timeout > 0:
                entrar_args += ["--timeout", str(args.entrar_timeout)]

            parsed = entrar.parse_args(entrar_args)
            p, browser, _context, _page, _ok, code = entrar.run_login(parsed)
            if code != 0:
                return code
        except Exception as exc:
            print(f"Falha ao abrir Protheus via entrar.protheus1.py: {exc}")
            return 1

    print("Pressione F9 para iniciar a gravacao e F10 para finalizar.")
    with keyboard.Listener(on_press=on_press, on_release=on_release) as k_listener, mouse.Listener(
        on_move=on_move, on_click=on_click, on_scroll=on_scroll
    ) as m_listener:
        while not stop_event.is_set():
            time.sleep(0.1)
        k_listener.stop()
        m_listener.stop()

    if not events:
        print("Nenhum evento gravado.")
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if p:
            try:
                p.stop()
            except Exception:
                pass
        return 1

    generate_playback_py(events, output_path, args.start_delay)
    print(f"Macro salva em: {output_path}")

    if browser:
        try:
            browser.close()
        except Exception:
            pass
    if p:
        try:
            p.stop()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
