import os
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from servidor_eleicao_darkjutsu import election_tick, publish_heartbeat


PRIMARY_IP = "192.168.5.44"
RESERVE_IP = "192.168.5.38"
API_PORT = 8765
FAILOVER_BLACKOUT_SECONDS = 180
SHARE_ROOT = Path(r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu")
SCRIPTS = SHARE_ROOT / "scripts"
STATUS_DIR = SHARE_ROOT / "status"
REQUEST_DIR = STATUS_DIR / "requests"
STATUS_SCRIPT = SCRIPTS / "status_compartilhado_servidores_darkjutsu.py"
SYSTEM_RUNTIME_ROOT = Path(r"C:\DarkJutsu")
USER_RUNTIME_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "DarkJutsu"
RUNTIME_ROOT = Path(os.environ.get("DARK_JUTSU_RUNTIME_ROOT") or (SYSTEM_RUNTIME_ROOT if SYSTEM_RUNTIME_ROOT.exists() else USER_RUNTIME_ROOT))
LOCAL_API = RUNTIME_ROOT / "Dark-Jutsu" / "api" / "dark_jutsu_api.py"
SHARE_API_DIR = SHARE_ROOT / "pacote" / "Dark-Jutsu" / "api"
LOCAL_API_DIR = LOCAL_API.parent
LOG_DIR = RUNTIME_ROOT / "logs"
USER_PG_HOME = Path.home() / "Desktop" / "aplicacoes code" / "pgsql"
PG_HOME = USER_PG_HOME if not SYSTEM_RUNTIME_ROOT.exists() and (USER_PG_HOME / "bin" / "pg_ctl.exe").exists() else RUNTIME_ROOT / "PostgreSQL" / "pgsql"
PG_BIN = PG_HOME / "bin"
PGDATA = (PG_HOME / "data") if PG_HOME == USER_PG_HOME else RUNTIME_ROOT / "postgres-data"
PG_CTL = PG_BIN / "pg_ctl.exe"
PG_ISREADY = PG_BIN / "pg_isready.exe"
PG_RUNTIME_LOG = LOG_DIR / "postgres_runtime.log"
LOG_FILE = LOG_DIR / "guardiao_loop_python.log"
API_LOG = LOG_DIR / "api_runtime_python_guardiao.log"
LOCK_FILE = LOG_DIR / "guardiao_loop_python.lock"
DB_URL = "postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
CREATE_NO_WINDOW = 0x08000000
GUARDIAN_VERSION = "2026-07-18.22"
MAINTENANCE_DIR = STATUS_DIR / "maintenance"
SHARED_LOG = SHARE_ROOT / "logs" / "guardiao_python_eventos.txt"
TEST_ACTIVE_FILE = SHARE_ROOT / "status" / "teste_inicializacao_ativo.txt"
TEST_LOG = SHARE_ROOT / "logs" / "teste_inicializacao_manual_darkjutsu.txt"


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


def boot_hint():
    try:
        ps = "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime"
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, text=True, errors="ignore", timeout=8, creationflags=CREATE_NO_WINDOW).stdout.strip()
        return out or "indisponivel"
    except Exception:
        return "indisponivel"


def acquire_lock():
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        if LOCK_FILE.exists():
            try:
                old_pid = int(LOCK_FILE.read_text(encoding="ascii").strip() or "0")
            except Exception:
                old_pid = 0
            if old_pid:
                try:
                    ps = (
                        f"Get-CimInstance Win32_Process -Filter \"ProcessId={old_pid}\" | "
                        "Select-Object -ExpandProperty CommandLine"
                    )
                    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, text=True, errors="ignore", timeout=8, creationflags=CREATE_NO_WINDOW).stdout
                    if "guardiao_loop_python_darkjutsu.py" in out:
                        log(f"Guardiao Python ja esta rodando no PID {old_pid}. Encerrando duplicado.")
                        return False
                    log(f"Lock antigo ignorado: PID {old_pid} nao e guardiao ativo.")
                except Exception:
                    pass
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
    try:
        with urllib.request.urlopen(f"http://{ip}:{API_PORT}/health", timeout=timeout) as resp:
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


def api_processes():
    try:
        ps = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -and "
            "($_.CommandLine -match 'dark_jutsu_api.py' -or $_.CommandLine -match 'iniciar_api_servidor.bat') "
            "-and $_.CommandLine -notmatch 'Get-CimInstance Win32_Process' } | "
            "Select-Object ProcessId,Name,CommandLine | Format-List"
        )
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, text=True, errors="ignore", timeout=10, creationflags=CREATE_NO_WINDOW).stdout
        return out
    except Exception:
        return ""


def api_process_running():
    return any(ch.isdigit() for ch in api_processes())


