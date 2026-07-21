import ctypes
import os
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from servidor_eleicao_darkjutsu import computer_name, election_tick, publish_heartbeat, read_lease


PRIMARY_IP = "192.168.5.44"
RESERVE_IP = "192.168.5.38"
API_PORT = 8765
MOBILE_API_PORT = 8766
FAILOVER_BLACKOUT_SECONDS = 180
API_STARTUP_WAIT_SECONDS = 45
SHARE_ROOT = Path(r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu")
SCRIPTS = SHARE_ROOT / "scripts"
STATUS_DIR = SHARE_ROOT / "status"
REQUEST_DIR = STATUS_DIR / "requests"
STATUS_SCRIPT = SCRIPTS / "status_compartilhado_servidores_darkjutsu.py"
GITHUB_UPDATE_SCRIPT = SCRIPTS / "atualizar_darkjutsu_do_github.bat"
BACKUP_SCRIPT = SCRIPTS / "backup_postgres_darkjutsu.bat"
SYSTEM_RUNTIME_ROOT = Path(r"C:\DarkJutsu")
USER_RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "DarkJutsu"
SYSTEM_PG_HOME = SYSTEM_RUNTIME_ROOT / "PostgreSQL" / "pgsql"
LOCALAPPDATA_PG_HOME = USER_RUNTIME_ROOT / "PostgreSQL" / "pgsql"
USER_PG_CANDIDATES = (
    Path.home() / "Desktop" / "aplicacoes code" / "pgsql",
    Path.home() / "Desktop" / "pgsql",
    Path.home() / "Desktop" / "PostgreSQL" / "pgsql",
    Path.home() / "Desktop" / "PostgreSQL",
    Path.home() / "Área de Trabalho" / "aplicacoes code" / "pgsql",
    Path.home() / "Área de Trabalho" / "pgsql",
    Path.home() / "Área de Trabalho" / "PostgreSQL" / "pgsql",
    Path.home() / "Área de Trabalho" / "PostgreSQL",
)


def has_pg_ctl(pg_home: Path) -> bool:
    return (pg_home / "bin" / "pg_ctl.exe").exists() and (pg_home / "share" / "postgres.bki").exists()


def desktop_roots() -> list[Path]:
    roots = [
        Path.home() / "Desktop",
        Path.home() / "Área de Trabalho",
    ]
    for env_name in ("USERPROFILE", "OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        value = os.environ.get(env_name)
        if value:
            roots.append(Path(value) / "Desktop")
    unique = []
    seen = set()
    for root in roots:
        key = str(root).lower()
        if key not in seen:
            unique.append(root)
            seen.add(key)
    return unique


def select_user_pg_home() -> Path:
    for candidate in USER_PG_CANDIDATES:
        if has_pg_ctl(candidate):
            return candidate
    for desktop in desktop_roots():
        try:
            for pg_ctl in desktop.rglob("pg_ctl.exe"):
                candidate = pg_ctl.parent.parent
                if pg_ctl.parent.name.lower() == "bin" and has_pg_ctl(candidate):
                    return candidate
        except Exception:
            pass
    return USER_PG_CANDIDATES[0]


USER_PG_HOME = select_user_pg_home()


def select_runtime_root() -> Path:
    override = os.environ.get("DARK_JUTSU_RUNTIME_ROOT")
    if override:
        return Path(override)
    if has_pg_ctl(SYSTEM_PG_HOME):
        return SYSTEM_RUNTIME_ROOT
    if has_pg_ctl(LOCALAPPDATA_PG_HOME) or has_pg_ctl(USER_PG_HOME):
        return USER_RUNTIME_ROOT
    return USER_RUNTIME_ROOT


RUNTIME_ROOT = select_runtime_root()
SHARE_API_DIR = SHARE_ROOT / "pacote" / "Dark-Jutsu" / "api"
LOG_DIR = RUNTIME_ROOT / "logs"
LOCAL_MONITOR_DIR = RUNTIME_ROOT / "monitor"
PG_HOME = USER_PG_HOME if has_pg_ctl(USER_PG_HOME) else (SYSTEM_PG_HOME if RUNTIME_ROOT == SYSTEM_RUNTIME_ROOT else LOCALAPPDATA_PG_HOME)
PG_BIN = PG_HOME / "bin"
PGDATA = (PG_HOME / "data") if PG_HOME == USER_PG_HOME else RUNTIME_ROOT / "postgres-data"
PG_CTL = PG_BIN / "pg_ctl.exe"
PG_ISREADY = PG_BIN / "pg_isready.exe"
PG_PSQL = PG_BIN / "psql.exe"
PG_RESTORE = PG_BIN / "pg_restore.exe"
PG_DROPDB = PG_BIN / "dropdb.exe"
PG_CREATEDB = PG_BIN / "createdb.exe"
PG_RUNTIME_LOG = LOG_DIR / "postgres_runtime.log"
LOG_FILE = LOG_DIR / "guardiao_loop_python.log"
API_LOG = LOG_DIR / "api_runtime_python_guardiao.log"
LOCK_FILE = LOG_DIR / "guardiao_loop_python.lock"
SCHEMA_RESTORE_MARKER = LOG_DIR / "schema_restore_darkjutsu_v2.marker"
STANDBY_BACKUP_MARKER = LOG_DIR / "standby_backup_applied.json"
LOCK_HANDLE = None
ERROR_ALREADY_EXISTS = 183
DB_URL = "postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
CREATE_NO_WINDOW = 0x08000000
GUARDIAN_VERSION = "2026-07-21.02"
MAINTENANCE_DIR = STATUS_DIR / "maintenance"
STARTUP_VBS_SOURCE = SCRIPTS / "iniciar_cluster_usuario_darkjutsu.vbs"
WATCHDOG_SOURCE = SCRIPTS / "watchdog_usuario_darkjutsu.ps1"
SHARED_LOG = SHARE_ROOT / "logs" / "guardiao_python_eventos.txt"
TEST_ACTIVE_FILE = SHARE_ROOT / "status" / "teste_inicializacao_ativo.txt"
TEST_LOG = SHARE_ROOT / "logs" / "teste_inicializacao_manual_darkjutsu.txt"
GITHUB_UPDATE_INTERVAL_SECONDS = 300
BACKUP_INTERVAL_SECONDS = 300
STANDBY_SYNC_INTERVAL_SECONDS = 30
MOBILE_TUNNEL_SCRIPT_NAME = "iniciar_tunel_celular_darkjutsu.ps1"
MOBILE_TUNNEL_SOURCE = SCRIPTS / MOBILE_TUNNEL_SCRIPT_NAME
MOBILE_TUNNEL_LOCAL = LOCAL_MONITOR_DIR / MOBILE_TUNNEL_SCRIPT_NAME
MOBILE_TUNNEL_LOG = LOG_DIR / "mobile_tunnel_guardiao.log"
MOBILE_TUNNEL_URL = f"http://127.0.0.1:{MOBILE_API_PORT}"
BACKUP_PROCESS = None


def select_api_runtime_root():
    override = os.environ.get("DARK_JUTSU_API_RUNTIME_ROOT")
    if override:
        return Path(override)
    preferred = RUNTIME_ROOT
    try:
        api_dir = preferred / "Dark-Jutsu" / "api"
        api_dir.mkdir(parents=True, exist_ok=True)
        probe = api_dir / ".guardian_write_test"
        probe.write_text("ok", encoding="ascii")
        probe.unlink(missing_ok=True)
        return preferred
    except Exception as exc:
        try:
            USER_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            SHARED_LOG.parent.mkdir(parents=True, exist_ok=True)
            actor = f"{os.environ.get('COMPUTERNAME', '?')}\\{os.environ.get('USERNAME', '?')}"
            with SHARED_LOG.open("a", encoding="utf-8") as fh:
                fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + f" | API runtime do sistema bloqueado; usando perfil do usuario. Motivo={type(exc).__name__}: {exc} | {actor}\n")
        except Exception:
            pass
        return USER_RUNTIME_ROOT


API_RUNTIME_ROOT = select_api_runtime_root()
LOCAL_API = API_RUNTIME_ROOT / "Dark-Jutsu" / "api" / "dark_jutsu_api.py"
LOCAL_API_DIR = LOCAL_API.parent


def set_api_runtime_root(root: Path, reason: str = ""):
    global API_RUNTIME_ROOT, LOCAL_API, LOCAL_API_DIR
    API_RUNTIME_ROOT = root
    LOCAL_API = API_RUNTIME_ROOT / "Dark-Jutsu" / "api" / "dark_jutsu_api.py"
    LOCAL_API_DIR = LOCAL_API.parent
    try:
        LOCAL_MONITOR_DIR.mkdir(parents=True, exist_ok=True)
        (LOCAL_MONITOR_DIR / "active_runtime.txt").write_text(str(API_RUNTIME_ROOT), encoding="utf-8")
    except Exception:
        pass
    if reason:
        log(f"Runtime da API alterado para {API_RUNTIME_ROOT}. Motivo={reason}")


def log(message):
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " | " + str(message)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    try:
        SHARED_LOG.parent.mkdir(parents=True, exist_ok=True)
        actor = f"{os.environ.get('COMPUTERNAME', '?')}\\{os.environ.get('USERNAME', '?')}"
        with SHARED_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + f" | {actor}\n")
    except Exception:
        pass
    try:
        if TEST_ACTIVE_FILE.exists():
            actor = f"{os.environ.get('COMPUTERNAME', '?')}\\{os.environ.get('USERNAME', '?')}"
            session = TEST_ACTIVE_FILE.read_text(encoding="utf-8", errors="ignore").strip().replace("\n", " | ")
            TEST_LOG.parent.mkdir(parents=True, exist_ok=True)
            with TEST_LOG.open("a", encoding="utf-8") as fh:
                fh.write(line + f" | {actor} | TESTE_ATIVO={session}\n")
    except Exception:
        pass


