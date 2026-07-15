import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


PRIMARY_IP = "192.168.5.44"
RESERVE_IP = "192.168.5.38"
API_PORT = 8765
SHARE_ROOT = Path(r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu")
SCRIPTS = SHARE_ROOT / "scripts"
STATUS_DIR = SHARE_ROOT / "status"
REQUEST_DIR = STATUS_DIR / "requests"
STATUS_SCRIPT = SCRIPTS / "status_compartilhado_servidores_darkjutsu.py"
LOCAL_API = Path(r"C:\DarkJutsu\Dark-Jutsu\api\dark_jutsu_api.py")
SHARE_API_DIR = SHARE_ROOT / "pacote" / "Dark-Jutsu" / "api"
LOCAL_API_DIR = LOCAL_API.parent
LOG_DIR = Path(r"C:\DarkJutsu\logs")
LOG_FILE = LOG_DIR / "guardiao_loop_python.log"
API_LOG = LOG_DIR / "api_runtime_python_guardiao.log"
LOCK_FILE = LOG_DIR / "guardiao_loop_python.lock"
DB_URL = "postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
CREATE_NO_WINDOW = 0x08000000
GUARDIAN_VERSION = "2026-07-15.8"
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
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, text=True, errors="ignore", timeout=8).stdout.strip()
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
                    out = subprocess.run(["tasklist", "/FI", f"PID eq {old_pid}"], capture_output=True, text=True, errors="ignore", timeout=5).stdout
                    if str(old_pid) in out:
                        log(f"Guardiao Python ja esta rodando no PID {old_pid}. Encerrando duplicado.")
                        return False
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
        out = subprocess.run(["ipconfig"], capture_output=True, text=True, errors="ignore", timeout=5).stdout
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
        subprocess.run([str(py), str(STATUS_SCRIPT), "--publish-only"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40, creationflags=CREATE_NO_WINDOW)
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
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, text=True, errors="ignore", timeout=10).stdout
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
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], capture_output=True, text=True, errors="ignore", timeout=10).stdout
        stopped = False
        for line in out.splitlines():
            line = line.strip()
            if line and line[0].isdigit():
                pid = line.split()[0]
                subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
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


def main():
    current_role = role()
    if not acquire_lock():
        return
    blackout_since = None
    last_full_cycle = 0
    log(f"Guardiao Python iniciado. Versao={GUARDIAN_VERSION} Papel={current_role} Usuario={os.environ.get('USERNAME')} Maquina={os.environ.get('COMPUTERNAME')} IPs={sorted(local_ips())} BootWindows={boot_hint()} PID={os.getpid()}")
    while True:
        try:
            handle_status_request(current_role)
            if time.time() - last_full_cycle >= 15:
                publish_status()
                primary_ok = health(PRIMARY_IP)
                reserve_ok = health(RESERVE_IP)
                local_ok = health("127.0.0.1", timeout=2)
                if primary_ok or reserve_ok:
                    blackout_since = None
                else:
                    if blackout_since is None:
                        blackout_since = time.time()
                blackout_seconds = 0 if blackout_since is None else int(time.time() - blackout_since)
                log(f"ciclo papel={current_role} primary={primary_ok} reserve={reserve_ok} local={local_ok} blackout={blackout_seconds}s")
                if current_role == "principal" and not primary_ok:
                    start_local_api("principal sem API ativa")
                elif current_role == "reserva":
                    if primary_ok:
                        if local_ok:
                            stop_local_api("principal voltou; reserva retorna para espera")
                    elif blackout_seconds >= 65 and not reserve_ok:
                        start_local_api(f"reserva assumindo apos {blackout_seconds}s sem principal")
                last_full_cycle = time.time()
            time.sleep(5)
        except Exception as exc:
            log(f"ERRO ciclo guardiao Python: {type(exc).__name__}: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    main()
