import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path, PureWindowsPath
from urllib.parse import urljoin


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
VERSION_PATH = SCRIPTS / "version.json"
DIST = ROOT / "dist"
APP_DIR = DIST / "Automus"
EXE = APP_DIR / "Automus.exe"
RELEASES = ROOT / "releases"


def python_console_executable() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        python_exe = exe.with_name("python.exe")
        if python_exe.exists():
            return str(python_exe)
    return sys.executable


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
    subprocess.check_call([python_console_executable(), str(SCRIPTS / "build_automus_exe.py")], cwd=ROOT)


def build_package_url(update_base_url: str, package_name: str) -> str:
    base = update_base_url.strip()
    if not base:
        return ""
    if base.startswith(("http://", "https://")):
        return urljoin(base.rstrip("/") + "/", package_name)
    if base.startswith("file://"):
        return urljoin(base.rstrip("/") + "/", package_name)
    return str(PureWindowsPath(base) / package_name)


def main():
    version_data = load_version()
    version = version_data["version"]
    build_exe()
    if not EXE.exists():
        raise RuntimeError(f"Build nao gerou {EXE}.")

    RELEASES.mkdir(parents=True, exist_ok=True)
    package_name = f"Automus-v{version}.zip"
    package_path = RELEASES / package_name
    checksum = sha256(EXE)
    update_base_url = str(version_data.get("updateBaseUrl") or "").strip()
    package_url = build_package_url(update_base_url, package_name)

    manifest = {
        **version_data,
        "package": package_name,
        "exe": "Automus.exe",
        "sha256": checksum,
        "layout": "onedir",
        "packagedAt": datetime.now().isoformat(timespec="seconds"),
        "install": "Feche o Automus antigo, extraia o pacote inteiro na pasta do Automus e abra novamente."
    }
    if package_url:
        manifest["packageUrl"] = package_url

    manifest_path = RELEASES / "latest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in APP_DIR.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(APP_DIR).as_posix())
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
