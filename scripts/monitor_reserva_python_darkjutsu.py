import ctypes
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from ctypes import wintypes


PRIMARY_IP = "192.168.5.44"
RESERVE_IP = "192.168.5.38"
PORT = 8765
HEALTH_TIMEOUT_SECONDS = 3
OFFLINE_GRACE_SECONDS = 45
SHARE_ROOT = r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
APP_PATH = os.path.join(SHARE_ROOT, "app", "index.html")
SCRIPTS = os.path.join(SHARE_ROOT, "scripts")
CMD_EXE = r"C:\Windows\SysWOW64\cmd.exe" if os.path.exists(r"C:\Windows\SysWOW64\cmd.exe") else "cmd.exe"
PYTHON_EXE = os.path.join(os.path.dirname(sys.executable), "python.exe")
PASSWORD = "654321"
INFINITY_PASSWORD = "123456789"
INFINITY_INTERVAL_SECONDS = 150
LOG_DIR = r"C:\DarkJutsu\logs"
LOG_FILE = os.path.join(LOG_DIR, "monitor_python.log")
ANTI_SLEEP_STATUS_FILE = os.path.join(LOG_DIR, "anti_sleep_darkjutsu.status")
SHARED_MONITOR_LOG = os.path.join(SHARE_ROOT, "logs", "monitor_python_eventos.txt")
TEST_ACTIVE_FILE = os.path.join(SHARE_ROOT, "status", "teste_inicializacao_ativo.txt")
TEST_LOG = os.path.join(SHARE_ROOT, "logs", "teste_inicializacao_manual_darkjutsu.txt")
MUTEX_NAME = "Global\\DarkJutsuMonitorReservaPython"
ERROR_ALREADY_EXISTS = 183
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

WM_USER = 0x0400
WM_TRAY = WM_USER + 20
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_RBUTTONUP = 0x0205
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010

ID_OPEN = 1001
ID_TEST = 1002
ID_SWITCH = 1003
ID_STOP = 1004
ID_GUARD = 1005
ID_INFINITY_TOGGLE = 1006

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

if not hasattr(wintypes, "HCURSOR"):
    wintypes.HCURSOR = wintypes.HANDLE
if not hasattr(wintypes, "HICON"):
    wintypes.HICON = wintypes.HANDLE
if not hasattr(wintypes, "HBRUSH"):
    wintypes.HBRUSH = wintypes.HANDLE
if not hasattr(wintypes, "HBITMAP"):
    wintypes.HBITMAP = wintypes.HANDLE
if not hasattr(wintypes, "HMODULE"):
    wintypes.HMODULE = wintypes.HANDLE
if not hasattr(wintypes, "HMENU"):
    wintypes.HMENU = wintypes.HANDLE
if not hasattr(wintypes, "LRESULT"):
    wintypes.LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
if not hasattr(wintypes, "LPVOID"):
    wintypes.LPVOID = ctypes.c_void_p
if not hasattr(wintypes, "UINT_PTR"):
    wintypes.UINT_PTR = ctypes.c_size_t

class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreatePopupMenu.argtypes = []
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT_PTR, wintypes.LPCWSTR]
user32.AppendMenuW.restype = wintypes.BOOL
user32.EnableMenuItem.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
user32.EnableMenuItem.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadImageW.restype = wintypes.HANDLE
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = wintypes.LRESULT
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.DestroyMenu.restype = wintypes.BOOL
user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.ULONG]
user32.mouse_event.restype = None


def message(text, title="Dark-Jutsu"):
    user32.MessageBoxW(None, text, title, 0x40)


def log(text):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " | " + str(text)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(SHARED_MONITOR_LOG), exist_ok=True)
        actor = f"{os.environ.get('COMPUTERNAME', '?')}\\{os.environ.get('USERNAME', '?')}"
        with open(SHARED_MONITOR_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + f" | {actor}\n")
    except Exception:
        pass
    try:
        if os.path.exists(TEST_ACTIVE_FILE):
            with open(TEST_ACTIVE_FILE, "r", encoding="utf-8", errors="ignore") as fh:
                session = fh.read().strip().replace("\n", " | ")
            os.makedirs(os.path.dirname(TEST_LOG), exist_ok=True)
            actor = f"{os.environ.get('COMPUTERNAME', '?')}\\{os.environ.get('USERNAME', '?')}"
            with open(TEST_LOG, "a", encoding="utf-8") as fh:
                fh.write(line + f" | {actor} | TESTE_ATIVO={session}\n")
    except Exception:
        pass


def boot_hint():
    try:
        ps = "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime"
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, text=True, errors="ignore", timeout=8).stdout.strip()
        return out or "indisponivel"
    except Exception:
        return "indisponivel"