def trigger_github_update_check(reason: str = "intervalo"):
    if not GITHUB_UPDATE_SCRIPT.exists():
        log(f"AVISO: atualizador GitHub nao encontrado: {GITHUB_UPDATE_SCRIPT}")
        return False
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", str(GITHUB_UPDATE_SCRIPT)],
            cwd=str(GITHUB_UPDATE_SCRIPT.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
        log(f"Checagem GitHub disparada pelo guardiao. Motivo={reason}")
        return True
    except Exception as exc:
        log(f"ERRO: falha ao disparar checagem GitHub: {type(exc).__name__}: {exc}")
        return False


def trigger_postgres_backup(reason: str = "intervalo"):
    global BACKUP_PROCESS
    if BACKUP_PROCESS is not None and BACKUP_PROCESS.poll() is None:
        return False
    if not BACKUP_SCRIPT.exists():
        log(f"AVISO: script de backup PostgreSQL nao encontrado: {BACKUP_SCRIPT}")
        return False
    try:
        env = os.environ.copy()
        env["DARK_JUTSU_PG_BIN"] = str(PG_BIN)
        BACKUP_PROCESS = subprocess.Popen(
            ["cmd.exe", "/d", "/c", str(BACKUP_SCRIPT)],
            cwd=str(BACKUP_SCRIPT.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            creationflags=CREATE_NO_WINDOW,
        )
        log(f"Backup PostgreSQL disparado pelo guardiao. Motivo={reason}")
        return True
    except Exception as exc:
        log(f"ERRO: falha ao disparar backup PostgreSQL: {type(exc).__name__}: {exc}")
        return False


def boot_hint():
    try:
        ps = "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime"
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, text=True, errors="ignore", timeout=8, creationflags=CREATE_NO_WINDOW).stdout.strip()
        return out or "indisponivel"
    except Exception:
        return "indisponivel"


def acquire_lock():
    global LOCK_HANDLE
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.GetLastError.argtypes = []
        kernel32.GetLastError.restype = ctypes.c_ulong
        handle = kernel32.CreateMutexW(None, True, "Global\\DarkJutsuGuardiaoLoopPython")
        if handle and kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            try:
                old_pid = LOCK_FILE.read_text(encoding="ascii").strip() or "desconhecido"
            except Exception:
                old_pid = "desconhecido"
            log(f"Guardiao Python ja esta rodando ou iniciando no PID {old_pid}. Encerrando duplicado.")
            return False
        LOCK_HANDLE = handle
        LOCK_FILE.write_text(str(os.getpid()), encoding="ascii")
        return True
    except Exception as exc:
        log(f"AVISO: nao consegui criar lock do guardiao: {type(exc).__name__}: {exc}")
        return True


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


def role():
    ips = local_ips()
    if PRIMARY_IP in ips:
        return "principal"
    if RESERVE_IP in ips:
        return "reserva"
    return "desconhecido"


def health(ip, timeout=4):
    return health_port(ip, API_PORT, timeout=timeout)


def health_port(ip, port, timeout=4):
    try:
        with urllib.request.urlopen(f"http://{ip}:{port}/health", timeout=timeout) as resp:
            body = resp.read(2000).replace(b" ", b"").lower()
            return resp.status == 200 and b'"ok":true' in body
    except Exception:
        return False


def live(ip, timeout=2):
    return live_port(ip, API_PORT, timeout=timeout)


def live_port(ip, port, timeout=2):
    try:
        with urllib.request.urlopen(f"http://{ip}:{port}/live", timeout=timeout) as resp:
            body = resp.read(2000).replace(b" ", b"").lower()
            return resp.status == 200 and b'"ok":true' in body
    except Exception:
        return False


def publish_status():
    if not STATUS_SCRIPT.exists():
        return
    py = Path(sys.executable)
    if py.name.lower() == "pythonw.exe":
        py = py.with_name("python.exe")
    try:
        subprocess.run([str(py), str(STATUS_SCRIPT), "--publish-only"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, creationflags=CREATE_NO_WINDOW)
    except Exception as exc:
        log(f"AVISO: falha ao publicar status: {type(exc).__name__}: {exc}")


def handle_status_request(current_role):
    try:
        REQUEST_DIR.mkdir(parents=True, exist_ok=True)
        request = REQUEST_DIR / f"{current_role}.request"
        response = REQUEST_DIR / f"{current_role}.response"
        if not request.exists():
            return False
        req_mtime = request.stat().st_mtime
        resp_mtime = response.stat().st_mtime if response.exists() else 0
        if resp_mtime >= req_mtime:
            return False
        publish_status()
        response.write_text(time.strftime("%Y-%m-%d %H:%M:%S") + f" | status publicado por {current_role}\n", encoding="ascii")
        log(f"Pedido remoto de status atendido para papel={current_role}.")
        return True
    except Exception as exc:
        log(f"AVISO: falha ao atender pedido remoto de status: {type(exc).__name__}: {exc}")
        return False


def port_processes(port: int) -> str:
    try:
        ps = (
            f"Get-NetTCPConnection -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue | "
            "ForEach-Object { $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; "
            "[pscustomobject]@{ProcessId=$_.OwningProcess;Name=$p.ProcessName;Path=$p.Path} } | "
            "Format-List"
        )
        return subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
        ).stdout
    except Exception:
        return ""


def port_process_running(port: int) -> bool:
    return any(ch.isdigit() for ch in port_processes(port))


def stop_port_processes(port: int, reason: str) -> bool:
    try:
        ps = (
            f"Get-NetTCPConnection -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue | "
            "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
        )
        log(f"Processos na porta {port} parados. Motivo={reason}")
        return True
    except Exception as exc:
        log(f"AVISO: falha ao parar processos da porta {port}: {type(exc).__name__}: {exc}")
        return False


def api_processes():
    by_port = port_processes(API_PORT)
    if by_port.strip():
        return by_port
    try:
        ps = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -and "
            "($_.CommandLine -match 'dark_jutsu_api.py' -or $_.CommandLine -match 'iniciar_api_servidor.bat') "
            f"-and $_.CommandLine -notmatch ':{MOBILE_API_PORT}' "
            "-and $_.CommandLine -notmatch 'iniciar_api_celular_8766_oculta' "
            "-and $_.CommandLine -notmatch 'Get-CimInstance Win32_Process' } | "
            "Select-Object ProcessId,Name,CommandLine | Format-List"
        )
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, text=True, errors="ignore", timeout=10, creationflags=CREATE_NO_WINDOW).stdout
        return out
    except Exception:
        return ""


