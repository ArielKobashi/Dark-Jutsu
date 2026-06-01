import json
import re
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

    index_html = (ROOT / "index.html").read_text(encoding="utf-8", errors="replace")
    api_match = re.search(r'apiKey:\s*"([^"]+)"', index_html)
    db_match = re.search(r'databaseURL:\s*"([^"]+)"', index_html)
    if not api_match or not db_match:
        raise RuntimeError("Não foi possível extrair a configuração Firebase do Dark Jutsu.")
    (STAGE_SCRIPTS / "firebase_config.json").write_text(
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


def prepare_encrypted_automus_config():
    if not AUTOMUS_CONFIG.exists():
        print("Aviso: automus_config.json nao encontrado; o exe dependera do login da sessao.")
        return

    sys.path.insert(0, str(SCRIPTS))
    from atualizacao.automus_crypto import encrypt_config, read_json

    firebase_cfg = read_json(STAGE_SCRIPTS / "firebase_config.json")
    api_key = str(firebase_cfg.get("apiKey") or "").strip()
    db_url = str(firebase_cfg.get("databaseURL") or "").strip().rstrip("/")
    if not api_key or not db_url:
        raise RuntimeError("firebase_config.json invalido para criptografar automus_config.")

    plain_cfg = read_json(AUTOMUS_CONFIG)
    email = str(plain_cfg.get("email") or "").strip()
    password = str(plain_cfg.get("password") or "").strip()
    if not email or not password:
        raise RuntimeError("Preencha email e password em scripts/atualizacao/automus_config.json antes do build.")

    encrypted = encrypt_config(plain_cfg, api_key, db_url)
    target = STAGE_SCRIPTS / "atualizacao" / "automus_config.enc.json"
    target.write_text(json.dumps(encrypted, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Credenciais Automus criptografadas no pacote: {target}")


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
