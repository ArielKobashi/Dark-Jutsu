import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
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
API_LOCAL = Path(r"C:\DarkJutsu\Dark-Jutsu\api\dark_jutsu_api.py")
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


def health(ip, timeout=4):
    try:
        with urllib.request.urlopen(f"http://{ip}:{API_PORT}/health", timeout=timeout) as resp:
            body = resp.read(2000).replace(b" ", b"").lower()
            return resp.status == 200 and b'"ok":true' in body
    except Exception:
        return False


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
    try:
        (MAINTENANCE_DIR / f"{name}.json").unlink(missing_ok=True)
        log(f"Manutencao controlada removida para {name}.")
    except Exception as exc:
        log(f"AVISO: nao consegui remover manutencao de {name}: {type(exc).__name__}: {exc}")


def int_arg(name, default=0):
    try:
        pos = sys.argv.index(name)
        return max(0, int(sys.argv[pos + 1]))
    except Exception:
        return default


def main():
    execute = "--execute" in sys.argv
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
    config = load_config()
    nodes = read_nodes(config)
    followers = sorted(
        (node for name, node in nodes.items() if name != me and node.get("eligible") and node_ip(node)),
        key=lambda node: (int(node.get("priority", 1000)), node.get("computer", "")),
    )
    if not followers:
        log("ABORTADO: nenhum outro candidato elegivel publicou heartbeat recente.")
        return 1
    successor = followers[0]
    successor_name = str(successor.get("computer"))
    successor_ip = node_ip(successor)
    log(f"Sucessor previsto: {successor_name} prioridade={successor.get('priority')} ip={successor_ip}.")
    if not execute:
        log("PRE-FLIGHT OK. Rode com --execute para derrubar API/guardiao do lider e testar a eleicao real.")
        return 0

    maintenance_mode = hold_seconds > 0
    if maintenance_mode:
        set_maintenance(me, hold_seconds + 120, "teste visual de failover")
        local_stopped = wait_until("lider local pausou API por manutencao", lambda: not health("127.0.0.1", timeout=2), 60)
        if not local_stopped:
            log("ABORTADO: API local continuou respondendo mesmo com manutencao controlada.")
            clear_maintenance(me)
            return 1
    else:
        log("DERRUBANDO lider atual: pausando guardiao e API local.")
        stop_processes(["guardiao_loop_python_darkjutsu", "dark_jutsu_api.py"])
        time.sleep(8)
        if health("127.0.0.1", timeout=2):
            log("ABORTADO: API local continuou respondendo; nao vou prosseguir.")
            start_guardian()
            return 1
    log(f"Lider saiu do ar. Aguardando {successor_name} assumir.")
    successor_assumed = wait_until(
        f"{successor_name} assumiu API/SQL",
        lambda: health(successor_ip, timeout=3) and str(read_lease().get("leader") or "").upper() == successor_name,
        150,
    )
    if successor_assumed and hold_seconds:
        log(f"Segurando {successor_name} como lider por {hold_seconds}s para o monitor exibir a troca.")
        hold_deadline = time.time() + hold_seconds
        while time.time() < hold_deadline:
            if not health(successor_ip, timeout=3) or str(read_lease().get("leader") or "").upper() != successor_name:
                log(f"AVISO: {successor_name} deixou de liderar antes do tempo de exibicao acabar.")
                break
            time.sleep(5)
    log("Retornando candidato preferencial original.")
    if maintenance_mode:
        clear_maintenance(me)
    start_api()
    start_guardian()
    preferred_back = wait_until(
        "preferencial reassumiu com API/SQL",
        lambda: health("127.0.0.1", timeout=3) and str(read_lease().get("leader") or "").upper() == me,
        210,
    )
    successor_stopped = wait_until(f"{successor_name} voltou para espera", lambda: not health(successor_ip, timeout=2), 120)
    if successor_assumed and preferred_back and successor_stopped:
        log("RESULTADO: OK failover dinamico e retorno por prioridade confirmados.")
        return 0
    log("RESULTADO: ATENCAO. Verifique tabela de status e logs.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