def stop_local_api(reason):
    try:
        ps = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -and "
            "($_.CommandLine -match 'dark_jutsu_api.py' -or $_.CommandLine -match 'iniciar_api_servidor.bat') "
            "-and $_.CommandLine -notmatch 'Get-CimInstance Win32_Process' } | "
            "Select-Object ProcessId,Name,CommandLine"
        )
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, text=True, errors="ignore", timeout=10, creationflags=CREATE_NO_WINDOW).stdout
        stopped = False
        for line in out.splitlines():
            line = line.strip()
            if line and line[0].isdigit():
                pid = line.split()[0]
                subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, creationflags=CREATE_NO_WINDOW)
                stopped = True
        if stopped:
            log(f"API local parada. Motivo={reason}")
        else:
            log(f"Nenhum processo de API local encontrado para parar. Motivo={reason}")
    except Exception as exc:
        log(f"AVISO: falha ao parar API local: {type(exc).__name__}: {exc}")


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
    if not LOCAL_API.exists():
        log(f"ERRO: API local nao encontrada em {LOCAL_API}")
        return
    sync_local_api()
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
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        shared_api_log = SHARE_ROOT / "logs" / f"api_runtime_{os.environ.get('COMPUTERNAME', 'desconhecido')}.log"
        shared_api_log.parent.mkdir(parents=True, exist_ok=True)
        fh = shared_api_log.open("a", encoding="utf-8")
        fh.write("\n" + "=" * 60 + "\n")
        fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + f" | Inicio API por guardiao. Motivo={reason}\n")
        fh.flush()
        proc = subprocess.Popen([str(py), str(LOCAL_API)], cwd=str(LOCAL_API.parent), stdout=fh, stderr=subprocess.STDOUT, env=env, creationflags=CREATE_NO_WINDOW)
        log(f"Solicitei inicio da API local. Motivo={reason}. Python={py} API={LOCAL_API}")
        for _ in range(12):
            time.sleep(1)
            if health("127.0.0.1", timeout=2):
                log("OK: API local iniciou e respondeu /health.")
                return
            code = proc.poll()
            if code is not None:
                log(f"ERRO: processo da API encerrou antes de responder /health. Codigo={code}. Log compartilhado={shared_api_log}")
                return
        log(f"ERRO: API local foi solicitada, mas nao respondeu /health em 12s. Log compartilhado={shared_api_log}")
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
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log("PostgreSQL local nao respondeu; iniciando pelo guardiao.")
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


def sync_local_api():
    if not SHARE_API_DIR.exists():
        log(f"AVISO: pasta compartilhada da API nao encontrada: {SHARE_API_DIR}")
        return
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
            log(f"API local sincronizada com pacote compartilhado. Arquivos copiados={copied}")
    except Exception as exc:
        log(f"AVISO: falha ao sincronizar API local: {type(exc).__name__}: {exc}")


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


def main():
    if not acquire_lock():
        return
    last_full_cycle = 0
    last_leader = None
    log(f"Guardiao Python dinamico iniciado. Versao={GUARDIAN_VERSION} Usuario={os.environ.get('USERNAME')} Maquina={os.environ.get('COMPUTERNAME')} IPs={sorted(local_ips())} BootWindows={boot_hint()} PID={os.getpid()}")
    while True:
        try:
            local_ok = health("127.0.0.1", timeout=2)
            sql_ok = pg_ready()
            if not sql_ok:
                sql_ok = ensure_postgres_ready()
            in_maintenance, maintenance = maintenance_active()
            if in_maintenance:
                publish_heartbeat(
                    ready=False,
                    api_healthy=False,
                    ips=sorted(local_ips()),
                    details={"guardianVersion": GUARDIAN_VERSION, "pid": os.getpid(), "maintenance": maintenance},
                )
                if local_ok or api_process_running():
                    stop_local_api("teste de queda controlado")
                log(f"manutencao controlada ativa ate epoch={maintenance.get('untilEpoch')}")
                time.sleep(5)
                continue
            heartbeat = publish_heartbeat(
                ready=sql_ok,
                api_healthy=local_ok,
                ips=sorted(local_ips()),
                details={"guardianVersion": GUARDIAN_VERSION, "pid": os.getpid()},
            )
            decision = election_tick()
            leader = decision.get("leader")
            if leader != last_leader:
                log(f"Eleicao alterada: lider={leader or 'nenhum'} epoch={decision.get('epoch')} prioridade_local={heartbeat.get('priority')}")
                last_leader = leader
            if decision.get("isLeader"):
                if not local_ok:
                    start_local_api(f"eleito lider dinamico epoch={decision.get('epoch')}")
            elif local_ok or api_process_running():
                stop_local_api(f"lease pertence a {leader or 'nenhum'}")
            if time.time() - last_full_cycle >= 15:
                log(
                    f"ciclo dinamico lider={leader or 'nenhum'} self_leader={decision.get('isLeader')} "
                    f"epoch={decision.get('epoch')} sql={sql_ok} api_local={local_ok} prioridade={heartbeat.get('priority')}"
                )
                publish_status()
                last_full_cycle = time.time()
            time.sleep(5)
        except Exception as exc:
            log(f"ERRO ciclo guardiao Python: {type(exc).__name__}: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    main()
