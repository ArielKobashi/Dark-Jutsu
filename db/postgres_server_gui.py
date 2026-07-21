from __future__ import annotations

import json
import os
import subprocess
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, scrolledtext
from urllib.request import urlopen


DB_DIR = Path(__file__).resolve().parent
ROOT_DIR = DB_DIR.parent
SHARE_ROOT = r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
SCRIPTS_DIR = Path(SHARE_ROOT) / "scripts"
PRIMARY_IP = "192.168.5.44"
RESERVE_IP = "192.168.5.38"
API_PORT = 8765


class ServerControlApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Dark-Jutsu Servidor")
        self.geometry("900x600")
        self.minsize(780, 500)
        self.configure(padx=14, pady=14)

        self.status_var = tk.StringVar(value="Status: aguardando")
        self.ip_var = tk.StringVar(value="IP local: detectando...")

        title = tk.Label(self, text="Controle do servidor Dark-Jutsu", font=("Segoe UI", 15, "bold"))
        title.pack(anchor="w")

        subtitle = tk.Label(
            self,
            text="PostgreSQL: 5433 | API: 8765 | Principal: 192.168.5.44 | Reserva: 192.168.5.38",
            font=("Segoe UI", 10),
        )
        subtitle.pack(anchor="w", pady=(2, 2))

        ip_label = tk.Label(self, textvariable=self.ip_var, font=("Segoe UI", 10))
        ip_label.pack(anchor="w", pady=(0, 12))

        rows = tk.Frame(self)
        rows.pack(fill="x", pady=(0, 10))

        row1 = tk.Frame(rows)
        row1.pack(fill="x", pady=(0, 6))
        self._button(row1, "Iniciar PostgreSQL", "start_pg", 16).pack(side="left", padx=(0, 8))
        self._button(row1, "Parar PostgreSQL", "stop_pg", 16).pack(side="left", padx=(0, 8))
        self._button(row1, "Iniciar API", "start_api", 14).pack(side="left", padx=(0, 8))
        self._button(row1, "Parar API", "stop_api", 14).pack(side="left", padx=(0, 8))
        self._button(row1, "Status Portas", "status", 14).pack(side="left", padx=(0, 8))

        row2 = tk.Frame(rows)
        row2.pack(fill="x", pady=(0, 6))
        self._button(row2, "Testar Tudo", "test_all", 16).pack(side="left", padx=(0, 8))
        self._button(row2, "Backup Agora", "backup", 16).pack(side="left", padx=(0, 8))
        self._button(row2, "Restore Reserva", "restore", 16).pack(side="left", padx=(0, 8))
        self._button(row2, "Tornar Servidor", "assume", 16).pack(side="left", padx=(0, 8))
        self._button(row2, "Abrir Sistema", "open_app", 14).pack(side="left", padx=(0, 8))
        self._button(row2, "Health Local", "health_local", 14).pack(side="left", padx=(0, 8))

        status = tk.Label(self, textvariable=self.status_var, anchor="w", font=("Segoe UI", 10, "bold"))
        status.pack(fill="x", pady=(0, 8))

        self.output = scrolledtext.ScrolledText(self, wrap="word", font=("Consolas", 10), height=20)
        self.output.pack(fill="both", expand=True)

        footer = tk.Label(
            self,
            text=(
                f"Sistema: http://{PRIMARY_IP}:{API_PORT}/app/index.html ou reserva ativa"
                " | API local: http://127.0.0.1:8765/health"
            ),
            anchor="w",
            font=("Segoe UI", 9),
        )
        footer.pack(fill="x", pady=(8, 0))

        self.after(300, self.detect_ip)
        self.after(700, lambda: self.run_action("status"))

    def _button(self, parent: tk.Frame, label: str, action: str, width: int) -> tk.Button:
        return tk.Button(parent, text=label, width=width, command=lambda: self.run_action(action))

    def append(self, text: str) -> None:
        self.output.insert("end", text)
        self.output.see("end")

    def detect_ip(self) -> None:
        try:
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    "(Get-NetIPAddress -AddressFamily IPv4 | "
                    "Where-Object { $_.IPAddress -like '192.168.*' -and $_.PrefixOrigin -ne 'WellKnown' } | "
                    "Select-Object -First 1 -ExpandProperty IPAddress)",
                ],
                text=True,
                capture_output=True,
                timeout=10,
            )
            ip = completed.stdout.strip() or "nao detectado"
            self.ip_var.set(f"IP local: {ip}")
        except Exception:
            self.ip_var.set("IP local: nao detectado")

    def run_action(self, action: str) -> None:
        if action == "open_app":
            webbrowser.open(self.active_app_url())
            return
        if action == "health_local":
            webbrowser.open("http://127.0.0.1:8765/health")
            return
        self.status_var.set(f"Status: executando {action}...")
        self.append(f"\n> {action}\n")
        threading.Thread(target=self._run_action_worker, args=(action,), daemon=True).start()

    def command_for(self, action: str) -> list[str]:
        script_map = {
            "start_pg": SCRIPTS_DIR / "iniciar_postgres_darkjutsu.bat",
            "stop_pg": SCRIPTS_DIR / "parar_postgres_darkjutsu.bat",
            "stop_api": SCRIPTS_DIR / "parar_api_darkjutsu.bat",
            "test_all": SCRIPTS_DIR / "testar_servidor_darkjutsu.bat",
            "backup": SCRIPTS_DIR / "backup_postgres_darkjutsu.bat",
            "restore": SCRIPTS_DIR / "restaurar_backup_reserva_darkjutsu.bat",
            "assume": SCRIPTS_DIR / "assumir_servidor_darkjutsu.bat",
        }
        if action == "start_api":
            return ["cmd", "/c", "start", "Dark-Jutsu API", str(ROOT_DIR / "api" / "iniciar_api_servidor.bat")]
        if action == "status":
            return [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                (
                    "Write-Host 'PostgreSQL 5433:'; "
                    "Get-NetTCPConnection -LocalPort 5433 -State Listen -ErrorAction SilentlyContinue | "
                    "Select-Object LocalAddress,LocalPort,State,OwningProcess | Format-Table -AutoSize; "
                    "Write-Host ''; Write-Host 'API 8765:'; "
                    "Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | "
                    "Select-Object LocalAddress,LocalPort,State,OwningProcess | Format-Table -AutoSize; "
                    "Write-Host ''; "
                    "try { Invoke-RestMethod -Uri 'http://127.0.0.1:8765/health' -TimeoutSec 3 | ConvertTo-Json -Compress } "
                    "catch { Write-Host 'Health local indisponivel' }"
                ),
            ]
        script = script_map[action]
        return ["cmd", "/c", str(script)]

    def active_app_url(self) -> str:
        return f"http://127.0.0.1:{API_PORT}/app/index.html"

    def _run_action_worker(self, action: str) -> None:
        try:
            completed = subprocess.run(
                self.command_for(action),
                cwd=ROOT_DIR,
                text=True,
                capture_output=True,
                timeout=240,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            output = completed.stdout
            if completed.stderr:
                output += "\n" + completed.stderr
            if not output.strip():
                output = f"{action} concluido sem mensagens.\n"
            self.after(0, lambda: self._finish_action(action, completed.returncode, output))
        except Exception as exc:
            self.after(0, lambda: self._finish_action(action, 1, f"Erro: {exc}\n"))

    def _finish_action(self, action: str, returncode: int, output: str) -> None:
        self.append(output)
        if not output.endswith("\n"):
            self.append("\n")
        if returncode == 0:
            self.status_var.set(f"Status: {action} concluido")
        else:
            self.status_var.set(f"Status: {action} falhou")
            messagebox.showerror("Dark-Jutsu Servidor", f"A acao '{action}' falhou. Veja o log na janela.")


if __name__ == "__main__":
    ServerControlApp().mainloop()
