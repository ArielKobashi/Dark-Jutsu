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


def _decimal_value(value: Any) -> Decimal | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except Exception:
        return None


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
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, PATCH, DELETE, OPTIONS")
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

    def do_POST(self) -> None:
        self._handle_write("POST")

    def do_PATCH(self) -> None:
        self._handle_write("PATCH")

    def do_DELETE(self) -> None:
        self._handle_write("DELETE")

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
        if method == "POST" and parts == ["api", "occurrences"]:
            return self._post_occurrence(payload)
        if method == "PATCH" and len(parts) == 3 and parts[:2] == ["api", "occurrences"]:
            return self._patch_occurrence(parts[2], payload)
        if method == "POST" and len(parts) == 5 and parts[:3] == ["api", "chat", "rooms"] and parts[4] == "messages":
            return self._post_chat_message(parts[3], payload)
        if method in {"PUT", "PATCH"} and parts == ["api", "chat", "read-state"]:
            return self._put_chat_read_state(payload)
        if method == "POST" and parts == ["api", "labels", "jobs"]:
            return self._post_label_job(payload)
        if method == "POST" and parts == ["api", "counting", "sessions"]:
            return self._post_counting_session(payload)
        if method in {"PUT", "POST", "PATCH"} and parts == ["api", "counting", "drafts"]:
            return self._put_counting_draft(payload)
        if method == "DELETE" and len(parts) == 4 and parts[:3] == ["api", "counting", "drafts"]:
            return self._delete_counting_draft(parts[3])
        if method in {"PUT", "POST", "PATCH"} and parts == ["api", "counting", "machine-status"]:
            return self._put_counting_machine_status(payload)
        if method == "POST" and parts == ["api", "counting", "reset"]:
            return self._post_counting_reset(payload)
        if method in {"PUT", "PATCH"} and len(parts) == 3 and parts[:2] == ["api", "settings"]:
            return self._put_setting(parts[2], payload)
        if method in {"POST", "PUT"} and len(parts) == 4 and parts[:3] == ["api", "automus", "releases"]:
            return self._put_automus_release(parts[3], payload)
        if method == "PATCH" and len(parts) == 3 and parts[:2] == ["api", "users"]:
            return self._patch_user(parts[2], payload)
        if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "users"] and parts[3] == "ban":
            return self._ban_user(parts[2], payload)
        if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "users"] and parts[3] == "reset-password":
            return self._reset_user_password(parts[2], payload)
        if method == "DELETE" and len(parts) == 3 and parts[:2] == ["api", "banned-users"]:
            return self._delete_banned_user(parts[2])
        if method == "PATCH" and len(parts) == 3 and parts[:2] == ["api", "signup-requests"]:
            return self._patch_signup_request(parts[2], payload)
        if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "signup-requests"] and parts[3] == "approve":
            return self._approve_signup_request(parts[2], payload)
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

    def _patch_user(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        existing = self._query("select raw_data from users where id = %s", (user_id,))
        if not existing:
            raise ApiError(HTTPStatus.NOT_FOUND, "Usuario nao encontrado.")
        raw_data = existing[0].get("raw_data") if isinstance(existing[0].get("raw_data"), dict) else {}
        raw_data = {**raw_data, **payload}
        row = self._execute_one(
            """
            update users
            set role = coalesce(%s, role),
                active = coalesce(%s, active),
                password_status = coalesce(%s, password_status),
                sector = coalesce(%s, sector),
                badge = coalesce(%s, badge),
                raw_data = %s::jsonb
            where id = %s
            returning id, firebase_uid, nickname, badge, sector, role,
                      active, password_status, created_at, updated_at
            """,
            (
                _clean_text(payload.get("role") or payload.get("nivel")),
                payload.get("active") if isinstance(payload.get("active"), bool) else payload.get("ativo") if isinstance(payload.get("ativo"), bool) else None,
                _clean_text(payload.get("password_status") or payload.get("senha")),
                _clean_text(payload.get("sector") or payload.get("setor")),
                _clean_text(payload.get("badge") or payload.get("cracha")),
                json.dumps(raw_data, ensure_ascii=False),
                user_id,
            ),
        )
        return {"ok": True, "user": row}

    def _ban_user(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        rows = self._query("select * from users where id = %s", (user_id,))
        if not rows:
            raise ApiError(HTTPStatus.NOT_FOUND, "Usuario nao encontrado.")
        user = rows[0]
        banned_at = _timestamp(payload.get("banned_at") or payload.get("banidoEm")) or datetime.now(timezone.utc)
        reason = _clean_text(payload.get("reason") or payload.get("motivo"))
        banned_by = self._existing_user_id(_clean_text(payload.get("banned_by") or payload.get("banidoPor")))
        raw_data = user.get("raw_data") if isinstance(user.get("raw_data"), dict) else {}
        raw_data = {**raw_data, "status": "banido", "banidoEm": payload.get("banidoEm") or int(banned_at.timestamp() * 1000), **payload}
        row = self._execute_one(
            """
            insert into banned_users (user_id, nickname, badge, sector, banned_at, banned_by, reason, raw_data)
            values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (user_id) do update set
              nickname = excluded.nickname,
              badge = excluded.badge,
              sector = excluded.sector,
              banned_at = excluded.banned_at,
              banned_by = excluded.banned_by,
              reason = excluded.reason,
              raw_data = excluded.raw_data
            returning user_id, nickname, badge, sector, banned_at, banned_by, reason
            """,
            (
                user_id,
                user.get("nickname"),
                user.get("badge"),
                user.get("sector"),
                banned_at,
                banned_by,
                reason,
                json.dumps(raw_data, ensure_ascii=False),
            ),
        )
        self._execute_one(
            """
            update users
            set active = false,
                raw_data = raw_data || %s::jsonb
            where id = %s
            returning id
            """,
            (json.dumps({"ativo": False, "status": "banido"}, ensure_ascii=False), user_id),
        )
        return {"ok": True, "banned_user": row}

    def _reset_user_password(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = self._execute_one(
            """
            update users
            set password_status = 'reset_required',
                raw_data = raw_data || %s::jsonb
            where id = %s
            returning id, nickname, role, active, password_status
            """,
            (json.dumps({"senha": "", "senhaReset": True, **payload}, ensure_ascii=False), user_id),
        )
        if not row:
            raise ApiError(HTTPStatus.NOT_FOUND, "Usuario nao encontrado.")
        return {"ok": True, "user": row}

    def _delete_banned_user(self, user_id: str) -> dict[str, Any]:
        row = self._execute_one(
            "delete from banned_users where user_id = %s returning user_id",
            (user_id,),
        )
        return {"ok": True, "deleted": bool(row), "user_id": user_id}

    def _patch_signup_request(self, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        status = _clean_text(payload.get("status"))
        decided_by = self._existing_user_id(_clean_text(payload.get("decided_by") or payload.get("decididoPor")))
        decided_at = _timestamp(payload.get("decided_at") or payload.get("decididoEm")) or datetime.now(timezone.utc)
        raw_merge = {**payload}
        row = self._execute_one(
            """
            update signup_requests
            set status = coalesce(%s, status),
                decided_at = %s,
                decided_by = %s,
                raw_data = raw_data || %s::jsonb
            where id = %s
            returning id, requested_uid, nickname, badge, sector, status,
                      duplicated, created_at, decided_at, decided_by
            """,
            (
                status,
                decided_at,
                decided_by,
                json.dumps(raw_merge, ensure_ascii=False),
                request_id,
            ),
        )
        if not row:
            raise ApiError(HTTPStatus.NOT_FOUND, "Solicitacao nao encontrada.")
        return {"ok": True, "signup_request": row}

    def _approve_signup_request(self, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        rows = self._query("select * from signup_requests where id = %s", (request_id,))
        if not rows:
            raise ApiError(HTTPStatus.NOT_FOUND, "Solicitacao nao encontrada.")
        req = rows[0]
        user_id = _clean_text(payload.get("uid") or payload.get("user_id") or req.get("requested_uid"))
        if not user_id:
            raise ApiError(HTTPStatus.BAD_REQUEST, "`uid` e obrigatorio para aprovar no SQL.")
        role = _clean_text(payload.get("role") or payload.get("nivel")) or "op"
        now = datetime.now(timezone.utc)
        raw_data = req.get("raw_data") if isinstance(req.get("raw_data"), dict) else {}
        raw_data = {**raw_data, "status": "aprovado", "nivel": role, **payload}
        user = self._execute_one(
            """
            insert into users (
              id, firebase_uid, nickname, badge, sector, role, active,
              password_status, created_at, updated_at, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, true, %s, %s, %s, %s::jsonb)
            on conflict (id) do update set
              nickname = excluded.nickname,
              badge = excluded.badge,
              sector = excluded.sector,
              role = excluded.role,
              active = true,
              password_status = excluded.password_status,
              updated_at = excluded.updated_at,
              raw_data = excluded.raw_data
            returning id, firebase_uid, nickname, badge, sector, role, active, password_status
            """,
            (
                user_id,
                user_id,
                req.get("nickname"),
                req.get("badge"),
                req.get("sector"),
                role,
                "definida",
                now,
                now,
                json.dumps(raw_data, ensure_ascii=False),
            ),
        )
        signup = self._patch_signup_request(request_id, {"status": "aprovado", "decididoEm": int(now.timestamp() * 1000)})
        return {"ok": True, "user": user, "signup_request": signup["signup_request"]}

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

    def _post_counting_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_name = _clean_text(payload.get("usuario") or payload.get("user_name")) or "desconhecido"
        uid = _clean_text(payload.get("uid"))
        session_date = _clean_text(payload.get("data") or payload.get("session_date")) or datetime.now(timezone.utc).date().isoformat()
        created_at = _timestamp(payload.get("timestamp") or payload.get("created_at")) or datetime.now(timezone.utc)
        legacy_key = _clean_text(payload.get("legacy_key") or payload.get("_key")) or f"api_{int(created_at.timestamp() * 1000)}"
        user_key = re.sub(r"[^a-z0-9_-]+", "_", user_name.lower()).strip("_") or "desconhecido"
        legacy_path = _clean_text(payload.get("legacy_path")) or f"api:contagens/{session_date}/{user_key}/{legacy_key}"
        items = payload.get("itens") if isinstance(payload.get("itens"), dict) else {}
        empty_checks = payload.get("verificacoesVazio") if isinstance(payload.get("verificacoesVazio"), dict) else {}
        total_items = len(items)
        total_empty = len(empty_checks)
        user_id = self._existing_user_id(uid)

        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("set local app.role = 'service'")
                cur.execute(
                    """
                    insert into counting_sessions (
                      legacy_path, session_date, user_id, user_name, uid, machine,
                      started_at, created_at, total_items, total_quantity_items,
                      total_empty_checks, is_draft, source, raw_data
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false, %s, %s::jsonb)
                    on conflict (legacy_path) do update set
                      session_date = excluded.session_date,
                      user_id = excluded.user_id,
                      user_name = excluded.user_name,
                      uid = excluded.uid,
                      machine = excluded.machine,
                      created_at = excluded.created_at,
                      total_items = excluded.total_items,
                      total_quantity_items = excluded.total_quantity_items,
                      total_empty_checks = excluded.total_empty_checks,
                      raw_data = excluded.raw_data
                    returning id, legacy_path, session_date, user_id, user_name, uid, machine,
                              created_at, total_items, total_empty_checks
                    """,
                    (
                        legacy_path,
                        session_date,
                        user_id,
                        user_name,
                        uid,
                        _clean_text(payload.get("maquina") or payload.get("machine")),
                        created_at,
                        created_at,
                        total_items + total_empty,
                        total_items,
                        total_empty,
                        "api:counting",
                        json.dumps(payload, ensure_ascii=False),
                    ),
                )
                session = dict(cur.fetchone())
                session_id = session["id"]
                cur.execute("delete from counting_items where session_id = %s", (session_id,))
                cur.execute("delete from counting_empty_checks where session_id = %s", (session_id,))
                for key, item in items.items():
                    if not isinstance(item, dict):
                        continue
                    counted = _decimal_value(item.get("contado"))
                    system_balance = _decimal_value(item.get("saldoSistema"))
                    diverges = counted is not None and system_balance is not None and counted != system_balance
                    cur.execute(
                        """
                        insert into counting_items (
                          session_id, item_id, item_legacy_key, protheus_code, cooperat_code,
                          description, warehouse, address, system_balance, reorder_qty,
                          counted_qty, diverges, raw_data
                        )
                        values (
                          %s,
                          (select id from inventory_items where protheus_code = %s order by is_dead asc limit 1),
                          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                        )
                        """,
                        (
                            session_id,
                            _clean_text(item.get("protheus")),
                            _clean_text(key),
                            _clean_text(item.get("protheus")),
                            _clean_text(item.get("cooperat")),
                            _clean_text(item.get("descricao")),
                            _clean_text(item.get("armazem")),
                            _clean_text(item.get("endereco")),
                            system_balance,
                            _decimal_value(item.get("reposicao")),
                            counted,
                            diverges,
                            json.dumps(item, ensure_ascii=False),
                        ),
                    )
                for _key, check in empty_checks.items():
                    if not isinstance(check, dict):
                        continue
                    cur.execute(
                        """
                        insert into counting_empty_checks (
                          session_id, address, warehouse, status, machine, section,
                          shelf, box, description, raw_data
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (
                            session_id,
                            _clean_text(check.get("endereco")),
                            _clean_text(check.get("armazem")),
                            _clean_text(check.get("status")),
                            _clean_text(check.get("maquina")),
                            _clean_text(check.get("secao")),
                            _clean_text(check.get("prateleira")),
                            _clean_text(check.get("caixa")),
                            _clean_text(check.get("descricao")),
                            json.dumps(check, ensure_ascii=False),
                        ),
                    )
        return {"ok": True, "session": session}

    def _put_counting_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        uid = _clean_text(payload.get("uid")) or _clean_text(payload.get("user_id"))
        if not uid:
            raise ApiError(HTTPStatus.BAD_REQUEST, "`uid` e obrigatorio para salvar rascunho.")
        cycle = _clean_text(payload.get("cycle") or payload.get("ciclo")) or "atual"
        user_name = _clean_text(payload.get("usuario") or payload.get("user_name")) or "desconhecido"
        session_json = payload.get("sessao") if isinstance(payload.get("sessao"), dict) else {}
        machine = _clean_text(payload.get("maquina") or session_json.get("maquina"))
        user_id = self._existing_user_id(uid)
        updated_at = _timestamp(payload.get("updatedAt") or payload.get("updated_at")) or datetime.now(timezone.utc)
        values_json = json.dumps(payload.get("valores") if isinstance(payload.get("valores"), dict) else {}, ensure_ascii=False)
        empty_checks_json = json.dumps(payload.get("verificacoesVazio") if isinstance(payload.get("verificacoesVazio"), dict) else {}, ensure_ascii=False)
        system_balances_json = json.dumps(payload.get("saldosSistema") if isinstance(payload.get("saldosSistema"), dict) else {}, ensure_ascii=False)
        session_dump = json.dumps(session_json, ensure_ascii=False)
        raw_dump = json.dumps(payload, ensure_ascii=False)
        row = self._execute_one(
            """
            update counting_drafts
            set user_id = %s,
                user_name = %s,
                machine = %s,
                updated_at = %s,
                values_json = %s::jsonb,
                empty_checks_json = %s::jsonb,
                system_balances_json = %s::jsonb,
                session_json = %s::jsonb,
                raw_data = %s::jsonb
            where uid = %s and cycle = %s
            returning id, uid, user_name, cycle, machine, updated_at
            """,
            (
                user_id,
                user_name,
                machine,
                updated_at,
                values_json,
                empty_checks_json,
                system_balances_json,
                session_dump,
                raw_dump,
                uid,
                cycle,
            ),
        )
        if not row:
            row = self._execute_one(
                """
                insert into counting_drafts (
                  user_id, uid, user_name, cycle, machine, updated_at,
                  values_json, empty_checks_json, system_balances_json, session_json, raw_data
                )
                values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
                returning id, uid, user_name, cycle, machine, updated_at
                """,
                (
                    user_id,
                    uid,
                    user_name,
                    cycle,
                    machine,
                    updated_at,
                    values_json,
                    empty_checks_json,
                    system_balances_json,
                    session_dump,
                    raw_dump,
                ),
            )
        return {"ok": True, "draft": row}

    def _delete_counting_draft(self, uid: str) -> dict[str, Any]:
        row = self._execute_one(
            "delete from counting_drafts where uid = %s returning uid",
            (uid,),
        )
        return {"ok": True, "deleted": bool(row), "uid": uid}

    def _put_counting_machine_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        cycle = _clean_text(payload.get("cycle") or payload.get("ciclo")) or "atual"
        user_key = _clean_text(payload.get("user_key") or payload.get("usuarioKey") or payload.get("usuario")) or "desconhecido"
        group_name = _clean_text(payload.get("grupo") or payload.get("group_name") or payload.get("machine")) or "geral"
        machine_key = _clean_text(payload.get("machine_key") or re.sub(r"[^a-z0-9_-]+", "_", group_name.lower()).strip("_")) or "geral"
        row = self._execute_one(
            """
            insert into counting_machine_status (
              cycle, machine_key, user_key, user_id, user_name, open, stage, group_name,
              machine_label, counted, total, completed, item_key, item_index, updated_at, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (cycle, machine_key, user_key) do update set
              user_id = excluded.user_id,
              user_name = excluded.user_name,
              open = excluded.open,
              stage = excluded.stage,
              group_name = excluded.group_name,
              machine_label = excluded.machine_label,
              counted = excluded.counted,
              total = excluded.total,
              completed = excluded.completed,
              item_key = excluded.item_key,
              item_index = excluded.item_index,
              updated_at = excluded.updated_at,
              raw_data = excluded.raw_data
            returning cycle, machine_key, user_key, user_name, open, counted, total, completed, updated_at
            """,
            (
                cycle,
                machine_key,
                user_key,
                self._existing_user_id(_clean_text(payload.get("uid") or payload.get("user_id"))),
                _clean_text(payload.get("usuario") or payload.get("user_name")),
                bool(payload.get("aberta", payload.get("open", True))),
                _clean_text(payload.get("etapa") or payload.get("stage")),
                group_name,
                _clean_text(payload.get("maquinaLabel") or payload.get("machine_label")),
                _int_value(payload.get("contados") or payload.get("counted"), 0),
                _int_value(payload.get("total"), 0),
                bool(payload.get("concluida") or payload.get("completed")),
                _clean_text(payload.get("itemKey") or payload.get("item_key")),
                _int_value(payload.get("indice") or payload.get("item_index"), 0),
                _timestamp(payload.get("updatedAt") or payload.get("updated_at")) or datetime.now(timezone.utc),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        return {"ok": True, "machine_status": row}

    def _post_counting_reset(self, payload: dict[str, Any]) -> dict[str, Any]:
        reset_info = {**payload, "resetAt": payload.get("resetAt") or int(datetime.now(timezone.utc).timestamp() * 1000)}
        setting = self._put_setting("counting.resetGlobal", {"value": reset_info, "updated_by": payload.get("uid")})
        self._execute_one("delete from counting_machine_status returning id")
        return {"ok": True, "reset": setting["setting"]}

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

    def _post_label_job(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_name = _clean_text(payload.get("usuario") or payload.get("user_name")) or "desconhecido"
        job_date = _clean_text(payload.get("data") or payload.get("job_date")) or datetime.now(timezone.utc).date().isoformat()
        created_at = _timestamp(payload.get("timestamp") or payload.get("created_at")) or datetime.now(timezone.utc)
        legacy_key = _clean_text(payload.get("legacy_key") or payload.get("_key"))
        if not legacy_key:
            legacy_key = f"api_{int(created_at.timestamp() * 1000)}"
        user_key = re.sub(r"[^a-z0-9_-]+", "_", user_name.lower()).strip("_") or "desconhecido"
        legacy_path = _clean_text(payload.get("legacy_path")) or f"api:labels/{job_date}/{user_key}/{legacy_key}"
        by_size = payload.get("porTamanho") or payload.get("by_size") or {}
        if not isinstance(by_size, dict):
            by_size = {}
        row = self._execute_one(
            """
            insert into label_print_jobs (
              legacy_path, user_id, user_name, job_date, created_at, total_labels,
              total_codes_submitted, by_size, had_missing_codes, source, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
            returning id, legacy_path, user_id, user_name, job_date, created_at,
                      total_labels, total_codes_submitted, by_size, had_missing_codes, source
            """,
            (
                legacy_path,
                self._existing_user_id(_clean_text(payload.get("uid") or payload.get("user_id"))),
                user_name,
                job_date,
                created_at,
                _int_value(payload.get("totalEtiquetas") or payload.get("total_labels"), 0),
                _int_value(payload.get("totalCodigosInformados") or payload.get("total_codes_submitted"), 0),
                json.dumps(by_size, ensure_ascii=False),
                bool(payload.get("teveNaoEncontrados") or payload.get("had_missing_codes")),
                "api:labels",
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        return {"ok": True, "job": row}

    def _setting(self, key: str) -> dict[str, Any]:
        rows = self._query(
            "select key, value, updated_at, updated_by from app_settings where key = %s",
            (key,),
        )
        if not rows:
            raise ApiError(HTTPStatus.NOT_FOUND, "Configuracao nao encontrada.")
        return {"setting": rows[0]}

    def _put_setting(self, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        value = payload.get("value", payload)
        updated_by = self._existing_user_id(_clean_text(payload.get("updated_by") or payload.get("atualizadoPorUid")))
        row = self._execute_one(
            """
            insert into app_settings (key, value, updated_by, raw_data)
            values (%s, %s::jsonb, %s, %s::jsonb)
            on conflict (key) do update set
              value = excluded.value,
              updated_by = excluded.updated_by,
              raw_data = excluded.raw_data
            returning key, value, updated_at, updated_by
            """,
            (
                key,
                json.dumps(value, ensure_ascii=False),
                updated_by,
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        return {"ok": True, "setting": row}

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

    def _post_occurrence(self, payload: dict[str, Any]) -> dict[str, Any]:
        occurrence_id = _clean_text(payload.get("id"))
        if not occurrence_id:
            created_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            suffix = (_clean_text(payload.get("operadorUid")) or "api")[:6]
            occurrence_id = f"ocorrencia_{created_ms}_{suffix}"
            payload = {**payload, "id": occurrence_id, "criadoEm": payload.get("criadoEm") or created_ms}
        row = self._upsert_occurrence(occurrence_id, payload, source_path=f"api/occurrences/{occurrence_id}")
        self._insert_occurrence_history_from_payload(occurrence_id, payload)
        return {"ok": True, "occurrence": row}

    def _patch_occurrence(self, occurrence_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        existing_rows = self._query("select raw_data from occurrences where id = %s", (occurrence_id,))
        if not existing_rows:
            raise ApiError(HTTPStatus.NOT_FOUND, "Ocorrencia nao encontrada.")
        raw_data = existing_rows[0].get("raw_data") if isinstance(existing_rows[0].get("raw_data"), dict) else {}
        merged = self._merge_firebase_patch(raw_data, payload)
        merged["id"] = occurrence_id
        row = self._upsert_occurrence(occurrence_id, merged, source_path=f"api/occurrences/{occurrence_id}")
        self._insert_occurrence_history_from_payload(occurrence_id, payload)
        return {"ok": True, "occurrence": row}

    def _merge_firebase_patch(self, current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        merged = dict(current)
        for key, value in patch.items():
            if "/" in key:
                parts = [part for part in key.split("/") if part]
                target = merged
                for part in parts[:-1]:
                    next_value = target.get(part)
                    if not isinstance(next_value, dict):
                        next_value = {}
                        target[part] = next_value
                    target = next_value
                target[parts[-1]] = value
            else:
                merged[key] = value
        return merged

    def _upsert_occurrence(self, occurrence_id: str, item: dict[str, Any], source_path: str) -> dict[str, Any]:
        row = self._execute_one(
            """
            insert into occurrences (
              id, source_path, created_at, date_label, time_label,
              operator_user_id, operator_name, operator_badge, operator_sector,
              involved_name, involved_badge, involved_sector, type, severity,
              item_code, item_description, quantity, description, status,
              responsible_user_id, responsible_name, responsible_badge, responsible_sector,
              responsible_assigned_at, treatment_text, treatment_signature,
              treatment_at, treatment_by_user_id, treatment_by_name,
              treatment_document, updated_at, updated_by, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
            on conflict (id) do update set
              source_path = excluded.source_path,
              created_at = excluded.created_at,
              date_label = excluded.date_label,
              time_label = excluded.time_label,
              operator_user_id = excluded.operator_user_id,
              operator_name = excluded.operator_name,
              operator_badge = excluded.operator_badge,
              operator_sector = excluded.operator_sector,
              involved_name = excluded.involved_name,
              involved_badge = excluded.involved_badge,
              involved_sector = excluded.involved_sector,
              type = excluded.type,
              severity = excluded.severity,
              item_code = excluded.item_code,
              item_description = excluded.item_description,
              quantity = excluded.quantity,
              description = excluded.description,
              status = excluded.status,
              responsible_user_id = excluded.responsible_user_id,
              responsible_name = excluded.responsible_name,
              responsible_badge = excluded.responsible_badge,
              responsible_sector = excluded.responsible_sector,
              responsible_assigned_at = excluded.responsible_assigned_at,
              treatment_text = excluded.treatment_text,
              treatment_signature = excluded.treatment_signature,
              treatment_at = excluded.treatment_at,
              treatment_by_user_id = excluded.treatment_by_user_id,
              treatment_by_name = excluded.treatment_by_name,
              treatment_document = excluded.treatment_document,
              updated_at = excluded.updated_at,
              updated_by = excluded.updated_by,
              raw_data = excluded.raw_data
            returning *
            """,
            (
                occurrence_id,
                source_path,
                _timestamp(item.get("criadoEm") or item.get("created_at")),
                _clean_text(item.get("data") or item.get("date_label")),
                _clean_text(item.get("hora") or item.get("time_label")),
                self._existing_user_id(_clean_text(item.get("operadorUid") or item.get("operator_user_id"))),
                _clean_text(item.get("operadorNome") or item.get("operator_name")),
                _clean_text(item.get("operadorCracha") or item.get("operator_badge")),
                _clean_text(item.get("operadorSetor") or item.get("operator_sector")),
                _clean_text(item.get("acusadoNome") or item.get("involved_name")),
                _clean_text(item.get("acusadoCracha") or item.get("involved_badge")),
                _clean_text(item.get("acusadoSetor") or item.get("involved_sector")),
                _clean_text(item.get("tipo") or item.get("type")),
                _clean_text(item.get("gravidade") or item.get("severity")),
                _clean_text(item.get("codigoItem") or item.get("item_code")),
                _clean_text(item.get("descricaoItem") or item.get("item_description")),
                item.get("quantidade") if isinstance(item.get("quantidade"), int | float) and not isinstance(item.get("quantidade"), bool) else None,
                _clean_text(item.get("descricao") or item.get("description")),
                _clean_text(item.get("status")) or "aberta",
                self._existing_user_id(_clean_text(item.get("responsavelUid") or item.get("responsible_user_id"))),
                _clean_text(item.get("responsavelNome") or item.get("responsible_name")),
                _clean_text(item.get("responsavelCracha") or item.get("responsible_badge")),
                _clean_text(item.get("responsavelSetor") or item.get("responsible_sector")),
                _timestamp(item.get("responsavelAtribuidoEm") or item.get("responsible_assigned_at")),
                _clean_text(item.get("tratativaRealizada") or item.get("treatment_text")),
                _clean_text(item.get("tratativaAssinatura") or item.get("treatment_signature")),
                _timestamp(item.get("tratativaEm") or item.get("treatment_at")),
                self._existing_user_id(_clean_text(item.get("tratativaPorUid") or item.get("treatment_by_user_id"))),
                _clean_text(item.get("tratativaPorNome") or item.get("treatment_by_name")),
                json.dumps(item.get("documentoTratativa") or item.get("treatment_document") or {}, ensure_ascii=False),
                _timestamp(item.get("atualizadoEm") or item.get("updated_at")) or datetime.now(timezone.utc),
                self._existing_user_id(_clean_text(item.get("atualizadoPor") or item.get("updated_by"))),
                json.dumps(item, ensure_ascii=False),
            ),
        )
        return row

    def _insert_occurrence_history_from_payload(self, occurrence_id: str, payload: dict[str, Any]) -> None:
        historico = payload.get("historico") if isinstance(payload.get("historico"), dict) else {}
        for key, value in payload.items():
            if key.startswith("historico/") and isinstance(value, dict):
                historico[key.split("/", 1)[1]] = value
        for legacy_key, event in historico.items():
            if not isinstance(event, dict):
                continue
            self._execute_one(
                """
                insert into occurrence_history (
                  occurrence_id, legacy_key, event_at, by_user_id, by_name, action, value, raw_data
                )
                select %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                where not exists (
                  select 1 from occurrence_history
                  where occurrence_id = %s and legacy_key = %s
                )
                returning id
                """,
                (
                    occurrence_id,
                    str(legacy_key),
                    _timestamp(event.get("em")),
                    self._existing_user_id(_clean_text(event.get("porUid"))),
                    _clean_text(event.get("porNome")),
                    _clean_text(event.get("acao")),
                    _clean_text(event.get("valor")),
                    json.dumps(event, ensure_ascii=False),
                    occurrence_id,
                    str(legacy_key),
                ),
            )

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

    def _post_chat_message(self, room_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._query("select 1 from chat_rooms where id = %s", (room_id,)):
            raise ApiError(HTTPStatus.NOT_FOUND, "Sala de chat nao encontrada.")
        legacy_key = _clean_text(payload.get("legacy_key") or payload.get("_key"))
        if not legacy_key:
            legacy_key = f"api_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        created_at = _timestamp(payload.get("timestamp") or payload.get("created_at")) or datetime.now(timezone.utc)
        row = self._execute_one(
            """
            insert into chat_messages (
              legacy_key, room_id, user_id, name, text, time_label,
              created_at, message_type, event, session_id, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            returning id, legacy_key, room_id, user_id, name, text, time_label,
                      created_at, message_type, event, session_id
            """,
            (
                legacy_key,
                room_id,
                self._existing_user_id(_clean_text(payload.get("uid") or payload.get("user_id"))),
                _clean_text(payload.get("nome") or payload.get("name")),
                _clean_text(payload.get("texto") or payload.get("text")),
                _clean_text(payload.get("data") or payload.get("time_label")),
                created_at,
                _clean_text(payload.get("tipo") or payload.get("message_type")),
                _clean_text(payload.get("evento") or payload.get("event")),
                _clean_text(payload.get("sessionId") or payload.get("session_id")),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        return {"ok": True, "message": row}

    def _put_chat_read_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_id = _clean_text(payload.get("user_id") or payload.get("uid"))
        room_id = _clean_text(payload.get("room_id") or payload.get("roomId"))
        if not user_id or not room_id:
            raise ApiError(HTTPStatus.BAD_REQUEST, "`user_id` e `room_id` sao obrigatorios.")
        if not self._existing_user_id(user_id):
            raise ApiError(HTTPStatus.NOT_FOUND, "Usuario nao encontrado.")
        if not self._query("select 1 from chat_rooms where id = %s", (room_id,)):
            raise ApiError(HTTPStatus.NOT_FOUND, "Sala de chat nao encontrada.")
        raw_timestamp = payload.get("last_seen_at") or payload.get("lastSeenAt") or payload.get("timestamp")
        last_seen_at = _timestamp(raw_timestamp) or datetime.now(timezone.utc)
        row = self._execute_one(
            """
            insert into chat_read_states (user_id, room_id, last_seen_at, raw_data)
            values (%s, %s, %s, %s::jsonb)
            on conflict (user_id, room_id) do update set
              last_seen_at = greatest(chat_read_states.last_seen_at, excluded.last_seen_at),
              raw_data = excluded.raw_data
            returning user_id, room_id, last_seen_at
            """,
            (
                user_id,
                room_id,
                last_seen_at,
                json.dumps({"firebase_value": raw_timestamp, **payload}, ensure_ascii=False),
            ),
        )
        return {"ok": True, "read_state": row}

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

    def _put_automus_release(self, channel: str, payload: dict[str, Any]) -> dict[str, Any]:
        version = _clean_text(payload.get("version"))
        if not version:
            raise ApiError(HTTPStatus.BAD_REQUEST, "`version` e obrigatorio.")
        notes_value = payload.get("notes")
        if isinstance(notes_value, list):
            notes = "\n".join(str(item) for item in notes_value)
        else:
            notes = _clean_text(notes_value)
        row = self._execute_one(
            """
            insert into automus_releases (
              channel, version, package_url, notes, published_at, published_by, raw_manifest
            )
            values (%s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (channel, version) do update set
              package_url = excluded.package_url,
              notes = excluded.notes,
              published_at = excluded.published_at,
              published_by = excluded.published_by,
              raw_manifest = excluded.raw_manifest
            returning channel, version, package_url, notes, published_at, published_by, raw_manifest
            """,
            (
                channel,
                version,
                _clean_text(payload.get("packageUrl") or payload.get("package_url")),
                notes,
                _timestamp(payload.get("publishedAt") or payload.get("packagedAt")) or datetime.now(timezone.utc),
                _clean_text(payload.get("publishedBy") or payload.get("published_by")),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        return {"ok": True, "release": row}


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