def api_process_running():
    return port_process_running(API_PORT)


def stop_local_api(reason):
    try:
        if port_process_running(API_PORT):
            stop_port_processes(API_PORT, reason)
            log(f"API local parada. Motivo={reason}")
        else:
            log(f"Nenhuma API local na porta {API_PORT} encontrada para parar. Motivo={reason}")
        stop_mobile_services(reason)
    except Exception as exc:
        log(f"AVISO: falha ao parar API local: {type(exc).__name__}: {exc}")


def mobile_tunnel_root() -> Path:
    return LOCAL_API.parent.parent


def mobile_state_file() -> Path:
    return mobile_tunnel_root() / "data" / "mobile_tunnel_url.json"


def read_mobile_state() -> dict:
    try:
        path = mobile_state_file()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def write_mobile_state(status: str, url: str = "", message: str = ""):
    try:
        path = mobile_state_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        previous = read_mobile_state()
        if (
            previous.get("status") == status
            and (previous.get("url") or "") == url
            and (previous.get("message") or "") == message
        ):
            return
        payload = {
            "ok": status == "online",
            "status": status,
            "url": url,
            "message": message,
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        log(f"AVISO: nao consegui gravar estado do tunnel celular: {type(exc).__name__}: {exc}")


def sync_mobile_tunnel_script() -> bool:
    if not MOBILE_TUNNEL_SOURCE.exists():
        write_mobile_state("ready", "", "Script do tunnel do celular ainda nao esta instalado neste PC.")
        log(f"AVISO: script do tunnel celular ausente: {MOBILE_TUNNEL_SOURCE}")
        return False
    try:
        LOCAL_MONITOR_DIR.mkdir(parents=True, exist_ok=True)
        needs_copy = (
            not MOBILE_TUNNEL_LOCAL.exists()
            or MOBILE_TUNNEL_SOURCE.stat().st_size != MOBILE_TUNNEL_LOCAL.stat().st_size
            or int(MOBILE_TUNNEL_SOURCE.stat().st_mtime) > int(MOBILE_TUNNEL_LOCAL.stat().st_mtime)
        )
        if needs_copy:
            shutil.copy2(MOBILE_TUNNEL_SOURCE, MOBILE_TUNNEL_LOCAL)
            log(f"Script do tunnel celular copiado para runtime local: {MOBILE_TUNNEL_LOCAL}")
        return True
    except Exception as exc:
        write_mobile_state("ready", "", f"Nao consegui preparar script do tunnel celular: {type(exc).__name__}.")
        log(f"AVISO: falha ao copiar script do tunnel celular: {type(exc).__name__}: {exc}")
        return False


def cloudflared_candidates() -> list[Path]:
    candidates = []
    override = os.environ.get("DARK_JUTSU_CLOUDFLARED_PATH")
    if override:
        candidates.append(Path(override))
    local_app = Path(os.environ.get("LOCALAPPDATA", str(USER_RUNTIME_ROOT)))
    candidates.extend(
        [
            USER_RUNTIME_ROOT / "cloudflared" / "cloudflared.exe",
            local_app / "DarkJutsu" / "cloudflared" / "cloudflared.exe",
            RUNTIME_ROOT / "cloudflared" / "cloudflared.exe",
            SHARE_ROOT / "tools" / "cloudflared.exe",
            SHARE_ROOT / "instaladores" / "cloudflared.exe",
        ]
    )
    seen = set()
    unique = []
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def cloudflared_path() -> Path | None:
    for candidate in cloudflared_candidates():
        if candidate.exists():
            return candidate
    return None


def mobile_tunnel_processes():
    try:
        ps = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -and ("
            "$_.CommandLine -match 'iniciar_tunel_celular_darkjutsu.ps1' -or "
            f"($_.Name -like 'cloudflared*' -and $_.CommandLine -match '--url' -and $_.CommandLine -match '127\\.0\\.0\\.1:({API_PORT}|{MOBILE_API_PORT})')"
            ") -and $_.CommandLine -notmatch 'Get-CimInstance Win32_Process' } | "
            "Select-Object ProcessId,Name,CommandLine"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
        ).stdout
        return out
    except Exception:
        return ""


def mobile_tunnel_running() -> bool:
    return any(ch.isdigit() for ch in mobile_tunnel_processes())


def stop_mobile_tunnel(reason: str):
    try:
        running = mobile_tunnel_running()
        if not running:
            current = read_mobile_state()
            if current.get("status") in {"online", "starting"}:
                write_mobile_state("offline", "", f"Tunnel parado: {reason}")
                log(f"Tunnel celular marcado offline. Motivo={reason}")
            return
        ps = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -and ("
            "$_.CommandLine -match 'iniciar_tunel_celular_darkjutsu.ps1' -or "
            f"($_.Name -like 'cloudflared*' -and $_.CommandLine -match '--url' -and $_.CommandLine -match '127\\.0\\.0\\.1:({API_PORT}|{MOBILE_API_PORT})')"
            ") -and $_.CommandLine -notmatch 'Get-CimInstance Win32_Process' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=12,
            creationflags=CREATE_NO_WINDOW,
        )
        write_mobile_state("offline", "", f"Tunnel parado: {reason}")
        log(f"Tunnel celular parado. Motivo={reason}")
    except Exception as exc:
        log(f"AVISO: falha ao parar tunnel celular: {type(exc).__name__}: {exc}")


def mobile_api_running() -> bool:
    return health_port("127.0.0.1", MOBILE_API_PORT, timeout=2)


def stop_mobile_api(reason: str):
    if port_process_running(MOBILE_API_PORT):
        stop_port_processes(MOBILE_API_PORT, reason)
        log(f"API celular parada. Motivo={reason}")


def stop_mobile_services(reason: str):
    stop_mobile_tunnel(reason)
    stop_mobile_api(reason)


def start_mobile_api(reason: str) -> bool:
    if mobile_api_running():
        return True
    if port_process_running(MOBILE_API_PORT):
        log(f"API celular tem processo, mas nao responde; vou limpar processo travado. Motivo={reason}")
        stop_mobile_api("processo de API celular travado antes de assumir")
        time.sleep(1)
        if mobile_api_running():
            return True
    if not health("127.0.0.1", timeout=2):
        log("API celular nao sera iniciada porque a API principal ainda nao esta saudavel.")
        return False
    sync_local_api()
    if not LOCAL_API.exists():
        log(f"ERRO: API celular nao encontrou codigo local em {LOCAL_API}")
        return False
    if not ensure_postgres_ready():
        log(f"ERRO: PostgreSQL local nao ficou pronto; API celular nao sera iniciada. Motivo={reason}")
        return False
    py = Path(sys.executable)
    if py.name.lower() == "pythonw.exe":
        py = py.with_name("python.exe")
    env = os.environ.copy()
    env["DARK_JUTSU_API_HOST"] = "127.0.0.1"
    env["DARK_JUTSU_API_PORT"] = str(MOBILE_API_PORT)
    env["DARK_JUTSU_DATABASE_URL"] = DB_URL
    env["DATABASE_URL"] = DB_URL
    env["DARK_JUTSU_ALLOWED_ORIGINS"] = "*"
    env["DARK_JUTSU_APP_WEB_ROOT"] = str(mobile_tunnel_root())
    env["PYTHONUNBUFFERED"] = "1"
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        computer = os.environ.get("COMPUTERNAME", "desconhecido")
        mobile_api_log = SHARE_ROOT / "logs" / f"api_mobile_8766_{computer}.log"
        mobile_detail_log = SHARE_ROOT / "logs" / f"api_mobile_detalhado_{computer}.log"
        env["DARK_JUTSU_API_DETAIL_LOG"] = str(mobile_detail_log)
        mobile_api_log.parent.mkdir(parents=True, exist_ok=True)
        fh = mobile_api_log.open("a", encoding="utf-8")
        fh.write("\n" + "=" * 60 + "\n")
        fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + f" | Inicio API celular por guardiao. Motivo={reason}\n")
        fh.flush()
        proc = subprocess.Popen([str(py), "-u", str(LOCAL_API)], cwd=str(LOCAL_API.parent), stdout=fh, stderr=subprocess.STDOUT, env=env, creationflags=CREATE_NO_WINDOW)
        log(f"Solicitei inicio da API celular. Motivo={reason}. Python={py} API={LOCAL_API} Porta={MOBILE_API_PORT}")
        for attempt in range(1, 16):
            time.sleep(1)
            if mobile_api_running():
                log("OK: API celular iniciou e respondeu /health.")
                return True
            code = proc.poll()
            if code is not None:
                log(f"ERRO: API celular encerrou antes de responder /health. Codigo={code}. Log={mobile_api_log}")
                return False
        log(f"ERRO: API celular nao respondeu /health em 15s. Log={mobile_api_log}")
        return False
    except Exception as exc:
        log(f"ERRO ao iniciar API celular: {type(exc).__name__}: {exc}")
        return False


