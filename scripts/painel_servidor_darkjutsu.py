from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

tk = None
ttk = None
messagebox = None


PRIMARY_IP = "192.168.5.44"
RESERVE_IP = "192.168.5.38"
API_PORT = 8765
SHARE_ROOT = r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
EVENT_LOG = Path(SHARE_ROOT) / "logs" / "servidor_eventos_darkjutsu.txt"
LOCAL_LOG = Path(r"C:\DarkJutsu\logs\painel_servidor.log")


COLORS = {
    "bg": "#f4f7fb",
    "panel": "#ffffff",
    "text": "#152033",
    "muted": "#697386",
    "ok": "#1f9d55",
    "warn": "#c47f00",
    "bad": "#d64545",
    "line": "#dbe3ef",
    "blue": "#246bfe",
}


def log(text: str) -> None:
    try:
        LOCAL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOCAL_LOG.open("a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + " | " + text + "\n")
    except Exception:
        pass


def load_tkinter() -> None:
    global tk, ttk, messagebox
    if tk is not None:
        return
    try:
        import tkinter as tk_module
        from tkinter import messagebox as messagebox_module
        from tkinter import ttk as ttk_module

        tk = tk_module
        ttk = ttk_module
        messagebox = messagebox_module
        log("tkinter carregado")
    except Exception as exc:
        log(f"ERRO ao carregar tkinter: {type(exc).__name__}: {exc}")
        raise


def run_cmd(command: str, timeout: int = 8) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except Exception as exc:
        return 999, str(exc)


def health(ip: str) -> tuple[bool, str]:
    try:
        with urlopen(f"http://{ip}:{API_PORT}/health", timeout=4) as response:
            payload = response.read().decode("utf-8", errors="ignore")
            data = json.loads(payload)
            if data.get("ok") is True:
                return True, data.get("database_time", "ok")
            return False, payload[:160]
    except Exception as exc:
        return False, str(exc)


def local_ips() -> set[str]:
    ips: set[str] = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(item[4][0])
    except Exception:
        pass
    code, output = run_cmd("ipconfig", timeout=5)
    if code == 0:
        for line in output.splitlines():
            if "IPv4" in line and ":" in line:
                ips.add(line.split(":", 1)[1].strip())
    return ips


def port_listening(port: int) -> tuple[bool, str]:
    code, output = run_cmd(f'netstat -ano -p tcp | findstr /R /C:":{port} .*LISTENING"', timeout=5)
    return code == 0 and bool(output), output


def pg_ready() -> tuple[bool, str]:
    pg = r"C:\DarkJutsu\PostgreSQL\pgsql\bin\pg_isready.exe"
    if not os.path.exists(pg):
        return False, "pg_isready.exe nao encontrado"
    code, output = run_cmd(f'"{pg}" -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu', timeout=8)
    return code == 0, output


def recent_event_lines(hours: int = 72) -> list[str]:
    if not EVENT_LOG.exists():
        return []
    cutoff = time.time() - hours * 3600
    lines: list[str] = []
    for line in EVENT_LOG.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            stamp = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S").timestamp()
        except Exception:
            continue
        if stamp >= cutoff:
            lines.append(line)
    return lines


def recent_events(hours: int = 72) -> tuple[int, int, int]:
    lines = recent_event_lines(hours)
    falls = errors = warnings = 0
    for line in lines:
        upper = line.upper()
        if "| ERRO |" in upper:
            errors += 1
        if "| AVISO |" in upper:
            warnings += 1
        if "NENHUM SERVIDOR RESPONDEU" in upper or "VAI ASSUMIR" in upper or "FALHOU AO INICIAR" in upper:
            falls += 1
    return falls, errors, warnings


def friendly_event(line: str) -> str:
    parts = [part.strip() for part in line.split("|", 4)]
    if len(parts) < 5:
        return line
    stamp, machine, user, level, rest = parts
    if "|" in rest:
        component, message = [part.strip() for part in rest.split("|", 1)]
    else:
        component, message = "", rest
    upper = message.upper()
    prefix = f"{stamp} - {machine}"
    if "PRINCIPAL RESPONDEU" in upper or "PRINCIPAL ATIVA" in upper:
        return f"{prefix}: Principal respondeu. Reserva deve ficar parada."
    if "RESERVA RESPONDEU" in upper and "PRINCIPAL" in upper:
        return f"{prefix}: Reserva esta ativa; principal recebeu sinal para reassumir."
    if "RESERVA ATIVA" in upper:
        return f"{prefix}: Reserva esta segurando o sistema enquanto aguarda o principal voltar."
    if "NENHUM SERVIDOR RESPONDEU" in upper:
        return f"{prefix}: Queda detectada. Nenhum servidor respondeu ao health."
    if "VAI ASSUMIR" in upper or "INICIAR IMEDIATAMENTE" in upper:
        return f"{prefix}: Tentativa de restabelecimento. Este lado vai iniciar API/servidor."
    if "FALHOU AO INICIAR" in upper or "FALHOU" in upper:
        return f"{prefix}: ERRO na tentativa de restabelecimento. {message}"
    if "TICK" in upper:
        status = message.replace("Tick.", "Conversa entre guardioes:")
        status = status.replace("principal=0", "principal=online")
        status = status.replace("principal=1", "principal=offline")
        status = status.replace("reserva=0", "reserva=online")
        status = status.replace("reserva=1", "reserva=offline")
        return f"{prefix}: {status}"
    if level.upper() == "ERRO":
        return f"{prefix}: ERRO em {component}. {message}"
    if level.upper() == "AVISO":
        return f"{prefix}: Aviso em {component}. {message}"
    return f"{prefix}: {message}"


class Panel:
    def __init__(self) -> None:
        load_tkinter()
        self.root = tk.Tk()
        self.root.title("Dark-Jutsu - Servidores e APIs")
        self.root.geometry("760x560")
        self.root.minsize(700, 520)
        self.root.configure(bg=COLORS["bg"])

        self.status = tk.StringVar(value="Pronto para escanear")
        self.summary = tk.StringVar(value="Clique em Escanear agora.")
        self.cards: dict[str, dict[str, tk.Label]] = {}

        self._build()
        self.scan()

    def _build(self) -> None:
        top = tk.Frame(self.root, bg=COLORS["bg"])
        top.pack(fill="x", padx=24, pady=(20, 10))

        tk.Label(top, text="Dark-Jutsu", font=("Segoe UI", 22, "bold"), fg=COLORS["text"], bg=COLORS["bg"]).pack(anchor="w")
        tk.Label(top, text="Painel de servidores, APIs, portas e integridade", font=("Segoe UI", 11), fg=COLORS["muted"], bg=COLORS["bg"]).pack(anchor="w")

        actions = tk.Frame(top, bg=COLORS["bg"])
        actions.pack(anchor="e", fill="x", pady=(8, 0))
        ttk.Button(actions, text="Escanear agora", command=self.scan).pack(side="right")

        tk.Label(self.root, textvariable=self.summary, font=("Segoe UI", 12, "bold"), fg=COLORS["text"], bg=COLORS["bg"], wraplength=710, justify="left").pack(fill="x", padx=24, pady=(0, 12))

        grid = tk.Frame(self.root, bg=COLORS["bg"])
        grid.pack(fill="x", padx=24)
        self.cards["principal"] = self._card(grid, "Principal", PRIMARY_IP, 0)
        self.cards["reserva"] = self._card(grid, "Reserva", RESERVE_IP, 1)

        local = tk.Frame(self.root, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        local.pack(fill="x", padx=24, pady=16)
        tk.Label(local, text="Este computador", font=("Segoe UI", 14, "bold"), fg=COLORS["text"], bg=COLORS["panel"]).pack(anchor="w", padx=16, pady=(14, 4))
        self.local_text = tk.Label(local, text="Aguardando scan...", font=("Segoe UI", 10), fg=COLORS["muted"], bg=COLORS["panel"], justify="left")
        self.local_text.pack(anchor="w", padx=16, pady=(0, 14))

        op = tk.Frame(self.root, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        op.pack(fill="x", padx=24, pady=(0, 16))
        tk.Label(op, text="Leitura operacional", font=("Segoe UI", 14, "bold"), fg=COLORS["text"], bg=COLORS["panel"]).pack(anchor="w", padx=16, pady=(14, 4))
        self.operation_text = tk.Label(op, text="Aguardando scan...", font=("Segoe UI", 10), fg=COLORS["muted"], bg=COLORS["panel"], justify="left", wraplength=700)
        self.operation_text.pack(anchor="w", padx=16, pady=(0, 14))

        events = tk.Frame(self.root, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        events.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        tk.Label(events, text="Eventos e quedas nas ultimas 72h", font=("Segoe UI", 14, "bold"), fg=COLORS["text"], bg=COLORS["panel"]).pack(anchor="w", padx=16, pady=(14, 4))
        self.events_text = tk.Label(events, text="Aguardando scan...", font=("Segoe UI", 10), fg=COLORS["muted"], bg=COLORS["panel"], justify="left")
        self.events_text.pack(anchor="w", padx=16, pady=(0, 8))
        self.log_box = tk.Text(events, height=6, relief="flat", bg="#f8fafd", fg=COLORS["text"], font=("Consolas", 9), wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        tk.Label(self.root, textvariable=self.status, font=("Segoe UI", 9), fg=COLORS["muted"], bg=COLORS["bg"]).pack(anchor="w", padx=24, pady=(0, 12))

    def _card(self, parent: tk.Frame, title: str, ip: str, col: int) -> dict[str, tk.Label]:
        card = tk.Frame(parent, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        card.grid(row=0, column=col, sticky="ew", padx=(0, 12) if col == 0 else (12, 0))
        parent.grid_columnconfigure(col, weight=1)

        title_row = tk.Frame(card, bg=COLORS["panel"])
        title_row.pack(fill="x", padx=16, pady=(14, 8))
        dot = tk.Label(title_row, text="●", font=("Segoe UI", 22), fg=COLORS["muted"], bg=COLORS["panel"])
        dot.pack(side="left")
        tk.Label(title_row, text=f"{title}  {ip}", font=("Segoe UI", 14, "bold"), fg=COLORS["text"], bg=COLORS["panel"]).pack(side="left", padx=8)

        state = tk.Label(card, text="Aguardando scan", font=("Segoe UI", 12, "bold"), fg=COLORS["muted"], bg=COLORS["panel"])
        state.pack(anchor="w", padx=16)
        detail = tk.Label(card, text="", font=("Segoe UI", 10), fg=COLORS["muted"], bg=COLORS["panel"], justify="left", wraplength=295)
        detail.pack(anchor="w", padx=16, pady=(6, 16))
        return {"dot": dot, "state": state, "detail": detail}

    def scan(self) -> None:
        self.status.set("Escaneando servidores e portas...")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self) -> None:
        results = {
            "principal": health(PRIMARY_IP),
            "reserva": health(RESERVE_IP),
            "local": health("127.0.0.1"),
            "port_api": port_listening(API_PORT),
            "port_pg": port_listening(5433),
            "pg": pg_ready(),
            "ips": local_ips(),
            "events": recent_events(),
            "event_lines": recent_event_lines(),
        }
        self.root.after(0, lambda: self._render(results))

    def _render(self, r: dict) -> None:
        for key, label, ip in (("principal", "Principal", PRIMARY_IP), ("reserva", "Reserva", RESERVE_IP)):
            ok, msg = r[key]
            color = COLORS["ok"] if ok else COLORS["bad"]
            self.cards[key]["dot"].config(fg=color)
            self.cards[key]["state"].config(text="Online" if ok else "Offline", fg=color)
            self.cards[key]["detail"].config(text=f"{label} em {ip}\n{msg}")

        principal_ok = r["principal"][0]
        reserve_ok = r["reserva"][0]
        if principal_ok:
            self.summary.set("Principal online. Estado normal: usuarios devem usar o servidor principal.")
        elif reserve_ok:
            self.summary.set("Principal parado ou inacessivel. Reserva online: sistema esta em contingencia.")
        else:
            self.summary.set("Nenhum servidor respondeu agora. O guardiao da reserva deve tentar assumir automaticamente.")

        ips = ", ".join(sorted(r["ips"])) or "nao detectado"
        local_ok = "OK" if r["local"][0] else "OFF"
        api_port = "ouvindo" if r["port_api"][0] else "fechada"
        pg_port = "ouvindo" if r["port_pg"][0] else "fechada"
        pg = "pronto" if r["pg"][0] else "nao confirmado"
        is_reserve_pc = RESERVE_IP in r["ips"]
        reserve_ready = is_reserve_pc and r["port_pg"][0] and r["pg"][0]
        if is_reserve_pc and reserve_ready:
            reserve_readiness = "Reserva pronta para assumir: PostgreSQL local responde e porta 5433 esta aberta."
        elif is_reserve_pc:
            reserve_readiness = "Reserva NAO esta pronta para assumir: verifique PostgreSQL local, porta 5433 ou permissao dos scripts."
        else:
            reserve_readiness = "Este computador nao e a reserva inicial."
        self.local_text.config(
            text=f"Maquina: {socket.gethostname()} | Usuario: {os.environ.get('USERNAME', '')}\n"
            f"IPs locais: {ips}\nAPI local: {local_ok} | Porta 8765: {api_port} | Porta 5433: {pg_port} | PostgreSQL: {pg}\n"
            f"{reserve_readiness}"
        )

        falls, errors, warnings = r["events"]
        if principal_ok and reserve_ok:
            operational = (
                "ATENCAO: principal e reserva responderam ao mesmo tempo. "
                "O guardiao deve mandar a reserva parar quando detectar o principal online."
            )
        elif principal_ok:
            operational = "Estado esperado: principal online, reserva em espera. Nao ha contingencia ativa."
        elif reserve_ok:
            operational = (
                "Contingencia ativa: principal nao respondeu e reserva esta atendendo. "
                "Quando o principal voltar, ele deve reassumir e a reserva deve parar."
            )
        elif reserve_ready:
            operational = (
                "Queda total detectada: nenhum health respondeu, mas esta reserva parece pronta. "
                "O guardiao deve iniciar a API/servidor no proximo ciclo."
            )
        else:
            operational = (
                "Queda total detectada e reserva ainda nao esta pronta. "
                "Veja os erros/avisos abaixo antes de confiar no failover."
            )
        self.operation_text.config(text=operational)
        self.events_text.config(text=f"Quedas/tentativas: {falls} | Erros: {errors} | Avisos: {warnings}")
        self.log_box.delete("1.0", "end")
        lines = r["event_lines"][-24:]
        if lines:
            self.log_box.insert("end", "\n".join(friendly_event(line) for line in lines))
        else:
            self.log_box.insert("end", "Nenhum evento compartilhado nas ultimas 72 horas.")
        self.status.set(f"Ultimo scan: {datetime.now():%d/%m/%Y %H:%M:%S}")

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    try:
        log("abrindo painel")
        Panel().run()
    except Exception as exc:
        log(f"ERRO: {type(exc).__name__}: {exc}")
        try:
            if messagebox is not None:
                messagebox.showerror("Dark-Jutsu - Painel", f"Erro ao abrir painel:\n{type(exc).__name__}: {exc}")
        except Exception:
            pass
        raise
