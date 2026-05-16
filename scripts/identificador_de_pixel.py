import ctypes
import time
import msvcrt


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def get_cursor_pos():
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def get_pixel_color(x, y):
    hdc = ctypes.windll.user32.GetDC(0)
    color = ctypes.windll.gdi32.GetPixel(hdc, x, y)
    ctypes.windll.user32.ReleaseDC(0, hdc)
    if color == -1:
        return 0, 0, 0
    r = color & 0xFF
    g = (color >> 8) & 0xFF
    b = (color >> 16) & 0xFF
    return r, g, b


def main():
    print("Identificador de pixel ativo. Pressione ESC ou Q para sair.")
    print("Teclas: F trava (freeze), U destrava (unfreeze).")
    frozen = False
    last_line = ""
    while True:
        if msvcrt.kbhit():
            key = msvcrt.getch()
            if key in (b"f", b"F"):
                frozen = True
            elif key in (b"u", b"U"):
                frozen = False
            if key in (b"\x1b", b"q", b"Q"):
                break
        if not frozen:
            x, y = get_cursor_pos()
            r, g, b = get_pixel_color(x, y)
            last_line = f"X:{x} Y:{y} RGB:({r},{g},{b}) HEX:#{r:02X}{g:02X}{b:02X}"
        label = " [TRAVADO]" if frozen else ""
        print("\r" + last_line + label + " " * 10, end="", flush=True)
        time.sleep(0.05)
    print("\nEncerrado.")


if __name__ == "__main__":
    main()
