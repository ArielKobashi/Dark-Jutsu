import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
BUILD = ROOT / "build" / "automus"
STAGE = BUILD / "stage"
STAGE_SCRIPTS = STAGE / "scripts"
DIST = ROOT / "dist"
ICON = BUILD / "automus.ico"
FIREBASE_CONFIG = SCRIPTS / "firebase_config.json"
RUNTIME_TMPDIR = Path(os.environ.get("PUBLIC") or r"C:\Users\Public") / "AutomusRuntimeTemp"


def python_console_executable() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        python_exe = exe.with_name("python.exe")
        if python_exe.exists():
            return str(python_exe)
    return sys.executable


def find_entry() -> Path:
    for candidate in SCRIPTS.glob("controladordeatualiza*.py"):
        return candidate
    raise FileNotFoundError("Arquivo principal do controlador Automus nao encontrado.")


def build_icon(path: Path):
    from PIL import Image, ImageDraw

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

    firebase_stage = STAGE_SCRIPTS / "firebase_config.json"
    if FIREBASE_CONFIG.exists():
        shutil.copy2(FIREBASE_CONFIG, firebase_stage)
        return

    index_path = ROOT / "index.html"
    if not index_path.exists():
        raise RuntimeError("Crie scripts/firebase_config.json antes de gerar o Automus.exe.")

    index_html = index_path.read_text(encoding="utf-8", errors="replace")
    api_match = re.search(r'apiKey:\s*"([^"]+)"', index_html)
    db_match = re.search(r'databaseURL:\s*"([^"]+)"', index_html)
    if not api_match or not db_match:
        raise RuntimeError("Nao foi possivel encontrar a configuracao Firebase.")
    firebase_stage.write_text(
        json.dumps(
            {
                "apiKey": api_match.group(1),
                "databaseURL": db_match.group(1),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def install_dependencies():
    python_exe = python_console_executable()
    requirements = ROOT / "requirements.txt"
    if requirements.exists():
        subprocess.check_call([python_exe, "-m", "pip", "install", "-r", str(requirements)])
        return
    subprocess.check_call([python_exe, "-m", "pip", "install", "pyinstaller", "pystray", "pillow", "openpyxl", "pynput"])


def main():
    entry = find_entry()
    python_exe = python_console_executable()
    install_dependencies()
    build_icon(ICON)
    prepare_stage()
    subprocess.check_call(
        [
            python_exe,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--onefile",
            "--windowed",
            "--name",
            "Automus",
            "--runtime-tmpdir",
            str(RUNTIME_TMPDIR),
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
            "pystray",
            "--distpath",
            str(DIST),
            "--workpath",
            str(BUILD / "pyinstaller"),
            "--specpath",
            str(BUILD),
            str(entry),
        ],
        cwd=ROOT,
    )
    print(f"Automus pronto: {DIST / 'Automus.exe'}")
    print("Pode copiar apenas esse arquivo. Ele criara a pasta AutomusData ao lado dele no primeiro uso.")


if __name__ == "__main__":
    main()