def ensure_mobile_tunnel(reason: str):
    if not mobile_api_running():
        stop_mobile_tunnel("API celular nao esta saudavel")
        return
    if mobile_tunnel_running():
        return
    if not sync_mobile_tunnel_script():
        return
    cloudflared = cloudflared_path()
    if not cloudflared:
        current = read_mobile_state()
        write_mobile_state(
            "ready",
            "",
            "API pronta para celular, aguardando cloudflared.exe em %LOCALAPPDATA%\\DarkJutsu\\cloudflared.",
        )
        if current.get("status") != "ready":
            log("Tunnel celular pronto para ligar, mas cloudflared.exe nao foi encontrado.")
        return
    root = mobile_tunnel_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        write_mobile_state("starting", "", "API ativa neste PC; iniciando tunnel do celular.")
        with MOBILE_TUNNEL_LOG.open("a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + f" | Inicio tunnel celular pelo guardiao. Motivo={reason}\n")
            fh.flush()
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-WindowStyle",
                    "Hidden",
                    "-File",
                    str(MOBILE_TUNNEL_LOCAL),
                    "-Cloudflared",
                    str(cloudflared),
                    "-Root",
                    str(root),
                    "-Url",
                    MOBILE_TUNNEL_URL,
                    "-KeepAlive",
                ],
                cwd=str(root),
                stdout=fh,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            )
        log(f"Tunnel celular solicitado pelo guardiao. Cloudflared={cloudflared} Root={root} Motivo={reason}")
    except Exception as exc:
        write_mobile_state("offline", "", f"Falha ao iniciar tunnel celular: {type(exc).__name__}.")
        log(f"ERRO ao iniciar tunnel celular: {type(exc).__name__}: {exc}")


