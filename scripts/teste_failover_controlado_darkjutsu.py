import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from servidor_eleicao_darkjutsu import computer_name, load_config, read_lease, read_nodes


PRIMARY_IP = "192.168.5.44"
RESERVE_IP = "192.168.5.38"
API_PORT = 8765
SHARE_ROOT = Path(r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu")
STATUS_DIR = SHARE_ROOT / "status"
REQUEST_DIR = STATUS_DIR / "requests"
MAINTENANCE_DIR = STATUS_DIR / "maintenance"
LOCAL_MONITOR = Path(os.environ.get("LOCALAPPDATA", "")) / "DarkJutsu" / "monitor"
PYTHONW = Path(os.environ.get("USERPROFILE", "")) / "Desktop" / "aplicacoes code" / "WPy64-3.13.12.0" / "python" / "pythonw.exe"
GUARDIAN_LOCAL = LOCAL_MONITOR / "guardiao_loop_python_darkjutsu.py"
API_CANDIDATES = (
    Path(r"C:\DarkJutsu\Dark-Jutsu\api\dark_jutsu_api.py"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "DarkJutsu" / "Dark-Jutsu" / "api" / "dark_jutsu_api.py",
)
API_LOCAL = next((path for path in API_CANDIDATES if path.exists()), API_CANDIDATES[-1])
LOG_FILE = Path(r"C:\DarkJutsu\logs\teste_failover_controlado.log")


def writable_log_file() -> Path:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        probe = LOG_FILE.parent / ".failover_write_test"
        probe.write_text("ok", encoding="ascii")
        probe.unlink(missing_ok=True)
        return LOG_FILE
    except Exception:
        fallback = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DarkJutsu" / "logs" / "teste_failover_controlado.log"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback


def log(message):
    log_file = writable_log_file()
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " | " + message
    print(line)
    with log_file.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def health_data(ip, timeout=4):
    try:
        with urllib.request.urlopen(f"http://{ip}:{API_PORT}/health", timeout=timeout) as resp:
            body = json.loads(resp.read(60000).decode("utf-8", errors="replace"))
            return body if resp.status == 200 and body.get("ok") is True else None
    except Exception:
        return None


def health(ip, timeout=4):
    return health_data(ip, timeout=timeout) is not None


def snapshot_signature(payload):
    snapshot = (payload or {}).get("latest_inventory_snapshot") or {}
    saved_at = str(snapshot.get("saved_at") or "")
    try:
        saved_at = datetime.fromisoformat(saved_at.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
    return {
        "saved_at": saved_at,
        "updated_by": str(snapshot.get("updated_by") or ""),
    }


def node_ip(node):
    for value in node.get("ips") or []:
        value = str(value).strip()
        if value and not value.startswith("127."):
            return value
    return ""


def local_role():
    ips = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(item[4][0])
    except Exception:
        pass
    if PRIMARY_IP in ips:
        return "principal"
    if RESERVE_IP in ips:
        return "reserva"
    return "desconhecido"


def read_status(role):
    path = STATUS_DIR / f"{role}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        age = int(time.time() - path.stat().st_mtime)
        return data, age
    except Exception:
        return {}, None


def request_reserve_now():
    REQUEST_DIR.mkdir(parents=True, exist_ok=True)
    status_file = STATUS_DIR / "reserva.json"
    before = status_file.stat().st_mtime if status_file.exists() else 0
    request = REQUEST_DIR / "reserva.request"
    request.write_text(f"{time.time()}|failover-test|{socket.gethostname()}\n", encoding="ascii")
    log("Pedido remoto enviado para reserva publicar status agora.")
    deadline = time.time() + 25
    while time.time() < deadline:
        if status_file.exists() and status_file.stat().st_mtime > before:
            log("Reserva respondeu ao pedido remoto de status.")
            return True
        time.sleep(1)
    log("ABORTADO: reserva nao respondeu ao pedido remoto novo. Atualize o guardiao da reserva antes do teste real.")
    return False


def stop_processes(patterns):
    pattern_text = ",".join([repr(p) for p in patterns])
    ps = f"""
$patterns = @({pattern_text})
Get-CimInstance Win32_Process -Filter "Name = 'python.exe' or Name = 'pythonw.exe' or Name = 'cmd.exe'" |
  Where-Object {{
    $cmd = $_.CommandLine
    if (-not $cmd -or $_.ProcessId -eq $PID) {{ return $false }}
    foreach ($p in $patterns) {{
      if ($cmd -match [regex]::Escape($p)) {{ return $true }}
    }}
    return $false
  }} |
  ForEach-Object {{
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Output $_.ProcessId
  }}
"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            errors="ignore",
            timeout=45,
        ).stdout
    except subprocess.TimeoutExpired:
        log("AVISO: consulta de processos excedeu 45s; nenhum processo foi confirmado como parado.")
        return []
    stopped = [line.strip() for line in out.splitlines() if line.strip().isdigit()]
    if stopped:
        log("Processos parados: " + ", ".join(stopped))
    else:
        log("AVISO: nenhum processo alvo encontrado para parar.")
    return stopped


def start_guardian():
    if PYTHONW.exists() and GUARDIAN_LOCAL.exists():
        subprocess.Popen([str(PYTHONW), str(GUARDIAN_LOCAL)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log("Guardiao principal reiniciado.")


def start_api():
    py = PYTHONW.with_name("python.exe")
    if py.exists() and API_LOCAL.exists():
        env = os.environ.copy()
        env["DARK_JUTSU_API_HOST"] = "0.0.0.0"
        env["DARK_JUTSU_API_PORT"] = str(API_PORT)
        env["DARK_JUTSU_DATABASE_URL"] = "postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
        env["DATABASE_URL"] = env["DARK_JUTSU_DATABASE_URL"]
        subprocess.Popen([str(py), str(API_LOCAL)], cwd=str(API_LOCAL.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        log("API principal reiniciada.")


def wait_until(label, predicate, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if predicate():
            log(f"OK: {label}")
            return True
        time.sleep(5)
    log(f"FALHOU: {label}")
    return False


def set_maintenance(name, seconds, reason):
    MAINTENANCE_DIR.mkdir(parents=True, exist_ok=True)
    path = MAINTENANCE_DIR / f"{name}.json"
    payload = {
        "computer": name,
        "reason": reason,
        "createdAtEpoch": time.time(),
        "untilEpoch": time.time() + seconds,
        "createdBy": computer_name(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Manutencao controlada criada para {name} por {seconds}s. Motivo={reason}.")


def clear_maintenance(name):
    path = MAINTENANCE_DIR / f"{name}.json"
    last_error = None
    for _ in range(30):
        try:
            path.unlink(missing_ok=True)
            log(f"Manutencao controlada removida para {name}.")
            return True
        except (PermissionError, OSError) as exc:
            last_error = exc
            time.sleep(0.5)
    log(f"AVISO: nao consegui remover manutencao de {name} apos 15s: {type(last_error).__name__}: {last_error}")
    return False


def int_arg(name, default=0):
    try:
        pos = sys.argv.index(name)
        return max(0, int(sys.argv[pos + 1]))
    except Exception:
        return default


def latest_backup_name():
    try:
        backups = sorted(
            (path for path in (SHARE_ROOT / "backups").glob("darkjutsu_backup_*.backup") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return backups[0].name if backups else ""
    except Exception:
        return ""


def node_backup_name(name, config):
    node = read_nodes(config).get(str(name).upper()) or {}
    return str((node.get("details") or {}).get("backupName") or "")


def run_candidate_test(me, target, followers, baseline_signature, expected_backup, hold_seconds, config):
    target_name = str(target.get("computer") or "").upper()
    target_ip = node_ip(target)
    blocked_followers = [
        node for node in followers
        if str(node.get("computer") or "").upper() != target_name
    ]
    blockers = [str(node.get("computer") or "").upper() for node in blocked_followers] + [me]
    maintenance_seconds = max(180, hold_seconds + 240)
    log(f"ETAPA {target_name}: bloqueios temporarios={blockers} backup={expected_backup}.")
    for name in blockers:
        set_maintenance(name, maintenance_seconds, f"teste de failover para {target_name}")

    target_assumed = False
    data_compatible = False
    backup_compatible = False
    try:
        local_stopped = wait_until(
            f"lider local pausou API para testar {target_name}",
            lambda: not health("127.0.0.1", timeout=2),
            60,
        )
        if not local_stopped:
            log(f"FALHOU: API local nao pausou para testar {target_name}.")
            return False
        for node in blocked_followers:
            ip = node_ip(node)
            if ip and not wait_until(
                f"{node.get('computer')} permaneceu em manutencao",
                lambda ip=ip: not health(ip, timeout=2),
                45,
            ):
                return False
        target_assumed = wait_until(
            f"{target_name} assumiu API/SQL",
            lambda: health(target_ip, timeout=3) and str(read_lease().get("leader") or "").upper() == target_name,
            180,
        )
        if target_assumed:
            successor_signature = snapshot_signature(health_data(target_ip, timeout=5))
            data_compatible = bool(baseline_signature.get("saved_at") and successor_signature == baseline_signature)
            current_backup = node_backup_name(target_name, config)
            backup_compatible = bool(expected_backup and current_backup == expected_backup)
            if data_compatible:
                log(f"OK: assinatura SQL preservada em {target_name}: {successor_signature}.")
            else:
                log(f"FALHOU: assinatura SQL diferente em {target_name}. Antes={baseline_signature} Sucessor={successor_signature}.")
            if backup_compatible:
                log(f"OK: {target_name} confirmou backup aplicado {current_backup}.")
            else:
                log(f"FALHOU: {target_name} anuncia backup={current_backup or 'nenhum'}, esperado={expected_backup}.")
        if target_assumed and hold_seconds:
            log(f"Segurando {target_name} como lider por {hold_seconds}s.")
            hold_deadline = time.time() + hold_seconds
            while time.time() < hold_deadline:
                if not health(target_ip, timeout=3) or str(read_lease().get("leader") or "").upper() != target_name:
                    log(f"AVISO: {target_name} deixou de liderar antes do tempo previsto.")
                    break
                time.sleep(5)
    finally:
        for name in reversed(blockers):
            clear_maintenance(name)

    preferred_back = wait_until(
        f"{me} reassumiu apos testar {target_name}",
        lambda: health("127.0.0.1", timeout=3) and str(read_lease().get("leader") or "").upper() == me,
        240,
    )
    target_stopped = wait_until(
        f"{target_name} voltou para espera",
        lambda: not health(target_ip, timeout=2),
        120,
    )
    return bool(target_assumed and data_compatible and backup_compatible and preferred_back and target_stopped)


def main():
    execute = "--execute" in sys.argv
    all_candidates = "--all-candidates" in sys.argv
    hold_seconds = int_arg("--hold-seconds", 0)
    log("==================================================")
    log("Teste de failover dinamico controlado iniciado.")
    me = computer_name()
    lease = read_lease()
    leader = str(lease.get("leader") or "").upper()
    if leader != me:
        log(f"ABORTADO: este teste deve rodar no lider atual. Lider={leader or 'nenhum'} EstePC={me}.")
        return 1
    if not health("127.0.0.1"):
        log("ABORTADO: API local do lider nao esta saudavel antes do teste.")
        return 1
    baseline_signature = snapshot_signature(health_data("127.0.0.1"))
    log(f"Assinatura SQL antes da queda: {baseline_signature}.")
    config = load_config()
    nodes = read_nodes(config)
    followers = sorted(
        (node for name, node in nodes.items() if name != me and node.get("eligible") and node_ip(node)),
        key=lambda node: (int(node.get("priority", 1000)), node.get("computer", "")),
    )
    if not followers:
        log("ABORTADO: nenhum outro candidato elegivel publicou heartbeat recente.")
        return 1
    targets = followers if all_candidates else followers[:1]
    expected_backup = latest_backup_name()
    for target in targets:
        target_name = str(target.get("computer") or "").upper()
        log(
            f"Candidato previsto: {target_name} prioridade={target.get('priority')} ip={node_ip(target)} "
            f"backup={node_backup_name(target_name, config) or 'nenhum'} esperado={expected_backup or 'nenhum'}."
        )
        if not execute and node_backup_name(target_name, config) != expected_backup:
            log(f"ABORTADO: {target_name} ainda nao confirmou o backup mais recente.")
            return 1
    if not execute:
        log(f"PRE-FLIGHT OK para {len(targets)} candidato(s). Rode com --execute para testar a eleicao real.")
        return 0

    results = []
    for target in targets:
        target_name = str(target.get("computer") or "").upper()
        stage_backup = latest_backup_name()
        if not wait_until(
            f"{target_name} sincronizou o backup vigente {stage_backup}",
            lambda name=target_name, expected=stage_backup: node_backup_name(name, config) == expected,
            240,
        ):
            results.append(False)
            break
        results.append(
            run_candidate_test(
                me,
                target,
                followers,
                baseline_signature,
                stage_backup,
                hold_seconds,
                config,
            )
        )
        if not results[-1]:
            break
    if len(results) == len(targets) and all(results):
        log(f"RESULTADO: OK failover dinamico confirmado em {len(targets)} candidato(s).")
        return 0
    log("RESULTADO: ATENCAO. Verifique tabela de status e logs.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
