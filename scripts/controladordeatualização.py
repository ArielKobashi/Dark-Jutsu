import ctypes
import hashlib
import json
import importlib
import msvcrt
import os
import queue
import re
import shutil
import sys
import tempfile
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# Evita carga duplicada quando o arquivo roda como script (__main__) e tambem
# e importado por nome de modulo em outros pontos (ex.: executar_tudo.py).
if __name__ == "__main__":
    sys.modules.setdefault("controladordeatualização", sys.modules[__name__])

try:
    from pynput import keyboard as pynput_keyboard, mouse as pynput_mouse  # type: ignore
except Exception:
    pynput_keyboard = None
    pynput_mouse = None


if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
    BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", APP_DIR))
    APPDATA_DIR = Path(os.environ.get("APPDATA") or APP_DIR)
    PROJECT_ROOT = APPDATA_DIR / "Automus" / "complemento"
    LEGACY_PROJECT_ROOT = APP_DIR / "AutomusData"
    SCRIPT_DIR = PROJECT_ROOT / "scripts"
    BUNDLED_SCRIPT_DIR = BUNDLE_ROOT / "scripts"
else:
    SCRIPT_DIR = Path(__file__).resolve().parent
    BUNDLED_SCRIPT_DIR = SCRIPT_DIR
    PROJECT_ROOT = SCRIPT_DIR.parent
    LEGACY_PROJECT_ROOT = None
if LEGACY_PROJECT_ROOT and LEGACY_PROJECT_ROOT.exists() and not PROJECT_ROOT.exists():
    shutil.copytree(LEGACY_PROJECT_ROOT, PROJECT_ROOT, dirs_exist_ok=True)
PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
(PROJECT_ROOT / "downloads").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("AUTOMUS_PROJECT_ROOT", str(PROJECT_ROOT))
os.environ.setdefault("AUTOMUS_SCRIPT_DIR", str(SCRIPT_DIR))
os.environ.setdefault("AUTOMUS_BUNDLED_SCRIPT_DIR", str(BUNDLED_SCRIPT_DIR))
CONTROLLER_CONFIG_PATH = SCRIPT_DIR / "controlador_config.json"
STARTUP_BAT_NAME = "DarkJutsu_Controlador_Atualizacoes.bat"
APP_DISPLAY_NAME = "Automus"
APP_TITLE = "Automus | Controlador de Atualizações"


def _http_json(url: str, method: str = "GET", payload: Optional[dict] = None, timeout: float = 25.0):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url=url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else None
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Falha de rede: {exc}") from exc


def _extract_firebase_config() -> tuple[str, str]:
    for config_path in (SCRIPT_DIR / "firebase_config.json", BUNDLED_SCRIPT_DIR / "firebase_config.json"):
        if not config_path.exists():
            continue
        cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
        api_key = str(cfg.get("apiKey") or "").strip()
        db_url = str(cfg.get("databaseURL") or "").strip().rstrip("/")
        if api_key and db_url:
            return api_key, db_url
    index_candidates = [PROJECT_ROOT / "index.html", BUNDLE_ROOT / "index.html"] if getattr(sys, "frozen", False) else [PROJECT_ROOT / "index.html"]
    html = ""
    for candidate in index_candidates:
        if candidate.exists():
            html = candidate.read_text(encoding="utf-8", errors="replace")
            break
    if not html:
        raise RuntimeError("Configuração Firebase não encontrada no Automus.")
    api_match = re.search(r'apiKey:\s*"([^"]+)"', html)
    db_match = re.search(r'databaseURL:\s*"([^"]+)"', html)
    if not api_match or not db_match:
        raise RuntimeError("Firebase não encontrado no index.html.")
    return api_match.group(1), db_match.group(1).rstrip("/")


def _auth_admin_dark_jutsu(login: str, senha: str) -> dict:
    nick = (login or "").strip().lower()
    if not nick or not senha:
        raise RuntimeError("Informe login e senha.")
    email = nick if "@" in nick else f"{nick}@sistema.com"
    api_key, db_url = _extract_firebase_config()
    auth = _http_json(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}",
        method="POST",
        payload={"email": email, "password": senha, "returnSecureToken": True},
    )
    if not isinstance(auth, dict) or not auth.get("idToken") or not auth.get("localId"):
        raise RuntimeError("Login ou senha inválido.")
    uid = str(auth["localId"])
    token = str(auth["idToken"])
    usuario = _http_json(f"{db_url}/usuarios/{uid}.json?auth={token}", method="GET")
    if not isinstance(usuario, dict) or usuario.get("nivel") != "admin":
        raise RuntimeError("Acesso bloqueado: este login não tem permissão ADM.")
    return {"uid": uid, "email": email, "nickname": usuario.get("nickname") or nick, "idToken": token}


def _machine_fingerprint() -> str:
    parts = [
        os.environ.get("COMPUTERNAME", ""),
        os.environ.get("USERNAME", ""),
        os.environ.get("USERDOMAIN", ""),
    ]
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            parts.append(str(winreg.QueryValueEx(key, "MachineGuid")[0]))
    except Exception:
        pass
    raw = "|".join(parts).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def _machine_lock_hash() -> str:
    return hashlib.sha256(("Automus.Controlador|" + _machine_fingerprint()).encode("utf-8")).hexdigest()


def _apply_machine_lock(config: dict) -> dict:
    # Modo portátil: a pasta do Automus pode ser copiada para outro PC.
    # A proteção real fica no login ADM obrigatório antes de qualquer atualização.
    security = config.get("security")
    if not isinstance(security, dict):
        security = {}
    security.pop("machineLock", None)
    config.pop("securityLocked", None)
    config.pop("securityMessage", None)
    security.setdefault("portable", True)
    security["lastCheckedAt"] = datetime.now().isoformat(timespec="seconds")
    config["security"] = security
    return config


