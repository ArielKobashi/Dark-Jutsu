import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from servidor_eleicao_darkjutsu import candidate_settings, computer_name, load_config, read_lease, read_nodes


SHARE_ROOT = Path(r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu")
STATUS_DIR = SHARE_ROOT / "status"
NODES_DIR = STATUS_DIR / "nodes"
REQUEST_DIR = STATUS_DIR / "requests"
BACKUP_DIR = SHARE_ROOT / "backups"
PRIMARY_IP = "192.168.5.44"
RESERVE_IP = "192.168.5.38"
API_PORT = 8765
PG_PORT = 5433
STATUS_VERSION = "2026-07-17.20"
SYSTEM_RUNTIME_ROOT = Path(r"C:\DarkJutsu")
USER_RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "DarkJutsu"
RUNTIME_ROOT = Path(os.environ.get("DARK_JUTSU_RUNTIME_ROOT") or (SYSTEM_RUNTIME_ROOT if SYSTEM_RUNTIME_ROOT.exists() else USER_RUNTIME_ROOT))
USER_PG_ISREADY = Path.home() / "Desktop" / "aplicacoes code" / "pgsql" / "bin" / "pg_isready.exe"
PG_ISREADY = USER_PG_ISREADY if not SYSTEM_RUNTIME_ROOT.exists() and USER_PG_ISREADY.exists() else RUNTIME_ROOT / "PostgreSQL" / "pgsql" / "bin" / "pg_isready.exe"
ANTI_SLEEP_STATUS_FILE = RUNTIME_ROOT / "logs" / "anti_sleep_darkjutsu.status"
LOCAL_MONITOR_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "DarkJutsu" / "monitor"
LOCAL_GUARDIAN = LOCAL_MONITOR_DIR / "guardiao_loop_python_darkjutsu.py"
SHARE_GUARDIAN = SHARE_ROOT / "scripts" / "guardiao_loop_python_darkjutsu.py"
SHARE_ELECTION = SHARE_ROOT / "scripts" / "servidor_eleicao_darkjutsu.py"
LOCAL_ELECTION = LOCAL_MONITOR_DIR / "servidor_eleicao_darkjutsu.py"
LOCAL_GUARDIAN_LOCK = RUNTIME_ROOT / "logs" / "guardiao_loop_python.lock"
LOCAL_GUARDIAN_RUNTIME_VERSION = LOCAL_MONITOR_DIR / "guardian_runtime_version.txt"
CREATE_NO_WINDOW = 0x08000000


SERVERS = {
    "principal": {"label": "Principal", "ip": PRIMARY_IP, "status_file": STATUS_DIR / "principal.json"},
    "reserva": {"label": "Reserva", "ip": RESERVE_IP, "status_file": STATUS_DIR / "reserva.json"},
}


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def local_ips():
    ips = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(item[4][0])
    except Exception:
        pass
    try:
        out = subprocess.run(["ipconfig"], capture_output=True, text=True, errors="ignore", timeout=5, creationflags=CREATE_NO_WINDOW).stdout
        for line in out.splitlines():
            if "IPv4" in line and ":" in line:
                ips.add(line.split(":", 1)[1].strip())
    except Exception:
        pass
    return ips


def role_for_ips(ips):
    lease = read_lease()
    return "lider" if str(lease.get("leader") or "").upper() == computer_name() else "candidato"


def http_probe(ip, endpoint, timeout=4):
    url = f"http://{ip}:{API_PORT}{endpoint}"
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read(60000)
            ms = int((time.perf_counter() - start) * 1000)
            ok = 200 <= resp.status < 300
            parsed = None
            try:
                parsed = json.loads(body.decode("utf-8", errors="replace"))
            except Exception:
                pass
            return {"ok": ok, "code": resp.status, "ms": ms, "error": "", "json": parsed}
    except Exception as exc:
        return {"ok": False, "code": 0, "ms": int((time.perf_counter() - start) * 1000), "error": type(exc).__name__, "json": None}


def port_listening(port):
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, errors="ignore", timeout=8, creationflags=CREATE_NO_WINDOW).stdout
        return any(f":{port} " in line and "LISTENING" in line.upper() for line in out.splitlines())
    except Exception:
        return False


