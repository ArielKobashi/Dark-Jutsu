from __future__ import annotations

import base64
import json
import re
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = "postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


DATABASE_URL = _env("DATABASE_URL", DEFAULT_DATABASE_URL)
API_HOST = _env("DARK_JUTSU_API_HOST", "127.0.0.1")
API_PORT = int(_env("DARK_JUTSU_API_PORT", "8765"))
API_TOKEN = _env("DARK_JUTSU_API_TOKEN")


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _limit(query: dict[str, list[str]], default: int = 100, maximum: int = 1000) -> int:
    raw = query.get("limit", [str(default)])[0]
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(1, min(value, maximum))


def _offset(query: dict[str, list[str]]) -> int:
    raw = query.get("offset", ["0"])[0]
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_value(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except Exception:
        return default


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, int | float):
        raw = float(value)
        if raw > 100000000000:
            raw = raw / 1000
        return datetime.fromtimestamp(raw, timezone.utc)
    text = _clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _hidden_codes(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = ",".join(str(item) for item in value)
    else:
        raw = str(value or "")
    codes = []
    for part in raw.split(","):
        cleaned = re.sub(r"[^0-9A-Za-z_-]", "", part.strip())
        if cleaned:
            codes.append(cleaned)
    return list(dict.fromkeys(codes))


def _decode_legacy_key(value: str) -> str:
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8") or value
    except Exception:
        return value


def _connect():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Handler(BaseHTTPRequestHandler):
    server_version = "DarkJutsuSQL/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "authorization, content-type, x-api-token")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, PATCH, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        try:
            if not self._authorized():
                raise ApiError(HTTPStatus.UNAUTHORIZED, "Token da API ausente ou invalido.")
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
            payload = self._route(parts, query)
            self._send_json(payload)
        except ApiError as exc:
            self._send_json({"ok": False, "error": exc.message}, exc.status)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self) -> None:
        self._handle_write("PUT")

    def _handle_write(self, method: str) -> None:
        try:
            if not self._authorized():
                raise ApiError(HTTPStatus.UNAUTHORIZED, "Token da API ausente ou invalido.")
            parsed = urlparse(self.path)
            parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
            payload = self._read_json_body()
            result = self._write_route(method, parts, payload)
            self._send_json(result)
        except ApiError as exc:
            self._send_json({"ok": False, "error": exc.message}, exc.status)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _authorized(self) -> bool:
        if self.path.startswith("/health"):
            return True
        if not API_TOKEN:
            return True
        bearer = self.headers.get("Authorization", "")
        token = self.headers.get("X-API-Token", "")
        return bearer == f"Bearer {API_TOKEN}" or token == API_TOKEN

    def _route(self, parts: list[str], query: dict[str, list[str]]) -> Any:
        if parts == ["health"]:
            return self._health()
        if parts[:1] != ["api"]:
            raise ApiError(HTTPStatus.NOT_FOUND, "Endpoint nao encontrado.")
        if parts == ["api", "inventory"]:
            return self._inventory(query)
        if len(parts) == 3 and parts[:2] == ["api", "inventory"]:
            return self._inventory_item(parts[2])
        if parts == ["api", "users"]:
            return self._users(query)
        if parts == ["api", "signup-requests"]:
            return self._signup_requests(query)
        if parts == ["api", "banned-users"]:
            return self._banned_users(query)
        if parts == ["api", "dashboard"]:
            return self._dashboard()
        if parts == ["api", "counting", "sessions"]:
            return self._counting_sessions(query)
        if len(parts) == 5 and parts[:3] == ["api", "counting", "sessions"] and parts[4] == "items":
            return self._counting_items(parts[3], query)
        if parts == ["api", "counting", "drafts"]:
            return self._counting_drafts(query)
        if parts == ["api", "counting", "machine-status"]:
            return self._counting_machine_status(query)
        if parts == ["api", "labels", "jobs"]:
            return self._label_jobs(query)
        if len(parts) == 3 and parts[:2] == ["api", "settings"]:
            return self._setting(parts[2])
        if len(parts) == 4 and parts[:3] == ["api", "cooperat", "history"]:
            return self._cooperat_history(parts[3], query)
        if parts == ["api", "occurrences"]:
            return self._occurrences(query)
        if parts == ["api", "chat", "rooms"]:
            return self._chat_rooms()
        if len(parts) == 5 and parts[:3] == ["api", "chat", "rooms"] and parts[4] == "messages":
            return self._chat_messages(parts[3], query)
        if len(parts) == 4 and parts[:3] == ["api", "automus", "releases"]:
            return self._automus_release(parts[3])
        raise ApiError(HTTPStatus.NOT_FOUND, "Endpoint nao encontrado.")

    def _write_route(self, method: str, parts: list[str], payload: dict[str, Any]) -> Any:
        if method == "PUT" and len(parts) == 4 and parts[:3] == ["api", "dashboard", "panels"]:
            return self._put_dashboard_panel(parts[3], payload)
        if method == "PUT" and len(parts) == 4 and parts[:3] == ["api", "dashboard", "evaluations"]:
            return self._put_dashboard_evaluation(parts[3], payload)
        raise ApiError(HTTPStatus.NOT_FOUND, "Endpoint de escrita nao encontrado.")

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "JSON invalido.") from exc
        if not isinstance(payload, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "O corpo da requisicao deve ser um objeto JSON.")
        return payload

    def _query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("set local app.role = 'service'")
                cur.execute(sql, params)
                return list(cur.fetchall())

    def _execute_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("set local app.role = 'service'")
                cur.execute(sql, params)
                row = cur.fetchone()
                if row is None:
                    return {}
                return dict(row)

    def _health(self) -> dict[str, Any]:
        rows = self._query("select now() as database_time")
        return {"ok": True, "database_time": rows[0]["database_time"], "database_url": "configured"}

    def _inventory(self, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 100, 500)
        offset = _offset(query)
        search = (query.get("q", [""])[0] or "").strip()
        where = "where not is_dead"
        params: list[Any] = []
        if search:
            where += " and (protheus_code ilike %s or cooperat_code ilike %s or description ilike %s)"
            like = f"%{search}%"
            params.extend([like, like, like])
        rows = self._query(
            f"""
            select id, legacy_key, protheus_code, cooperat_code, description,
                   primary_address, primary_warehouse, balance, min_qty, max_qty,
                   reorder_qty, limit_source, is_dead, updated_at
            from inventory_items
            {where}
            order by description nulls last, protheus_code nulls last
            limit %s offset %s
            """,
            (*params, limit, offset),
        )
        return {"items": rows, "limit": limit, "offset": offset}

    def _inventory_item(self, code: str) -> dict[str, Any]:
        rows = self._query(
            """
            select *
            from inventory_items
            where protheus_code = %s or cooperat_code = %s or legacy_key = %s
            order by is_dead asc
            limit 1
            """,
            (code, code, code),
        )
        if not rows:
            raise ApiError(HTTPStatus.NOT_FOUND, "Item nao encontrado.")
        addresses = self._query(
            """
            select address, warehouse, balance, source
            from inventory_item_addresses
            where item_id = %s
            order by warehouse nulls last, address nulls last
            """,
            (rows[0]["id"],),
        )
        limits = self._query(
            """
            select source, min_qty, max_qty, reorder_qty, previous_balance, applied, imported_at
            from inventory_item_limits
            where item_id = %s
            order by applied desc, imported_at desc
            """,
            (rows[0]["id"],),
        )
        return {"item": rows[0], "addresses": addresses, "limits": limits}

    def _users(self, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 100, 500)
        offset = _offset(query)
        rows = self._query(
            """
            select id, firebase_uid, nickname, nickname_key, badge, sector, role,
                   active, password_status, created_at, updated_at
            from users
            order by nickname nulls last
            limit %s offset %s
            """,
            (limit, offset),
        )
        return {"users": rows, "limit": limit, "offset": offset}

    def _signup_requests(self, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 100, 500)
        rows = self._query(
            """
            select id, requested_uid, nickname, nickname_key, badge, sector,
                   status, duplicated, created_at, decided_at, decided_by
            from signup_requests
            order by created_at desc nulls last, id
            limit %s
            """,
            (limit,),
        )
        return {"signup_requests": rows, "limit": limit}

    def _banned_users(self, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 100, 500)
        rows = self._query(
            """
            select user_id, nickname, badge, sector, banned_at, banned_by, reason
            from banned_users
            order by banned_at desc nulls last, nickname nulls last
            limit %s
            """,
            (limit,),
        )
        return {"banned_users": rows, "limit": limit}

    def _dashboard(self) -> dict[str, Any]:
        panels = self._query("select * from dashboard_panels order by id")
        evaluations = self._query("select * from purchase_evaluations order by updated_at desc nulls last, id desc limit 500")
        return {"panels": panels, "purchase_evaluations": evaluations}

    def _put_dashboard_panel(self, panel_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row_limit = _int_value(payload.get("limite", payload.get("row_limit")), 8)
        hidden_codes = _hidden_codes(payload.get("codigosOcultos", payload.get("hidden_codes")))
        updated_by = _clean_text(payload.get("updatedBy") or payload.get("atualizadoPor"))
        raw_data = {
            "limite": row_limit,
            "codigosOcultos": ",".join(hidden_codes),
            **{k: v for k, v in payload.items() if k not in {"limite", "row_limit", "codigosOcultos", "hidden_codes"}},
        }
        row = self._execute_one(
            """
            insert into dashboard_panels (id, title, row_limit, hidden_codes, updated_at, updated_by, raw_data)
            values (%s, %s, %s, %s, now(), %s, %s::jsonb)
            on conflict (id) do update set
              row_limit = excluded.row_limit,
              hidden_codes = excluded.hidden_codes,
              updated_at = excluded.updated_at,
              updated_by = excluded.updated_by,
              raw_data = excluded.raw_data
            returning *
            """,
            (
                panel_id,
                panel_id.replace("_", " ").title(),
                row_limit,
                hidden_codes,
                self._existing_user_id(updated_by),
                json.dumps(raw_data, ensure_ascii=False),
            ),
        )
        return {"ok": True, "panel": row}

    def _put_dashboard_evaluation(self, legacy_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        item_code = _clean_text(payload.get("codigo") or payload.get("item_code")) or _decode_legacy_key(legacy_key)
        evaluated_at = _timestamp(payload.get("avaliadoEm") or payload.get("evaluated_at"))
        updated_at = _timestamp(payload.get("atualizadoEm") or payload.get("updated_at")) or evaluated_at or datetime.now(timezone.utc)
        row = self._execute_one(
            """
            insert into purchase_evaluations (
              legacy_key, item_id, item_code, decision, kanban_status, note,
              evaluated_at, evaluated_by, updated_at, updated_by, raw_data
            )
            values (
              %s,
              (select id from inventory_items where protheus_code = %s order by is_dead asc limit 1),
              %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
            )
            on conflict (legacy_key) do update set
              item_id = excluded.item_id,
              item_code = excluded.item_code,
              decision = excluded.decision,
              kanban_status = excluded.kanban_status,
              note = excluded.note,
              evaluated_at = excluded.evaluated_at,
              evaluated_by = excluded.evaluated_by,
              updated_at = excluded.updated_at,
              updated_by = excluded.updated_by,
              raw_data = excluded.raw_data
            returning *
            """,
            (
                legacy_key,
                item_code,
                item_code,
                _clean_text(payload.get("decisao") or payload.get("decision")) or "indefinido",
                _clean_text(payload.get("statusManual") or payload.get("kanban_status")),
                _clean_text(payload.get("observacao") or payload.get("note")),
                evaluated_at,
                _clean_text(payload.get("avaliadoPor") or payload.get("evaluated_by")),
                updated_at,
                self._existing_user_id(_clean_text(payload.get("atualizadoPor") or payload.get("updated_by"))),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        return {"ok": True, "evaluation": row}

    def _existing_user_id(self, value: str | None) -> str | None:
        if not value:
            return None
        rows = self._query("select id from users where id = %s limit 1", (value,))
        return rows[0]["id"] if rows else None

    def _counting_sessions(self, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 100, 500)
        rows = self._query(
            """
            select id, legacy_path, session_date, user_id, user_name, uid, machine,
                   started_at, created_at, total_items, total_quantity_items,
                   total_empty_checks, is_draft, source
            from counting_sessions
            order by session_date desc nulls last, created_at desc nulls last
            limit %s
            """,
            (limit,),
        )
        return {"sessions": rows, "limit": limit}

    def _counting_items(self, session_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 500, 2000)
        rows = self._query(
            """
            select id, session_id, item_id, item_legacy_key, protheus_code,
                   cooperat_code, description, warehouse, address, system_balance,
                   reorder_qty, counted_qty, diverges
            from counting_items
            where session_id = %s
            order by description nulls last, protheus_code nulls last
            limit %s
            """,
            (session_id, limit),
        )
        return {"items": rows, "limit": limit}

    def _counting_drafts(self, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 100, 500)
        rows = self._query(
            """
            select id, user_id, uid, user_name, cycle, machine, updated_at,
                   values_json, empty_checks_json, system_balances_json, session_json
            from counting_drafts
            order by updated_at desc nulls last
            limit %s
            """,
            (limit,),
        )
        return {"drafts": rows, "limit": limit}

    def _counting_machine_status(self, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 200, 1000)
        rows = self._query(
            """
            select cycle, machine_key, user_key, user_id, user_name, open, stage,
                   group_name, machine_label, counted, total, completed,
                   item_key, item_index, updated_at
            from counting_machine_status
            order by updated_at desc nulls last
            limit %s
            """,
            (limit,),
        )
        return {"machine_status": rows, "limit": limit}

    def _label_jobs(self, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 100, 500)
        rows = self._query(
            """
            select id, legacy_path, user_id, user_name, job_date, created_at,
                   total_labels, total_codes_submitted, by_size,
                   had_missing_codes, source
            from label_print_jobs
            order by created_at desc nulls last
            limit %s
            """,
            (limit,),
        )
        return {"jobs": rows, "limit": limit}

    def _setting(self, key: str) -> dict[str, Any]:
        rows = self._query(
            "select key, value, updated_at, updated_by from app_settings where key = %s",
            (key,),
        )
        if not rows:
            raise ApiError(HTTPStatus.NOT_FOUND, "Configuracao nao encontrada.")
        return {"setting": rows[0]}

    def _cooperat_history(self, code: str, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 200, 1000)
        codes = self._query("select * from cooperat_purchase_codes where code = %s", (code,))
        events = self._query(
            """
            select *
            from cooperat_purchase_events
            where code = %s
            order by event_date desc nulls last, id desc
            limit %s
            """,
            (code, limit),
        )
        return {"code": codes[0] if codes else None, "events": events, "limit": limit}

    def _occurrences(self, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 100, 500)
        rows = self._query("select * from occurrences order by created_at desc nulls last limit %s", (limit,))
        return {"occurrences": rows, "limit": limit}

    def _chat_rooms(self) -> dict[str, Any]:
        rows = self._query("select id, label, public, updated_at from chat_rooms order by public desc, id")
        return {"rooms": rows}

    def _chat_messages(self, room_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 100, 500)
        rows = self._query(
            """
            select id, legacy_key, room_id, user_id, name, text, time_label,
                   created_at, message_type, event, session_id
            from chat_messages
            where room_id = %s
            order by created_at desc nulls last, id desc
            limit %s
            """,
            (room_id, limit),
        )
        return {"messages": rows, "limit": limit}

    def _automus_release(self, channel: str) -> dict[str, Any]:
        rows = self._query(
            """
            select channel, version, package_url, notes, published_at, published_by, raw_manifest
            from automus_releases
            where channel = %s
            order by published_at desc, id desc
            limit 1
            """,
            (channel,),
        )
        if not rows:
            raise ApiError(HTTPStatus.NOT_FOUND, "Release nao encontrada.")
        return {"release": rows[0]}


def main() -> int:
    server = ThreadingHTTPServer((API_HOST, API_PORT), Handler)
    print(f"Dark-Jutsu SQL API em http://{API_HOST}:{API_PORT}")
    print(f"Banco: {DATABASE_URL}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Encerrando API...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
