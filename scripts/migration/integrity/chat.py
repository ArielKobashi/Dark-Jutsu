from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.migration.domains.chat import deterministic_sample, inspect, load_raw
from scripts.migration.integrity.base import CheckResult
from scripts.migration.sql_client import MissingSqlDriver, connect
from scripts.migration.utils import sha256_file


DOMAIN = "chat"


def _raw_summary(raw_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_hash = sha256_file(raw_path)
    raw = load_raw(raw_path)
    return raw, inspect(raw, source_hash), deterministic_sample(raw, 50)


def check_raw(raw_path: Path) -> tuple[dict[str, Any], list[CheckResult]]:
    raw, summary, _sample = _raw_summary(raw_path)
    results: list[CheckResult] = []
    if not isinstance(raw.get("chatRooms"), dict):
        results.append(CheckResult(DOMAIN, "medium", "chatRooms", "type", "Mapa de salas ausente."))
    return summary, results


def _fetch_sql_summary(database_url: str) -> dict[str, Any]:
    with connect(database_url) as (_driver_name, _driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        counts: dict[str, Any] = {}
        for table, key in [
            ("chat_rooms", "chat_rooms"),
            ("chat_messages", "chat_messages"),
            ("chat_read_states", "chat_read_states"),
        ]:
            cur.execute(f"select count(*)::int from {table}")
            counts[key] = int(cur.fetchone()[0])
        cur.execute("select count(*)::int from chat_rooms where password_hash is not null")
        counts["password_rooms"] = int(cur.fetchone()[0])
        cur.execute("select count(*)::int from chat_rooms where raw_data ? 'senha' and raw_data->>'senha' <> '[redacted]'")
        counts["unredacted_room_passwords"] = int(cur.fetchone()[0])
        cur.execute("select room_id, legacy_key from chat_messages")
        counts["messages_by_key"] = {f"{row[0]}/{row[1]}" for row in cur.fetchall()}
    return counts


def check_sql(raw_path: Path, database_url: str) -> tuple[dict[str, Any], list[CheckResult]]:
    _raw, summary, sample = _raw_summary(raw_path)
    results = check_raw(raw_path)[1]
    try:
        sql = _fetch_sql_summary(database_url)
    except MissingSqlDriver as exc:
        results.append(CheckResult(DOMAIN, "critical", "sql", "driver", str(exc)))
        return summary, results
    except Exception as exc:
        results.append(CheckResult(DOMAIN, "critical", "sql", "connection", f"Falha ao consultar SQL: {exc}"))
        return summary, results

    for key in ("chat_rooms", "chat_messages", "chat_read_states", "password_rooms"):
        if summary[key] != sql[key]:
            results.append(CheckResult(DOMAIN, "critical", key, "count", "Total SQL diverge do raw.", summary[key], sql[key]))
    if sql["unredacted_room_passwords"]:
        results.append(
            CheckResult(DOMAIN, "critical", "chat_rooms", "raw_data.senha", "Senha de sala nao sanitizada no SQL.", 0, sql["unredacted_room_passwords"])
        )

    messages_by_key = sql.get("messages_by_key", set())
    for item in sample.get("messages", [])[:50]:
        key = f"{item.get('room_id')}/{item.get('legacy_key')}"
        if key not in messages_by_key:
            results.append(CheckResult(DOMAIN, "high", key, "legacy_key", "Mensagem da amostra ausente no SQL."))
    return summary | {"sql": {k: v for k, v in sql.items() if k != "messages_by_key"}}, results


def write_report(run_dir: Path, summary: dict[str, Any], results: list[CheckResult], mode: str) -> None:
    reports_dir = run_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    status = "ok" if not results else "failed"
    data = {
        "domain": DOMAIN,
        "mode": mode,
        "status": status,
        "summary": summary,
        "results": [item.to_dict() for item in results],
    }
    (reports_dir / "integrity-chat.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with (reports_dir / "integrity-chat-differences.jsonl").open("w", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
    md = [
        "# Chat integrity report",
        "",
        f"Mode: `{mode}`",
        f"Status: `{status}`",
        "",
        "## Totals",
        "",
        f"- Raw rooms: {summary.get('chat_rooms')}",
        f"- Raw messages: {summary.get('chat_messages')}",
        f"- Raw read states: {summary.get('chat_read_states')}",
        f"- Raw password rooms: {summary.get('password_rooms')}",
    ]
    if "sql" in summary:
        sql = summary["sql"]
        md.extend(
            [
                f"- SQL rooms: {sql.get('chat_rooms')}",
                f"- SQL messages: {sql.get('chat_messages')}",
                f"- SQL read states: {sql.get('chat_read_states')}",
                f"- SQL password rooms: {sql.get('password_rooms')}",
                f"- SQL unredacted room passwords: {sql.get('unredacted_room_passwords')}",
            ]
        )
    md.extend(["", "## Findings", ""])
    if not results:
        md.append("- No findings.")
    else:
        for item in results[:100]:
            md.append(f"- `{item.severity}` `{item.key}` `{item.field}`: {item.message}")
    (reports_dir / "integrity-chat.md").write_text("\n".join(md) + "\n", encoding="utf-8")
