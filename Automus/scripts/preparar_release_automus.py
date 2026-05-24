import argparse
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
VERSION_PATH = SCRIPTS / "version.json"
RELEASES = ROOT / "releases"


def load_version() -> dict:
    if VERSION_PATH.exists():
        data = json.loads(VERSION_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    return {"app": "Automus", "version": "1.0.0", "notes": []}


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def ask_notes(current_notes: list[str]) -> list[str]:
    print("")
    print("Notas da versao. Digite uma por linha; deixe vazio para terminar.")
    print("Se nao digitar nada, mantenho as notas atuais.")
    notes: list[str] = []
    while True:
        line = input(f"Nota {len(notes) + 1}: ").strip()
        if not line:
            break
        notes.append(line)
    return notes or current_notes


def save_version(data: dict):
    VERSION_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_packager():
    subprocess.check_call([sys.executable, str(SCRIPTS / "package_automus_release.py")], cwd=ROOT)


def copy_to_publish_dir(version: str, publish_dir: str):
    target = Path(publish_dir).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    package_name = f"Automus-v{version}.zip"
    for filename in (package_name, "latest.json"):
        source = RELEASES / filename
        if source.exists():
            shutil.copy2(source, target / filename)
    print(f"Arquivos copiados para: {target}")


def open_releases_folder():
    try:
        subprocess.Popen(["explorer", str(RELEASES)])
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Prepara uma nova release do Automus.")
    parser.add_argument("--version", help="Nova versao, exemplo: 1.0.1")
    parser.add_argument("--note", action="append", dest="notes", help="Nota da versao. Pode repetir.")
    parser.add_argument("--publish-dir", help="Pasta local para copiar latest.json e o zip.")
    parser.add_argument("--no-open", action="store_true", help="Nao abrir a pasta releases ao final.")
    args = parser.parse_args()

    data = load_version()
    current_version = str(data.get("version") or "").strip()
    current_notes = [str(note) for note in data.get("notes", []) if str(note).strip()]

    print("=== Release Automus ===")
    version = args.version or ask("Nova versao", current_version)
    if not version:
        raise RuntimeError("Informe uma versao.")

    notes = args.notes if args.notes is not None else ask_notes(current_notes)
    update_manifest_url = ask("URL do latest.json", str(data.get("updateManifestUrl") or "")) if args.version is None else str(data.get("updateManifestUrl") or "")
    update_base_url = ask("URL base dos pacotes", str(data.get("updateBaseUrl") or "")) if args.version is None else str(data.get("updateBaseUrl") or "")
    publish_dir = args.publish_dir
    if args.version is None:
        publish_dir = ask("Pasta local para publicar/copiar, opcional", str(data.get("publishDir") or ""))

    data["app"] = str(data.get("app") or "Automus")
    data["version"] = version
    data["releasedAt"] = date.today().isoformat()
    data["updateManifestUrl"] = update_manifest_url
    data["updateBaseUrl"] = update_base_url
    data["notes"] = notes
    if publish_dir:
        data["publishDir"] = publish_dir
    elif "publishDir" in data:
        data.pop("publishDir", None)

    save_version(data)
    print("")
    print(f"Versao salva em {VERSION_PATH}")
    run_packager()

    publish_dir = publish_dir or str(data.get("publishDir") or "")
    if publish_dir:
        copy_to_publish_dir(version, publish_dir)

    if not args.no_open:
        open_releases_folder()

    print("")
    print("Pronto.")
    print(f"Publique estes arquivos: {RELEASES / f'Automus-v{version}.zip'} e {RELEASES / 'latest.json'}")


if __name__ == "__main__":
    main()