def anti_sleep_loop():
    last_logged = 0
    while True:
        try:
            result = kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(ANTI_SLEEP_STATUS_FILE, "w", encoding="ascii") as fh:
                fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + " | anti-sleep ativo | retorno=" + str(result) + "\n")
            now = time.time()
            if now - last_logged > 1800:
                log("anti-sleep ativo: Windows nao deve suspender enquanto o monitor estiver aberto")
                last_logged = now
        except Exception as exc:
            log(f"ERRO anti-sleep: {type(exc).__name__}: {exc}")
        time.sleep(45)


_mutex_handle = None


def acquire_single_instance():
    global _mutex_handle
    try:
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.GetLastError.argtypes = []
        kernel32.GetLastError.restype = wintypes.DWORD
        _mutex_handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
        if _mutex_handle and kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            log("monitor ja estava aberto; encerrando instancia duplicada")
            return False
    except Exception as exc:
        log(f"AVISO: nao consegui criar mutex do monitor: {type(exc).__name__}: {exc}")
    return True


def ask_password(action):
    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.title("Dark-Jutsu")
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()
        root.withdraw()
        value = simpledialog.askstring("Dark-Jutsu", f"Senha para {action}:", show="*", parent=root)
        root.destroy()
        if value == PASSWORD:
            return True
        if value:
            message("Senha incorreta.", "Dark-Jutsu")
        return False
    except Exception:
        return True


def ask_infinity_password(action):
    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.title("Infinity")
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()
        root.withdraw()
        value = simpledialog.askstring("Infinity", f"Senha do Infinity para {action}:", show="*", parent=root)
        root.destroy()
        if value == INFINITY_PASSWORD:
            return True
        if value:
            message("Senha incorreta.", "Infinity")
        return False
    except Exception:
        return False


def run_hidden(args):
    try:
        log("run_hidden: " + " ".join(args))
        subprocess.Popen(args, creationflags=0x08000000)
    except Exception as exc:
        log(f"ERRO run_hidden: {type(exc).__name__}: {exc}")
        message(f"Nao consegui abrir o comando:\n{type(exc).__name__}: {exc}", "Dark-Jutsu")


def run_visible(args):
    try:
        log("run_visible: " + " ".join(args))
        subprocess.Popen(args, creationflags=0x00000010)
    except Exception as exc:
        log(f"ERRO run_visible: {type(exc).__name__}: {exc}")
        message(f"Nao consegui abrir o comando:\n{type(exc).__name__}: {exc}", "Dark-Jutsu")


class InfinityKeepAwake:
    def __init__(self):
        self.enabled = True
        self._lock = threading.Lock()

    def status_text(self):
        return f"Infinity: {'ativo (2m30s)' if self.enabled else 'parado'}"

    def set_enabled(self, enabled):
        with self._lock:
            self.enabled = enabled
        log(f"Infinity {'iniciado' if enabled else 'parado'} pelo menu")

    def nudge(self):
        with self._lock:
            enabled = self.enabled
        if not enabled:
            return
        try:
            user32.mouse_event(0x0001, 1, 0, 0, 0)
            time.sleep(0.08)
            user32.mouse_event(0x0001, -1, 0, 0, 0)
            log("Infinity: mouse movido 1px e retornado")
        except Exception as exc:
            log(f"Infinity: falha ao mover mouse: {type(exc).__name__}: {exc}")

    def run(self):
        self.nudge()
        while True:
            time.sleep(INFINITY_INTERVAL_SECONDS)
            self.nudge()


def local_ips():
    ips = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(item[4][0])
    except Exception:
        pass
    try:
        output = subprocess.check_output("ipconfig", shell=True, text=True, errors="ignore")
        for line in output.splitlines():
            if "IPv4" in line and ":" in line:
                ips.add(line.split(":", 1)[1].strip())
    except Exception:
        pass
    return ips


def health(ip):
    try:
        with urllib.request.urlopen(f"http://{ip}:{PORT}/health", timeout=HEALTH_TIMEOUT_SECONDS) as resp:
            return b'"ok":true' in resp.read().replace(b" ", b"").lower()
    except Exception:
        return False


def local_script(name):
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    if os.path.exists(local):
        return local
    return os.path.join(SCRIPTS, name)


def script_args(name, keep_open=False):
    mode = "/k" if keep_open else "/c"
    wrapper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_" + name.replace(".bat", ".cmd"))
    if os.path.exists(wrapper):
        return [CMD_EXE, mode, wrapper]
    body = f'pushd {SCRIPTS} && call {name} && popd'
    return [CMD_EXE, mode, body]


def panel_args():
    panel = local_script("abrir_painel_servidor_darkjutsu.bat")
    return [CMD_EXE, "/k", panel]


