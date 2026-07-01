from __future__ import annotations

import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext


DB_DIR = Path(__file__).resolve().parent
ROOT_DIR = DB_DIR.parent
SCRIPT = DB_DIR / "postgres-server.ps1"


class PostgresControlApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Dark-Jutsu SQL")
        self.geometry("780x480")
        self.minsize(680, 420)
        self.configure(padx=14, pady=14)

        self.status_var = tk.StringVar(value="Status: aguardando")

        title = tk.Label(self, text="Controle do PostgreSQL local", font=("Segoe UI", 15, "bold"))
        title.pack(anchor="w")

        subtitle = tk.Label(
            self,
            text="Banco: dark_jutsu | Host: 127.0.0.1 | Porta: 5433",
            font=("Segoe UI", 10),
        )
        subtitle.pack(anchor="w", pady=(2, 12))

        buttons = tk.Frame(self)
        buttons.pack(fill="x", pady=(0, 10))

        self._button(buttons, "Iniciar", "start").pack(side="left", padx=(0, 8))
        self._button(buttons, "Parar", "stop").pack(side="left", padx=(0, 8))
        self._button(buttons, "Reiniciar", "restart").pack(side="left", padx=(0, 8))
        self._button(buttons, "Status", "status").pack(side="left", padx=(0, 8))
        self._button(buttons, "Verificar", "check").pack(side="left", padx=(0, 8))

        status = tk.Label(self, textvariable=self.status_var, anchor="w", font=("Segoe UI", 10, "bold"))
        status.pack(fill="x", pady=(0, 8))

        self.output = scrolledtext.ScrolledText(self, wrap="word", font=("Consolas", 10), height=18)
        self.output.pack(fill="both", expand=True)

        footer = tk.Label(
            self,
            text="DATABASE_URL=postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu",
            anchor="w",
            font=("Segoe UI", 9),
        )
        footer.pack(fill="x", pady=(8, 0))

        self.after(300, lambda: self.run_action("status"))

    def _button(self, parent: tk.Frame, label: str, action: str) -> tk.Button:
        return tk.Button(parent, text=label, width=12, command=lambda: self.run_action(action))

    def append(self, text: str) -> None:
        self.output.insert("end", text)
        self.output.see("end")

    def run_action(self, action: str) -> None:
        self.status_var.set(f"Status: executando {action}...")
        self.append(f"\n> {action}\n")
        threading.Thread(target=self._run_action_worker, args=(action,), daemon=True).start()

    def _run_action_worker(self, action: str) -> None:
        try:
            cmd = [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                action,
            ]
            completed = subprocess.run(
                cmd,
                cwd=ROOT_DIR,
                text=True,
                capture_output=True,
                timeout=120,
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
            messagebox.showerror("Dark-Jutsu SQL", f"A acao '{action}' falhou. Veja o log na janela.")


if __name__ == "__main__":
    PostgresControlApp().mainloop()
