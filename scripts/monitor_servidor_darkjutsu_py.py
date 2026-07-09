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
SHARE_ROOT = r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
APP_PATH = os.path.join(SHARE_ROOT, "app", "index.html")
SCRIPTS = os.path.join(SHARE_ROOT, "scripts")
PASSWORD = "654321"
LOG_DIR = r"C:\DarkJutsu\logs"
LOG_FILE = os.path.join(LOG_DIR, "monitor_python.log")

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

ID_OPEN = 1001
ID_TEST = 1002
ID_SWITCH = 1003
ID_STOP = 1004

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32


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


def message(text, title="Dark-Jutsu"):
    user32.MessageBoxW(None, text, title, 0x40)


def log(text):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + " | " + str(text) + "\n")
    except Exception:
        pass


def ask_password(action):
    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        value = simpledialog.askstring("Dark-Jutsu", f"Senha para {action}:", show="*")
        root.destroy()
        if value == PASSWORD:
            return True
        if value:
            message("Senha incorreta.", "Dark-Jutsu")
        return False
    except Exception:
        return True


def run_hidden(command):
    subprocess.Popen(command, shell=True, creationflags=0x08000000)


def run_visible(command):
    subprocess.Popen(command, shell=True)


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
        with urllib.request.urlopen(f"http://{ip}:{PORT}/health", timeout=2) as resp:
            return b'"ok":true' in resp.read().replace(b" ", b"").lower()
    except Exception:
        return False


def make_icon(color):
    hdc = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, 16, 16)
    old = gdi32.SelectObject(mem, bmp)
    brush = gdi32.CreateSolidBrush(color)
    rect = wintypes.RECT(0, 0, 16, 16)
    user32.FillRect(mem, ctypes.byref(rect), brush)
    gdi32.SelectObject(mem, old)
    gdi32.DeleteObject(brush)
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


class Tray:
    def __init__(self):
        self.local_ip = ""
        self.this_active = False
        self.tip = "Dark-Jutsu: verificando..."
        self.icon_black = make_icon(0x202020)
        self.icon_red = make_icon(0x2D2DCD)
        self.icon_green = make_icon(0x56A11C)
        self.icon = self.icon_black
        self.wndproc = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)(self.proc)
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
            self.this_active = False
            self.icon = self.icon_black
            self.tip = "Dark-Jutsu: nenhum servidor esta ligado"
        self.update_icon()

    def popup_menu(self):
        self.update_status()
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, 0, 1, self.tip)
        user32.EnableMenuItem(menu, 1, 0x00000002)
        user32.AppendMenuW(menu, 0, ID_OPEN, "Abrir Dark-Jutsu")
        user32.AppendMenuW(menu, 0, ID_TEST, "Testar servidor")
        switch_text = "Tornar este PC o reserva" if self.this_active else "Tornar este PC o Principal"
        user32.AppendMenuW(menu, 0, ID_SWITCH, switch_text)
        user32.AppendMenuW(menu, 0, ID_STOP, "Encerrar servidor local")
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON, pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(menu)

    def command(self, ident):
        if ident == ID_OPEN:
            os.startfile(APP_PATH)
        elif ident == ID_TEST:
            run_visible(f'cmd /k "{os.path.join(SCRIPTS, "testar_servidor_darkjutsu.bat")}"')
        elif ident == ID_SWITCH:
            if self.this_active:
                if ask_password("tornar reserva"):
                    run_hidden(f'cmd /c "{os.path.join(SCRIPTS, "tornar_reserva_operacional_darkjutsu.bat")}"')
            else:
                if ask_password("tornar Principal"):
                    target = "assumir_servidor_darkjutsu.bat" if self.local_ip == PRIMARY_IP else "tornar_principal_operacional_darkjutsu.bat"
                    run_hidden(f'cmd /c "{os.path.join(SCRIPTS, target)}"')
        elif ident == ID_STOP:
            if ask_password("encerrar servidor local"):
                run_hidden(f'cmd /c "{os.path.join(SCRIPTS, "parar_api_darkjutsu.bat")}"')
        time.sleep(1)
        self.update_status()

    def proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY and lparam == WM_RBUTTONUP:
            self.popup_menu()
            return 0
        if msg == WM_COMMAND:
            self.command(wparam & 0xFFFF)
            return 0
        if msg == WM_DESTROY:
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
        log("iniciando monitor python")
        Tray().run()
    except Exception as exc:
        log(f"ERRO: {type(exc).__name__}: {exc}")
        try:
            message(f"Erro ao abrir monitor Python:\n{type(exc).__name__}: {exc}")
        except Exception:
            pass
        raise
