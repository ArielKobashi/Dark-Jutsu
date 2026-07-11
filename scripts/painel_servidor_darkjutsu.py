from __future__ import annotations

import html
import json
import os
import socket
import subprocess
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen


PRIMARY_IP = "192.168.5.44"
RESERVE_IP = "192.168.5.38"
API_PORT = 8765
SHARE_ROOT = r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
EVENT_LOG = Path(SHARE_ROOT) / "logs" / "servidor_eventos_darkjutsu.txt"
LOCAL_LOG = Path(r"C:\DarkJutsu\logs\painel_servidor.log")
REPORT_FILE = Path(r"C:\DarkJutsu\logs\painel_servidor_darkjutsu.html")


COLORS = {
    "bg": "#f4f7fb",
    "panel": "#ffffff",
    "text": "#152033",
    "muted": "#697386",
    "ok": "#1f9d55",
    "warn": "#c47f00",
    "bad": "#d64545",
    "line": "#dbe3ef",
}


def log(text: str) -> None:
    try:
        LOCAL_LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOCAL_LOG.open("a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + " | " + text + "\n")
    except Exception:
        pass


def run_cmd(command: str, timeout: int = 8) -> tuple[int, str]:
    try:
        proc = subprocess.run(command, shell=True, capture_output=True, text=True, errors="ignore", timeout=timeout)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except Exception as exc:
        return 999, str(exc)


def health(ip: str) -> tuple[bool, str]:
    try:
        with urlopen(f"http://{ip}:{API_PORT}/health", timeout=3) as response:
            payload = response.read().decode("utf-8", errors="ignore")
            data = json.loads(payload)
            if data.get("ok") is True:
                return True, data.get("database_time", "ok")
            return False, payload[:180]
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


def event_counts(lines: list[str]) -> tuple[int, int, int]:
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
    stamp, machine, _user, level, rest = parts
    if "|" in rest:
        component, message = [part.strip() for part in rest.split("|", 1)]
    else:
        component, message = "", rest
    upper = message.upper()
    prefix = f"{stamp} - {machine}"
    if component.upper() == "ATUALIZACAO":
        if level.upper() == "OK":
            return f"{prefix}: Atualizacao GitHub aplicada com sucesso. {message}"
        if level.upper() == "ERRO":
            return f"{prefix}: ERRO na atualizacao GitHub. {message}"
        return f"{prefix}: Atualizacao GitHub. {message}"
    if component.upper() == "AUTOATUALIZACAO":
        if level.upper() == "OK":
            return f"{prefix}: Guardiao/monitor local atualizado automaticamente. {message}"
        if level.upper() == "ERRO":
            return f"{prefix}: ERRO na autoatualizacao local. {message}"
        return f"{prefix}: Autoatualizacao local. {message}"
    if "PRINCIPAL RESPONDEU" in upper or "PRINCIPAL ATIVA" in upper:
        return f"{prefix}: Principal respondeu. Reserva deve ficar parada."
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


def collect() -> dict:
    events = recent_event_lines()
    return {
        "principal": health(PRIMARY_IP),
        "reserva": health(RESERVE_IP),
        "local": health("127.0.0.1"),
        "api_port": port_listening(API_PORT),
        "pg_port": port_listening(5433),
        "pg": pg_ready(),
        "ips": local_ips(),
        "events": events,
        "counts": event_counts(events),
    }


def problem_messages(data: dict) -> list[tuple[str, str]]:
    problems: list[tuple[str, str]] = []
    principal_ok = data["principal"][0]
    reserve_ok = data["reserva"][0]
    ips = data["ips"]
    is_reserve = RESERVE_IP in ips
    is_primary = PRIMARY_IP in ips

    if principal_ok and not reserve_ok:
        problems.append((
            "OK: reserva sem API e principal online",
            "Isso e esperado. Quando o principal responde, a reserva deve ficar parada para evitar dois servidores ativos.",
        ))
    elif not principal_ok and reserve_ok:
        problems.append((
            "CONTINGENCIA: principal nao respondeu",
            "A reserva esta atendendo. Quando o principal voltar, ele deve reassumir e a reserva deve parar.",
        ))
    elif principal_ok and reserve_ok:
        problems.append((
            "ATENCAO: dois servidores responderam",
            "Principal e reserva estao online ao mesmo tempo. O guardiao deve mandar a reserva parar no proximo ciclo.",
        ))
    elif not principal_ok and not reserve_ok:
        problems.append((
            "ERRO: nenhum servidor respondeu",
            "Nenhuma API respondeu ao /health. A reserva deve assumir se PostgreSQL e porta 5433 estiverem prontos.",
        ))

    if is_reserve and not data["pg"][0]:
        problems.append((
            "Reserva nao pronta: PostgreSQL nao confirmado",
            "Sem PostgreSQL local pronto, a reserva nao consegue assumir com seguranca.",
        ))
    if is_reserve and not data["pg_port"][0]:
        problems.append((
            "Reserva nao pronta: porta 5433 fechada",
            "A porta do PostgreSQL local nao esta ouvindo. Inicie/verifique o PostgreSQL portatil.",
        ))

    recent_errors = []
    for line in data["events"][-80:]:
        upper = line.upper()
        if "| ERRO |" not in upper and "| AVISO |" not in upper:
            continue
        if "AUTOATUALIZACAO" in upper:
            recent_errors.append((
                "Aviso/erro recente de autoatualizacao local",
                friendly_event(line),
            ))
        elif "GIT NAO ENCONTRADO NA RESERVA" in upper:
            recent_errors.append((
                "Atualizacao GitHub na reserva sem Git",
                "Nao afeta o servidor se o principal tiver Git. Para a reserva tambem atualizar, instale/copiar PortableGit nela.",
            ))
        elif "GIT NAO ENCONTRADO NO PRINCIPAL" in upper:
            recent_errors.append((
                "Atualizacao GitHub parada no principal",
                "O principal nao achou git.exe. Sem isso, o fileserver nao puxa novas versoes do GitHub.",
            ))
        elif "FALHA AO PUBLICAR ATUALIZACAO" in upper or "CODIGO=16" in upper:
            recent_errors.append((
                "Atualizacao GitHub falhou ao publicar",
                "Robocopy retornou erro ao copiar para o fileserver. Veja C:\\DarkJutsu\\logs\\atualizacao_github.log na maquina que tentou atualizar.",
            ))
        elif "ATUALIZACAO" in upper:
            recent_errors.append((
                "Aviso/erro recente de atualizacao",
                friendly_event(line),
            ))

    seen = set()
    for title, detail in recent_errors:
        if title in seen:
            continue
        seen.add(title)
        problems.append((title, detail))

    if is_primary and not any("Atualizacao" in title for title, _detail in problems):
        problems.append((
            "OK: principal pode cuidar das atualizacoes",
            "Este PC tem o papel principal. Se ele tiver Git funcionando, ele publica novas versoes do GitHub.",
        ))
    return problems


def state_text(data: dict) -> tuple[str, str, str]:
    principal_ok = data["principal"][0]
    reserve_ok = data["reserva"][0]
    ips = data["ips"]
    reserve_ready = RESERVE_IP in ips and data["pg_port"][0] and data["pg"][0]
    if principal_ok and reserve_ok:
        return "ATENCAO: principal e reserva responderam ao mesmo tempo.", "warn", "O guardiao deve mandar a reserva parar."
    if principal_ok:
        return "Estado normal: principal online.", "ok", "Reserva deve ficar em espera."
    if reserve_ok:
        return "Contingencia ativa: reserva esta atendendo.", "warn", "Principal nao respondeu; quando voltar deve reassumir."
    if reserve_ready:
        return "Queda total detectada, mas reserva parece pronta.", "warn", "O guardiao deve assumir no proximo ciclo."
    return "Queda total e reserva nao confirmada.", "bad", "Verifique PostgreSQL, porta 5433 e API local."


def render_html(data: dict) -> str:
    summary, klass, detail = state_text(data)
    falls, errors, warnings = data["counts"]
    lines = "\n".join(html.escape(friendly_event(line)) for line in data["events"][-24:])
    problems = "".join(f"<li><b>{html.escape(title)}</b><br>{html.escape(detail)}</li>" for title, detail in problem_messages(data))
    return f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Dark-Jutsu - Teste</title>
<style>body{{font-family:Segoe UI,Arial;background:#f4f7fb;color:#152033;margin:20px}}.box{{background:white;border:1px solid #dbe3ef;padding:14px;margin:10px 0;max-width:760px}}.ok{{color:#1f9d55}}.warn{{color:#c47f00}}.bad{{color:#d64545}}pre{{white-space:pre-wrap;background:#f8fafd;padding:10px;max-height:260px;overflow:auto}}</style>
<h1>Dark-Jutsu</h1><div class="box"><h2 class="{klass}">{html.escape(summary)}</h2><p>{html.escape(detail)}</p></div>
<div class="box"><b>Principal:</b> {data["principal"][0]} - {html.escape(data["principal"][1])}<br><b>Reserva:</b> {data["reserva"][0]} - {html.escape(data["reserva"][1])}</div>
<div class="box"><b>Local:</b> {html.escape(socket.gethostname())}<br><b>IPs:</b> {html.escape(", ".join(sorted(data["ips"])))}<br><b>API 8765:</b> {data["api_port"][0]} | <b>Postgres 5433:</b> {data["pg_port"][0]} | <b>PostgreSQL:</b> {data["pg"][0]}</div>
<div class="box"><h2>Problemas encontrados / leitura clara</h2><ul>{problems}</ul></div>
<div class="box"><b>72h:</b> {falls} quedas/tentativas, {errors} erros, {warnings} avisos<pre>{lines or "Nenhum evento."}</pre></div></html>"""


def fallback_html(data: dict) -> None:
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(render_html(data), encoding="utf-8")
    webbrowser.open(REPORT_FILE.as_uri())


class TkPanel:
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = tk.Tk()
        self.root.title("Dark-Jutsu - Teste do Servidor")
        self.root.geometry("760x640")
        self.root.minsize(700, 580)
        self.root.configure(bg=COLORS["bg"])
        self.summary = tk.StringVar(value="Escaneando...")
        self.detail = tk.StringVar(value="")
        self.local = tk.StringVar(value="")
        self.events_text = tk.StringVar(value="")
        self.cards: dict[str, dict[str, object]] = {}
        self._build()
        self.scan()

    def _label(self, parent, text="", size=10, bold=False, color=None):
        font = ("Segoe UI", size, "bold" if bold else "normal")
        return self.tk.Label(parent, text=text, font=font, fg=color or COLORS["text"], bg=parent["bg"], justify="left")

    def _build(self) -> None:
        tk = self.tk
        ttk = self.ttk
        top = tk.Frame(self.root, bg=COLORS["bg"])
        top.pack(fill="x", padx=18, pady=(14, 8))
        self._label(top, "Dark-Jutsu", 22, True).pack(anchor="w")
        self._label(top, "Servidores, APIs, portas, failover e atualizacao GitHub", 10, False, COLORS["muted"]).pack(anchor="w")
        ttk.Button(top, text="Escanear agora", command=self.scan).pack(anchor="e")
        self.summary_label = self._label(self.root, size=12, bold=True)
        self.summary_label.pack(fill="x", padx=18, pady=(0, 4))
        self.detail_label = self._label(self.root, size=10, color=COLORS["muted"])
        self.detail_label.pack(fill="x", padx=18, pady=(0, 10))

        grid = tk.Frame(self.root, bg=COLORS["bg"])
        grid.pack(fill="x", padx=18)
        self.cards["principal"] = self._card(grid, "Principal", PRIMARY_IP, 0)
        self.cards["reserva"] = self._card(grid, "Reserva", RESERVE_IP, 1)

        local_box = tk.Frame(self.root, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        local_box.pack(fill="x", padx=18, pady=12)
        self._label(local_box, "Este computador", 13, True).pack(anchor="w", padx=12, pady=(10, 4))
        self.local_label = self._label(local_box, size=10, color=COLORS["muted"])
        self.local_label.pack(anchor="w", padx=12, pady=(0, 10))

        problems = tk.Frame(self.root, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        problems.pack(fill="x", padx=18, pady=(0, 12))
        self._label(problems, "Problemas encontrados / leitura clara", 13, True).pack(anchor="w", padx=12, pady=(10, 4))
        self.problems_label = self._label(problems, size=10, color=COLORS["muted"])
        self.problems_label.pack(anchor="w", padx=12, pady=(0, 10))

        events = tk.Frame(self.root, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        events.pack(fill="both", expand=True, padx=18, pady=(0, 14))
        self._label(events, "Eventos traduzidos das ultimas 72h", 13, True).pack(anchor="w", padx=12, pady=(10, 4))
        self.events_label = self._label(events, size=10, color=COLORS["muted"])
        self.events_label.pack(anchor="w", padx=12, pady=(0, 6))
        self.log_box = tk.Text(events, height=7, relief="flat", bg="#f8fafd", fg=COLORS["text"], font=("Consolas", 9), wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _card(self, parent, title: str, ip: str, col: int) -> dict[str, object]:
        tk = self.tk
        card = tk.Frame(parent, bg=COLORS["panel"], highlightbackground=COLORS["line"], highlightthickness=1)
        card.grid(row=0, column=col, sticky="ew", padx=(0, 8) if col == 0 else (8, 0))
        parent.grid_columnconfigure(col, weight=1)
        self._label(card, f"{title} {ip}", 13, True).pack(anchor="w", padx=12, pady=(10, 4))
        state = self._label(card, "Aguardando", 11, True, COLORS["muted"])
        state.pack(anchor="w", padx=12)
        detail = self._label(card, "", 9, False, COLORS["muted"])
        detail.pack(anchor="w", padx=12, pady=(4, 10))
        return {"state": state, "detail": detail}

    def scan(self) -> None:
        self.summary_label.config(text="Escaneando servidores...")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self) -> None:
        data = collect()
        self.root.after(0, lambda: self._render(data))

    def _render(self, data: dict) -> None:
        summary, klass, detail = state_text(data)
        color = COLORS[klass]
        self.summary_label.config(text=summary, fg=color)
        self.detail_label.config(text=detail)
        for key, label, ip in (("principal", "Principal", PRIMARY_IP), ("reserva", "Reserva", RESERVE_IP)):
            ok, msg = data[key]
            self.cards[key]["state"].config(text="Online" if ok else "Offline", fg=COLORS["ok"] if ok else COLORS["bad"])
            self.cards[key]["detail"].config(text=f"{label} em {ip}\n{msg}")
        ips = ", ".join(sorted(data["ips"])) or "nao detectado"
        reserve_ready = RESERVE_IP in data["ips"] and data["pg_port"][0] and data["pg"][0]
        readiness = "Reserva pronta para assumir." if reserve_ready else "Reserva nao confirmada como pronta nesta maquina."
        self.local_label.config(text=f"Maquina: {socket.gethostname()} | Usuario: {os.environ.get('USERNAME', '')}\nIPs: {ips}\nAPI 8765: {data['api_port'][0]} | Postgres 5433: {data['pg_port'][0]} | PostgreSQL: {data['pg'][0]}\n{readiness}")
        readable_problems = []
        for title, msg in problem_messages(data):
            readable_problems.append(f"- {title}: {msg}")
        self.problems_label.config(text="\n".join(readable_problems[:6]))
        falls, errors, warnings = data["counts"]
        self.events_label.config(text=f"Historico 72h: {falls} quedas/tentativas | {errors} erros | {warnings} avisos. Isso e historico; veja a leitura clara acima.")
        self.log_box.delete("1.0", "end")
        self.log_box.insert("end", "\n".join(friendly_event(line) for line in data["events"][-24:]) or "Nenhum evento compartilhado nas ultimas 72 horas.")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    log("abrindo painel tkinter")
    try:
        TkPanel().run()
    except Exception as exc:
        log(f"ERRO Tkinter: {type(exc).__name__}: {exc}")
        data = collect()
        fallback_html(data)
        raise


if __name__ == "__main__":
    main()