def _load_controller_config() -> dict:
    if not CONTROLLER_CONFIG_PATH.exists():
        return _apply_machine_lock({"horarios": [], "frequencia": "todos_os_dias", "vezesPorDia": 1, "iniciarComWindows": True})
    try:
        data = json.loads(CONTROLLER_CONFIG_PATH.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            return {"horarios": [], "frequencia": "todos_os_dias", "vezesPorDia": 1, "iniciarComWindows": True}
        data.setdefault("horarios", [])
        data.setdefault("frequencia", "todos_os_dias")
        data.setdefault("vezesPorDia", min(4, max(1, len(data.get("horarios") or []) or 1)))
        data.setdefault("iniciarComWindows", True)
        data.setdefault("historicoAtualizacoes", [])
        data.setdefault("usuariosAtualizacao", {})
        return _apply_machine_lock(data)
    except Exception:
        return _apply_machine_lock({"horarios": [], "frequencia": "todos_os_dias", "vezesPorDia": 1, "iniciarComWindows": True})


def _save_controller_config(config: dict):
    CONTROLLER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CONTROLLER_CONFIG_PATH.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(CONTROLLER_CONFIG_PATH)


def _startup_bat_path() -> Path:
    startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup / STARTUP_BAT_NAME


def _set_startup_enabled(enabled: bool):
    path = _startup_bat_path()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        pythonw = Path(sys.executable)
        if pythonw.name.lower() == "python.exe":
            candidate = pythonw.with_name("pythonw.exe")
            if candidate.exists():
                pythonw = candidate
        path.write_text(
            "@echo off\r\n"
            f'cd /d "{PROJECT_ROOT}"\r\n'
            f'start "" /min "{pythonw}" "{Path(sys.executable).resolve() if getattr(sys, "frozen", False) else Path(__file__).resolve()}" --background\r\n',
            encoding="utf-8",
        )
    elif path.exists():
        path.unlink()


class StopRequested(RuntimeError):
    pass


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _set_window_click_through(hwnd: int, enabled: bool = True):
    try:
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        exstyle = user32.GetWindowLongW(int(hwnd), GWL_EXSTYLE)
        if enabled:
            exstyle |= (WS_EX_LAYERED | WS_EX_TRANSPARENT)
        else:
            exstyle &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(int(hwnd), GWL_EXSTYLE, exstyle)
    except Exception:
        pass


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

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Automus.Controlador.Atualizacoes")
        except Exception:
            pass

        root = tk.Tk()
        root.title(APP_TITLE)
        root.geometry("576x672")
        root.minsize(560, 624)
        root.configure(bg="#0f172a")

        palette = {
            "bg": "#0f172a",
            "panel": "#111827",
            "panel2": "#182235",
            "text": "#e5e7eb",
            "muted": "#94a3b8",
            "accent": "#22c55e",
            "warn": "#f59e0b",
            "danger": "#ef4444",
            "line": "#334155",
        }

        def make_button(parent, text, command, bg=None, width=14, height=1):
            return tk.Button(
                parent,
                text=text,
                command=command,
                width=width,
                height=height,
                bg=bg or palette["panel2"],
                fg=palette["text"],
                activebackground=palette["accent"],
                activeforeground="#04130a",
                relief="flat",
                bd=0,
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
            )

        def build_config_icon(size=64):
            try:
                from PIL import Image, ImageDraw
                img = Image.new("RGBA", (size, size), (15, 23, 42, 0))
                draw = ImageDraw.Draw(img)
                cx = cy = size // 2
                outer = int(size * 0.34)
                inner = int(size * 0.18)
                tooth_w = max(3, size // 10)
                tooth_h = max(6, size // 7)
                for angle in range(0, 360, 45):
                    import math
                    rad = math.radians(angle)
                    x = cx + math.cos(rad) * outer
                    y = cy + math.sin(rad) * outer
                    draw.rounded_rectangle(
                        (x - tooth_w / 2, y - tooth_h / 2, x + tooth_w / 2, y + tooth_h / 2),
                        radius=2,
                        fill=(34, 197, 94, 255),
                    )
                draw.ellipse((cx - outer, cy - outer, cx + outer, cy + outer), fill=(34, 197, 94, 255))
                draw.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=(15, 23, 42, 255))
                draw.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), fill=(229, 231, 235, 255))
                return img
            except Exception:
                return None

        config_icon_image = build_config_icon(64)
        config_icon_photo = None
        if config_icon_image is not None:
            try:
                from PIL import ImageTk
                icon_path = Path(tempfile.gettempdir()) / "automus_controlador.ico"
                config_icon_image.save(icon_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
                root.iconbitmap(str(icon_path))
                config_icon_photo = ImageTk.PhotoImage(config_icon_image)
                root.iconphoto(True, config_icon_photo)
                root._config_icon_photo = config_icon_photo
                root._automus_icon_path = str(icon_path)
            except Exception:
                pass

        login_frame = tk.Frame(root, bg=palette["bg"])
        login_frame.pack(fill="both", expand=True)
        login_bg = tk.Canvas(login_frame, bg=palette["bg"], highlightthickness=0, bd=0)
        login_bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        def draw_login_background(event=None):
            login_bg.delete("all")
            w = max(1, login_bg.winfo_width())
            h = max(1, login_bg.winfo_height())
            login_bg.create_rectangle(0, 0, w, h, fill="#07111f", outline="")
            for i in range(0, w + 90, 90):
                login_bg.create_line(i, 0, max(0, i - 160), h, fill="#12314a", width=1)
            for y in range(42, h, 64):
                login_bg.create_line(0, y, w, y - 24, fill="#0c2539", width=1)
            for x, y, r in ((int(w * 0.18), int(h * 0.24), 74), (int(w * 0.82), int(h * 0.78), 96)):
                login_bg.create_oval(x - r, y - r, x + r, y + r, outline="#14532d", width=2)
                login_bg.create_oval(x - 5, y - 5, x + 5, y + 5, fill="#22c55e", outline="")
            login_bg.create_text(w // 2, int(h * 0.12), text="AUTOMUS", fill="#12314a", font=("Segoe UI", 38, "bold"))

        login_bg.bind("<Configure>", draw_login_background)
        login_card = tk.Frame(login_frame, bg=palette["panel"], highlightbackground=palette["line"], highlightthickness=1)
        login_card.place(relx=0.5, rely=0.53, anchor="center", width=380, height=330)
        if config_icon_photo is not None:
            tk.Label(login_card, image=config_icon_photo, bg=palette["panel"]).pack(pady=(18, 0))
        tk.Label(
            login_card,
            text=APP_DISPLAY_NAME,
            bg=palette["panel"],
            fg=palette["text"],
            font=("Segoe UI", 24, "bold"),
        ).pack(pady=(10 if config_icon_photo is not None else 28, 4))
        tk.Label(
            login_card,
            text="Controlador de atualizações",
            bg=palette["panel"],
            fg=palette["muted"],
            font=("Segoe UI", 10),
        ).pack(pady=(0, 18))
        login_var = tk.StringVar()
        senha_var = tk.StringVar()
        login_status = tk.StringVar(value="Entre com um login ADM do Dark Jutsu.")
        login_entry = tk.Entry(login_card, textvariable=login_var, bg="#020617", fg=palette["text"], insertbackground=palette["text"], relief="flat", font=("Segoe UI", 11))
        login_entry.pack(fill="x", padx=42, ipady=8, pady=(0, 10))
        login_entry.insert(0, "")
        senha_entry = tk.Entry(login_card, textvariable=senha_var, show="*", bg="#020617", fg=palette["text"], insertbackground=palette["text"], relief="flat", font=("Segoe UI", 11))
        senha_entry.pack(fill="x", padx=42, ipady=8, pady=(0, 12))

        main_frame = tk.Frame(root, bg=palette["bg"])

        def do_login(event=None):
            login_status.set("Validando permissão ADM...")
            try:
                admin = self._state.login_admin(login_var.get(), senha_var.get())
                login_frame.pack_forget()
                main_frame.pack(fill="both", expand=True)
                root.title(f"{APP_DISPLAY_NAME} | {admin.get('nickname')}")
                try:
                    root.after(0, refresh_schedule_ui)
                except Exception:
                    pass
            except Exception as exc:
                login_status.set(str(exc))
            return "break"

        make_button(login_card, "Entrar", do_login, bg=palette["accent"], width=28, height=1).pack(fill="x", padx=42, ipady=5)
        tk.Label(login_card, textvariable=login_status, bg=palette["panel"], fg=palette["muted"], font=("Segoe UI", 9), wraplength=330).pack(pady=(14, 0))
        senha_entry.bind("<Return>", do_login)
        login_entry.focus_set()

        header = tk.Frame(main_frame, bg=palette["bg"])
        header.pack(fill="x", padx=14, pady=(14, 10))
        if config_icon_photo is not None:
            tk.Label(header, image=config_icon_photo, bg=palette["bg"]).pack(side="left", padx=(0, 8))
        tk.Label(
            header,
            text=APP_TITLE,
            bg=palette["bg"],
            fg=palette["text"],
            font=("Segoe UI", 15, "bold"),
        ).pack(side="left")
        tk.Label(
            header,
            text="Sempre ativo",
            bg="#064e3b",
            fg="#bbf7d0",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=3,
        ).pack(side="right")

        buttons = tk.Frame(main_frame, bg=palette["panel"], highlightbackground=palette["line"], highlightthickness=1)
        buttons.pack(fill="x", padx=14, pady=(0, 8), ipady=5)

        pause_btn = make_button(
            buttons,
            text="Pausar (PauseBreak)",
            command=self._state.request_pause,
            width=14,
            height=1,
            bg=palette["warn"],
        )
        pause_btn.pack(side="left", padx=(0, 6))

        resume_btn = make_button(
            buttons,
            text="Retomar (F9 / R)",
            command=self._state.request_resume,
            width=13,
            height=1,
            bg=palette["accent"],
        )
        resume_btn.pack(side="left", padx=(0, 6))

        stop_btn = make_button(
            buttons,
            text="Parar (F10 / S)",
            command=self._state.request_stop,
            width=10,
            height=1,
            bg=palette["danger"],
        )
        stop_btn.pack(side="left")

        run_btn = make_button(
            buttons,
            text="Executar tudo",
            command=self._state.run_executar_tudo,
            width=13,
            height=1,
            bg="#2563eb",
        )
        run_btn.pack(side="left", padx=(6, 0))

        schedule_shell = tk.Frame(main_frame, bg=palette["panel"], highlightbackground=palette["line"], highlightthickness=1)
        schedule_shell.pack(fill="x", padx=14, pady=(0, 10))
        schedule_expanded = tk.BooleanVar(value=False)
        schedule_header_var = tk.StringVar(value="Agendamento  >")
        schedule_header = tk.Label(
            schedule_shell,
            textvariable=schedule_header_var,
            bg=palette["panel"],
            fg=palette["text"],
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            padx=10,
            pady=8,
            cursor="hand2",
        )
        schedule_header.pack(fill="x")

        schedule_frame = tk.Frame(schedule_shell, bg=palette["panel"])

        def toggle_schedule_section(event=None):
            if schedule_expanded.get():
                schedule_frame.pack_forget()
                schedule_expanded.set(False)
                schedule_header_var.set("Agendamento  >")
            else:
                schedule_frame.pack(fill="x", padx=10, pady=(0, 8))
                schedule_expanded.set(True)
                schedule_header_var.set("Agendamento  v")
            return "break"

        schedule_header.bind("<Button-1>", toggle_schedule_section)
        freq_row = tk.Frame(schedule_frame, bg=palette["panel"])
        freq_row.pack(fill="x", pady=(0, 8))
        tk.Label(freq_row, text="Frequência", bg=palette["panel"], fg=palette["muted"], font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        freq_label_map = {
            "todos_os_dias": "Todos os dias",
            "a_cada_2_dias": "A cada 2 dias",
        }
        freq_config = self._state.get_schedule_config().get("frequencia", "todos_os_dias")
        freq_var = tk.StringVar(value=freq_label_map.get(freq_config, "Todos os dias"))
        freq_menu = tk.OptionMenu(freq_row, freq_var, "Todos os dias", "A cada 2 dias")
        freq_menu.configure(bg="#020617", fg=palette["text"], activebackground=palette["panel2"], activeforeground=palette["text"], relief="flat", highlightthickness=0, width=16)
        freq_menu["menu"].configure(bg="#020617", fg=palette["text"])
        freq_menu.pack(side="left", padx=(0, 18))

        tk.Label(freq_row, text="Vezes por dia", bg=palette["panel"], fg=palette["muted"], font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        vezes_var = tk.IntVar(value=int(self._state.get_schedule_config().get("vezesPorDia", 1)))
        vezes_spin = tk.Spinbox(freq_row, from_=1, to=4, textvariable=vezes_var, width=4, bg="#020617", fg=palette["text"], buttonbackground=palette["panel2"], insertbackground=palette["text"], relief="flat")
        vezes_spin.pack(side="left", padx=(0, 18))

        horarios_frame = tk.Frame(schedule_frame, bg=palette["panel"])
        horarios_frame.pack(fill="x", pady=(0, 8))
        tk.Label(horarios_frame, text="Horários", bg=palette["panel"], fg=palette["muted"], font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        cfg_horarios = list(self._state.get_schedule_config().get("horarios") or [])
        horario_vars = []

        def refresh_schedule_ui():
            cfg = self._state.get_schedule_config()
            freq_var.set(freq_label_map.get(cfg.get("frequencia", "todos_os_dias"), "Todos os dias"))
            try:
                vezes_var.set(int(cfg.get("vezesPorDia", 1) or 1))
            except Exception:
                vezes_var.set(1)
            horarios_salvos = list(cfg.get("horarios") or [])
            for idx, var in enumerate(horario_vars):
                var.set(horarios_salvos[idx] if idx < len(horarios_salvos) else "")

        def aplicar_mascara_horario(var):
            updating = {"value": False}

            def format_digits(digits: str) -> str:
                if len(digits) == 3:
                    return f"0{digits[0]}:{digits[1:]}"
                if len(digits) == 4:
                    return f"{digits[:2]}:{digits[2:]}"
                return digits

            def on_change(*_):
                if updating["value"]:
                    return
                raw = var.get()
                digits = re.sub(r"\D", "", raw)[:4]
                formatted = format_digits(digits) if len(digits) == 4 else digits
                if formatted != raw:
                    updating["value"] = True
                    var.set(formatted)
                    updating["value"] = False

            var.trace_add("write", on_change)
            return format_digits

        for i in range(4):
            var = tk.StringVar(value=cfg_horarios[i] if i < len(cfg_horarios) else "")
            horario_vars.append(var)
            format_horario = aplicar_mascara_horario(var)
            entry = tk.Entry(horarios_frame, textvariable=var, bg="#020617", fg=palette["text"], insertbackground=palette["text"], relief="flat", font=("Segoe UI", 10), width=7, justify="center")
            entry.bind("<FocusOut>", lambda _event, v=var, fmt=format_horario: v.set(fmt(re.sub(r"\D", "", v.get())[:4])))
            entry.pack(side="left", ipady=6, padx=(0, 6))

        def save_schedule():
            try:
                self._state.set_schedule_config(
                    frequencia=freq_var.get(),
                    vezes_por_dia=int(vezes_var.get()),
                    horarios=[v.get() for v in horario_vars],
                )
            except Exception as exc:
                emit_status(str(exc), level="WARNING")

        make_button(freq_row, "Salvar", save_schedule, bg="#2563eb", width=12, height=1).pack(side="right")

        startup_var = tk.BooleanVar(value=bool(self._state.config.get("iniciarComWindows")))

        def toggle_startup():
            try:
                self._state.set_startup(startup_var.get())
            except Exception as exc:
                emit_status(f"Falha ao ajustar inicialização: {exc}", level="ERROR")

        startup_chk = tk.Checkbutton(
            schedule_frame,
            text="Iniciar com o Windows",
            variable=startup_var,
            command=toggle_startup,
            bg=palette["panel"],
            fg=palette["text"],
            selectcolor="#020617",
            activebackground=palette["panel"],
            activeforeground=palette["text"],
            font=("Segoe UI", 9, "bold"),
        )
        startup_chk.pack(side="left")

        macro_shell = tk.Frame(main_frame, bg=palette["panel"], highlightbackground=palette["line"], highlightthickness=1)
        macro_shell.pack(fill="x", padx=14, pady=(0, 10))
        macro_expanded = tk.BooleanVar(value=False)
        macro_header_var = tk.StringVar(value="Macros separadas  >")
        macro_header = tk.Label(
            macro_shell,
            textvariable=macro_header_var,
            bg=palette["panel"],
            fg=palette["text"],
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            padx=10,
            pady=8,
            cursor="hand2",
        )
        macro_header.pack(fill="x")

        macro_exec_frame = tk.Frame(macro_shell, bg=palette["panel"])

        def toggle_macro_section(event=None):
            if macro_expanded.get():
                macro_exec_frame.pack_forget()
                macro_expanded.set(False)
                macro_header_var.set("Macros separadas  >")
            else:
                macro_exec_frame.pack(fill="x", padx=8, pady=(0, 8))
                macro_expanded.set(True)
                macro_header_var.set("Macros separadas  v")
            return "break"

        macro_header.bind("<Button-1>", toggle_macro_section)

        macro_exec_row1 = tk.Frame(macro_exec_frame, bg=palette["panel"])
        macro_exec_row1.pack(fill="x", pady=(0, 4))
        macro_exec_row2 = tk.Frame(macro_exec_frame, bg=palette["panel"])
        macro_exec_row2.pack(fill="x")
        macro_exec_row3 = tk.Frame(macro_exec_frame, bg=palette["panel"])
        macro_exec_row3.pack(fill="x", pady=(4, 0))

        macro_buttons = [
            ("Macro 1", "macro_001.py"),
            ("Macro 2", "macro_002.py"),
            ("Macro 3", "macro_003.py"),
            ("Macro 4", "macro_004.py"),
            ("Macro 5", "macro_005.py"),
            ("Macro 12", "macro_012.py"),
        ]

        for index, (label, filename) in enumerate(macro_buttons):
            if index < 3:
                parent = macro_exec_row1
            elif index < 6:
                parent = macro_exec_row2
            else:
                parent = macro_exec_row3
            button = make_button(
                parent,
                text=label,
                command=lambda name=filename: self._state.run_macro_file(name),
                width=14,
                height=1,
            )
            button.pack(side="left", padx=(0, 6 if index % 3 != 2 else 0))

        overlay = tk.Toplevel(root)
        overlay.title("Macro atual")
        overlay_width = 340
        overlay_height = 118
        screen_w = overlay.winfo_screenwidth()
        x_top_center = max(0, int((screen_w - overlay_width) / 2))
        y_top = 12
        overlay.geometry(f"{overlay_width}x{overlay_height}+{x_top_center}+{y_top}")
        overlay.resizable(False, False)
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.30)
        try:
            overlay.configure(bg="#111827")
        except Exception:
            pass
        overlay.protocol("WM_DELETE_WINDOW", lambda: None)

        overlay_frame = tk.Frame(overlay, bg="#111827", highlightbackground="#f59e0b", highlightthickness=1)
        overlay_frame.pack(fill="both", expand=True)

        overlay_macro_var = tk.StringVar(value="Macro atual: aguardando início")
        overlay_action_var = tk.StringVar(value="Ação atual: --")

        overlay_macro_label = tk.Label(
            overlay_frame,
            textvariable=overlay_macro_var,
            anchor="w",
            justify="left",
            padx=8,
            pady=3,
            fg="white",
            bg="#111827",
        )
        overlay_macro_label.pack(fill="x")

        overlay_action_label = tk.Label(
            overlay_frame,
            textvariable=overlay_action_var,
            anchor="w",
            justify="left",
            padx=8,
            pady=2,
            fg="#cbd5e1",
            bg="#111827",
        )
        overlay_action_label.pack(fill="x")

        overlay_buttons = tk.Frame(overlay_frame, bg="#111827")
        overlay_buttons.pack(fill="x", padx=8, pady=(2, 6))

        overlay_pause_btn = tk.Button(
            overlay_buttons,
            text="Pausar",
            command=self._state.request_pause,
            width=10,
            height=1,
        )
        overlay_pause_btn.pack(side="left", padx=(0, 6))

        overlay_resume_btn = tk.Button(
            overlay_buttons,
            text="Retomar",
            command=self._state.request_resume,
            width=10,
            height=1,
        )
        overlay_resume_btn.pack(side="left", padx=(0, 6))

        overlay_stop_btn = tk.Button(
            overlay_buttons,
            text="Parar",
            command=self._state.request_stop,
            width=10,
            height=1,
        )
        overlay_stop_btn.pack(side="left")
        overlay.update_idletasks()
        _set_window_click_through(overlay.winfo_id(), enabled=True)
        overlay.withdraw()

        pixel_buttons = tk.Frame(main_frame, bg=palette["bg"])
        pixel_buttons.pack(fill="x", padx=14, pady=(0, 6))

        pixel_on_btn = make_button(
            pixel_buttons,
            text="Ativar identificador (Espaço captura)",
            command=self._state.activate_pixel_identifier,
            width=30,
            height=1,
            bg="#334155",
        )
        pixel_on_btn.pack(side="left", padx=(0, 6))

        pixel_off_btn = make_button(
            pixel_buttons,
            text="Desativar identificador",
            command=self._state.deactivate_pixel_identifier,
            width=22,
            height=1,
            bg="#334155",
        )
        pixel_off_btn.pack(side="left")

        totvs_capture_btn = make_button(
            main_frame,
            text="Capturar referência TOTVS (F6)",
            command=self._state.start_totvs_news_reference_capture,
            width=32,
            height=1,
            bg="#334155",
        )
        totvs_capture_btn.pack(fill="x", padx=14, pady=(2, 3))

        totvs_test_btn = make_button(
            main_frame,
            text="Verificar TOTVS (F7)",
            command=self._state.start_totvs_news_test,
            width=26,
            height=1,
            bg="#334155",
        )
        totvs_test_btn.pack(fill="x", padx=14, pady=(2, 3))

        totvs_test_var = tk.StringVar(value="TOTVS News | aguardando teste")
        totvs_test_label = tk.Label(
            main_frame,
            textvariable=totvs_test_var,
            anchor="w",
            justify="left",
            padx=8,
            pady=4,
            fg="white",
            bg="#666666",
        )
        totvs_test_label.pack(fill="x", padx=14, pady=(0, 6))

        live_pixel_var = tk.StringVar(value="PIXEL AO VIVO | desativado")
        live_pixel_label = tk.Label(
            main_frame,
            textvariable=live_pixel_var,
            anchor="w",
            justify="left",
            bg=palette["bg"],
            fg=palette["muted"],
        )
        live_pixel_label.pack(fill="x", padx=14, pady=(0, 4))

        history_shell = tk.Frame(main_frame, bg=palette["panel"], highlightbackground=palette["line"], highlightthickness=1)
        history_shell.pack(fill="x", padx=14, pady=(0, 6))
        history_expanded = tk.BooleanVar(value=False)
        history_header_var = tk.StringVar(value="Histórico de atualização  >")
        history_header = tk.Label(
            history_shell,
            textvariable=history_header_var,
            bg=palette["panel"],
            fg=palette["text"],
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            padx=10,
            pady=7,
            cursor="hand2",
        )
        history_header.pack(fill="x")

        history_frame = tk.Frame(history_shell, bg=palette["panel"])
        history_var = tk.StringVar(value="\n".join(self._state.get_history_lines(limit=3)))
        history_label = tk.Label(
            history_frame,
            textvariable=history_var,
            bg=palette["panel"],
            fg=palette["muted"],
            anchor="w",
            justify="left",
            font=("Segoe UI", 8),
        )
        history_label.pack(fill="x", padx=8, pady=(0, 7))

        def toggle_history_section(event=None):
            if history_expanded.get():
                history_frame.pack_forget()
                history_expanded.set(False)
                history_header_var.set("Histórico de atualização  >")
            else:
                history_frame.pack(fill="x")
                history_expanded.set(True)
                history_header_var.set("Histórico de atualização  v")
            return "break"

        history_header.bind("<Button-1>", toggle_history_section)

        log = scrolledtext.ScrolledText(main_frame, wrap="word", height=18, state="disabled", bg="#020617", fg=palette["text"], insertbackground=palette["text"], relief="flat")
        log.pack(fill="both", expand=True, padx=14, pady=(4, 14))
        try:
            current_font = tkfont.Font(font=log.cget("font"))
            # Tamanho compacto e legivel para as mensagens de status.
            current_font.configure(size=8, weight="bold")
            log.configure(font=current_font)
            hud_font = tkfont.Font(font=overlay_macro_label.cget("font"))
            hud_font.configure(size=9, weight="bold")
            overlay_macro_label.configure(font=hud_font)
            overlay_action_label.configure(font=hud_font)
            live_font = tkfont.Font(font=live_pixel_label.cget("font"))
            live_font.configure(size=9, weight="bold")
            live_pixel_label.configure(font=live_font)
        except Exception:
            pass

        def trigger_totvs_test(event=None):
            self._state.start_totvs_news_test()
            return "break"

        def trigger_totvs_capture(event=None):
            self._state.start_totvs_news_reference_capture()
            return "break"

        root.bind("<F6>", trigger_totvs_capture)
        root.bind("<F7>", trigger_totvs_test)

        tray_icon_holder = {"icon": None}

        def bring_to_front():
            try:
                icon = tray_icon_holder.get("icon")
                if icon is not None:
                    try:
                        icon.stop()
                    except Exception:
                        pass
                    tray_icon_holder["icon"] = None
                    self._state.notify_callback = None
                root.deiconify()
                root.lift()
                # Pulso de "sempre no topo" para garantir foco visual imediato.
                root.attributes("-topmost", True)
                root.after(350, lambda: root.attributes("-topmost", False))
                root.focus_force()
            except Exception:
                pass

        def ensure_tray_icon():
            if tray_icon_holder.get("icon") is not None:
                return True
            if config_icon_image is None:
                return False
            try:
                import pystray

                def open_from_tray(_icon=None, _item=None):
                    root.after(0, bring_to_front)

                icon = pystray.Icon(
                    "automus_controlador",
                    config_icon_image,
                    self._state.get_tray_tooltip(),
                    menu=pystray.Menu(
                        pystray.MenuItem("Abrir Automus", open_from_tray, default=True),
                    ),
                )
                tray_icon_holder["icon"] = icon
                self._state.notify_callback = lambda title, message: icon.notify(message, title)
                threading.Thread(target=icon.run, name="dark-jutsu-tray", daemon=True).start()
                return True
            except Exception as exc:
                emit_status(f"Não foi possível criar o ícone em segundo plano: {exc}", level="WARNING")
                tray_icon_holder["icon"] = None
                return False

        def on_close():
            try:
                if ensure_tray_icon():
                    root.withdraw()
                    try:
                        tray_icon_holder["icon"].title = self._state.get_tray_tooltip()
                    except Exception:
                        pass
                    emit_status("Interface enviada para apps em segundo plano. Clique no ícone de configuração para abrir novamente.")
                else:
                    root.iconify()
                    emit_status("Interface minimizada. O controlador continua ativo em segundo plano.")
            except Exception:
                pass

        def pump():
            icon = tray_icon_holder.get("icon")
            if icon is not None:
                try:
                    icon.title = self._state.get_tray_tooltip()
                except Exception:
                    pass

            macro_text, action_text, window_title = self._state.get_macro_hud_status()
            overlay_macro_var.set(macro_text)
            overlay_action_var.set(action_text)
            overlay.title(window_title)

            history_var.set("\n".join(self._state.get_history_lines(limit=3)))

            test_text, test_bg = self._state.get_totvs_news_status()
            totvs_test_var.set(test_text)
            totvs_test_label.configure(bg=test_bg)

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
                log.insert("end", f"{line}\n")
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
        self.macro_display_name: Optional[str] = None
        self.total_events: int = 0
        self.prev_event_idx: int = 0
        self.next_event_idx: int = 1
        self.pixel_identifier_active = False
        self.last_pixel_capture_at = 0.0
        self.totvs_news_reference_loaded = False
        self.totvs_news_test_running = False
        self.totvs_news_test_progress = "aguardando teste"
        self.totvs_news_last_result: Optional[bool] = None
        self.totvs_news_last_score = 0
        self.totvs_news_last_details = ""
        self.automation_running = False
        self.mouse_lock_enabled = False
        self.locked_mouse_pos: Optional[tuple] = None
        self._mouse_repositioning = False
        self.authenticated_admin: Optional[dict] = None
        self.config = _load_controller_config()
        self.scheduler_thread: Optional[threading.Thread] = None
        self.scheduler_stop = threading.Event()
        self.last_schedule_run: dict[str, str] = {}
        self.warned_schedule: set[str] = set()
        self.history_version = 0
        self.notify_callback = None

    def ensure_window(self):
        if self.window is None:
            self.window = _ControlWindow(self)
        self.ensure_scheduler()

    def login_admin(self, login: str, senha: str) -> dict:
        admin = _auth_admin_dark_jutsu(login, senha)
        with self.lock:
            self.authenticated_admin = admin
        self._ensure_user_schedule(admin)
        emit_status(f"Interface liberada para ADM: {admin.get('nickname')}.")
        return admin

    def _current_user_key(self) -> Optional[str]:
        admin = self.authenticated_admin or {}
        key = admin.get("uid") or admin.get("email") or admin.get("nickname")
        return str(key) if key else None

    def _base_schedule_config(self) -> dict:
        horarios = self.config.get("horarios") if isinstance(self.config, dict) else []
        return {
            "frequencia": self.config.get("frequencia", "todos_os_dias"),
            "vezesPorDia": min(4, max(1, int(self.config.get("vezesPorDia", 1) or 1))),
            "horarios": list(horarios or [])[:4],
            "inicioAgendamento": self.config.get("inicioAgendamento") or datetime.now().strftime("%Y-%m-%d"),
        }

    def _user_schedules(self) -> dict:
        schedules = self.config.get("usuariosAtualizacao")
        if not isinstance(schedules, dict):
            schedules = {}
            self.config["usuariosAtualizacao"] = schedules
        return schedules

    def _ensure_user_schedule(self, admin: dict):
        key = str(admin.get("uid") or admin.get("email") or admin.get("nickname") or "")
        if not key:
            return
        schedules = self._user_schedules()
        if key not in schedules or not isinstance(schedules.get(key), dict):
            schedules[key] = {
                **self._base_schedule_config(),
                "usuario": admin.get("nickname") or admin.get("email") or key,
            }
            _save_controller_config(self.config)

    def get_schedule_config(self) -> dict:
        key = self._current_user_key()
        if key:
            cfg = self._user_schedules().get(key)
            if isinstance(cfg, dict):
                horarios = cfg.get("horarios") if isinstance(cfg.get("horarios"), list) else []
                return {
                    "frequencia": cfg.get("frequencia", "todos_os_dias"),
                    "vezesPorDia": min(4, max(1, int(cfg.get("vezesPorDia", 1) or 1))),
                    "horarios": list(horarios or [])[:4],
                    "inicioAgendamento": cfg.get("inicioAgendamento") or datetime.now().strftime("%Y-%m-%d"),
                    "usuario": cfg.get("usuario") or (self.authenticated_admin or {}).get("nickname") or key,
                }
        return self._base_schedule_config()

    def _iter_schedule_configs(self) -> list[dict]:
        key = self._current_user_key()
        if not key:
            return []
        schedules = []
        users = self._user_schedules()
        cfg = users.get(key)
        if isinstance(cfg, dict):
            item = dict(cfg)
            item.setdefault("usuario", cfg.get("usuario") or (self.authenticated_admin or {}).get("nickname") or key)
            schedules.append(item)
        return schedules

    def _next_for_config(self, cfg: dict, now: datetime) -> Optional[datetime]:
        horarios = cfg.get("horarios") if isinstance(cfg.get("horarios"), list) else []
        if not horarios:
            return None
        freq = cfg.get("frequencia", "todos_os_dias")
        start_raw = cfg.get("inicioAgendamento") or now.strftime("%Y-%m-%d")
        try:
            start_date = datetime.strptime(start_raw, "%Y-%m-%d").date()
        except Exception:
            start_date = now.date()
        candidates: list[datetime] = []
        for offset in range(0, 8):
            day = now.date() + timedelta(days=offset)
            if freq == "a_cada_2_dias" and ((day - start_date).days % 2) != 0:
                continue
            for horario in horarios:
                try:
                    hh, mm = [int(part) for part in str(horario).split(":", 1)]
                    candidate = datetime.combine(day, datetime.min.time()).replace(hour=hh, minute=mm)
                except Exception:
                    continue
                if candidate > now:
                    candidates.append(candidate)
        return min(candidates) if candidates else None

    def get_next_update_datetime(self, now: Optional[datetime] = None) -> Optional[datetime]:
        now = now or datetime.now()
        candidates = [dt for cfg in self._iter_schedule_configs() if (dt := self._next_for_config(cfg, now)) is not None]
        return min(candidates) if candidates else None

    def get_tray_tooltip(self) -> str:
        next_dt = self.get_next_update_datetime()
        if next_dt is None:
            if self.authenticated_admin is None:
                return "Proxima atualização: login pendente"
            return "Proxima atualização: sem horário"
        delta = max(0, int((next_dt - datetime.now()).total_seconds()))
        hours, rem = divmod(delta, 3600)
        minutes, seconds = divmod(rem, 60)
        return f"Proxima atualização: {hours:02d}:{minutes:02d}:{seconds:02d}"

    def notify_user(self, title: str, message: str):
        callback = self.notify_callback
        if callable(callback):
            try:
                callback(title, message)
            except Exception:
                pass

    def record_update_history(self, status: str, origem: str = "manual", usuario: Optional[str] = None) -> dict:
        usuario = usuario or (self.authenticated_admin or {}).get("nickname") or "Automus"
        entry = {
            "id": str(int(time.time() * 1000)),
            "usuario": usuario,
            "status": status,
            "origem": origem,
            "quando": datetime.now().isoformat(timespec="seconds"),
        }
        historico = self.config.get("historicoAtualizacoes")
        if not isinstance(historico, list):
            historico = []
        historico.insert(0, entry)
        self.config["historicoAtualizacoes"] = historico[:20]
        self.history_version += 1
        _save_controller_config(self.config)
        return entry

    def finish_update_history(self, entry: Optional[dict], status: str):
        if not entry:
            return
        historico = self.config.get("historicoAtualizacoes")
        if not isinstance(historico, list):
            return
        for item in historico:
            if isinstance(item, dict) and item.get("id") == entry.get("id"):
                item["status"] = status
                item["finalizadoEm"] = datetime.now().isoformat(timespec="seconds")
                break
        self.history_version += 1
        _save_controller_config(self.config)

    def get_history_lines(self, limit: int = 3) -> list[str]:
        historico = self.config.get("historicoAtualizacoes")
        if not isinstance(historico, list) or not historico:
            return ["Nenhuma atualização registrada ainda."]
        lines = []
        for item in historico[:limit]:
            if not isinstance(item, dict):
                continue
            try:
                quando = datetime.fromisoformat(str(item.get("quando"))).strftime("%d/%m %H:%M")
            except Exception:
                quando = "-"
            usuario = item.get("usuario") or "Automus"
            status = item.get("status") or "ativou"
            origem = item.get("origem") or "manual"
            lines.append(f"{quando} | {usuario} | {origem} | {status}")
        return lines or ["Nenhuma atualização registrada ainda."]

    def set_schedule_config(self, frequencia: str, vezes_por_dia: int, horarios: list[str]):
        freq_raw = (frequencia or "").strip().lower()
        freq_map = {
            "todos os dias": "todos_os_dias",
            "todos_os_dias": "todos_os_dias",
            "a cada 2 dias": "a_cada_2_dias",
            "a_cada_2_dias": "a_cada_2_dias",
        }
        freq = freq_map.get(freq_raw)
        if freq is None:
            raise RuntimeError("Frequência inválida.")

        vezes = min(4, max(1, int(vezes_por_dia or 1)))
        normalizados: list[str] = []
        for raw_value in horarios:
            raw = str(raw_value or "").strip()
            if not raw:
                continue
            digits = re.sub(r"\D", "", raw)
            if ":" not in raw and len(digits) == 3:
                raw = f"0{digits[0]}:{digits[1:]}"
            elif ":" not in raw and len(digits) == 4:
                raw = f"{digits[:2]}:{digits[2:]}"
            match = re.match(r"^(\d{1,2}):(\d{2})$", raw)
            if not match:
                raise RuntimeError(f"Horário inválido: {raw}. Use HH:MM.")
            hh = int(match.group(1))
            mm = int(match.group(2))
            if hh > 23 or mm > 59:
                raise RuntimeError(f"Horário inválido: {raw}. Use HH:MM.")
            normalizados.append(f"{hh:02d}:{mm:02d}")

        normalizados = sorted(set(normalizados))[:vezes]
        if len(normalizados) < vezes:
            raise RuntimeError(f"Informe {vezes} horário(s) válido(s).")

        self.config["frequencia"] = freq
        self.config["vezesPorDia"] = vezes
        self.config["horarios"] = normalizados
        self.config.setdefault("inicioAgendamento", datetime.now().strftime("%Y-%m-%d"))
        key = self._current_user_key()
        if key:
            admin = self.authenticated_admin or {}
            self._user_schedules()[key] = {
                "frequencia": freq,
                "vezesPorDia": vezes,
                "horarios": normalizados,
                "inicioAgendamento": datetime.now().strftime("%Y-%m-%d"),
                "usuario": admin.get("nickname") or admin.get("email") or key,
            }
        _save_controller_config(self.config)
        freq_txt = "todos os dias" if freq == "todos_os_dias" else "a cada 2 dias"
        emit_status(f"Agendamento salvo: {freq_txt}, {vezes} vez(es) por dia, horários {', '.join(normalizados)}.")

    def set_startup(self, enabled: bool):
        _set_startup_enabled(enabled)
        self.config["iniciarComWindows"] = bool(enabled)
        _save_controller_config(self.config)
        emit_status("Inicialização com o Windows ativada." if enabled else "Inicialização com o Windows desativada.")

    def ensure_scheduler(self):
        if self.scheduler_thread is not None:
            return
        if self.config.get("iniciarComWindows"):
            try:
                _set_startup_enabled(True)
            except Exception as exc:
                emit_status(f"Falha ao registrar inicialização com o Windows: {exc}", level="WARNING")
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, name="dark-jutsu-scheduler", daemon=True)
        self.scheduler_thread.start()

    def _scheduler_loop(self):
        while not self.scheduler_stop.is_set():
            try:
                now = datetime.now()
                current = now.strftime("%H:%M")
                today = now.strftime("%Y-%m-%d")
                due_runs: list[dict] = []

                if self.authenticated_admin is None:
                    self.scheduler_stop.wait(20)
                    continue

                for cfg in self._iter_schedule_configs():
                    horarios = cfg.get("horarios") if isinstance(cfg.get("horarios"), list) else []
                    should_run_today = True
                    if cfg.get("frequencia") == "a_cada_2_dias":
                        start_raw = cfg.get("inicioAgendamento") or today
                        try:
                            start_dt = datetime.strptime(start_raw, "%Y-%m-%d").date()
                        except Exception:
                            start_dt = now.date()
                        should_run_today = ((now.date() - start_dt).days % 2) == 0

                    next_dt = self._next_for_config(cfg, now - timedelta(seconds=1))
                    if next_dt is not None:
                        seconds_to_next = int((next_dt - now).total_seconds())
                        for minutes_before in (10, 5):
                            target_seconds = minutes_before * 60
                            usuario = cfg.get("usuario") or "Automus"
                            warn_key = f"{usuario}|{next_dt.strftime('%Y-%m-%d %H:%M')}|{minutes_before}"
                            if 0 <= seconds_to_next <= target_seconds and warn_key not in self.warned_schedule:
                                self.warned_schedule.add(warn_key)
                                emit_status(
                                    f"Aviso: haverá uma atualização do {APP_DISPLAY_NAME} em {minutes_before} minutos. Prepare-se.",
                                    level="WARNING",
                                )
                                self.notify_user(
                                    f"{APP_DISPLAY_NAME}: atualização em {minutes_before} minutos",
                                    "Prepare-se para a atualização programada.",
                                )

                    if should_run_today and current in horarios:
                        usuario = cfg.get("usuario") or "Automus"
                        run_key = f"{usuario}|{today}|{current}"
                        if self.last_schedule_run.get(run_key) != "done":
                            due_runs.append({"key": run_key, "usuario": usuario, "horario": current})

                if due_runs:
                    selected = due_runs[0]
                    self.last_schedule_run[selected["key"]] = "done"
                    emit_status(f"Horário programado atingido ({selected['horario']}). Iniciando atualização.")
                    self.run_executar_tudo(origem=f"agendada {selected['horario']}", usuario=selected["usuario"])
            except Exception as exc:
                emit_status(f"Falha no agendador: {exc}", level="ERROR")
            self.scheduler_stop.wait(20)

    def _show_window_now(self):
        if self.window is not None:
            self.window.request_attention()

    def _control_window_is_foreground(self) -> bool:
        title = _normalize_screen_text(_get_foreground_window_title())
        return "controles da macro" in title

    def _minimize_window_now(self):
        if self.window is not None:
            self.window.request_minimize()

    def ensure_listener(self):
        if self.listener is not None or pynput_keyboard is None:
            return

        def on_press(key):
            if key == pynput_keyboard.Key.pause:
                self.request_pause()
                return
            if key == pynput_keyboard.Key.f6:
                self.start_totvs_news_reference_capture()
            elif key == pynput_keyboard.Key.f7:
                self.start_totvs_news_test()
            elif key == pynput_keyboard.Key.f8:
                self.request_pause()
            elif key == pynput_keyboard.Key.f9:
                self.request_resume()
            elif key == pynput_keyboard.Key.f10:
                self.request_stop()
            elif key == pynput_keyboard.Key.f12:
                self._show_window_now()
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

    def trigger_dark_jutsu_reset_shortcut(self):
        if pynput_keyboard is None:
            emit_status(
                "Não foi possível acionar o reset do Dark Jutsu: pynput keyboard indisponível.",
                level="WARNING",
            )
            return
        try:
            kb = pynput_keyboard.Controller()
            kb.press(pynput_keyboard.Key.ctrl_l)
            kb.press(pynput_keyboard.Key.alt_l)
            kb.press("r")
            kb.release("r")
            kb.release(pynput_keyboard.Key.alt_l)
            kb.release(pynput_keyboard.Key.ctrl_l)
            emit_status(
                "Atalho de reset enviado (Ctrl+Alt+R). Com o Dark Jutsu em foco, o rollback será executado.",
                level="INFO",
            )
        except Exception as exc:
            emit_status(
                f"Falha ao enviar atalho de reset do Dark Jutsu: {exc}",
                level="WARNING",
            )

    def set_locked_mouse_position(self, x: int, y: int):
        with self.lock:
            if not self.mouse_lock_enabled:
                return
            self.locked_mouse_pos = (int(x), int(y))

    def set_macro_context(self, macro_name: str, total_events: int):
        with self.lock:
            self.macro_name = macro_name
            match = re.search(r"(\d+)$", macro_name or "")
            self.macro_display_name = str(int(match.group(1))) if match else macro_name
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
            self.macro_display_name = None
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

    def current_pause_text(self) -> str:
        with self.lock:
            digits = self._digits()
            action_txt = f"# {self.next_event_idx:0{digits}d}"
            macro_txt = self.macro_display_name or self.macro_name or "?"
            return f"na ação:{action_txt} da macro:{macro_txt}"

    def get_macro_hud_status(self):
        with self.lock:
            macro_name = self.macro_name or "aguardando inicio"
            if self.stop_requested:
                state = "parado"
            elif self.paused:
                state = "pausado"
            elif self.automation_running:
                state = "executando"
            else:
                state = "aguardando"

            macro_text = f"Macro atual: {macro_name}.py" if self.macro_name else "Macro atual: aguardando início"
            if self.total_events > 0:
                digits = self._digits()
                action_text = f"Ação atual: #{self.next_event_idx:0{digits}d}/{self.total_events:0{digits}d} | Estado: {state}"
            else:
                action_text = f"Ação atual: -- | Estado: {state}"

            title = f"Controles da Macro | {macro_name}.py | {state}" if self.macro_name else f"Controles da Macro | {state}"
            return macro_text, action_text, title

    def stop_message(self) -> str:
        return f"Parada solicitada. Encerrando macro. Posicao atual: {self.current_between_text()}."

    def request_pause(self):
        with self.lock:
            if self.paused:
                return
            self.paused = True
        self._show_window_now()
        emit_status(
            f"Atualização pausada {self.current_pause_text()}. "
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
                "Janela fechada. Parando macro e encerrando execução imediatamente.",
                level="WARNING",
            )

    def _prepare_new_run(self):
        with self.lock:
            self.paused = False
            self.stop_requested = False
            self.prev_event_idx = 0
            self.next_event_idx = 1

    def _start_worker(self, worker_name: str, target):
        with self.lock:
            if self.authenticated_admin is None:
                self._show_window_now()
                emit_status("Login ADM necessário. A atualização não será iniciada sem usuário de sessão.", level="WARNING")
                return
            if self.automation_running:
                self._show_window_now()
                emit_status("Automação já está em execução.")
                return
            self.automation_running = True

        self._show_window_now()
        self._prepare_new_run()
        thread = threading.Thread(target=target, name=worker_name, daemon=True)
        thread.start()

    def run_macro_file(self, macro_filename: str):
        macro_filename = str(macro_filename)
        worker_name = f"macro-worker-{Path(macro_filename).stem}"
        self._start_worker(
            worker_name,
            lambda: self._run_single_macro_worker(macro_filename),
        )

    def run_executar_tudo(self, origem: str = "manual", usuario: Optional[str] = None):
        self._start_worker(
            "executar-tudo-worker",
            lambda: self._run_executar_tudo_worker(origem, usuario),
        )

    def _run_single_macro_worker(self, macro_filename: str):
        macro_path = BUNDLED_SCRIPT_DIR / macro_filename
        try:
            if not macro_path.exists():
                raise FileNotFoundError(f"Não encontrei {macro_path}")
            if macro_path.name.lower() == "macro_012.py":
                emit_status("Iniciando Macro 12 com verificador de azuis e mata185.xlsx mais recente...")
                mod = importlib.import_module("executar_tudo")
                if not hasattr(mod, "main"):
                    raise RuntimeError("executar_tudo.py nao possui funcao main().")
                result = mod.main("macro_012.py", modo_atualizacao="nivel1")
                if result is False:
                    raise RuntimeError("Macro 12 com verificador nao completou.")
                return
            emit_status(f"Iniciando {macro_path.name} pelo controlador...")
            spec = importlib.util.spec_from_file_location(macro_path.stem, macro_path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Falha ao carregar {macro_path}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not hasattr(mod, "play"):
                raise RuntimeError(f"{macro_path.name} não possui função play().")
            mod.play()
        except Exception as exc:
            emit_status(f"Falha ao executar {macro_path.name}: {exc}", level="ERROR")
        finally:
            self.deactivate_mouse_lock()
            with self.lock:
                self.automation_running = False
            emit_status(f"Execução de {macro_path.name} finalizada.")

    def _run_executar_tudo_worker(self, origem: str = "manual", usuario: Optional[str] = None):
        history_entry = self.record_update_history("ativou", origem=origem, usuario=usuario)
        completed = False
        try:
            emit_status("Iniciando executar_tudo.py pelo controlador...")
            mod = importlib.import_module("executar_tudo")
            if not hasattr(mod, "main"):
                raise RuntimeError("executar_tudo.py não possui função main().")
            auth = self.authenticated_admin or {}
            result = mod.main(
                automus_auth={
                    "idToken": auth.get("idToken"),
                    "email": auth.get("email"),
                    "nickname": auth.get("nickname"),
                }
            )
            completed = result is not False
        except Exception as exc:
            emit_status(f"Falha ao executar executar_tudo.py: {exc}", level="ERROR")
        finally:
            self.deactivate_mouse_lock()
            with self.lock:
                self.automation_running = False
            self.finish_update_history(history_entry, "concluiu" if completed else "ativou e não completou")
            emit_status("Execução do executar_tudo.py finalizada.")

    def activate_pixel_identifier(self):
        with self.lock:
            if self.pixel_identifier_active:
                return
            self.pixel_identifier_active = True
        self._show_window_now()
        emit_status(
            "Identificador de pixel ativado. "
            "Pressione Espaço para capturar o pixel atual do cursor."
        )

    def deactivate_pixel_identifier(self):
        with self.lock:
            if not self.pixel_identifier_active:
                return
            self.pixel_identifier_active = False
        self._show_window_now()
        emit_status("Identificador de pixel desativado.")

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

    def start_totvs_news_reference_capture(self):
        self._show_window_now()
        with self.lock:
            if self.totvs_news_test_running:
                return
            self.totvs_news_test_running = True
            self.totvs_news_test_progress = "capturando referência"
            self.totvs_news_last_result = None
            self.totvs_news_last_details = ""
            self.totvs_news_last_score = 0

        emit_status("Capturando referência do TOTVS News...", level="INFO")

        def worker():
            try:
                reference = capture_totvs_news_reference()
                with self.lock:
                    self.totvs_news_reference_loaded = True
                    self.totvs_news_last_result = True
                    self.totvs_news_test_progress = "referência capturada"
                    self.totvs_news_last_details = (
                        f"{reference.get('columns', 0)}x{reference.get('rows', 0)} | "
                        f"foto={TOTVS_NEWS_REFERENCE_IMAGE_PATH.name}"
                    )
                    self.totvs_news_last_score = 5
                    self.totvs_news_test_running = False
                emit_status(
                    f"Referência do TOTVS News capturada com sucesso em {TOTVS_NEWS_REFERENCE_IMAGE_PATH.name}.",
                    level="INFO",
                )
            except Exception as exc:
                with self.lock:
                    self.totvs_news_reference_loaded = False
                    self.totvs_news_test_running = False
                    self.totvs_news_last_result = False
                    self.totvs_news_test_progress = "erro na referência"
                    self.totvs_news_last_details = str(exc)
                    self.totvs_news_last_score = 0
                emit_status(f"Falha ao capturar referência do TOTVS News: {exc}", level="ERROR")

        threading.Thread(target=worker, name="totvs-news-capture", daemon=True).start()

    def check_totvs_news_visibility(self):
        visible, score, detail, _ = _evaluate_totvs_news_layers()
        with self.lock:
            self.totvs_news_last_result = visible
            self.totvs_news_last_score = score
            self.totvs_news_last_details = detail
            self.totvs_news_test_running = False
            self.totvs_news_test_progress = "concluido"
        if visible:
            emit_status(f"TOTVS News detectado na tela. score={score}/5 | {detail}", level="INFO")
        else:
            emit_status(f"TOTVS News não detectado na tela. score={score}/5 | {detail}", level="WARNING")
        return visible

    def start_totvs_news_test(self):
        with self.lock:
            if self.totvs_news_test_running:
                return
            self.totvs_news_test_running = True
            self.totvs_news_last_result = None
            self.totvs_news_test_progress = "iniciando"
            self.totvs_news_last_details = ""
            self.totvs_news_last_score = 0

        self._show_window_now()
        emit_status("Verificando TOTVS News em 4 camadas...", level="INFO")

        def worker():
            try:
                visible, score, detail, layers = _evaluate_totvs_news_layers()
                for idx, (name, ok) in enumerate(layers, start=1):
                    with self.lock:
                        self.totvs_news_test_progress = f"{name} {'OK' if ok else 'NO'}"
                    emit_status(f"{name}: {'OK' if ok else 'NÃO'}", level="INFO" if ok else "WARNING")
                    time.sleep(0.12)
                with self.lock:
                    self.totvs_news_last_result = visible
                    self.totvs_news_last_score = score
                    self.totvs_news_last_details = detail
                    self.totvs_news_test_running = False
                    self.totvs_news_test_progress = "concluido"
                if visible:
                    emit_status(f"TOTVS News detectado na tela. score={score}/5 | {detail}", level="INFO")
                else:
                    emit_status(f"TOTVS News não detectado na tela. score={score}/5 | {detail}", level="WARNING")
            except Exception as exc:
                with self.lock:
                    self.totvs_news_test_running = False
                    self.totvs_news_last_result = False
                    self.totvs_news_test_progress = "erro"
                    self.totvs_news_last_details = str(exc)
                emit_status(f"Falha ao verificar TOTVS News: {exc}", level="ERROR")

        threading.Thread(target=worker, name="totvs-news-test", daemon=True).start()

    def get_totvs_news_status(self) -> tuple[str, str]:
        with self.lock:
            running = self.totvs_news_test_running
            progress = self.totvs_news_test_progress
            visible = self.totvs_news_last_result
            score = self.totvs_news_last_score
            details = self.totvs_news_last_details
            ref_loaded = self.totvs_news_reference_loaded
        loader = globals().get("_load_totvs_news_reference")
        if not ref_loaded and callable(loader) and loader() is not None:
            with self.lock:
                self.totvs_news_reference_loaded = True
            ref_loaded = True
        if running:
            return f"TOTVS News | {progress} | ref={'SIM' if ref_loaded else 'NÃO'}", "#b38f00"
        if visible is True:
            return f"TOTVS News | DETECTADO ({score}/5) | ref={'SIM' if ref_loaded else 'NÃO'}", "#1f8a3b"
        if visible is False:
            return f"TOTVS News | NÃO DETECTADO ({score}/5) | ref={'SIM' if ref_loaded else 'NÃO'}", "#b3261e"
        return f"TOTVS News | aguardando teste | ref={'SIM' if ref_loaded else 'NÃO'}", "#666666"

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
            title = _get_foreground_window_title()
            news = totvs_news_visible()
            pos = _STATE.current_between_text()
            return (
                f"STATUS | pausado={paused} parar={stop} "
                f"pixel_ativo={pixel} executando={running} posicao={pos} "
                f"janela={title!r} totvs_news={news}"
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
        "Controlador iniciado. Use o botão 'Executar tudo' ou o comando interno "
        "'executar_tudo'."
    )
    while True:
        time.sleep(0.5)


def validate_macro_comment_sequence(path: Path):
    """
    Garante que comentários numerados das macros estejam em sequência:
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
                f"Comentários fora de sequência em {path.name}:{lineno}. "
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
        if char == "r":
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

    def screen_contains_text(self, text: str, region=None) -> bool:
        return screen_contains_text(text, region=region)

    def totvs_news_visible(self, region=None) -> bool:
        return totvs_news_visible(region=region)

    def start_totvs_news_reference_capture(self):
        _STATE.start_totvs_news_reference_capture()

    def start_totvs_news_test(self):
        _STATE.start_totvs_news_test()

    def check_totvs_news_visibility(self):
        return _STATE.check_totvs_news_visibility()

    def totvs_news_test_running(self) -> bool:
        with _STATE.lock:
            return _STATE.totvs_news_test_running

    def wait_for_totvs_news_idle(self, timeout: Optional[float] = None, poll_interval: float = 0.1) -> bool:
        deadline = None if timeout is None else time.time() + timeout
        while True:
            with _STATE.lock:
                running = _STATE.totvs_news_test_running
            if not running:
                return True
            if deadline is not None and time.time() >= deadline:
                return False
            time.sleep(poll_interval)

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


def _normalize_screen_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


def _get_foreground_window_title() -> str:
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _make_guid(value: str) -> _GUID:
    guid = _GUID()
    result = ctypes.windll.ole32.IIDFromString(ctypes.c_wchar_p(value), ctypes.byref(guid))
    if result != 0:
        raise RuntimeError(f"Falha ao converter GUID {value!r}.")
    return guid


def _get_window_text(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value


def _enum_visible_window_handles():
    handles = []
    user32 = ctypes.windll.user32

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd):
            handles.append(int(hwnd))
        return True

    user32.EnumWindows(_callback, 0)
    return handles


def _find_window_handles_for_text(fragment: str):
    fragment_norm = _normalize_screen_text(fragment)
    if not fragment_norm:
        return []
    matches = []
    for hwnd in _enum_visible_window_handles():
        title = _normalize_screen_text(_get_window_text(hwnd))
        if fragment_norm in title or "totvs" in title or "smartclient" in title:
            matches.append(hwnd)
    if matches:
        return matches
    return _enum_visible_window_handles()


def _find_totvs_window_handle():
    best_match = None
    best_score = -1
    for hwnd in _enum_visible_window_handles():
        title = _normalize_screen_text(_get_window_text(hwnd))
        if "totvs" not in title:
            continue
        score = 1
        if "smartclient" in title:
            score += 4
        if "manufatura" in title:
            score += 2
        if "html" in title:
            score += 1
        if score > best_score:
            best_score = score
            best_match = hwnd
    return best_match


def _find_best_window_handle(titles):
    normalized = [_normalize_screen_text(str(t)) for t in (titles or []) if str(t).strip()]
    normalized = [t for t in normalized if t]
    if not normalized:
        return _find_totvs_window_handle()

    best_match = None
    best_score = -1
    for hwnd in _enum_visible_window_handles():
        title_norm = _normalize_screen_text(_get_window_text(hwnd))
        if not title_norm:
            continue
        score = 0
        for token in normalized:
            if token in title_norm:
                score += 10
        if "totvs" in title_norm:
            score += 3
        if "smartclient" in title_norm:
            score += 5
        if score > best_score:
            best_score = score
            best_match = hwnd

    if best_score <= 0 and any(("totvs" in t or "smartclient" in t) for t in normalized):
        return _find_totvs_window_handle()
    return best_match


def _activate_window(hwnd: int) -> bool:
    try:
        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        SW_SHOW = 5

        user32.ShowWindow(hwnd, SW_RESTORE if user32.IsIconic(hwnd) else SW_SHOW)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.SetFocus(hwnd)
        time.sleep(0.06)

        current = int(user32.GetForegroundWindow() or 0)
        if current == int(hwnd):
            return True

        # Fallback: tenta Alt+Tab uma vez para alternar e reaplica foco.
        if pynput_keyboard is not None:
            kb = pynput_keyboard.Controller()
            kb.press(pynput_keyboard.Key.alt_l)
            kb.press(pynput_keyboard.Key.tab)
            kb.release(pynput_keyboard.Key.tab)
            kb.release(pynput_keyboard.Key.alt_l)
            time.sleep(0.12)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.05)
            current = int(user32.GetForegroundWindow() or 0)
            return current == int(hwnd)

        return False
    except Exception:
        return False


def _get_accessible_dispatch(hwnd: int):
    try:
        import pythoncom
        import win32com.client
    except Exception:
        return None

    try:
        iid = _make_guid("{00020400-0000-0000-C000-000000000046}")
        ptr = ctypes.c_void_p()
        hr = ctypes.windll.oleacc.AccessibleObjectFromWindow(
            int(hwnd),
            ctypes.c_long(-4).value,
            ctypes.byref(iid),
            ctypes.byref(ptr),
        )
        if hr != 0 or not ptr.value:
            return None
        return win32com.client.Dispatch(pythoncom.ObjectFromAddress(ptr.value, pythoncom.IID_IDispatch))
    except Exception:
        return None


def _accessible_contains_text(acc, target: str, depth: int = 0, max_depth: int = 6) -> bool:
    if acc is None or depth > max_depth:
        return False

    for attr in ("accName", "accValue", "accDescription"):
        try:
            value = getattr(acc, attr)(0)
        except Exception:
            value = None
        if value and target in _normalize_screen_text(str(value)):
            return True

    try:
        child_count = int(getattr(acc, "accChildCount"))
    except Exception:
        child_count = 0

    for index in range(1, child_count + 1):
        try:
            child_name = acc.accName(index)
        except Exception:
            child_name = None
        if child_name and target in _normalize_screen_text(str(child_name)):
            return True

        try:
            child = acc.accChild(index)
        except Exception:
            child = None
        if child is None:
            continue
        if hasattr(child, "accName"):
            if _accessible_contains_text(child, target, depth + 1, max_depth=max_depth):
                return True
            continue
        if target in _normalize_screen_text(str(child)):
            return True

    return False


def _text_visible_in_accessibility_tree(text: str) -> bool:
    for hwnd in _find_window_handles_for_text(text):
        acc = _get_accessible_dispatch(hwnd)
        if acc is None:
            continue
        if _accessible_contains_text(acc, _normalize_screen_text(text)):
            return True
    return False


def _coerce_region(region):
    if region is None:
        return None
    if isinstance(region, dict):
        return (
            int(region["left"]),
            int(region["top"]),
            int(region["right"]),
            int(region["bottom"]),
        )
    if isinstance(region, (list, tuple)) and len(region) == 4:
        return tuple(int(value) for value in region)
    raise ValueError("region precisa ser dict ou sequência com 4 valores")


DEFAULT_TOTVS_NEWS_LEFT_RATIO = 0.14
DEFAULT_TOTVS_NEWS_VERTICAL_START_RATIO = 0.53
DEFAULT_TOTVS_NEWS_VERTICAL_END_RATIO = 0.64
TOTVS_NEWS_REFERENCE_PATH = SCRIPT_DIR / "totvs_news_reference.json"
TOTVS_NEWS_REFERENCE_IMAGE_PATH = SCRIPT_DIR / "totvs_news_reference.png"
_BUNDLED_TOTVS_NEWS_REFERENCE_PATH = BUNDLED_SCRIPT_DIR / "totvs_news_reference.json"
_TOTVS_NEWS_REFERENCE = None
DEFAULT_TOTVS_NEWS_PATTERN = [
    ((0.08, 0.50), "dark"),
    ((0.18, 0.50), "blue"),
    ((0.28, 0.50), "blue"),
    ((0.40, 0.50), "blue"),
    ((0.58, 0.50), "dark"),
]


def _default_totvs_news_region():
    width, height = _get_screen_size()
    right = max(1, int(width * DEFAULT_TOTVS_NEWS_LEFT_RATIO))
    top = max(0, int(height * DEFAULT_TOTVS_NEWS_VERTICAL_START_RATIO))
    bottom = max(top + 1, int(height * DEFAULT_TOTVS_NEWS_VERTICAL_END_RATIO))
    return (0, top, right, min(height, bottom))


def _capture_window_image(hwnd: int):
    try:
        import win32con  # type: ignore
        import win32gui  # type: ignore
        import win32ui  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:
        return None, None

    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = max(1, right - left)
        height = max(1, bottom - top)
    except Exception:
        return None, None

    hwnd_dc = None
    mfc_dc = None
    save_dc = None
    bmp = None
    try:
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        if not hwnd_dc:
            return None, None
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bmp)
        render_flag = 2
        ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), render_flag)
        bmpinfo = bmp.GetInfo()
        bmp_bytes = bmp.GetBitmapBits(True)
        image = Image.frombuffer(
            "RGB",
            (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
            bmp_bytes,
            "raw",
            "BGRX",
            0,
            1,
        )
        return image, (left, top, right, bottom)
    except Exception:
        return None, None
    finally:
        try:
            if save_dc is not None:
                save_dc.DeleteDC()
        except Exception:
            pass
        try:
            if mfc_dc is not None:
                mfc_dc.DeleteDC()
        except Exception:
            pass
        try:
            if hwnd_dc:
                win32gui.ReleaseDC(hwnd, hwnd_dc)
        except Exception:
            pass
        try:
            if bmp is not None:
                bmp.DeleteObject()
        except Exception:
            pass


def _capture_region_image(region):
    region = _coerce_region(region)
    if region is None:
        return None

    left, top, right, bottom = region
    width = max(1, right - left)
    height = max(1, bottom - top)

    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None

    hwnd = _find_totvs_window_handle()
    if hwnd:
        window_image, window_rect = _capture_window_image(hwnd)
        if window_image is not None and window_rect is not None:
            win_left, win_top, _, _ = window_rect
            crop_left = max(0, left - win_left)
            crop_top = max(0, top - win_top)
            crop_right = min(window_image.size[0], crop_left + width)
            crop_bottom = min(window_image.size[1], crop_top + height)
            if crop_right > crop_left and crop_bottom > crop_top:
                try:
                    return window_image.crop((crop_left, crop_top, crop_right, crop_bottom))
                except Exception:
                    pass

    hdc = None
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        if not hdc:
            return None
        image = Image.new("RGB", (width, height))
        pixels = image.load()
        for y in range(height):
            screen_y = top + y
            for x in range(width):
                screen_x = left + x
                color = ctypes.windll.gdi32.GetPixel(hdc, screen_x, screen_y)
                if color == -1:
                    pixels[x, y] = (0, 0, 0)
                    continue
                r = color & 0xFF
                g = (color >> 8) & 0xFF
                b = (color >> 16) & 0xFF
                pixels[x, y] = (r, g, b)
        return image
    except Exception:
        return None
    finally:
        try:
            if hdc:
                ctypes.windll.user32.ReleaseDC(0, hdc)
        except Exception:
            pass


def _sample_region_grid(region, columns: int = 8, rows: int = 5):
    region = _coerce_region(region)
    if region is None:
        return None

    image = _capture_region_image(region)
    if image is None:
        return None

    width, height = image.size
    if width <= 0 or height <= 0:
        return None

    columns = max(2, int(columns))
    rows = max(2, int(rows))
    pixels = image.load()
    samples = []

    for row in range(rows):
        y_ratio = (row + 0.5) / rows
        y = min(height - 1, max(0, int(round(height * y_ratio))))
        row_samples = []
        for col in range(columns):
            x_ratio = (col + 0.5) / columns
            x = min(width - 1, max(0, int(round(width * x_ratio))))
            row_samples.append(list(map(int, pixels[x, y])))
        samples.append(row_samples)

    return {
        "region": list(region),
        "columns": columns,
        "rows": rows,
        "samples": samples,
    }


def _grid_signature_distance(reference: dict, current: dict) -> float:
    if not reference or not current:
        return float("inf")

    ref_rows = int(reference.get("rows", 0))
    ref_cols = int(reference.get("columns", 0))
    cur_rows = int(current.get("rows", 0))
    cur_cols = int(current.get("columns", 0))
    if ref_rows <= 0 or ref_cols <= 0 or ref_rows != cur_rows or ref_cols != cur_cols:
        return float("inf")

    ref_samples = reference.get("samples", [])
    cur_samples = current.get("samples", [])
    total = 0.0
    count = 0
    for row in range(ref_rows):
        for col in range(ref_cols):
            try:
                r1, g1, b1 = ref_samples[row][col]
                r2, g2, b2 = cur_samples[row][col]
            except Exception:
                return float("inf")
            total += abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
            count += 1
    if count == 0:
        return float("inf")
    return total / count


def _load_totvs_news_reference():
    global _TOTVS_NEWS_REFERENCE
    if _TOTVS_NEWS_REFERENCE is not None:
        return _TOTVS_NEWS_REFERENCE
    try:
        if TOTVS_NEWS_REFERENCE_PATH.exists():
            _TOTVS_NEWS_REFERENCE = json.loads(TOTVS_NEWS_REFERENCE_PATH.read_text(encoding="utf-8"))
        elif _BUNDLED_TOTVS_NEWS_REFERENCE_PATH.exists():
            _TOTVS_NEWS_REFERENCE = json.loads(_BUNDLED_TOTVS_NEWS_REFERENCE_PATH.read_text(encoding="utf-8"))
        else:
            _TOTVS_NEWS_REFERENCE = None
    except Exception:
        _TOTVS_NEWS_REFERENCE = None
    return _TOTVS_NEWS_REFERENCE


def _save_totvs_news_reference(reference: dict):
    global _TOTVS_NEWS_REFERENCE
    _TOTVS_NEWS_REFERENCE = reference
    TOTVS_NEWS_REFERENCE_PATH.write_text(json.dumps(reference, ensure_ascii=False, indent=2), encoding="utf-8")


def capture_totvs_news_reference(region=None):
    target_region = region if region is not None else _default_totvs_news_region()
    image = _capture_region_image(target_region)
    if image is None:
        raise RuntimeError("Não consegui capturar a imagem do TOTVS News.")
    try:
        image.save(TOTVS_NEWS_REFERENCE_IMAGE_PATH)
    except Exception as exc:
        raise RuntimeError(f"Não consegui salvar a imagem de referência: {exc}") from exc
    reference = _sample_region_grid(target_region)
    if reference is None:
        raise RuntimeError("Não consegui capturar a referência do TOTVS News.")
    reference["image_path"] = str(TOTVS_NEWS_REFERENCE_IMAGE_PATH)
    _save_totvs_news_reference(reference)
    return reference


def _reference_matches_current_screen(region=None) -> tuple[bool, float]:
    reference = _load_totvs_news_reference()
    if not reference:
        return False, float("inf")
    target_region = region if region is not None else reference.get("region") or _default_totvs_news_region()
    current = _sample_region_grid(target_region, columns=int(reference.get("columns", 8)), rows=int(reference.get("rows", 5)))
    if current is None:
        return False, float("inf")
    distance = _grid_signature_distance(reference, current)
    return distance <= 35.0, distance


def _region_looks_like_blue_link(region) -> bool:
    region = _coerce_region(region)
    if region is None:
        return False

    image = _capture_region_image(region)
    if image is None:
        return False

    width, height = image.size
    if width <= 0 or height <= 0:
        return False

    pixels = image.load()
    blue_count = 0
    total_count = width * height

    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            if (
                b >= 150
                and b >= r + 30
                and b >= g + 15
                and (r + g + b) >= 180
                and r <= 140
                and g <= 180
            ):
                blue_count += 1

    if total_count == 0:
        return False
    return (blue_count / total_count) >= 0.01


def _is_blue_like(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return b >= 150 and b >= r + 30 and b >= g + 15 and (r + g + b) >= 180 and r <= 140 and g <= 180


def _is_dark_like(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    return (r + g + b) <= 140


def _region_matches_pixel_pattern(region, pattern=None) -> bool:
    region = _coerce_region(region)
    if region is None:
        return False

    image = _capture_region_image(region)
    if image is None:
        return False

    width, height = image.size
    if width <= 0 or height <= 0:
        return False

    points = pattern or DEFAULT_TOTVS_NEWS_PATTERN
    pixels = image.load()

    for (rx, ry), expected in points:
        x = min(width - 1, max(0, int(round(width * rx))))
        y = min(height - 1, max(0, int(round(height * ry))))
        rgb = pixels[x, y]
        if expected == "blue":
            if not _is_blue_like(rgb):
                return False
        elif expected == "dark":
            if not _is_dark_like(rgb):
                return False
        else:
            raise ValueError(f"Tipo de amostra desconhecido: {expected!r}")

    return True


def _totvs_news_layer_1_accessibility() -> bool:
    return _text_visible_in_accessibility_tree("TOTVS News")


def _totvs_news_layer_2_reference(region) -> bool:
    matched, _ = _reference_matches_current_screen(region)
    return matched


def _totvs_news_layer_3_pixel_pattern(region) -> bool:
    return _region_matches_pixel_pattern(region)


def _totvs_news_layer_4_blue_density(region) -> bool:
    return _region_looks_like_blue_link(region)


def _totvs_news_layer_5_menu_context(region) -> bool:
    region = _coerce_region(region)
    if region is None:
        return False

    image = _capture_region_image(region)
    if image is None:
        return False

    width, height = image.size
    if width <= 0 or height <= 0:
        return False

    pixels = image.load()
    # Em vez de olhar um ponto exato, procura uma estrutura de menu:
    # varias linhas azuis sobre um fundo escuro na faixa esquerda.
    row_hits = 0
    center_hit = False
    left_limit = max(1, int(width * 0.72))

    for y in range(height):
        blue = 0
        dark = 0
        for x in range(left_limit):
            rgb = pixels[x, y]
            if _is_blue_like(rgb):
                blue += 1
            elif _is_dark_like(rgb):
                dark += 1
        if blue >= 4 and blue > dark * 0.18:
            row_hits += 1
            if int(height * 0.36) <= y <= int(height * 0.64):
                center_hit = True

    return row_hits >= 3 and center_hit


def _safe_totvs_news_probe(label: str, fn, *args, default=False):
    try:
        return fn(*args), None
    except Exception as exc:
        return default, f"{label}: {exc}"


def _evaluate_totvs_news_layers(region=None):
    target_region = region if region is not None else _default_totvs_news_region()
    reference_result, reference_error = _safe_totvs_news_probe(
        "Camada 2/4",
        _reference_matches_current_screen,
        target_region,
        default=(False, float("inf")),
    )
    if isinstance(reference_result, tuple) and len(reference_result) == 2:
        reference_ok, reference_distance = reference_result
    else:
        reference_ok, reference_distance = False, float("inf")

    layer1_ok, layer1_error = _safe_totvs_news_probe(
        "Camada 1/4",
        _totvs_news_layer_1_accessibility,
    )
    layer3_ok, layer3_error = _safe_totvs_news_probe(
        "Camada 3/4",
        _totvs_news_layer_3_pixel_pattern,
        target_region,
    )
    layer4a_ok, layer4a_error = _safe_totvs_news_probe(
        "Camada 4/4A",
        _totvs_news_layer_4_blue_density,
        target_region,
    )
    layer4b_ok, layer4b_error = _safe_totvs_news_probe(
        "Camada 4/4B",
        _totvs_news_layer_5_menu_context,
        target_region,
    )
    blue_density_ok = bool(layer4a_ok)
    menu_context_ok = bool(layer4b_ok)
    layers = [
        ("Camada 1/4", bool(layer1_ok)),
        ("Camada 2/4", bool(reference_ok)),
        ("Camada 3/4", bool(layer3_ok)),
        ("Camada 4/4", blue_density_ok and menu_context_ok),
    ]
    score = 0
    if layers[0][1]:
        score += 2
    if layers[1][1]:
        score += 3
    if layers[2][1]:
        score += 1
    if layers[3][1]:
        score += 1
    visible = layers[0][1] or layers[1][1] or (layers[2][1] and layers[3][1]) or score >= 4
    detail = " | ".join(
        f"{name}={'OK' if ok else 'NO'}"
        for name, ok in layers
    )
    if reference_distance != float("inf"):
        detail = f"{detail} | dist={reference_distance:.1f}"
    errors = [msg for msg in (layer1_error, reference_error, layer3_error, layer4a_error, layer4b_error) if msg]
    if errors:
        detail = f"{detail} | erros=" + " ; ".join(errors)
    return visible, score, detail, layers


def screen_contains_text(text: str, region=None) -> bool:
    """
    Verifica se um texto aparece na janela em foco.

    A primeira checagem usa o título da janela ativa. Se você quiser capturar
    o texto realmente renderizado na tela, passe `region=(left, top, right, bottom)`
    e tenha Pillow + pytesseract instalados; nesse caso a função tenta OCR como
    fallback.
    """
    target = _normalize_screen_text(text)
    if not target:
        return False

    title = _normalize_screen_text(_get_foreground_window_title())
    if target in title:
        return True

    try:
        if _text_visible_in_accessibility_tree(target):
            return True
    except Exception as exc:
        # Alguns dialogs nativos do Windows podem disparar erro COM transitório
        # na varredura de acessibilidade. Nesses casos, seguimos para os
        # próximos métodos de detecção em vez de abortar a macro.
        emit_status(
            f"screen_contains_text: falha na checagem de acessibilidade para {text!r}: {exc}",
            level="WARNING",
        )

    region = _coerce_region(region)
    if region is None:
        return False

    try:
        from PIL import ImageGrab  # type: ignore
        import pytesseract  # type: ignore
    except Exception:
        return False

    try:
        image = ImageGrab.grab(bbox=region)
        ocr_text = pytesseract.image_to_string(image, lang="por+eng")
    except Exception:
        return False

    return target in _normalize_screen_text(ocr_text)


def totvs_news_visible(region=None) -> bool:
    visible, _, _, _ = _evaluate_totvs_news_layers(region=region)
    return visible


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


def _run_macro_like_events(mouse_controller, controller: ExecutionController, macro_like_events, context: str):
    last = 0.0
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

    emit_status(f"{context}: varredura concluída.", level="INFO")


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
        target_rgbs = [tuple(rgb) for rgb in data.get("rgbs", []) if isinstance(rgb, (list, tuple)) and len(rgb) == 3]
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
            target_rgbs,
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
                f"{context}: pixel igual a uma das cores informadas, pulando a sequência.",
                level="INFO",
            )
            return True

        mouse_controller = pynput_mouse.Controller() if pynput_mouse is not None else None
        if mouse_controller is None:
            return True

        emit_status(
            f"{context}: pixel diferente das cores informadas, executando sequência.",
            level="INFO",
        )
        macro_like_events = data.get("macro_like_events", [])
        _run_macro_like_events(mouse_controller, controller, macro_like_events, context)

        emit_status(f"{context}: sequência concluída.", level="INFO")
        return True

    if kind == "wait_screen_text":
        token = str(data.get("text") or data.get("token") or data.get("value") or "TOTVS News")
        region = data.get("region")
        timeout = float(data.get("timeout", 0))
        interval = float(data.get("interval", 0.2))
        error_on_timeout = bool(data.get("error_on_timeout", False))
        context = data.get("label") or data.get("_event_index") or "wait_screen_text"
        start = time.time()
        while True:
            controller.poll_keypress()
            controller.wait_if_paused()
            if controller.stop_requested:
                raise StopRequested(controller.get_stop_message())
            if screen_contains_text(token, region=region):
                emit_status(f"{context}: texto {token!r} detectado na tela.", level="INFO")
                return True
            if timeout > 0 and (time.time() - start) >= timeout:
                if error_on_timeout:
                    raise RuntimeError(f"Timeout esperando o texto {token!r} aparecer na tela.")
                emit_status(f"{context}: timeout aguardando {token!r}.", level="WARNING")
                return True
            time.sleep(interval)

    if kind == "wait_window_title":
        titles_raw = data.get("titles") or data.get("texts") or []
        titles = [str(t) for t in titles_raw if str(t).strip()]
        if not titles:
            single = str(data.get("title") or data.get("text") or "Salvar como").strip()
            titles = [single]
        timeout = float(data.get("timeout", 0))
        interval = float(data.get("interval", 0.2))
        error_on_timeout = bool(data.get("error_on_timeout", False))
        context = data.get("label") or data.get("_event_index") or "wait_window_title"
        normalized_titles = [_normalize_screen_text(t) for t in titles if _normalize_screen_text(t)]
        start = time.time()
        while True:
            controller.poll_keypress()
            controller.wait_if_paused()
            if controller.stop_requested:
                raise StopRequested(controller.get_stop_message())
            current_title = _normalize_screen_text(_get_foreground_window_title())
            for t in normalized_titles:
                if t and t in current_title:
                    emit_status(f"{context}: título detectado: {t!r}.", level="INFO")
                    return True
            if timeout > 0 and (time.time() - start) >= timeout:
                if error_on_timeout:
                    raise RuntimeError(
                        f"Timeout esperando título da janela conter um dos termos: {titles!r}."
                    )
                emit_status(f"{context}: timeout aguardando título da janela.", level="WARNING")
                return True
            time.sleep(interval)

    if kind in ("focus_window", "focus_totvs_window"):
        titles_raw = data.get("titles") or data.get("texts") or []
        titles = [str(t) for t in titles_raw if str(t).strip()]
        if not titles:
            single = str(data.get("title") or data.get("text") or "TOTVS SmartClient HTML").strip()
            titles = [single]
        timeout = float(data.get("timeout", 8.0))
        interval = float(data.get("interval", 0.2))
        error_on_timeout = bool(data.get("error_on_timeout", True))
        post_wait = float(data.get("post_wait", 0.2))
        context = data.get("label") or data.get("_event_index") or kind

        start = time.time()
        while True:
            controller.poll_keypress()
            controller.wait_if_paused()
            if controller.stop_requested:
                raise StopRequested(controller.get_stop_message())

            hwnd = _find_totvs_window_handle() if kind == "focus_totvs_window" else _find_best_window_handle(titles)
            if hwnd and _activate_window(hwnd):
                focused_title = _get_window_text(hwnd)
                emit_status(f"{context}: foco aplicado na janela: {focused_title!r}.", level="INFO")
                if post_wait > 0:
                    if not sleep_with_controls(post_wait, controller):
                        raise StopRequested(controller.get_stop_message())
                return True

            if timeout > 0 and (time.time() - start) >= timeout:
                if error_on_timeout:
                    raise RuntimeError(
                        f"Timeout ao focar janela. Titulos esperados: {titles!r}."
                    )
                emit_status(f"{context}: timeout ao tentar focar janela.", level="WARNING")
                return True
            time.sleep(interval)

    if kind == "wait_native_file_dialog":
        timeout = float(data.get("timeout", 0))
        interval = float(data.get("interval", 0.2))
        error_on_timeout = bool(data.get("error_on_timeout", False))
        context = data.get("label") or data.get("_event_index") or "wait_native_file_dialog"
        expected_class = str(data.get("class_name") or "#32770").strip()
        title_tokens_raw = data.get("title_tokens") or ["Salvar como", "Save As"]
        title_tokens = [_normalize_screen_text(str(t)) for t in title_tokens_raw if str(t).strip()]
        start = time.time()
        while True:
            controller.poll_keypress()
            controller.wait_if_paused()
            if controller.stop_requested:
                raise StopRequested(controller.get_stop_message())

            cls = _get_foreground_window_class_name()
            title = _normalize_screen_text(_get_foreground_window_title())
            class_ok = (not expected_class) or (cls.lower() == expected_class.lower())
            title_ok = any(tok and tok in title for tok in title_tokens) if title_tokens else True

            if class_ok and title_ok:
                emit_status(
                    f"{context}: diálogo nativo detectado (class={cls!r}, title={title!r}).",
                    level="INFO",
                )
                return True

            if timeout > 0 and (time.time() - start) >= timeout:
                if error_on_timeout:
                    raise RuntimeError(
                        f"Timeout aguardando diálogo nativo class={expected_class!r} com título contendo {title_tokens_raw!r}."
                    )
                emit_status(f"{context}: timeout aguardando diálogo nativo.", level="WARNING")
                return True
            time.sleep(interval)

    if kind == "wait_any_screen_text":
        tokens_raw = data.get("texts") or data.get("tokens") or []
        tokens = [str(t) for t in tokens_raw if str(t).strip()]
        if not tokens:
            token_single = str(data.get("text") or data.get("token") or data.get("value") or "").strip()
            if token_single:
                tokens = [token_single]
        if not tokens:
            tokens = ["Salvar como"]
        region = data.get("region")
        timeout = float(data.get("timeout", 0))
        interval = float(data.get("interval", 0.2))
        error_on_timeout = bool(data.get("error_on_timeout", False))
        context = data.get("label") or data.get("_event_index") or "wait_any_screen_text"
        start = time.time()
        while True:
            controller.poll_keypress()
            controller.wait_if_paused()
            if controller.stop_requested:
                raise StopRequested(controller.get_stop_message())
            for token in tokens:
                if screen_contains_text(token, region=region):
                    emit_status(f"{context}: texto {token!r} detectado na tela.", level="INFO")
                    return True
            if timeout > 0 and (time.time() - start) >= timeout:
                if error_on_timeout:
                    raise RuntimeError(
                        f"Timeout esperando qualquer texto da lista aparecer na tela: {tokens!r}."
                    )
                emit_status(f"{context}: timeout aguardando qualquer texto da lista.", level="WARNING")
                return True
            time.sleep(interval)

    if kind == "wait_any_trigger":
        tokens_raw = data.get("texts") or data.get("tokens") or []
        tokens = [str(t) for t in tokens_raw if str(t).strip()]
        rgbs = [tuple(rgb) for rgb in data.get("rgbs", []) if isinstance(rgb, (list, tuple)) and len(rgb) == 3]
        tolerance = int(data.get("tolerance", 0))
        use_quadrants = bool(data.get("quadrants", False))
        timeout = float(data.get("timeout", 0))
        interval = float(data.get("interval", 0.2))
        error_on_timeout = bool(data.get("error_on_timeout", False))
        region = data.get("region")
        context = data.get("label") or data.get("_event_index") or "wait_any_trigger"
        start = time.time()
        while True:
            controller.poll_keypress()
            controller.wait_if_paused()
            if controller.stop_requested:
                raise StopRequested(controller.get_stop_message())

            for token in tokens:
                try:
                    if screen_contains_text(token, region=region):
                        emit_status(f"{context}: gatilho por texto {token!r}.", level="INFO")
                        return True
                except Exception:
                    pass

            if use_quadrants and rgbs:
                current, match_pos = _find_pixel_in_quadrant_centers_any(rgbs, tolerance)
                if current is not None:
                    emit_status(
                        f"{context}: gatilho por cor RGB{current} em quadrante {match_pos}.",
                        level="INFO",
                    )
                    return True

            if timeout > 0 and (time.time() - start) >= timeout:
                if error_on_timeout:
                    raise RuntimeError(
                        f"Timeout aguardando qualquer gatilho (texto/cor) em {timeout:.1f}s."
                    )
                emit_status(f"{context}: timeout aguardando qualquer gatilho.", level="WARNING")
                return True
            time.sleep(interval)

    if kind == "screen_branch_sequence":
        token = str(data.get("text") or data.get("token") or data.get("value") or "TOTVS News")
        region = data.get("region")
        context = data.get("label") or data.get("_event_index") or "screen_branch_sequence"
        visible = screen_contains_text(token, region=region)
        emit_status(
            f"{context}: checagem de tela para {token!r} -> {'VISÍVEL' if visible else 'NÃO visível'}.",
            level="INFO",
        )
        mouse_controller = pynput_mouse.Controller() if pynput_mouse is not None else None
        if mouse_controller is None:
            return True

        if visible:
            branch_events = data.get("when_visible", [])
            emit_status(f"{context}: executando ramo when_visible.", level="INFO")
        else:
            branch_events = data.get("when_hidden", [])
            emit_status(f"{context}: executando ramo when_hidden.", level="INFO")

        _run_macro_like_events(mouse_controller, controller, branch_events, context)
        emit_status(f"{context}: ramo concluído.", level="INFO")
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
    target_rgbs: list[tuple],
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
        elif search_mode == "quadrants_dual":
            rgb_targets = target_rgbs if target_rgbs else [target_rgb]
            current, match_pos = _find_pixel_in_quadrant_centers_any(rgb_targets, tolerance)
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
            rgb_targets = target_rgbs if target_rgbs else [target_rgb]
            current, match_pos = _find_any_pixel_within_radius(x, y, rgb_targets, tolerance, search_radius)
            matches = current is not None
        else:
            current = _get_pixel_color(x, y)
            match_pos = (x, y)
            rgb_targets = target_rgbs if target_rgbs else [target_rgb]
            matches = any(_color_matches(current, tuple(rgb), tolerance) for rgb in rgb_targets)
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


def _get_foreground_window_class_name() -> str:
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return (buf.value or "").strip()
    except Exception:
        return ""


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


def _find_pixel_in_quadrant_centers_any(target_rgbs: list[tuple], tolerance: int):
    width, height = _get_screen_size()
    centers = [
        (width // 4, height // 4),
        ((width * 3) // 4, height // 4),
        (width // 4, (height * 3) // 4),
        ((width * 3) // 4, (height * 3) // 4),
    ]
    for point in centers:
        current = _get_pixel_color(point[0], point[1])
        for target_rgb in target_rgbs:
            if _color_matches(current, tuple(target_rgb), tolerance):
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


def _find_any_pixel_within_radius(
    center_x: int,
    center_y: int,
    target_rgbs: list[tuple],
    tolerance: int,
    radius: int,
):
    for dy in range(-radius, radius + 1):
        y = center_y + dy
        for dx in range(-radius, radius + 1):
            x = center_x + dx
            current = _get_pixel_color(x, y)
            for rgb in target_rgbs:
                if _color_matches(current, tuple(rgb), tolerance):
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
