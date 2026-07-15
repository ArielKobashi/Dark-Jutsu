import json
import socket
import time
import urllib.request
from pathlib import Path


PRIMARY_IP = "192.168.5.44"
RESERVE_IP = "192.168.5.38"
API_PORT = 8765
SHARE_ROOT = Path(r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu")
STATUS_DIR = SHARE_ROOT / "status"


def probe(ip, endpoint="/health", timeout=4):
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(f"http://{ip}:{API_PORT}{endpoint}", timeout=timeout) as resp:
            body = resp.read(4000)
            ms = int((time.perf_counter() - start) * 1000)
            ok_json = False
            try:
                ok_json = json.loads(body.decode("utf-8", errors="replace")).get("ok") is True
            except Exception:
                pass
            return {"ok": 200 <= resp.status < 300, "sql_ok": ok_json, "ms": ms, "error": ""}
    except Exception as exc:
        return {"ok": False, "sql_ok": False, "ms": int((time.perf_counter() - start) * 1000), "error": type(exc).__name__}


def local_role():
    ips = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(item[4][0])
    except Exception:
        pass
    if PRIMARY_IP in ips:
        return "PRINCIPAL"
    if RESERVE_IP in ips:
        return "RESERVA"
    return "DESCONHECIDO"


def read_status(name):
    path = STATUS_DIR / f"{name}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        age = int(time.time() - path.stat().st_mtime)
        return data, age
    except Exception:
        return {}, None


def action(primary_ok, reserve_ok, role, blackout_seconds):
    if primary_ok:
        return "Principal comanda. Reserva deve ficar sem API ativa."
    if reserve_ok:
        if role == "PRINCIPAL":
            return "Principal deve reassumir quando conseguir iniciar API/SQL local."
        return "Reserva comanda temporariamente."
    if role == "PRINCIPAL":
        return "Principal deve assumir imediatamente."
    if role == "RESERVA":
        if blackout_seconds < 65:
            return "Reserva aguarda; janela de tolerancia de 65s ainda nao passou."
        return "Reserva deve assumir porque o principal passou de 65s offline."
    return "PC desconhecido nao deve assumir."


def line(label, primary, reserve, expected):
    print(f"| {label:<34} | {primary:<20} | {reserve:<20} | {expected:<54} |")


def main():
    role = local_role()
    ph = probe(PRIMARY_IP, "/health")
    rh = probe(RESERVE_IP, "/health", timeout=2)
    pl = probe(PRIMARY_IP, "/live")
    rl = probe(RESERVE_IP, "/live", timeout=2)
    ps, ps_age = read_status("principal")
    rs, rs_age = read_status("reserva")

    print("")
    print("=" * 142)
    print("DARK-JUTSU - SIMULACAO DE QUEDAS E CHECK DE FAILOVER")
    print(f"Agora: {time.strftime('%Y-%m-%d %H:%M:%S')} | Este PC: {socket.gethostname()} | Papel: {role}")
    print("=" * 142)
    print(f"| {'CHECK':<34} | {'PRINCIPAL':<20} | {'RESERVA':<20} | {'LEITURA':<54} |")
    print("-" * 142)
    line("API /health real", f"{'OK' if ph['ok'] else 'OFF'} {ph['ms']}ms", f"{'OK' if rh['ok'] else 'OFF'} {rh['ms']}ms", "Estado real neste momento.")
    line("API /live real", f"{'OK' if pl['ok'] else 'OFF'} {pl['ms']}ms", f"{'OK' if rl['ok'] else 'OFF'} {rl['ms']}ms", "Mostra se a API abriu, mesmo sem SQL.")
    line("Status compartilhado", f"{ps_age}s" if ps_age is not None else "sem status", f"{rs_age}s" if rs_age is not None else "sem status", "Menos de 180s significa comunicacao recente.")
    line("Guardiao publicado", str(bool(ps.get("guardiao_active"))), str(bool(rs.get("guardiao_active"))), "Deve ser True nos dois PCs.")
    line("Monitor publicado", str(bool(ps.get("monitor_active"))), str(bool(rs.get("monitor_active"))), "Deve ser True nos dois PCs.")
    line("Anti-sleep publicado", str(bool(ps.get("anti_sleep_active"))), str(bool(rs.get("anti_sleep_active"))), "Deve ser True nos dois PCs com monitor aberto.")
    print("-" * 142)
    print("")
    print("CENARIOS SIMULADOS DA LOGICA DO GUARDIAO:")
    scenarios = [
        ("1. Principal OK, reserva OFF", True, False, 0),
        ("2. Principal OFF, reserva OK", False, True, 0),
        ("3. Nenhum OK, 30s preto", False, False, 30),
        ("4. Nenhum OK, 65s preto", False, False, 65),
        ("5. Nenhum OK, 2min preto", False, False, 120),
        ("6. Os dois OK ao mesmo tempo", True, True, 0),
    ]
    for label, p_ok, r_ok, minutes in scenarios:
        print(f"- {label}: {action(p_ok, r_ok, role, minutes)}")
    print("")
    print("RESULTADO REAL AGORA:")
    print(f"- Acao esperada neste PC: {action(ph['ok'], rh['ok'], role, 0)}")
    if ph["ok"] and not rh["ok"] and ps_age is not None and rs_age is not None and rs_age <= 180:
        if rs.get("monitor_active") and rs.get("guardiao_active") and rs.get("anti_sleep_active"):
            print("- OK: Principal comanda e reserva esta pronta.")
        else:
            print("- ATENCAO: Reserva conversa, mas ainda falta monitor/guardiao/anti-sleep ficar SIM.")
    elif not ph["ok"] and not rh["ok"]:
        print("- CRITICO: Nenhuma API respondeu. O guardiao deve agir conforme papel e tempo de blackout.")
    else:
        print("- Verifique a tabela acima para detalhes.")
    print("")
    try:
        input("Pressione ENTER para fechar...")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