def proc_exists(*patterns):
    try:
        match_expr = " -or ".join([f"$_.CommandLine -match '{p}'" for p in patterns])
        ps = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and (" + match_expr + ") "
            "-and $_.CommandLine -notmatch 'Get-CimInstance Win32_Process' } | "
            "Select-Object -First 1 -ExpandProperty ProcessId"
        )
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, text=True, errors="ignore", timeout=10, creationflags=CREATE_NO_WINDOW).stdout
        return any(ch.isdigit() for ch in out)
    except Exception:
        return False


def pg_ready():
    if not PG_ISREADY.exists():
        return False
    try:
        return subprocess.run([str(PG_ISREADY), "-h", "127.0.0.1", "-p", str(PG_PORT), "-U", "dark_jutsu", "-d", "dark_jutsu"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, creationflags=CREATE_NO_WINDOW).returncode == 0
    except Exception:
        return False


def latest_backup():
    try:
        backups = sorted(
            (p for p in BACKUP_DIR.glob("darkjutsu_backup_*.backup") if p.stat().st_size >= 1_000_000),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not backups:
            return {"name": "", "mtime": "", "age_min": None}
        p = backups[0]
        age = int((time.time() - p.stat().st_mtime) / 60)
        return {
            "name": p.name,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "age_min": age,
            "size_bytes": p.stat().st_size,
        }
    except Exception:
        return {"name": "", "mtime": "", "age_min": None}


def quality(ms, ok):
    if not ok:
        return "OFF"
    if ms <= 400:
        return "alta"
    if ms <= 1200:
        return "normal"
    return "lenta"


def backup_status(age_min):
    if age_min is None:
        return "sem info"
    if age_min <= 90:
        return f"OK {age_min}min"
    if age_min <= 360:
        return f"velho {age_min}min"
    return f"critico {age_min}min"


def shared_backup_status(data):
    age = data.get("_age_sec")
    if age is None:
        return "sem status"
    if age > 180:
        return f"VELHO {age}s"
    return backup_status((data.get("backup_latest") or {}).get("age_min"))


def local_recent_file(path, max_age=180):
    try:
        if not path.exists():
            return {"active": False, "age_sec": None}
        age = int(time.time() - path.stat().st_mtime)
        return {"active": age <= max_age, "age_sec": age}
    except Exception:
        return {"active": False, "age_sec": None}


def shared_recent_status(data, key):
    value = data.get(key)
    age = data.get("_age_sec")
    if not value:
        return "NAO"
    if age is None:
        return "SIM"
    if age > 180:
        return f"VELHO {age}s"
    return "SIM"


def progress(message):
    if "--publish-only" in sys.argv:
        return
    print(f"[...] {message}", flush=True)


def collect_local_status():
    progress("Coletando status deste PC: IP, API local, SQL, portas, guardiao e monitor...")
    ips = local_ips()
    role = role_for_ips(ips)
    self_heal_guardian(role)
    health = http_probe("127.0.0.1", "/health", 4)
    live = http_probe("127.0.0.1", "/live", 3)
    backup = latest_backup()
    status = {
        "schema": 1,
        "status_version": STATUS_VERSION,
        "guardian_version": read_guardian_version(),
        "updated_at": now_iso(),
        "computer": os.environ.get("COMPUTERNAME", ""),
        "user": os.environ.get("USERNAME", ""),
        "role": role,
        "ips": sorted(ips),
        "api_port": API_PORT,
        "pg_port": PG_PORT,
        "api_local_health": health["ok"],
        "api_local_live": live["ok"],
        "api_local_ms": health["ms"] if health["ok"] else live["ms"],
        "sql_local": pg_ready(),
        "api_port_listening": port_listening(API_PORT),
        "pg_port_listening": port_listening(PG_PORT),
        "guardiao_active": proc_exists("guardiao_loop", "guardiao_servidor_tick_darkjutsu", "guardiao_loop_python_darkjutsu"),
        "monitor_active": proc_exists("monitor_servidor_python_darkjutsu", "monitor_reserva_python_darkjutsu", "monitor_principal_powershell_darkjutsu"),
        "anti_sleep_active": local_recent_file(ANTI_SLEEP_STATUS_FILE)["active"],
        "backup_latest": backup,
    }
    return status


def read_guardian_version():
    marker = 'GUARDIAN_VERSION = "'
    path = LOCAL_GUARDIAN
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if marker in text:
            return text.split(marker, 1)[1].split('"', 1)[0]
        return "sem-versao-local"
    except Exception:
        return "sem-arquivo-local"


def guardian_version_from(path):
    marker = 'GUARDIAN_VERSION = "'
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if marker in text:
            return text.split(marker, 1)[1].split('"', 1)[0]
        return "sem-versao-local"
    except Exception:
        return "sem-arquivo-local"


def local_pythonw():
    base = Path(os.environ.get("USERPROFILE", "")) / "Desktop" / "aplicacoes code" / "WPy64-3.13.12.0" / "python"
    pyw = base / "pythonw.exe"
    if pyw.exists():
        return pyw
    return Path(sys.executable)


def self_heal_guardian(local_role):
    if not SHARE_GUARDIAN.exists():
        return
    local_version = guardian_version_from(LOCAL_GUARDIAN)
    share_version = guardian_version_from(SHARE_GUARDIAN)
    try:
        runtime_version = LOCAL_GUARDIAN_RUNTIME_VERSION.read_text(encoding="ascii").strip()
    except Exception:
        runtime_version = ""
    heartbeat_version = ""
    try:
        heartbeat = json.loads((NODES_DIR / f"{computer_name()}.json").read_text(encoding="utf-8"))
        heartbeat_version = str((heartbeat.get("details") or {}).get("guardianVersion") or "")
    except Exception:
        pass
    if local_version == share_version and runtime_version == share_version and heartbeat_version == share_version:
        return
    try:
        LOCAL_MONITOR_DIR.mkdir(parents=True, exist_ok=True)
        if local_version != share_version:
            shutil.copy2(SHARE_GUARDIAN, LOCAL_GUARDIAN)
        if SHARE_ELECTION.exists():
            shutil.copy2(SHARE_ELECTION, LOCAL_ELECTION)
        stop_guardian_processes()
        try:
            LOCAL_GUARDIAN_LOCK.unlink()
        except Exception:
            pass
        pyw = local_pythonw()
        subprocess.Popen([str(pyw), str(LOCAL_GUARDIAN)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        LOCAL_GUARDIAN_RUNTIME_VERSION.write_text(share_version, encoding="ascii")
        progress(f"Guardiao local atualizado automaticamente: arquivo={local_version}, processo={heartbeat_version or '?'} -> {share_version}")
    except Exception as exc:
        progress(f"AVISO: nao consegui autoatualizar guardiao local: {type(exc).__name__}: {exc}")


def stop_guardian_processes():
    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -and $_.CommandLine -match 'guardiao_loop_python_darkjutsu.py' "
        "-and $_.CommandLine -notmatch 'Get-CimInstance Win32_Process' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass


def write_local_status(status):
    progress("Publicando status local no servidor de arquivos...")
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    name = str(status.get("computer") or "desconhecido").upper()
    detail_dir = STATUS_DIR / "nodes-detail"
    detail_dir.mkdir(parents=True, exist_ok=True)
    path = detail_dir / f"{name}.json"
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.{int(time.time() * 1000)}.tmp")
    tmp.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    for _ in range(5):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.3)
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def print_dynamic_cluster():
    config = load_config()
    lease = read_lease()
    nodes = read_nodes(config)
    leader = str(lease.get("leader") or "").upper()
    print("")
    print("=" * 104)
    print("DARK-JUTSU - CLUSTER DINAMICO DE SERVIDORES")
    print(f"Lider atual: {leader or 'NENHUM'} | epoch={lease.get('epoch', 0)}")
    print("=" * 104)
    print(f"{'COMPUTADOR':<22} {'PRIORIDADE':<11} {'ESTADO':<14} {'API':<8} {'SQL':<8} {'IPS'}")
    print("-" * 104)
    for name, node in sorted(nodes.items(), key=lambda item: (int(item[1].get('priority', 1000)), item[0])):
        state = "LIDER" if name == leader else "PRONTO" if node.get("eligible") else "INDISPONIVEL"
        details = node.get("details") if isinstance(node.get("details"), dict) else {}
        print(
            f"{name:<22} {int(node.get('priority', 1000)):<11} {state:<14} "
            f"{'SIM' if node.get('apiHealthy') else 'NAO':<8} "
            f"{'SIM' if node.get('ready') else 'NAO':<8} {', '.join(node.get('ips') or [])}"
        )
    if not nodes:
        print("Nenhum candidato publicou heartbeat ainda.")
    print("=" * 104)


def read_status(role):
    progress(f"Lendo status compartilhado do servidor {SERVERS[role]['label'].lower()}...")
    path = SERVERS[role]["status_file"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(data.get("updated_at", "2000-01-01T00:00:00"))
        data["_age_sec"] = int((datetime.now() - ts).total_seconds())
        return data
    except Exception:
        return {"role": role, "_age_sec": None}


def request_remote_status(target_role, requester_role, wait_seconds=18):
    if target_role not in SERVERS or target_role == requester_role:
        return False
    try:
        REQUEST_DIR.mkdir(parents=True, exist_ok=True)
        request = REQUEST_DIR / f"{target_role}.request"
        before = SERVERS[target_role]["status_file"].stat().st_mtime if SERVERS[target_role]["status_file"].exists() else 0
        stamp = f"{time.time()}|requester={requester_role}|target={target_role}|computer={os.environ.get('COMPUTERNAME','')}\n"
        request.write_text(stamp, encoding="ascii")
        progress(f"Pedindo status remoto escondido para o servidor {SERVERS[target_role]['label'].lower()}...")
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            try:
                if SERVERS[target_role]["status_file"].exists() and SERVERS[target_role]["status_file"].stat().st_mtime > before:
                    progress(f"Resposta remota recebida do servidor {SERVERS[target_role]['label'].lower()}.")
                    return True
            except Exception:
                pass
            time.sleep(1)
        progress(f"Sem resposta remota nova do servidor {SERVERS[target_role]['label'].lower()} dentro de {wait_seconds}s.")
    except Exception as exc:
        progress(f"Falha ao pedir status remoto para {target_role}: {type(exc).__name__}.")
    return False


def yes_no(value):
    if value is True:
        return "SIM"
    if value is False:
        return "NAO"
    return "?"


def hosting_label(ph_ok, rh_ok):
    if ph_ok and not rh_ok:
        return f"PRINCIPAL hospedando em http://{PRIMARY_IP}:{API_PORT}"
    if rh_ok and not ph_ok:
        return f"RESERVA hospedando em http://{RESERVE_IP}:{API_PORT}"
    if ph_ok and rh_ok:
        return "ATENCAO: principal e reserva hospedando ao mesmo tempo"
    return "CRITICO: nenhuma API hospedando agora"


def api_state(ok, ms, active_host, this_role):
    if ok:
        return f"SIM {ms}ms"
    if active_host == "principal" and this_role == "reserva":
        return "EM ESPERA"
    if active_host == "reserva" and this_role == "principal":
        return "EM ESPERA"
    return f"NAO {ms}ms"


def host_role(ph_ok, rh_ok):
    if ph_ok and not rh_ok:
        return "principal"
    if rh_ok and not ph_ok:
        return "reserva"
    if ph_ok and rh_ok:
        return "ambos"
    return "nenhum"


def expected_for(role, active_host):
    if active_host == "principal":
        return "HOSPEDANDO" if role == "principal" else "EM ESPERA"
    if active_host == "reserva":
        return "REASSUMIR" if role == "principal" else "HOSPEDANDO TEMP"
    if active_host == "ambos":
        return "MANTER PRINCIPAL" if role == "principal" else "PARAR API"
    return "ASSUMIR AGORA" if role == "principal" else "AGUARDAR/ASSUMIR"


def quality_for_role(probe, data, active_host, role):
    if probe["ok"]:
        return quality(probe["ms"], True)
    if active_host == "principal" and role == "reserva" and fresh(data):
        return "standby ok"
    if active_host == "reserva" and role == "principal" and fresh(data):
        return "standby ok"
    return "OFF"


def shared_value(data, key):
    age = data.get("_age_sec")
    if age is None:
        return "? (sem status)"
    if age > 180:
        return f"VELHO {age}s"
    return yes_no(data.get(key)) + status_age(data)


def shared_short(data, key):
    value = shared_value(data, key)
    return value.split()[0]


def fresh(data):
    age = data.get("_age_sec")
    return age is not None and age <= 180


def cell(text, width):
    text = str(text)
    if len(text) > width:
        text = text[: width - 1] + "~"
    return text + (" " * (width - len(text)))


def draw_table(rows):
    w1, w2, w3 = 44, 30, 30
    line = "+" + "-" * (w1 + 2) + "+" + "-" * (w2 + 2) + "+" + "-" * (w3 + 2) + "+"
    print(line)
    print(f"| {cell('CHECK', w1)} | {cell('SERVIDOR PRINCIPAL', w2)} | {cell('SERVIDOR RESERVA', w3)} |")
    print(line)
    for name, p, r in rows:
        print(f"| {cell(name, w1)} | {cell(p, w2)} | {cell(r, w3)} |")
    print(line)


def main():
    if "--publish-only" not in sys.argv:
        print("")
        print("DARK-JUTSU - escaneando servidores, aguarde...")
        print("Isso pode levar alguns segundos quando algum servidor esta offline.")
        print("")
    local = collect_local_status()
    write_local_status(local)
    if "--publish-only" in sys.argv:
        return

    print_dynamic_cluster()
    return

    local_role = local.get("role")
    if local_role == "principal":
        request_remote_status("reserva", local_role)
    elif local_role == "reserva":
        request_remote_status("principal", local_role)

    remote = {}
    probes = {}
    for role, meta in SERVERS.items():
        ip = meta["ip"]
        progress(f"Testando API do servidor {meta['label'].lower()} em {ip}:{API_PORT}...")
        probes[role] = {
            "health": http_probe(ip, "/health", 5),
            "live": http_probe(ip, "/live", 3),
        }
        remote[role] = read_status(role)

    p = remote["principal"]
    r = remote["reserva"]
    ph = probes["principal"]["health"]
    rh = probes["reserva"]["health"]
    pl = probes["principal"]["live"]
    rl = probes["reserva"]["live"]
    active_host = host_role(ph["ok"], rh["ok"])

    rows = [
        ("SQL local pronto para hospedar?", shared_short(p, "sql_local"), shared_short(r, "sql_local")),
        ("API hospedando com SQL?", api_state(ph["ok"] and (ph["json"] or {}).get("ok") is True, ph["ms"], active_host, "principal"), api_state(rh["ok"] and (rh["json"] or {}).get("ok") is True, rh["ms"], active_host, "reserva")),
        ("API /health da hospedagem?", api_state(ph["ok"], ph["ms"], active_host, "principal"), api_state(rh["ok"], rh["ms"], active_host, "reserva")),
        ("API /live da hospedagem?", api_state(pl["ok"], pl["ms"], active_host, "principal"), api_state(rl["ok"], rl["ms"], active_host, "reserva")),
        ("Guardiao ativo?", shared_value(p, "guardiao_active"), shared_value(r, "guardiao_active")),
        ("Versao guardiao/status", f"{p.get('guardian_version', '-')}/{p.get('status_version', '-')}", f"{r.get('guardian_version', '-')}/{r.get('status_version', '-')}"),
        ("Monitor ativo?", shared_value(p, "monitor_active"), shared_value(r, "monitor_active")),
        ("Anti-sleep ativo?", shared_recent_status(p, "anti_sleep_active"), shared_recent_status(r, "anti_sleep_active")),
        ("Status compartilhado recente?", yes_no(fresh(p)) + status_age(p), yes_no(fresh(r)) + status_age(r)),
        ("Porta API configurada", f"{PRIMARY_IP}:{API_PORT}", f"{RESERVE_IP}:{API_PORT}"),
        ("Porta PostgreSQL local", f"{PRIMARY_IP}:5433 {shared_short(p, 'pg_port_listening')}", f"{RESERVE_IP}:5433 {shared_short(r, 'pg_port_listening')}"),
        ("API local ouvindo neste PC?", shared_short(p, "api_port_listening"), shared_short(r, "api_port_listening")),
        ("Qualidade/conexao", quality_for_role(ph, p, active_host, "principal"), quality_for_role(rh, r, active_host, "reserva")),
        ("Backup mais recente", shared_backup_status(p), shared_backup_status(r)),
        ("Maquina/usuario", f"{p.get('computer','?')} / {p.get('user','?')}", f"{r.get('computer','?')} / {r.get('user','?')}"),
        ("Comunicacao entre servidores", comm_status(ph["ok"], rh["ok"], fresh(p), fresh(r)), comm_status(ph["ok"], rh["ok"], fresh(p), fresh(r))),
        ("Acao esperada do guardiao", expected_for("principal", active_host), expected_for("reserva", active_host)),
    ]

    print("")
    print("=" * 112)
    print("DARK-JUTSU - STATUS COMPARTILHADO DOS SERVIDORES")
    print("SERVIDOR ATUAL: " + hosting_label(ph["ok"], rh["ok"]))
    print(f"Agora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Este PC: {local.get('computer')} | Papel: {local.get('role').upper()}")
    print("=" * 112)
    draw_table(rows)
    print("")
    print("LEITURA RAPIDA:")
    print(f"- Principal health: {'OK' if ph['ok'] else 'OFF'} ({ph['ms']}ms, erro={ph['error'] or '-'})")
    print(f"- Reserva health:   {'OK' if rh['ok'] else 'OFF'} ({rh['ms']}ms, erro={rh['error'] or '-'})")
    print(f"- Status principal compartilhado: {status_summary(p)}")
    print(f"- Status reserva compartilhado:   {status_summary(r)}")
    print("")
    print("TRADUCAO DOS CAMPOS:")
    print("- SQL local pronto: banco PostgreSQL daquele PC esta pronto para hospedar se precisar.")
    print("- API hospedando com SQL: aquele PC esta sendo o servidor ativo e consultando SQL pela API.")
    print("- EM ESPERA: PC esta pronto/comunicando, mas a API fica desligada porque outro PC esta hospedando.")
    print("- API /health: teste completo da API ativa, incluindo banco.")
    print("- API /live: teste simples da API ativa. Se live OK e health falha, a API abriu mas o SQL pode estar ruim.")
    print("- Guardiao ativo: processo que verifica queda e decide iniciar/parar servidor.")
    print("- Monitor ativo: icone perto do relogio do Windows.")
    print("- Anti-sleep ativo: monitor esta impedindo suspensao do Windows sem manter a tela forcada.")
    print("- Status compartilhado recente: o outro PC publicou informacoes no fileserver ha menos de 3 minutos.")
    print("- API local ouvindo: aquele PC esta hospedando na porta 8765; na reserva deve ficar NAO quando o principal comanda.")
    print("- Qualidade/conexao: mede a API ativa; standby ok significa reserva/principal em espera com status recente.")
    print("- Comunicacao: ativa se API/status estao bons; parcial se so o status ou so a API respondeu; fraca se faltam sinais.")
    print("")
    primary_ready = fresh(p) and bool(p.get("guardiao_active")) and bool(p.get("monitor_active")) and bool(p.get("anti_sleep_active"))
    reserve_ready = fresh(r) and bool(r.get("guardiao_active")) and bool(r.get("monitor_active")) and bool(r.get("anti_sleep_active"))
    if ph["ok"] and not rh["ok"]:
        if not primary_ready or not reserve_ready:
            print("RESULTADO: ATENCAO. Principal comanda, mas ha componentes auxiliares faltando.")
            if not primary_ready:
                print("ACAO PRINCIPAL: confirme guardiao, monitor e anti-sleep no principal.")
            if not reserve_ready:
                print("ACAO RESERVA: atualize/reinicie monitor+guardiao no PC reserva ate Monitor e Anti-sleep ficarem SIM.")
        else:
            print("RESULTADO: OK. Principal comanda; reserva fica sem API ativa, mas com guardiao/monitor vivos.")
    elif rh["ok"] and not ph["ok"]:
        print("RESULTADO: ATENCAO. Reserva comanda; principal deve reassumir quando estiver disponivel.")
    elif ph["ok"] and rh["ok"]:
        print("RESULTADO: ATENCAO. Principal e reserva responderam ao mesmo tempo.")
    else:
        print("RESULTADO: CRITICO. Nenhuma API respondeu.")


def status_age(data):
    age = data.get("_age_sec")
    if age is None:
        return " (sem status)"
    return f" ({age}s)"


def status_summary(data):
    age = data.get("_age_sec")
    if age is None:
        return "nao encontrado"
    return f"{age}s atras por {data.get('computer','?')}\\{data.get('user','?')}"


def comm_status(primary_ok, reserve_ok, primary_fresh, reserve_fresh):
    if primary_ok and reserve_fresh:
        return "ativa"
    if reserve_ok and primary_fresh:
        return "ativa"
    if primary_fresh and reserve_fresh:
        return "parcial"
    if primary_ok or reserve_ok or primary_fresh or reserve_fresh:
        return "parcial"
    return "fraca"


def expected_action(primary_ok, reserve_ok, local_role):
    if primary_ok and not reserve_ok:
        return "principal comanda"
    if primary_ok and reserve_ok:
        return "reserva deve parar"
    if reserve_ok and not primary_ok:
        return "principal reassume"
    if local_role == "principal":
        return "principal assume ja"
    if local_role == "reserva":
        return "reserva aguarda prazo"
    return "sem acao local"


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f"ERRO NO STATUS COMPARTILHADO: {type(exc).__name__}: {exc}")
        sys.exit(1)