def test_args():
    base = os.path.dirname(os.path.abspath(__file__))
    local_launcher = os.path.join(base, "abrir_status_darkjutsu.py")
    shared_launcher = os.path.join(SCRIPTS, "abrir_status_darkjutsu.py")
    script = local_launcher if os.path.exists(local_launcher) else shared_launcher
    if not os.path.exists(script):
        local_status = os.path.join(base, "status_compartilhado_servidores_darkjutsu.py")
        shared_status = os.path.join(SCRIPTS, "status_compartilhado_servidores_darkjutsu.py")
        script = local_status if os.path.exists(local_status) else shared_status
    return [PYTHON_EXE, script]


def make_icon(color):
    hdc = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, 64, 64)
    old = gdi32.SelectObject(mem, bmp)
    bg = gdi32.CreateSolidBrush(0x202020)
    rect = wintypes.RECT(0, 0, 64, 64)
    user32.FillRect(mem, ctypes.byref(rect), bg)
    brush = gdi32.CreateSolidBrush(color)
    pen = gdi32.CreatePen(0, 5, 0xFFFFFF)
    old_pen = gdi32.SelectObject(mem, pen)
    old_brush = gdi32.SelectObject(mem, brush)
    gdi32.Ellipse(mem, 6, 6, 58, 58)
    gdi32.SelectObject(mem, old_brush)
    gdi32.SelectObject(mem, old_pen)

    font = gdi32.CreateFontW(
        36,
        0,
        0,
        0,
        700,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        "Segoe UI",
    )
    old_font = gdi32.SelectObject(mem, font)
    gdi32.SetTextColor(mem, 0xFFFFFF)
    gdi32.SetBkMode(mem, 1)
    text_rect = wintypes.RECT(0, 2, 64, 62)
    user32.DrawTextW(mem, "D", 1, ctypes.byref(text_rect), 0x00000001 | 0x00000004 | 0x00000020)
    gdi32.SelectObject(mem, old_font)

    gdi32.SelectObject(mem, old)
    gdi32.DeleteObject(bg)
    gdi32.DeleteObject(brush)
    gdi32.DeleteObject(pen)
    gdi32.DeleteObject(font)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(None, hdc)

    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ("fIcon", wintypes.BOOL),
            ("xHotspot", wintypes.DWORD),
            ("yHotspot", wintypes.DWORD),
            ("hbmMask", wintypes.HBITMAP),
            ("hbmColor", wintypes.HBITMAP),
        ]

    info = ICONINFO(True, 0, 0, bmp, bmp)
    icon = user32.CreateIconIndirect(ctypes.byref(info))
    return icon


def load_icon(name, fallback_color):
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", name),
        os.path.join(SCRIPTS, "icons", name),
    ]
    for path in candidates:
        if os.path.exists(path):
            icon = user32.LoadImageW(None, path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE)
            if icon:
                return icon
    return make_icon(fallback_color)


def format_duration(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}min {sec}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}min"


