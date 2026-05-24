import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
VERSION_PATH = SCRIPTS / "version.json"
DIST = ROOT / "dist"
EXE = DIST / "Automus.exe"
RELEASES = ROOT / "releases"


def load_version() -> dict:
    data = json.loads(VERSION_PATH.read_text(encoding="utf-8"))
    version = str(data.get("version") or "").strip()
    if not version:
        raise RuntimeError("Informe uma versao em scripts/version.json.")
    return data


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_exe():
    subprocess.check_call([sys.executable, str(SCRIPTS / "build_automus_exe.py")], cwd=ROOT)


def main():
    version_data = load_version()
    version = version_data["version"]
    build_exe()

    RELEASES.mkdir(parents=True, exist_ok=True)
    package_name = f"Automus-v{version}.zip"
    package_path = RELEASES / package_name
    checksum = sha256(EXE)
    update_base_url = str(version_data.get("updateBaseUrl") or "").strip()
    package_url = urljoin(update_base_url.rstrip("/") + "/", package_name) if update_base_url else ""

    manifest = {
        **version_data,
        "package": package_name,
        "exe": "Automus.exe",
        "sha256": checksum,
        "packagedAt": datetime.now().isoformat(timespec="seconds"),
        "install": "Feche o Automus antigo, coloque o novo Automus.exe no lugar e abra novamente."
    }
    if package_url:
        manifest["packageUrl"] = package_url

    manifest_path = RELEASES / "latest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(EXE, "Automus.exe")
        zf.write(VERSION_PATH, "version.json")
        zf.write(manifest_path, "latest.json")
        readme = ROOT / "README.md"
        if readme.exists():
            zf.write(readme, "README.md")

    shutil.copy2(manifest_path, DIST / "latest.json")
    print(f"Pacote pronto: {package_path}")
    print(f"SHA256: {checksum}")
    print("Envie esse .zip para os outros dispositivos.")


if __name__ == "__main__":
    main()
