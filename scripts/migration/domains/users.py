from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.migration.sql_client import connect, json_param
from scripts.migration.utils import ensure_dir, sha256_file, utc_now, write_json


DOMAIN = "users"
REQUEST_PATHS = ("solicitacoesCadastro", "solicitaçõesCadastro")
SECRET_KEYS = {"senha", "senhaAntiga", "senhaResetToken", "password", "passwordPlain"}


def load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo Firebase export nao encontrado: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    if any(key in data for key in ("usuarios", "usuariosBanidos", *REQUEST_PATHS)):
        return data
    return {}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, int | float):
        raw = float(value)
        if raw > 100000000000:
            raw = raw / 1000
        return datetime.fromtimestamp(raw, timezone.utc)
    return None


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            clean[key] = "[redacted]" if key in SECRET_KEYS else _sanitize(item)
        return clean
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _role(value: Any) -> str:
    role = (_clean_text(value) or "op").lower()
    return role if role in {"op", "mod", "admin", "service"} else "op"


def _status(value: Any) -> str:
    status = (_clean_text(value) or "pendente").lower()
    if status in {"aprovado", "aprovada", "approved"}:
        return "aprovado"
    if status in {"recusado", "recusada", "rejeitado", "rejeitada", "denied"}:
        return "recusado"
    return status