class Tray:
    def __init__(self):
        self.local_ip = ""
        self.this_active = False
        self.offline_since = None
        self.tip = "Dark-Jutsu: verificando..."
        self.icon_black = load_icon("dark-jutsu-black.ico", 0x202020)
        self.icon_red = load_icon("dark-jutsu-red.ico", 0x2D2DCD)
        self.icon_green = load_icon("dark-jutsu-green.ico", 0x56A11C)
        self.icon = self.icon_black
        self.infinity = InfinityKeepAwake()
        self.wndproc = ctypes.WINFUNCTYPE(wintypes.LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)(self.proc)
        cls = WNDCLASSW()
        cls.lpfnWndProc = ctypes.cast(self.wndproc, ctypes.c_void_p).value
        cls.hInstance = kernel32.GetModuleHandleW(None)
        cls.lpszClassName = "DarkJutsuPythonTray"
        user32.RegisterClassW(ctypes.byref(cls))
        self.hwnd = user32.CreateWindowExW(0, cls.lpszClassName, "Dark-Jutsu", 0, 0, 0, 0, 0, None, None, cls.hInstance, None)
        self.nid = NOTIFYICONDATAW()
        self.nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self.nid.hWnd = self.hwnd
        self.nid.uID = 1
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self.nid.uCallbackMessage = WM_TRAY
        self.nid.hIcon = self.icon
        self.nid.szTip = self.tip
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid))
        self.update_status()
        threading.Thread(target=self.loop_status, daemon=True).start()
        threading.Thread(target=self.infinity.run, daemon=True).start()

    def loop_status(self):
        while True:
            time.sleep(15)
            self.update_status()

    def update_icon(self):
        self.nid.hIcon = self.icon
        self.nid.szTip = self.tip[:127]
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))

    def update_status(self):
        ips = local_ips()
        self.local_ip = PRIMARY_IP if PRIMARY_IP in ips else RESERVE_IP if RESERVE_IP in ips else ""
        primary = health(PRIMARY_IP)
        reserve = health(RESERVE_IP)
        if primary or reserve:
            self.offline_since = None
            active_ip = PRIMARY_IP if primary else RESERVE_IP
            active_name = "principal" if primary else "reserva"
            self.this_active = self.local_ip == active_ip
            if self.this_active:
                self.icon = self.icon_green
                self.tip = f"Dark-Jutsu: este PC esta rodando o servidor ({active_name})"
            else:
                self.icon = self.icon_red
                self.tip = f"Dark-Jutsu: servidor ativo em outro PC ({active_name})"
        else:
            if self.offline_since is None:
                self.offline_since = time.time()
            offline_seconds = time.time() - self.offline_since
            offline_text = format_duration(offline_seconds)
            self.this_active = False
            self.icon = self.icon_black
            self.tip = f"Dark-Jutsu: reconfirmando servidor - sem resposta ha {offline_text}"
            if offline_seconds >= OFFLINE_GRACE_SECONDS:
                self.icon = self.icon_red
                self.tip = f"Dark-Jutsu: nenhum servidor ligado - offline ha {offline_text}"
        self.update_icon()

    def popup_menu(self):
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, 0, 1, self.tip)
        user32.EnableMenuItem(menu, 1, 0x00000002)
        user32.AppendMenuW(menu, 0, ID_OPEN, "Abrir Dark-Jutsu")
        user32.AppendMenuW(menu, 0, ID_TEST, "Testar servidor")
        user32.AppendMenuW(menu, 0, ID_GUARD, "Verificar/iniciar agora")
        switch_text = "Tornar este PC o reserva" if self.this_active else "Tornar este PC o Principal"
        user32.AppendMenuW(menu, 0, ID_SWITCH, switch_text)
        user32.AppendMenuW(menu, 0, 2, self.infinity.status_text())
        user32.EnableMenuItem(menu, 2, 0x00000002)
        infinity_text = "Parar Infinity" if self.infinity.enabled else "Iniciar Infinity"
        user32.AppendMenuW(menu, 0, ID_INFINITY_TOGGLE, infinity_text)
        user32.AppendMenuW(menu, 0, ID_STOP, "Encerrar servidor local")
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        command_id = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(menu)
        if command_id:
            self.command(command_id)

    def command(self, ident):
        log(f"menu command: {ident}")
        if ident == ID_OPEN:
            os.startfile(APP_PATH)
        elif ident == ID_TEST:
            if ask_password("testar servidor"):
                run_visible(test_args())
        elif ident == ID_GUARD:
            if ask_password("verificar/iniciar agora"):
                run_visible(script_args("guardiao_servidor_tick_darkjutsu.bat", keep_open=True))
        elif ident == ID_SWITCH:
            if self.this_active:
                if ask_password("tornar reserva"):
                    run_hidden(script_args("tornar_reserva_operacional_darkjutsu.bat"))
            else:
                if ask_password("tornar Principal"):
                    target = "assumir_servidor_darkjutsu.bat" if self.local_ip == PRIMARY_IP else "tornar_principal_operacional_darkjutsu.bat"
                    run_hidden(script_args(target))
        elif ident == ID_STOP:
            if ask_password("encerrar servidor local"):
                run_hidden(script_args("parar_api_darkjutsu.bat"))
        elif ident == ID_INFINITY_TOGGLE:
            if self.infinity.enabled:
                if ask_infinity_password("parar"):
                    self.infinity.set_enabled(False)
            else:
                self.infinity.set_enabled(True)
        threading.Thread(target=self.update_status, daemon=True).start()

    def proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY and lparam == WM_RBUTTONUP:
            self.popup_menu()
            return 0
        if msg == WM_COMMAND:
            self.command(wparam & 0xFFFF)
            return 0
        if msg == WM_DESTROY:
            try:
                kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            except Exception:
                pass
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self):
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


if __name__ == "__main__":
    try:
        log(f"iniciando monitor python. Maquina={os.environ.get('COMPUTERNAME')} Usuario={os.environ.get('USERNAME')} IPs={sorted(local_ips())} BootWindows={boot_hint()} PID={os.getpid()}")
        if not acquire_single_instance():
            sys.exit(0)
        threading.Thread(target=anti_sleep_loop, daemon=True).start()
        Tray().run()
    except Exception as exc:
        log(f"ERRO: {type(exc).__name__}: {exc}")
        try:
            message(f"Erro ao abrir monitor Python:\n{type(exc).__name__}: {exc}")
        except Exception:
            pass
        raise
