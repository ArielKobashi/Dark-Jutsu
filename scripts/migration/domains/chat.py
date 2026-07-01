from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.migration.sql_client import connect, json_param
from scripts.migration.utils import ensure_dir, sha256_file, utc_now, write_json


DOMAIN = "chat"
LEGACY_GLOBAL_ROOM = "chatGlobal"
SECRET_KEYS = {"senha", "password"}


def load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo Firebase export nao encontrado: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return data


def _node(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    return value if isinstance(value, dict) else {}


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


def _parse_legacy_date(value: Any) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None
    for fmt in ("%d/%m/%Y, %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("[redacted]" if key in SECRET_KEYS else _sanitize(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _password_hash(room_id: str, password: Any) -> str | None:
    text = _clean_text(password)
    if not text:
        return None
    salt = hashlib.sha256(f"dark-jutsu:{room_id}".encode("utf-8")).hexdigest()[:16]
    digest = hashlib.pbkdf2_hmac("sha256", text.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()
    return f"pbkdf2_sha256$200000${salt}${digest}"


def _room_label(room_id: str) -> str:
    if room_id == "publica":
        return "Publica"
    if room_id == LEGACY_GLOBAL_ROOM:
        return "Chat global legado"
    return room_id.replace("_", " ").title()


def _iter_room_messages(raw: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    rows: list[tuple[str, str, dict[str, Any]]] = []
    for room_id, room in _node(raw, "chatRooms").items():
        if not isinstance(room, dict):
            continue
        messages = room.get("messages") if isinstance(room.get("messages"), dict) else {}
        for key, message in messages.items():
            if isinstance(message, dict):
                rows.append((str(room_id), str(key), message))
    for key, message in _node(raw, "chatGlobal").items():
        if isinstance(message, dict) and "texto" in message:
            rows.append((LEGACY_GLOBAL_ROOM, str(key), message))
    return rows


def _read_state_count(raw: dict[str, Any]) -> int:
    total = 0
    for rooms in _node(raw, "chatReadState").values():
        if isinstance(rooms, dict):
            total += len(rooms)
    return total


def inspect(raw: dict[str, Any], source_hash: str) -> dict[str, Any]:
    rooms = _node(raw, "chatRooms")
    current_messages = sum(
        len(room.get("messages") if isinstance(room, dict) and isinstance(room.get("messages"), dict) else {})
        for room in rooms.values()
    )
    legacy_messages = len([item for item in _node(raw, "chatGlobal").values() if isinstance(item, dict) and "texto" in item])
    password_rooms = len([room for room in rooms.values() if isinstance(room, dict) and _clean_text(room.get("senha"))])
    return {
        "domain": DOMAIN,
        "source_hash": source_hash,
        "chat_rooms": len(rooms) + (1 if legacy_messages else 0),
        "current_rooms": len(rooms),
        "password_rooms": password_rooms,
        "current_messages": current_messages,
        "legacy_global_messages": legacy_messages,
        "chat_messages": current_messages + legacy_messages,
        "chat_read_states": _read_state_count(raw),
    }


def deterministic_sample(raw: dict[str, Any], sample_size: int = 20) -> dict[str, Any]:
    messages = []
    for room_id, key, message in _iter_room_messages(raw)[:sample_size]:
        messages.append(
            {
                "room_id": room_id,
                "legacy_key": key,
                "name": message.get("nome"),
                "type": message.get("tipo"),
                "event": message.get("evento"),
                "timestamp": message.get("timestamp") or message.get("data"),
            }
        )
    return {"messages": messages}


def write_reports(run_dir: Path, inspection: dict[str, Any], sample: dict[str, Any], mode: str) -> None:
    reports_dir = ensure_dir(run_dir / "reports")
    write_json(reports_dir / "chat-summary.json", {"mode": mode, "inspection": inspection, "sample": sample})
    md = [
        "# Chat migration report",
        "",
        f"Mode: `{mode}`",
        f"Source hash: `{inspection['source_hash']}`",
        "",
        "## Totals",
        "",
        f"- Chat rooms: {inspection['chat_rooms']}",
        f"- Password rooms: {inspection['password_rooms']}",
        f"- Current messages: {inspection['current_messages']}",
        f"- Legacy global messages: {inspection['legacy_global_messages']}",
        f"- Chat messages: {inspection['chat_messages']}",
        f"- Read states: {inspection['chat_read_states']}",
        "",
        "## Sample messages",
        "",
    ]
    for item in sample.get("messages", [])[:20]:
        md.append(f"- `{item.get('room_id')}/{item.get('legacy_key')}` name={item.get('name')} type={item.get('type')}")
    (reports_dir / "chat-summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def apply_to_sql(raw: dict[str, Any], database_url: str) -> dict[str, int]:
    with connect(database_url) as (driver_name, driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        cur.execute("delete from chat_read_states")
        cur.execute("delete from chat_messages")
        cur.execute("delete from chat_rooms")

        room_sql = """
            insert into chat_rooms (id, label, public, password_hash, updated_at, raw_data)
            values (%s, %s, %s, %s, now(), %s::jsonb)
            on conflict (id) do update set
              label = excluded.label,
              public = excluded.public,
              password_hash = excluded.password_hash,
              updated_at = excluded.updated_at,
              raw_data = excluded.raw_data
        """
        rooms_loaded = 0
        for room_id, room in _node(raw, "chatRooms").items():
            if not isinstance(room, dict):
                continue
            cur.execute(
                room_sql,
                (
                    str(room_id),
                    _room_label(str(room_id)),
                    str(room_id) == "publica",
                    _password_hash(str(room_id), room.get("senha")),
                    json_param(driver_name, driver, _sanitize({k: v for k, v in room.items() if k != "messages"})),
                ),
            )
            rooms_loaded += 1
        if inspect(raw, "")["legacy_global_messages"]:
            cur.execute(
                room_sql,
                (
                    LEGACY_GLOBAL_ROOM,
                    _room_label(LEGACY_GLOBAL_ROOM),
                    True,
                    None,
                    json_param(driver_name, driver, {"source": "chatGlobal"}),
                ),
            )
            rooms_loaded += 1

        message_sql = """
            insert into chat_messages (
              legacy_key, room_id, user_id, name, text, time_label,
              created_at, message_type, event, session_id, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """
        messages_loaded = 0
        for room_id, key, message in _iter_room_messages(raw):
            cur.execute(
                message_sql,
                (
                    key,
                    room_id,
                    _clean_text(message.get("uid")),
                    _clean_text(message.get("nome")),
                    _clean_text(message.get("texto")),
                    _clean_text(message.get("data")),
                    _timestamp(message.get("timestamp")) or _parse_legacy_date(message.get("data")),
                    _clean_text(message.get("tipo")),
                    _clean_text(message.get("evento")),
                    _clean_text(message.get("sessionId")),
                    json_param(driver_name, driver, message),
                ),
            )
            messages_loaded += 1

        read_states_loaded = 0
        for uid, rooms in _node(raw, "chatReadState").items():
            if not isinstance(rooms, dict):
                continue
            for room_id, value in rooms.items():
                room_id = str(room_id)
                if room_id not in _node(raw, "chatRooms") and room_id != LEGACY_GLOBAL_ROOM:
                    continue
                cur.execute(
                    """
                    insert into chat_read_states (user_id, room_id, last_seen_at, raw_data)
                    values (%s, %s, %s, %s::jsonb)
                    on conflict (user_id, room_id) do update set
                      last_seen_at = excluded.last_seen_at,
                      raw_data = excluded.raw_data
                    """,
                    (
                        str(uid),
                        room_id,
                        _timestamp(value),
                        json_param(driver_name, driver, {"firebase_value": value}),
                    ),
                )
                read_states_loaded += 1

        return {
            "chat_rooms_loaded": rooms_loaded,
            "chat_messages_loaded": messages_loaded,
            "chat_read_states_loaded": read_states_loaded,
        }


def run(source: Path, run_dir: Path, mode: str, database_url: str = "", sample_size: int = 20) -> dict[str, Any]:
    raw_dir = ensure_dir(run_dir / "raw")
    source_hash = sha256_file(source)
    raw = load_raw(source)
    write_json(raw_dir / "chat-domain.json", _sanitize({
        "chatRooms": _node(raw, "chatRooms"),
        "chatReadState": _node(raw, "chatReadState"),
        "chatGlobal": _node(raw, "chatGlobal"),
    }))
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
    write_json(run_dir / "manifest-chat.json", result)
    return result