def _requests(raw: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    rows: list[tuple[str, str, dict[str, Any]]] = []
    for path in REQUEST_PATHS:
        node = raw.get(path)
        if not isinstance(node, dict):
            continue
        for key, value in node.items():
            if isinstance(value, dict):
                rows.append((path, str(key), value))
    return rows


def inspect(raw: dict[str, Any], source_hash: str) -> dict[str, Any]:
    usuarios = raw.get("usuarios") if isinstance(raw.get("usuarios"), dict) else {}
    banidos = raw.get("usuariosBanidos") if isinstance(raw.get("usuariosBanidos"), dict) else {}
    requests = _requests(raw)
    request_counts = {
        path: len(raw.get(path)) if isinstance(raw.get(path), dict) else 0
        for path in REQUEST_PATHS
    }
    duplicated_request_ids = len(requests) - len({f"{path}:{key}" for path, key, _ in requests})
    return {
        "domain": DOMAIN,
        "source_hash": source_hash,
        "users": len(usuarios),
        "banned_users": len(banidos),
        "signup_requests": len(requests),
        "signup_request_paths": request_counts,
        "duplicated_request_ids": duplicated_request_ids,
        "nicknames": len(raw.get("nicknames") if isinstance(raw.get("nicknames"), dict) else {}),
        "nicknames_auth": len(raw.get("nicknamesAuth") if isinstance(raw.get("nicknamesAuth"), dict) else {}),
        "nicknames_simple": len(raw.get("nicknamesSimple") if isinstance(raw.get("nicknamesSimple"), dict) else {}),
    }


def deterministic_sample(raw: dict[str, Any], sample_size: int = 20) -> dict[str, Any]:
    usuarios = raw.get("usuarios") if isinstance(raw.get("usuarios"), dict) else {}
    sample_users = []
    for uid in sorted(usuarios)[:sample_size]:
        item = usuarios.get(uid) if isinstance(usuarios.get(uid), dict) else {}
        sample_users.append(
            {
                "uid": uid,
                "nickname": item.get("nickname"),
                "badge": item.get("cracha"),
                "role": item.get("nivel"),
                "active": item.get("ativo"),
                "sector": item.get("setor"),
            }
        )
    sample_requests = []
    for path, key, item in _requests(raw)[:sample_size]:
        sample_requests.append(
            {
                "path": path,
                "id": key,
                "nickname": item.get("nickname"),
                "badge": item.get("cracha"),
                "status": item.get("status"),
            }
        )
    return {"users": sample_users, "signup_requests": sample_requests}


def write_reports(run_dir: Path, inspection: dict[str, Any], sample: dict[str, Any], mode: str) -> None:
    reports_dir = ensure_dir(run_dir / "reports")
    write_json(reports_dir / "users-summary.json", {"mode": mode, "inspection": inspection, "sample": sample})
    md = [
        "# Users migration report",
        "",
        f"Mode: `{mode}`",
        f"Source hash: `{inspection['source_hash']}`",
        "",
        "## Totals",
        "",
        f"- Users: {inspection['users']}",
        f"- Banned users: {inspection['banned_users']}",
        f"- Signup requests: {inspection['signup_requests']}",
        f"- `solicitacoesCadastro`: {inspection['signup_request_paths'].get('solicitacoesCadastro', 0)}",
        f"- `solicitaçõesCadastro`: {inspection['signup_request_paths'].get('solicitaçõesCadastro', 0)}",
        f"- Nicknames auth index: {inspection['nicknames_auth']}",
        f"- Nicknames simple index: {inspection['nicknames_simple']}",
        "",
        "## Sample users",
        "",
    ]
    for item in sample.get("users", [])[:20]:
        md.append(f"- `{item.get('uid')}` `{item.get('nickname')}` role={item.get('role')} active={item.get('active')}")
    (reports_dir / "users-summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def apply_to_sql(raw: dict[str, Any], database_url: str) -> dict[str, Any]:
    usuarios = raw.get("usuarios") if isinstance(raw.get("usuarios"), dict) else {}
    banidos = raw.get("usuariosBanidos") if isinstance(raw.get("usuariosBanidos"), dict) else {}
    requests = _requests(raw)
    with connect(database_url) as (driver_name, driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        cur.execute("delete from banned_users")
        cur.execute("delete from signup_requests")
        cur.execute("delete from users")

        user_sql = """
            insert into users (
              id, firebase_uid, nickname, badge, sector, role, active,
              password_status, created_at, updated_at, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s::jsonb)
        """
        users_loaded = 0
        for uid, item in usuarios.items():
            if not isinstance(item, dict):
                continue
            nickname = _clean_text(item.get("nickname")) or str(uid)
            cur.execute(
                user_sql,
                (
                    str(uid),
                    str(uid),
                    nickname,
                    _clean_text(item.get("cracha")),
                    _clean_text(item.get("setor")),
                    _role(item.get("nivel")),
                    bool(item.get("ativo", True)),
                    _clean_text(item.get("senha")),
                    _timestamp(item.get("criadoEm")),
                    json_param(driver_name, driver, _sanitize(item)),
                ),
            )
            users_loaded += 1

        request_sql = """
            insert into signup_requests (
              id, requested_uid, nickname, password_plain_legacy, badge, sector,
              status, duplicated, created_at, decided_at, decided_by, raw_data
            )
            values (%s, %s, %s, null, %s, %s, %s, %s, %s, %s, null, %s::jsonb)
        """
        seen_request_keys: set[str] = set()
        requests_loaded = 0
        for path, key, item in requests:
            nickname = _clean_text(item.get("nickname")) or f"request-{key}"
            sql_id = f"{path}:{key}"
            duplicate = sql_id in seen_request_keys
            seen_request_keys.add(sql_id)
            cur.execute(
                request_sql,
                (
                    sql_id,
                    _clean_text(item.get("uid")) or _clean_text(item.get("requested_uid")),
                    nickname,
                    _clean_text(item.get("cracha")),
                    _clean_text(item.get("setor")),
                    _status(item.get("status")),
                    duplicate,
                    _timestamp(item.get("criadoEm")),
                    _timestamp(item.get("decididoEm") or item.get("aprovadoEm") or item.get("recusadoEm")),
                    json_param(driver_name, driver, {"source_path": path, **_sanitize(item)}),
                ),
            )
            requests_loaded += 1

        banned_sql = """
            insert into banned_users (
              user_id, nickname, badge, sector, banned_at, banned_by, reason, raw_data
            )
            values (%s, %s, %s, %s, %s, null, %s, %s::jsonb)
        """
        banned_loaded = 0
        for uid, item in banidos.items():
            if not isinstance(item, dict):
                continue
            cur.execute(
                banned_sql,
                (
                    str(uid),
                    _clean_text(item.get("nickname")),
                    _clean_text(item.get("cracha")),
                    _clean_text(item.get("setor")),
                    _timestamp(item.get("banidoEm")),
                    _clean_text(item.get("motivo") or item.get("reason") or item.get("status")),
                    json_param(driver_name, driver, _sanitize(item)),
                ),
            )
            banned_loaded += 1

        return {"users_loaded": users_loaded, "signup_requests_loaded": requests_loaded, "banned_users_loaded": banned_loaded}


def run(source: Path, run_dir: Path, mode: str, database_url: str = "", sample_size: int = 20) -> dict[str, Any]:
    raw_dir = ensure_dir(run_dir / "raw")
    source_hash = sha256_file(source)
    raw = load_raw(source)
    write_json(
        raw_dir / "users-domain.json",
        {
            "usuarios": _sanitize(raw.get("usuarios") if isinstance(raw.get("usuarios"), dict) else {}),
            "usuariosBanidos": _sanitize(raw.get("usuariosBanidos") if isinstance(raw.get("usuariosBanidos"), dict) else {}),
            "solicitacoesCadastro": _sanitize(raw.get("solicitacoesCadastro") if isinstance(raw.get("solicitacoesCadastro"), dict) else {}),
            "solicitaçõesCadastro": _sanitize(raw.get("solicitaçõesCadastro") if isinstance(raw.get("solicitaçõesCadastro"), dict) else {}),
            "nicknames": raw.get("nicknames") if isinstance(raw.get("nicknames"), dict) else {},
            "nicknamesAuth": raw.get("nicknamesAuth") if isinstance(raw.get("nicknamesAuth"), dict) else {},
            "nicknamesSimple": raw.get("nicknamesSimple") if isinstance(raw.get("nicknamesSimple"), dict) else {},
        },
    )
    inspection = inspect(raw, source_hash)
    sample = deterministic_sample(raw, sample_size)
    apply_result = apply_to_sql(raw, database_url) if mode == "apply" else None
    write_reports(run_dir, inspection, sample, mode)
    result = {
        "domain": DOMAIN,
        "mode": mode,
        "source": str(source),
        "run_dir": str(run_dir),
        "source_hash": source_hash,
        "inspection": inspection,
        "sample_size": sample_size,
        "apply_result": apply_result,
        "finished_at": utc_now().isoformat(),
    }
    write_json(run_dir / "manifest-users.json", result)
    return result
