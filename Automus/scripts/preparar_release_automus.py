import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
VERSION_PATH = SCRIPTS / "version.json"
RELEASES = ROOT / "releases"


def python_console_executable() -> str:
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        python_exe = exe.with_name("python.exe")
        if python_exe.exists():
            return str(python_exe)
    return sys.executable


def load_version() -> dict:
    if VERSION_PATH.exists():
        data = json.loads(VERSION_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    return {"app": "Automus", "version": "1.0.0", "notes": []}


def save_version(data: dict):
    VERSION_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def http_json(url: str, method: str = "GET", payload: dict | None = None, timeout: float = 30.0, headers_extra: dict | None = None):
    data = None
    headers = {"Accept": "application/json"}
    if headers_extra:
        headers.update(headers_extra)
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url=url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Falha de rede: {exc}") from exc


def publish_manifest_to_sql(channel: str, manifest: dict, log=print):
    base_url = os.environ.get("DARK_JUTSU_API_BASE_URL", "http://127.0.0.1:8765").rstrip("/")
    token = os.environ.get("DARK_JUTSU_API_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    clean_channel = (channel or "latest").strip().strip("/") or "latest"
    result = http_json(
        f"{base_url}/api/automus/releases/{clean_channel}",
        method="PUT",
        payload=manifest,
        headers_extra=headers,
    )
    version = (result or {}).get("release", {}).get("version") or manifest.get("version")
    log(f"Manifesto publicado no SQL: {clean_channel} {version}")


def ensure_manifest_package_url(manifest_path: Path, version: str) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not str(manifest.get("packageUrl") or "").strip():
        raise RuntimeError("Manifesto sem packageUrl. Confira updateBaseUrl no version.json.")
    manifest.setdefault("package", f"Automus-v{version}.zip")
    return manifest


def run_packager_once(log=print):
    proc = subprocess.Popen(
        [python_console_executable(), str(SCRIPTS / "package_automus_release.py")],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        log(line.rstrip())
    code = proc.wait()
    if code:
        raise subprocess.CalledProcessError(code, proc.args)


def run_packager(log=print):
    try:
        run_packager_once(log=log)
    except subprocess.CalledProcessError:
        log("Geracao falhou na primeira tentativa. Fechando Automus e tentando novamente...")
        close_running_automus(log=log)
        time.sleep(2)
        run_packager_once(log=log)


def close_running_automus(log=print):
    log("Fechando Automus aberto, se existir...")
    result = subprocess.run(["taskkill", "/IM", "Automus.exe", "/F", "/T"], text=True, capture_output=True)
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode == 0:
        log("Automus aberto foi fechado.")
    elif "nao foi encontrado" in output.lower() or "não foi encontrado" in output.lower() or "not found" in output.lower():
        log("Nenhum Automus aberto encontrado.")
    else:
        log(output or "Nenhum Automus aberto encontrado.")


def copy_to_publish_dir(version: str, publish_dir: str, log=print):
    target = Path(publish_dir).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    package_name = f"Automus-v{version}.zip"
    for filename in (package_name, "latest.json", "latest"):
        source = RELEASES / filename
        if source.exists():
            shutil.copy2(source, target / filename)
    log(f"Arquivos copiados para: {target}")


def open_releases_folder():
    try:
        subprocess.Popen(["explorer", str(RELEASES)])
    except Exception:
        pass


def bump_patch(version: str) -> str:
    parts = str(version or "1.0.0").split(".")
    while len(parts) < 3:
        parts.append("0")
    try:
        parts[-1] = str(int(parts[-1]) + 1)
    except Exception:
        parts.append("1")
    return ".".join(parts)


def prepare_release(
    version: str,
    notes: list[str],
    publish_dir: str = "",
    publish_sql: bool = True,
    open_folder: bool = True,
    log=print,
):
    data = load_version()
    version = version.strip()
    if not version:
        raise RuntimeError("Informe uma versao.")
    notes = notes or [f"Atualizacao Automus {version}"]
    publish_dir = publish_dir or str(data.get("publishDir") or "")

    data["app"] = str(data.get("app") or "Automus")
    data["version"] = version
    data["releasedAt"] = date.today().isoformat()
    data["notes"] = notes
    if publish_dir:
        data["publishDir"] = publish_dir

    save_version(data)
    log(f"Versao salva em {VERSION_PATH}")
    close_running_automus(log=log)
    run_packager(log=log)

    if publish_dir:
        copy_to_publish_dir(version, publish_dir, log=log)

    manifest = ensure_manifest_package_url(RELEASES / "latest.json", version)
    if publish_sql:
        try:
            publish_manifest_to_sql("latest", manifest, log=log)
        except Exception as exc:
            log(f"Nao foi possivel publicar manifesto no SQL: {exc}")

    if open_folder:
        open_releases_folder()

    log("Pronto.")
    log(f"Pacote: {RELEASES / f'Automus-v{version}.zip'}")


def run_gui():
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk

    data = load_version()
    current_version = str(data.get("version") or "1.0.0")
    publish_dir = str(data.get("publishDir") or "")
    current_notes = "\n".join(str(note) for note in data.get("notes", []) if str(note).strip())
    messages: "queue.Queue[tuple[str, str]]" = queue.Queue()

    root = tk.Tk()
    root.title("Atualizar Automus")
    root.geometry("560x500")
    root.minsize(520, 460)
    bg = "#0f172a"
    panel = "#111827"
    text = "#e5e7eb"
    muted = "#94a3b8"
    accent = "#22c55e"
    root.configure(bg=bg)

    def make_label(parent, value="", **kw):
        return tk.Label(parent, text=value, bg=kw.pop("bg", bg), fg=kw.pop("fg", text), font=kw.pop("font", ("Segoe UI", 9, "bold")), **kw)

    header = tk.Frame(root, bg=bg)
    header.pack(fill="x", padx=12, pady=(10, 6))
    header.columnconfigure(0, weight=1)
    make_label(header, "Atualizar Automus", font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w")
    make_label(header, f"Versao atual: {current_version}", fg=muted, font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w")

    form = tk.Frame(root, bg=panel, highlightbackground="#334155", highlightthickness=1)
    form.pack(fill="x", padx=12, pady=(0, 6), ipady=6)
    form.columnconfigure(0, weight=1)

    version_var = tk.StringVar(value=bump_patch(current_version))

    make_label(form, "Nova versao", bg=panel).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 3))
    version_entry = tk.Entry(form, textvariable=version_var, bg="#020617", fg=text, insertbackground=text, relief="flat", font=("Segoe UI", 11))
    version_entry.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6), ipady=5)

    make_label(form, "Notas da versao", bg=panel).grid(row=2, column=0, sticky="w", padx=10, pady=(0, 3))
    notes_box = tk.Text(form, height=3, bg="#020617", fg=text, insertbackground=text, relief="flat", font=("Segoe UI", 9))
    notes_box.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 6))
    notes_box.insert("1.0", current_notes or "Atualizacao do Automus")

    make_label(form, f"Pasta: {publish_dir or 'nao configurada'}", bg=panel, fg=muted, font=("Segoe UI", 8)).grid(row=4, column=0, sticky="w", padx=10, pady=(0, 5))
    make_label(form, "Publicacao: SQL/API", bg=panel, fg=muted, font=("Segoe UI", 8)).grid(row=5, column=0, sticky="w", padx=10, pady=(0, 8))

    status_var = tk.StringVar(value="Pronto para gerar e publicar.")
    make_label(root, "", textvariable=status_var, fg=muted, font=("Segoe UI", 8)).pack(fill="x", padx=12)
    progress = ttk.Progressbar(root, mode="indeterminate")
    progress.pack(fill="x", padx=12, pady=(3, 6))

    log_box = scrolledtext.ScrolledText(root, height=7, bg="#020617", fg=text, insertbackground=text, relief="flat", font=("Consolas", 8), state="disabled")
    log_box.pack(fill="both", expand=True, padx=12, pady=(0, 8))

    actions = tk.Frame(root, bg=bg)
    actions.pack(fill="x", padx=12, pady=(0, 10))
    running = {"value": False}

    def append_log(message: str):
        messages.put(("log", message))

    def start_release():
        if running["value"]:
            return
        notes = [line.strip() for line in notes_box.get("1.0", "end").splitlines() if line.strip()]
        running["value"] = True
        start_btn.configure(state="disabled")
        progress.start(12)
        status_var.set("Gerando release...")

        def worker():
            try:
                prepare_release(
                    version=version_var.get(),
                    notes=notes,
                    publish_dir=publish_dir,
                    open_folder=True,
                    log=append_log,
                )
                messages.put(("done", "Release publicada com sucesso."))
            except Exception as exc:
                messages.put(("error", str(exc)))

        threading.Thread(target=worker, name="automus-release-gui", daemon=True).start()

    def pump_messages():
        while True:
            try:
                kind, message = messages.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                log_box.configure(state="normal")
                log_box.insert("end", message + "\n")
                log_box.see("end")
                log_box.configure(state="disabled")
                status_var.set(message[-140:] or "Trabalhando...")
            elif kind in ("done", "error"):
                progress.stop()
                running["value"] = False
                start_btn.configure(state="normal")
                status_var.set(message)
                if kind == "done":
                    messagebox.showinfo("Atualizar Automus", message)
                else:
                    messagebox.showerror("Atualizar Automus", "Falha ao publicar. Veja o log na janela.")
        root.after(80, pump_messages)

    start_btn = tk.Button(actions, text="ENVIAR ATUALIZACAO", command=start_release, bg=accent, fg="#04130a", relief="flat", font=("Segoe UI", 11, "bold"), cursor="hand2")
    start_btn.pack(side="left", fill="x", expand=True, ipady=9)
    tk.Button(actions, text="Fechar", command=root.destroy, bg="#334155", fg=text, relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2").pack(side="right", padx=(8, 0), ipady=9, ipadx=12)
    tk.Button(header, text="ENVIAR", command=start_release, bg=accent, fg="#04130a", relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2").grid(row=0, column=1, rowspan=2, sticky="e", padx=(8, 0), ipadx=12, ipady=6)

    pump_messages()
    version_entry.focus_set()
    root.mainloop()


def cli_main(args):
    data = load_version()
    notes = args.notes or [f"Atualizacao Automus {args.version}"]
    publish_dir = args.publish_dir or str(data.get("publishDir") or "")
    prepare_release(
        version=args.version,
        notes=notes,
        publish_dir=publish_dir,
        open_folder=not args.no_open,
    )


def main():
    parser = argparse.ArgumentParser(description="Prepara uma nova release do Automus.")
    parser.add_argument("--version", help="Nova versao, exemplo: 1.0.1")
    parser.add_argument("--note", action="append", dest="notes", help="Nota da versao. Pode repetir.")
    parser.add_argument("--publish-dir", help="Pasta local para copiar latest.json e o zip.")
    parser.add_argument("--no-open", action="store_true", help="Nao abrir a pasta releases ao final.")
    args = parser.parse_args()
    if args.version:
        cli_main(args)
    else:
        run_gui()


if __name__ == "__main__":
    main()
