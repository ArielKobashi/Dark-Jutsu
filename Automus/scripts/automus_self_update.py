import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import urlopen


@dataclass
class UpdateInfo:
    current_version: str
    latest_version: str
    manifest_url: str
    package_url: str
    package_name: str
    sha256: str
    current_sha256: str
    notes: list[str]

    @property
    def has_update(self) -> bool:
        version_compare = _compare_versions(self.latest_version, self.current_version)
        if version_compare > 0:
            return True
        if version_compare == 0 and self.current_sha256 and self.sha256:
            return self.current_sha256.lower() != self.sha256.lower()
        return False


def _version_parts(version: str) -> list[int]:
    parts: list[int] = []
    for piece in str(version or "").replace("-", ".").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or 0))
    return parts or [0]


def _compare_versions(left: str, right: str) -> int:
    a = _version_parts(left)
    b = _version_parts(right)
    size = max(len(a), len(b))
    a.extend([0] * (size - len(a)))
    b.extend([0] * (size - len(b)))
    return (a > b) - (a < b)


def load_local_version(script_dir: Path, bundled_script_dir: Path) -> dict:
    for path in (script_dir / "version.json", bundled_script_dir / "version.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return {"version": "dev"}


def get_manifest_url(script_dir: Path, bundled_script_dir: Path) -> str:
    data = load_local_version(script_dir, bundled_script_dir)
    return str(data.get("updateManifestUrl") or "").strip()


def get_manifest_firebase_path(script_dir: Path, bundled_script_dir: Path) -> str:
    data = load_local_version(script_dir, bundled_script_dir)
    return str(data.get("updateManifestFirebasePath") or "").strip().strip("/")


def _current_exe_sha256() -> str:
    try:
        if getattr(sys, "frozen", False):
            exe = Path(sys.executable)
            if exe.exists():
                return _sha256(exe).lower()
    except Exception:
        pass
    return ""


def update_info_from_manifest(current_version: str, manifest: dict, manifest_source: str) -> UpdateInfo:
    latest_version = str(manifest.get("version") or "").strip()
    package_name = str(manifest.get("package") or "Automus.zip").strip()
    package_url = str(manifest.get("packageUrl") or manifest.get("url") or "").strip()
    if not package_url and manifest_source.startswith(("http://", "https://")):
        package_url = urljoin(manifest_source, package_name)
    checksum = str(manifest.get("sha256") or "").strip().lower()
    notes = manifest.get("notes") if isinstance(manifest.get("notes"), list) else []

    if not latest_version:
        raise RuntimeError("Manifesto de atualizacao sem versao.")
    if not package_url:
        raise RuntimeError("Manifesto de atualizacao sem packageUrl.")
    if not checksum:
        raise RuntimeError("Manifesto de atualizacao sem SHA256.")

    return UpdateInfo(
        current_version=current_version,
        latest_version=latest_version,
        manifest_url=manifest_source,
        package_url=package_url,
        package_name=package_name,
        sha256=checksum,
        current_sha256=_current_exe_sha256(),
        notes=[str(note) for note in notes],
    )


def check_for_update(script_dir: Path, bundled_script_dir: Path, timeout: float = 20.0) -> Optional[UpdateInfo]:
    local = load_local_version(script_dir, bundled_script_dir)
    current_version = str(local.get("version") or "dev").strip()
    manifest_url = str(local.get("updateManifestUrl") or "").strip()
    if not manifest_url:
        return None

    with urlopen(manifest_url, timeout=timeout) as resp:
        manifest = json.loads(resp.read().decode("utf-8-sig"))

    return update_info_from_manifest(current_version, manifest, manifest_url)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_package(package_url: str, package_path: Path):
    parsed = urlparse(package_url)
    if parsed.scheme in ("http", "https"):
        with urlopen(package_url, timeout=90) as resp, package_path.open("wb") as fh:
            shutil.copyfileobj(resp, fh)
        return

    if parsed.scheme == "file":
        if parsed.netloc:
            source = Path(f"//{parsed.netloc}{unquote(parsed.path)}")
        else:
            source = Path(unquote(parsed.path))
    else:
        source = Path(package_url)

    if not source.exists():
        raise RuntimeError(f"Pacote de atualizacao nao encontrado: {source}")
    shutil.copy2(source, package_path)


def download_update(info: UpdateInfo) -> Path:
    work_dir = Path(tempfile.gettempdir()) / "AutomusUpdater" / info.latest_version
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    package_path = work_dir / info.package_name
    _copy_package(info.package_url, package_path)

    with zipfile.ZipFile(package_path, "r") as zf:
        zf.extractall(work_dir)

    exe_path = work_dir / "Automus.exe"
    if not exe_path.exists():
        raise RuntimeError("Pacote de atualizacao nao contem Automus.exe.")

    checksum = _sha256(exe_path).lower()
    if checksum != info.sha256:
        raise RuntimeError("SHA256 do Automus.exe baixado nao confere com o manifesto.")

    return exe_path


def install_downloaded_update(new_exe: Path) -> None:
    if not getattr(sys, "frozen", False):
        raise RuntimeError("A troca automatica do executavel so funciona no Automus.exe instalado.")

    current_exe = Path(sys.executable).resolve()
    helper = new_exe.parent / "instalar_automus_update.bat"
    pid = os.getpid()
    current_dir = current_exe.parent
    helper.write_text(
        "@echo off\r\n"
        "setlocal\r\n"
        "title Atualizando Automus\r\n"
        f'set "NEW_EXE={new_exe}"\r\n'
        f'set "CURRENT_EXE={current_exe}"\r\n'
        f'set "CURRENT_DIR={current_dir}"\r\n'
        f'set "PID={pid}"\r\n'
        'set "AUTOMUS_RUNTIME_TEMP=%APPDATA%\\Automus\\complemento\\RuntimeTemp"\r\n'
        "echo Atualizando Automus. Aguarde...\r\n"
        "echo Novo EXE: %NEW_EXE%\r\n"
        "echo EXE atual: %CURRENT_EXE%\r\n"
        ":wait_process\r\n"
        "echo Aguardando Automus atual encerrar...\r\n"
        'tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul\r\n'
        "if not errorlevel 1 (\r\n"
        "  timeout /t 1 /nobreak >nul\r\n"
        "  goto wait_process\r\n"
        ")\r\n"
        "timeout /t 2 /nobreak >nul\r\n"
        "taskkill /IM Automus.exe /F /T >nul 2>nul\r\n"
        'rmdir /S /Q "%PUBLIC%\\AutomusRuntimeTemp" >nul 2>nul\r\n'
        "set /a TRY=0\r\n"
        ":copy_retry\r\n"
        "set /a TRY+=1\r\n"
        "echo Copiando Automus.exe... tentativa %TRY%/30\r\n"
        'copy /Y "%NEW_EXE%" "%CURRENT_EXE%" >nul 2>nul\r\n'
        "if not errorlevel 1 goto start_app\r\n"
        "if %TRY% GEQ 30 goto fail\r\n"
        "echo Aguardando o Windows liberar o Automus.exe...\r\n"
        "timeout /t 1 /nobreak >nul\r\n"
        "goto copy_retry\r\n"
        ":start_app\r\n"
        "echo Atualizacao concluida.\r\n"
        "echo Abrindo Automus atualizado...\r\n"
        "timeout /t 2 /nobreak >nul\r\n"
        'echo Abrindo "%CURRENT_EXE%"\r\n'
        'start "" "%CURRENT_EXE%"\r\n'
        "goto done\r\n"
        ":done\r\n"
        "echo.\r\n"
        "echo Pronto. Se o Automus nao abriu sozinho, abra pelo Automus.exe atualizado.\r\n"
        "echo Esta janela vai fechar em 8 segundos.\r\n"
        "timeout /t 8 /nobreak >nul\r\n"
        "exit /b 0\r\n"
        ":fail\r\n"
        "echo.\r\n"
        "echo ERRO: nao foi possivel substituir o Automus.exe.\r\n"
        "echo Feche qualquer Automus aberto e tente atualizar novamente.\r\n"
        "pause\r\n"
        "exit /b 1\r\n",
        encoding="utf-8",
    )
    subprocess.Popen(["cmd.exe", "/c", "start", "Atualizando Automus", "cmd.exe", "/c", str(helper)], shell=False)
