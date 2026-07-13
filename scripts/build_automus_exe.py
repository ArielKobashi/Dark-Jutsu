import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
BUILD = ROOT / "build" / "automus"
STAGE = BUILD / "stage"
STAGE_SCRIPTS = STAGE / "scripts"
DIST = ROOT / "dist"
ENTRY = SCRIPTS / "controladordeatualização.py"
ICON = BUILD / "automus.ico"
AUTOMUS_CONFIG = SCRIPTS / "atualizacao" / "automus_config.json"


def build_icon(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    size = 256
    img = Image.new("RGBA", (size, size), (15, 23, 42, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = size // 2
    outer = int(size * 0.34)
    inner = int(size * 0.18)
    tooth_w = max(10, size // 10)
    tooth_h = max(20, size // 7)
    import math

    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x = cx + math.cos(rad) * outer
        y = cy + math.sin(rad) * outer
        draw.rounded_rectangle(
            (x - tooth_w / 2, y - tooth_h / 2, x + tooth_w / 2, y + tooth_h / 2),
            radius=8,
            fill=(34, 197, 94, 255),
        )
    draw.ellipse((cx - outer, cy - outer, cx + outer, cy + outer), fill=(34, 197, 94, 255))
    draw.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=(15, 23, 42, 255))
    draw.ellipse((cx - 28, cy - 28, cx + 28, cy + 28), fill=(229, 231, 235, 255))
    img.save(path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def prepare_stage():
    if STAGE.exists():
        shutil.rmtree(STAGE)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "controlador_config.json", "automus_config.json")
    shutil.copytree(SCRIPTS, STAGE_SCRIPTS, ignore=ignore)
    legacy_config = STAGE_SCRIPTS / "legacy_config_disabled.json"
    if legacy_config.exists():
        legacy_config.unlink()
    print("Build Automus SQL-only: config legada nao sera empacotada.")
    return

def prepare_encrypted_automus_config():
    print("Build Automus SQL-only: credenciais legadas nao serao criptografadas nem empacotadas.")
    return


def main():
    build_icon(ICON)
    prepare_stage()
    prepare_encrypted_automus_config()
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller", "pystray", "pillow", "openpyxl", "pynput"])
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--onefile",
            "--windowed",
            "--name",
            "Automus",
            "--icon",
            str(ICON),
            "--paths",
            str(SCRIPTS),
            "--add-data",
            f"{STAGE_SCRIPTS};scripts",
            "--hidden-import",
            "executar_tudo",
            "--hidden-import",
            "atualizacao.automus_update",
            "--hidden-import",
            "atualizacao.automus_crypto",
            "--hidden-import",
            "pystray",
            "--distpath",
            str(DIST),
            "--workpath",
            str(BUILD / "pyinstaller"),
            "--specpath",
            str(BUILD),
            str(ENTRY),
        ],
        cwd=ROOT,
    )
    print(f"Automus pronto: {DIST / 'Automus.exe'}")
    print(r"Pode copiar apenas esse arquivo. Os complementos ficam em %APPDATA%\Automus\complemento.")


if __name__ == "__main__":
    main()