def start_local_api(reason):
    if health("127.0.0.1", timeout=2):
        log(f"API local ja responde; nao precisei iniciar. Motivo={reason}")
        return
    if api_process_running():
        log(f"API local tem processo, mas nao responde; vou limpar processo travado. Motivo={reason}. Processos={api_processes()[:700]!r}")
        stop_local_api("processo de API travado antes de assumir")
        time.sleep(2)
        if health("127.0.0.1", timeout=2):
            log("API local respondeu depois da limpeza.")
            return
    sync_local_api()
    if not LOCAL_API.exists():
        log(f"ERRO: API local nao encontrada em {LOCAL_API}")
        return
    if not ensure_postgres_ready():
        log(f"ERRO: PostgreSQL local nao ficou pronto; API nao sera iniciada. Motivo={reason}")
        return
    py = Path(sys.executable)
    if py.name.lower() == "pythonw.exe":
        py = py.with_name("python.exe")
    env = os.environ.copy()
    env["DARK_JUTSU_API_HOST"] = "0.0.0.0"
    env["DARK_JUTSU_API_PORT"] = str(API_PORT)
    env["DARK_JUTSU_DATABASE_URL"] = DB_URL
    env["DATABASE_URL"] = DB_URL
    env["PYTHONUNBUFFERED"] = "1"
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        computer = os.environ.get("COMPUTERNAME", "desconhecido")
        shared_api_log = SHARE_ROOT / "logs" / f"api_runtime_{computer}.log"
        shared_detail_log = SHARE_ROOT / "logs" / f"api_detalhado_{computer}.log"
        env["DARK_JUTSU_API_DETAIL_LOG"] = str(shared_detail_log)
        shared_api_log.parent.mkdir(parents=True, exist_ok=True)
        fh = shared_api_log.open("a", encoding="utf-8")
        fh.write("\n" + "=" * 60 + "\n")
        fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + f" | Inicio API por guardiao. Motivo={reason}\n")
        fh.flush()
        proc = subprocess.Popen([str(py), "-u", str(LOCAL_API)], cwd=str(LOCAL_API.parent), stdout=fh, stderr=subprocess.STDOUT, env=env, creationflags=CREATE_NO_WINDOW)
        log(f"Solicitei inicio da API local. Motivo={reason}. Python={py} API={LOCAL_API}")
        live_seen = False
        for attempt in range(1, API_STARTUP_WAIT_SECONDS + 1):
            time.sleep(1)
            if health("127.0.0.1", timeout=2):
                log("OK: API local iniciou e respondeu /health.")
                return
            if not live_seen and live("127.0.0.1", timeout=1):
                live_seen = True
                log("API local ja abriu /live; aguardando /health com SQL.")
            code = proc.poll()
            if code is not None:
                log(f"ERRO: processo da API encerrou antes de responder /health. Codigo={code}. Log compartilhado={shared_api_log}")
                return
            if attempt in {12, 25, 40}:
                log(f"API ainda iniciando: tentativa={attempt}s live={live_seen} health=False log={shared_api_log} detalhe={shared_detail_log}")
        log(f"ERRO: API local foi solicitada, mas nao respondeu /health em {API_STARTUP_WAIT_SECONDS}s. Log compartilhado={shared_api_log} detalhe={shared_detail_log}")
    except Exception as exc:
        log(f"ERRO ao iniciar API local: {type(exc).__name__}: {exc}")


