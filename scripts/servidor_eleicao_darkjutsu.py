import json
import os
import shutil
import socket
import time
from contextlib import contextmanager
from pathlib import Path


SHARE_ROOT = Path(r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu")
CONFIG_PATH = SHARE_ROOT / "scripts" / "servidores_config.json"
STATUS_DIR = SHARE_ROOT / "status"
NODES_DIR = STATUS_DIR / "nodes"
LEASE_PATH = STATUS_DIR / "leader_lease.json"
LOCK_DIR = STATUS_DIR / "leader-election.lock"

DEFAULT_CONFIG = {
    "schema": 2,
    "autoDiscover": True,
    "defaultPriority": 1000,
    "heartbeatTimeoutSeconds": 60,
    "leaseSeconds": 35,
    "leaderApiStartupGraceSeconds": 45,
    "preferredReturnGraceSeconds": 90,
    "candidates": [],
}


def computer_name() -> str:
    return (os.environ.get("COMPUTERNAME") or socket.gethostname() or "desconhecido").strip().upper()


def _read_json(path: Path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data
    except Exception:
        return default


def _atomic_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{computer_name()}.{os.getpid()}.{int(time.time() * 1000)}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    for _ in range(8):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.15)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        tmp.unlink()
    except Exception:
        pass


def load_config() -> dict:
    raw = _read_json(CONFIG_PATH, {})
    config = dict(DEFAULT_CONFIG)
    if isinstance(raw, dict):
        config.update(raw)
    candidates = config.get("candidates")
    config["candidates"] = candidates if isinstance(candidates, list) else []
    return config


def candidate_settings(config: dict, name: str) -> dict:
    name = name.upper()
    for item in config.get("candidates", []):
        if isinstance(item, dict) and str(item.get("computer") or "").strip().upper() == name:
            return {
                "enabled": item.get("enabled") is not False,
                "priority": int(item.get("priority", config.get("defaultPriority", 1000))),
            }
    return {
        "enabled": bool(config.get("autoDiscover", True)),
        "priority": int(config.get("defaultPriority", 1000)),
    }


def publish_heartbeat(*, ready: bool, api_healthy: bool, ips: list[str], details: dict | None = None) -> dict:
    config = load_config()
    name = computer_name()
    settings = candidate_settings(config, name)
    path = NODES_DIR / f"{name}.json"
    old = _read_json(path, {})
    now = time.time()
    was_ready = bool(old.get("ready"))
    ready_since = float(old.get("readySinceEpoch") or now) if ready and was_ready else now
    heartbeat = {
        "schema": 2,
        "computer": name,
        "updatedAtEpoch": now,
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "priority": settings["priority"],
        "enabled": settings["enabled"],
        "ready": bool(ready and settings["enabled"]),
        "readySinceEpoch": ready_since,
        "apiHealthy": bool(api_healthy),
        "ips": sorted(set(ips)),
        "details": details or {},
    }
    _atomic_json(path, heartbeat)
    return heartbeat


def read_nodes(config: dict, now: float | None = None) -> dict[str, dict]:
    now = now or time.time()
    timeout = max(15, int(config.get("heartbeatTimeoutSeconds", 60)))
    result = {}
    try:
        paths = list(NODES_DIR.glob("*.json"))
    except Exception:
        paths = []
    for path in paths:
        node = _read_json(path, {})
        if not isinstance(node, dict):
            continue
        name = str(node.get("computer") or path.stem).strip().upper()
        settings = candidate_settings(config, name)
        age = now - float(node.get("updatedAtEpoch") or 0)
        node["computer"] = name
        node["priority"] = settings["priority"]
        node["enabled"] = settings["enabled"]
        node["fresh"] = 0 <= age <= timeout
        node["eligible"] = bool(node["enabled"] and node["fresh"] and node.get("ready"))
        result[name] = node
    return result


def read_lease() -> dict:
    lease = _read_json(LEASE_PATH, {})
    return lease if isinstance(lease, dict) else {}


def choose_preferred(nodes: dict[str, dict]) -> dict | None:
    eligible = [node for node in nodes.values() if node.get("eligible")]
    if not eligible:
        return None
    return min(eligible, key=lambda node: (int(node.get("priority", 1000)), node.get("computer", "")))


def decide_leader(config: dict, nodes: dict[str, dict], lease: dict, now: float | None = None) -> str | None:
    now = now or time.time()
    current_name = str(lease.get("leader") or "").strip().upper()
    current_api_grace = max(15, int(config.get("leaderApiStartupGraceSeconds", 45)))
    current_acquired_at = float(lease.get("acquiredAtEpoch") or now)
    current_api_grace_expired = bool(
        current_name
        and (now - current_acquired_at) > current_api_grace
        and (nodes.get(current_name) or {}).get("apiHealthy") is False
    )
    if current_api_grace_expired:
        nodes = {name: dict(node) for name, node in nodes.items()}
        if current_name in nodes:
            nodes[current_name]["eligible"] = False

    preferred = choose_preferred(nodes)
    current = nodes.get(current_name)
    lease_valid = bool(
        current_name
        and float(lease.get("expiresAtEpoch") or 0) > now
        and current
        and current.get("eligible")
    )
    if not preferred:
        return current_name if lease_valid else None
    if not lease_valid:
        return str(preferred["computer"])
    if preferred["computer"] == current_name:
        return current_name
    if int(preferred.get("priority", 1000)) >= int(current.get("priority", 1000)):
        return current_name
    grace = max(0, int(config.get("preferredReturnGraceSeconds", 90)))
    stable_for = now - float(preferred.get("readySinceEpoch") or now)
    return str(preferred["computer"]) if stable_for >= grace else current_name


@contextmanager
def election_lock(timeout: float = 8.0):
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout
    acquired = False
    while time.time() < deadline:
        try:
            LOCK_DIR.mkdir()
            (LOCK_DIR / "owner.txt").write_text(f"{computer_name()}|{os.getpid()}|{time.time()}", encoding="ascii")
            acquired = True
            break
        except FileExistsError:
            try:
                if time.time() - LOCK_DIR.stat().st_mtime > 20:
                    shutil.rmtree(LOCK_DIR, ignore_errors=True)
                    continue
            except Exception:
                pass
            time.sleep(0.2)
    try:
        yield acquired
    finally:
        if acquired:
            shutil.rmtree(LOCK_DIR, ignore_errors=True)


def election_tick() -> dict:
    now = time.time()
    config = load_config()
    me = computer_name()
    result = {"leader": None, "isLeader": False, "epoch": 0, "reason": "lock-indisponivel"}
    with election_lock() as locked:
        if not locked:
            lease = read_lease()
            result.update({"leader": lease.get("leader"), "epoch": int(lease.get("epoch") or 0)})
            return result
        nodes = read_nodes(config, now)
        lease = read_lease()
        selected = decide_leader(config, nodes, lease, now)
        old_leader = str(lease.get("leader") or "").strip().upper()
        epoch = int(lease.get("epoch") or 0)
        if selected == me:
            if old_leader != me:
                epoch += 1
            next_lease = {
                "schema": 2,
                "leader": me,
                "epoch": epoch,
                "priority": int((nodes.get(me) or {}).get("priority", 1000)),
                "acquiredAtEpoch": now if old_leader != me else float(lease.get("acquiredAtEpoch") or now),
                "renewedAtEpoch": now,
                "expiresAtEpoch": now + max(15, int(config.get("leaseSeconds", 35))),
                "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            _atomic_json(LEASE_PATH, next_lease)
            result.update({"leader": me, "isLeader": True, "epoch": epoch, "reason": "eleito-ou-renovado"})
            return result
        result.update({"leader": selected or old_leader or None, "isLeader": False, "epoch": epoch, "reason": "seguidor"})
        return result