def ensure_postgres_ready():
    if pg_ready():
        log("PostgreSQL local pronto antes de iniciar API.")
        return True
    if not PG_CTL.exists():
        log(f"ERRO: pg_ctl.exe nao encontrado em {PG_CTL}")
        return False
    if not (PGDATA / "postgresql.conf").exists():
        log(f"ERRO: PGDATA invalido em {PGDATA}")
        return False
    ensure_postgres_config()
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log("PostgreSQL local nao respondeu; iniciando pelo guardiao.")
        subprocess.run(
            [str(PG_CTL), "-D", str(PGDATA), "stop", "-m", "fast"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            creationflags=CREATE_NO_WINDOW,
        )
        proc = subprocess.run(
            [str(PG_CTL), "-D", str(PGDATA), "-l", str(PG_RUNTIME_LOG), "start"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            creationflags=CREATE_NO_WINDOW,
        )
        log(f"pg_ctl start retorno={proc.returncode}; vou verificar pg_isready.")
    except subprocess.TimeoutExpired:
        log("AVISO: pg_ctl start excedeu 15s; vou continuar verificando pg_isready.")
    except Exception as exc:
        log(f"ERRO ao iniciar PostgreSQL pelo guardiao: {type(exc).__name__}: {exc}")
    for attempt in range(1, 31):
        if pg_ready():
            log(f"PostgreSQL local pronto apos tentativa {attempt}/30.")
            return True
        time.sleep(1)
    return False


def ensure_postgres_config():
    conf = PGDATA / "postgresql.conf"
    try:
        text = conf.read_text(encoding="utf-8", errors="ignore")
        if "# Dark-Jutsu runtime config" in text and "port = 5433" in text:
            return
        with conf.open("a", encoding="utf-8") as fh:
            fh.write("\n# Dark-Jutsu runtime config\n")
            fh.write("port = 5433\n")
            fh.write("listen_addresses = '*'\n")
        log(f"Config PostgreSQL ajustada para porta 5433 em {conf}")
    except Exception as exc:
        log(f"AVISO: nao consegui ajustar postgresql.conf: {type(exc).__name__}: {exc}")


def pg_ready():
    if not PG_ISREADY.exists():
        return False
    try:
        return subprocess.run(
            [str(PG_ISREADY), "-h", "127.0.0.1", "-p", "5433", "-U", "dark_jutsu", "-d", "dark_jutsu"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
        ).returncode == 0
    except Exception:
        return False


def schema_ready():
    if not PG_PSQL.exists():
        return False
    sql = (
        "select case when "
        "current_setting('server_encoding') = 'UTF8' and "
        "to_regclass('public.users') is not null and "
        "to_regclass('public.inventory_items') is not null and "
        "to_regclass('public.chat_messages') is not null and "
        "to_regclass('public.app_settings') is not null "
        "then 'OK' else 'MISSING' end"
    )
    env = os.environ.copy()
    env.setdefault("PGPASSWORD", "dark_jutsu_dev")
    try:
        proc = subprocess.run(
            [str(PG_PSQL), "-h", "127.0.0.1", "-p", "5433", "-U", "dark_jutsu", "-d", "dark_jutsu", "-Atq", "-c", sql],
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=10,
            env=env,
            creationflags=CREATE_NO_WINDOW,
        )
        return proc.returncode == 0 and proc.stdout.strip().upper() == "OK"
    except Exception:
        return False


def latest_valid_backup():
    if not PG_RESTORE.exists():
        log(f"ERRO: pg_restore.exe nao encontrado para validar backup: {PG_RESTORE}")
        return None
    backup_dir = SHARE_ROOT / "backups"
    try:
        backups = sorted(
            (p for p in backup_dir.glob("darkjutsu_backup_*.backup") if p.is_file() and p.stat().st_size >= 1_000_000),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:20]
    except Exception as exc:
        log(f"ERRO: nao consegui listar backups em {backup_dir}: {type(exc).__name__}: {exc}")
        return None
    for backup in backups:
        try:
            proc = subprocess.run(
                [str(PG_RESTORE), "-l", str(backup)],
                capture_output=True,
                text=True,
                errors="ignore",
                timeout=30,
                creationflags=CREATE_NO_WINDOW,
            )
            listing = proc.stdout
            if proc.returncode == 0 and "TABLE DATA public users" in listing and "TABLE DATA public inventory_items" in listing:
                return backup
            log(f"Backup ignorado por validacao incompleta: {backup.name}")
        except Exception as exc:
            log(f"AVISO: falha ao validar backup {backup.name}: {type(exc).__name__}: {exc}")
    return None


def schema_restore_recent(cooldown_seconds=3600):
    try:
        if not SCHEMA_RESTORE_MARKER.exists():
            return False
        return (time.time() - SCHEMA_RESTORE_MARKER.stat().st_mtime) < cooldown_seconds
    except Exception:
        return False


def restore_schema_from_backup(*, backup=None, force=False, reason="schema local incompleto"):
    if not force and schema_restore_recent():
        log("Restore de schema ignorado: tentativa recente ainda em cooldown.")
        return False
    if not PG_RESTORE.exists() or not PG_PSQL.exists() or not PG_DROPDB.exists() or not PG_CREATEDB.exists():
        log(
            "ERRO: ferramentas de restore ausentes. "
            f"pg_restore={PG_RESTORE.exists()} psql={PG_PSQL.exists()} dropdb={PG_DROPDB.exists()} createdb={PG_CREATEDB.exists()}"
        )
        return False
    backup = backup or latest_valid_backup()
    if not backup:
        log("ERRO: nenhum backup valido encontrado para restaurar schema local.")
        return False
    try:
        SCHEMA_RESTORE_MARKER.parent.mkdir(parents=True, exist_ok=True)
        SCHEMA_RESTORE_MARKER.write_text(f"{time.time()}|{backup}\n", encoding="ascii")
    except Exception:
        pass
    env = os.environ.copy()
    env.setdefault("PGPASSWORD", "dark_jutsu_dev")
    log(f"Restaurando banco local a partir do backup valido: {backup}. Motivo={reason}")
    try:
        terminate = subprocess.run(
            [
                str(PG_PSQL),
                "-h",
                "127.0.0.1",
                "-p",
                "5433",
                "-U",
                "postgres",
                "-d",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                "select pg_terminate_backend(pid) from pg_stat_activity where datname='dark_jutsu' and pid <> pg_backend_pid();",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            errors="ignore",
            timeout=60,
            env=env,
            creationflags=CREATE_NO_WINDOW,
        )
        if terminate.returncode != 0:
            log(f"AVISO: nao consegui encerrar conexoes antes do restore codigo={terminate.returncode} erro={terminate.stderr[-500:]}")
        drop = subprocess.run(
            [str(PG_DROPDB), "-h", "127.0.0.1", "-p", "5433", "-U", "postgres", "--if-exists", "dark_jutsu"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            errors="ignore",
            timeout=60,
            env=env,
            creationflags=CREATE_NO_WINDOW,
        )
        if drop.returncode != 0:
            log(f"ERRO: dropdb antes do restore falhou codigo={drop.returncode} erro={drop.stderr[-700:]}")
            return False
        create = subprocess.run(
            [str(PG_CREATEDB), "-h", "127.0.0.1", "-p", "5433", "-U", "postgres", "-O", "dark_jutsu", "-E", "UTF8", "-T", "template0", "dark_jutsu"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            errors="ignore",
            timeout=60,
            env=env,
            creationflags=CREATE_NO_WINDOW,
        )
        if create.returncode != 0:
            log(f"ERRO: createdb UTF8 antes do restore falhou codigo={create.returncode} erro={create.stderr[-700:]}")
            return False
        restore = subprocess.run(
            [str(PG_RESTORE), "--exit-on-error", "-h", "127.0.0.1", "-p", "5433", "-U", "postgres", "-d", "dark_jutsu", "--no-owner", str(backup)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            errors="ignore",
            timeout=300,
            env=env,
            creationflags=CREATE_NO_WINDOW,
        )
        if restore.returncode != 0:
            log(f"ERRO: restore do backup falhou codigo={restore.returncode} erro={restore.stderr[-700:]}")
            return False
        grants = [
            "grant usage on schema public to dark_jutsu; grant select, insert, update, delete on all tables in schema public to dark_jutsu; grant usage, select, update on all sequences in schema public to dark_jutsu; grant execute on all functions in schema public to dark_jutsu;",
            "do $$ begin if exists (select 1 from pg_roles where rolname='dark_jutsu_service') then grant dark_jutsu_service to dark_jutsu; alter role dark_jutsu inherit; end if; end $$;",
        ]
        for sql in grants:
            proc = subprocess.run(
                [str(PG_PSQL), "-h", "127.0.0.1", "-p", "5433", "-U", "postgres", "-d", "dark_jutsu", "-v", "ON_ERROR_STOP=1", "-c", sql],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                errors="ignore",
                timeout=60,
                env=env,
                creationflags=CREATE_NO_WINDOW,
            )
            if proc.returncode != 0:
                log(f"ERRO: grant apos restore falhou codigo={proc.returncode} erro={proc.stderr[-700:]}")
                return False
        ok = schema_ready()
        log(f"Restore do banco concluido. schema_ok={ok} backup={backup.name} motivo={reason}")
        return ok
    except subprocess.TimeoutExpired:
        log("ERRO: restore do backup excedeu 300s.")
        return False
    except Exception as exc:
        log(f"ERRO: restore automatico falhou: {type(exc).__name__}: {exc}")
        return False


def backup_identity(backup: Path) -> dict:
    try:
        stat = backup.stat()
        return {"name": backup.name, "size": int(stat.st_size), "mtimeNs": int(stat.st_mtime_ns)}
    except Exception:
        return {"name": backup.name, "size": 0, "mtimeNs": 0}


def read_standby_backup_marker() -> dict:
    try:
        data = json.loads(STANDBY_BACKUP_MARKER.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def standby_backup_is_current(backup: Path) -> bool:
    current = read_standby_backup_marker()
    expected = backup_identity(backup)
    return all(current.get(key) == value for key, value in expected.items())


def mark_standby_backup_applied(backup: Path):
    payload = {
        **backup_identity(backup),
        "computer": computer_name(),
        "appliedAtEpoch": time.time(),
        "appliedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    STANDBY_BACKUP_MARKER.parent.mkdir(parents=True, exist_ok=True)
    temp = STANDBY_BACKUP_MARKER.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(STANDBY_BACKUP_MARKER)


def sync_standby_from_latest_backup() -> bool:
    backup = latest_valid_backup()
    if not backup:
        log("ERRO: candidato nao pode ficar pronto sem backup central valido.")
        return False
    if standby_backup_is_current(backup):
        return True
    identity = backup_identity(backup)
    publish_heartbeat(
        ready=False,
        api_healthy=False,
        ips=sorted(local_ips()),
        details={
            "guardianVersion": GUARDIAN_VERSION,
            "pid": os.getpid(),
            "schemaReady": schema_ready(),
            "backupSync": "restoring",
            "backupName": identity.get("name"),
        },
    )
    stop_local_api(f"sincronizacao do candidato com {backup.name}")
    ok = restore_schema_from_backup(
        backup=backup,
        force=True,
        reason="sincronizacao automatica do candidato",
    )
    if not ok:
        return False
    try:
        mark_standby_backup_applied(backup)
        log(f"Candidato sincronizado com backup central: {backup.name}")
        return True
    except Exception as exc:
        log(f"ERRO: restore concluiu, mas marcador do candidato falhou: {type(exc).__name__}: {exc}")
        return False


def sync_local_api():
    if not SHARE_API_DIR.exists():
        log(f"AVISO: pasta compartilhada da API nao encontrada: {SHARE_API_DIR}")
        return False

    for attempt in range(2):
        try:
            LOCAL_API_DIR.mkdir(parents=True, exist_ok=True)
            copied = 0
            for source in SHARE_API_DIR.rglob("*"):
                if not source.is_file():
                    continue
                rel = source.relative_to(SHARE_API_DIR)
                target = LOCAL_API_DIR / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                needs_copy = not target.exists() or source.stat().st_size != target.stat().st_size or int(source.stat().st_mtime) > int(target.stat().st_mtime)
                if needs_copy:
                    shutil.copy2(source, target)
                    copied += 1
            if copied:
                log(f"API local sincronizada com pacote compartilhado. Arquivos copiados={copied} Destino={LOCAL_API_DIR}")
            return True
        except PermissionError as exc:
            if API_RUNTIME_ROOT != USER_RUNTIME_ROOT and attempt == 0:
                set_api_runtime_root(USER_RUNTIME_ROOT, f"sem permissao em {API_RUNTIME_ROOT}: {exc}")
                continue
            log(f"AVISO: falha ao sincronizar API local: {type(exc).__name__}: {exc}")
            return False
        except Exception as exc:
            log(f"AVISO: falha ao sincronizar API local: {type(exc).__name__}: {exc}")
            return False
    return False


def maintenance_active():
    request = MAINTENANCE_DIR / f"{os.environ.get('COMPUTERNAME', '').strip().upper()}.json"
    try:
        data = json.loads(request.read_text(encoding="utf-8"))
        until = float(data.get("untilEpoch") or 0)
        if until > time.time():
            return True, data
        request.unlink(missing_ok=True)
    except FileNotFoundError:
        pass
    except Exception as exc:
        log(f"AVISO: pedido de manutencao invalido: {type(exc).__name__}: {exc}")
    return False, {}


def registry_startup_ready():
    try:
        import winreg

        names = (
            "Dark-Jutsu Monitor Servidor",
            "Dark-Jutsu Guardiao Servidor",
            "Dark-Jutsu Automus",
            "Dark-Jutsu Watchdog",
        )
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            return all(str(winreg.QueryValueEx(key, name)[0]).strip() for name in names)
    except Exception:
        return False


def command_process_running(pattern: str) -> bool:
    try:
        escaped = pattern.replace("'", "''")
        ps = (
            "Get-CimInstance Win32_Process | "
            f"Where-Object {{ $_.CommandLine -and $_.CommandLine -match '{escaped}' "
            "-and $_.CommandLine -notmatch 'Get-CimInstance Win32_Process' } | "
            "Select-Object -First 1 -ExpandProperty ProcessId"
        )
        out = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
        ).stdout
        return any(ch.isdigit() for ch in out)
    except Exception:
        return False


def ensure_hidden_user_startup():
    startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    if not os.environ.get("APPDATA"):
        return False
    registry_ok = registry_startup_ready()
    startup_ok = registry_ok
    try:
        startup.mkdir(parents=True, exist_ok=True)
        if not registry_ok and STARTUP_VBS_SOURCE.exists():
            target = startup / "Dark-Jutsu Cluster Usuario.vbs"
            source_bytes = STARTUP_VBS_SOURCE.read_bytes()
            if not target.exists() or target.read_bytes() != source_bytes:
                target.write_bytes(source_bytes)
                log(f"Inicializacao oculta do usuario atualizada: {target}")
            startup_ok = True
    except Exception as exc:
        log(f"AVISO: falha ao ajustar inicializacao oculta do usuario: {type(exc).__name__}: {exc}")
    watchdog_ok = False
    try:
        local_watchdog = LOCAL_MONITOR_DIR / "watchdog_usuario_darkjutsu.ps1"
        if WATCHDOG_SOURCE.exists():
            watchdog_bytes = WATCHDOG_SOURCE.read_bytes()
            if not local_watchdog.exists() or local_watchdog.read_bytes() != watchdog_bytes:
                local_watchdog.write_bytes(watchdog_bytes)
                log(f"Watchdog do usuario atualizado: {local_watchdog}")
            if not command_process_running("watchdog_usuario_darkjutsu"):
                subprocess.Popen(
                    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(local_watchdog)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW,
                )
            watchdog_ok = True
    except Exception as exc:
        log(f"AVISO: falha ao sincronizar watchdog do usuario: {type(exc).__name__}: {exc}")
    try:
        for name in (
            "Automus_Controlador_Atualizacoes.bat",
            "Automus_Atualizacoes.bat",
            "Automus.bat",
            "Dark-Jutsu Cluster Usuario.cmd",
        ):
            legacy = startup / name
            if legacy.exists():
                legacy.unlink()
                log(f"Inicializacao direta antiga removida: {legacy.name}")
    except Exception as exc:
        log(f"AVISO: falha ao limpar inicializacao antiga: {type(exc).__name__}: {exc}")
    return startup_ok and watchdog_ok


def main():
    if not acquire_lock():
        return
    last_full_cycle = 0
    last_startup_check = 0
    last_github_update_check = 0
    last_backup_check = 0
    last_standby_sync_check = 0
    standby_data_ready = False
    last_leader = None
    log(f"Guardiao Python dinamico iniciado. Versao={GUARDIAN_VERSION} Usuario={os.environ.get('USERNAME')} Maquina={os.environ.get('COMPUTERNAME')} IPs={sorted(local_ips())} BootWindows={boot_hint()} PID={os.getpid()}")
    while True:
        try:
            if time.time() - last_startup_check >= 60:
                ensure_hidden_user_startup()
                last_startup_check = time.time()
            local_ok = health("127.0.0.1", timeout=2)
            mobile_ok = mobile_api_running()
            sql_ok = pg_ready()
            if not sql_ok:
                sql_ok = ensure_postgres_ready()
            schema_ok = schema_ready() if sql_ok else False
            if sql_ok and not schema_ok:
                schema_ok = restore_schema_from_backup()
            lease_snapshot = read_lease()
            lease_leader = str(lease_snapshot.get("leader") or "").strip().upper()
            is_standby = bool(lease_leader and lease_leader != computer_name())
            if is_standby and sql_ok and time.time() - last_standby_sync_check >= STANDBY_SYNC_INTERVAL_SECONDS:
                standby_data_ready = sync_standby_from_latest_backup()
                last_standby_sync_check = time.time()
                schema_ok = schema_ready() if standby_data_ready else False
            elif not is_standby:
                standby_data_ready = True
            if sql_ok and not LOCAL_API.exists():
                sync_local_api()
            can_serve_api = bool(sql_ok and schema_ok and standby_data_ready and LOCAL_API.exists())
            standby_marker = read_standby_backup_marker()
            heartbeat_details = {
                "guardianVersion": GUARDIAN_VERSION,
                "pid": os.getpid(),
                "schemaReady": schema_ok,
                "mobileApiHealthy": mobile_ok,
                "backupSync": "current" if standby_data_ready else "pending",
                "backupName": standby_marker.get("name") if is_standby else "leader-live",
            }
            in_maintenance, maintenance = maintenance_active()
            if in_maintenance:
                maintenance_details = dict(heartbeat_details)
                maintenance_details["maintenance"] = maintenance
                publish_heartbeat(
                    ready=False,
                    api_healthy=False,
                    ips=sorted(local_ips()),
                    details=maintenance_details,
                )
                if local_ok or api_process_running():
                    stop_local_api("teste de queda controlado")
                else:
                    stop_mobile_services("teste de queda controlado")
                log(f"manutencao controlada ativa ate epoch={maintenance.get('untilEpoch')}")
                time.sleep(5)
                continue
            heartbeat = publish_heartbeat(
                ready=can_serve_api,
                api_healthy=local_ok,
                ips=sorted(local_ips()),
                details=heartbeat_details,
            )
            decision = election_tick()
            leader = decision.get("leader")
            if leader != last_leader:
                log(f"Eleicao alterada: lider={leader or 'nenhum'} epoch={decision.get('epoch')} prioridade_local={heartbeat.get('priority')}")
                last_leader = leader
            if decision.get("isLeader"):
                if time.time() - last_github_update_check >= GITHUB_UPDATE_INTERVAL_SECONDS:
                    trigger_github_update_check("lider ativo / intervalo de 5 minutos")
                    last_github_update_check = time.time()
                if not local_ok:
                    start_local_api(f"eleito lider dinamico epoch={decision.get('epoch')}")
                    local_ok = health("127.0.0.1", timeout=2)
                if local_ok:
                    if time.time() - last_backup_check >= BACKUP_INTERVAL_SECONDS:
                        trigger_postgres_backup("lider ativo / intervalo de 5 minutos")
                        last_backup_check = time.time()
                    mobile_ok = start_mobile_api(f"lider dinamico epoch={decision.get('epoch')}")
                    if mobile_ok:
                        ensure_mobile_tunnel(f"lider dinamico epoch={decision.get('epoch')}")
                    else:
                        stop_mobile_tunnel("API celular ainda sem health")
                else:
                    stop_mobile_services("lider ainda sem API local saudavel")
            elif local_ok or api_process_running():
                stop_local_api(f"lease pertence a {leader or 'nenhum'}")
            else:
                stop_mobile_services(f"lease pertence a {leader or 'nenhum'}")
            if time.time() - last_full_cycle >= 15:
                log(
                    f"ciclo dinamico lider={leader or 'nenhum'} self_leader={decision.get('isLeader')} "
                    f"epoch={decision.get('epoch')} sql={sql_ok} schema={schema_ok} backup_sync={standby_data_ready} "
                    f"api_preparada={can_serve_api} api_local={local_ok} api_celular={mobile_ok} prioridade={heartbeat.get('priority')}"
                )
                publish_status()
                last_full_cycle = time.time()
            time.sleep(5)
        except Exception as exc:
            log(f"ERRO ciclo guardiao Python: {type(exc).__name__}: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    main()
