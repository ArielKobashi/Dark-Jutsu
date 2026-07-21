from __future__ import annotations

import base64
import copy
import gzip
import hmac
import hashlib
import json
import logging
import mimetypes
import re
import os
import secrets
import socket
import subprocess
import threading
import time
import traceback
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
API_HOST = _env("DARK_JUTSU_API_HOST", "0.0.0.0")
API_PORT = int(_env("DARK_JUTSU_API_PORT", "8765"))
API_TOKEN = _env("DARK_JUTSU_API_TOKEN")
AUTH_SECRET = _env("DARK_JUTSU_AUTH_SECRET") or API_TOKEN or hashlib.sha256(DATABASE_URL.encode("utf-8")).hexdigest()
AUTH_TOKEN_TTL_SECONDS = int(_env("DARK_JUTSU_AUTH_TOKEN_TTL_SECONDS", str(7 * 24 * 60 * 60)))
REQUIRE_AUTH = _env("DARK_JUTSU_REQUIRE_AUTH", "1").lower() not in {"0", "false", "no", "nao"}
ALLOWED_ORIGINS = [origin.strip().rstrip("/") for origin in _env("DARK_JUTSU_ALLOWED_ORIGINS", "*").split(",") if origin.strip()]
PUBLIC_TUNNEL_MODE = _env("DARK_JUTSU_PUBLIC_TUNNEL_MODE", "0").lower() in {"1", "true", "sim", "yes"}
LOGIN_RATE_LIMIT_MAX = int(_env("DARK_JUTSU_LOGIN_RATE_LIMIT_MAX", "8"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(_env("DARK_JUTSU_LOGIN_RATE_LIMIT_WINDOW_SECONDS", "600"))
SYSTEM_UPDATE_LOG = Path(_env("DARK_JUTSU_SYSTEM_UPDATE_LOG", r"C:\DarkJutsu\logs\atualizacao_github.log"))
SYSTEM_UPDATE_VERSION_FILE = Path(_env("DARK_JUTSU_SYSTEM_VERSION_FILE", r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\versao_github_atual.txt"))
APP_WEB_ROOT = Path(_env("DARK_JUTSU_APP_WEB_ROOT", r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\app"))
APP_PUBLIC_FILES = {
    "index.html",
    "dashboard.html",
    "label-editor.html",
    "medidores.html",
    "style.css",
    "mobile.css",
    "dashboard-nav.js",
    "critical-stock-manager.js",
    "sw.js",
    "site.webmanifest",
    "logo.png",
    "logo-tab.png",
}
SYSTEM_UPDATE_LOCK = threading.Lock()
SYSTEM_UPDATE_RUNNING = False
SYSTEM_UPDATE_LAST: dict[str, Any] = {}
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMIT_BUCKETS: dict[str, list[float]] = {}
API_STARTED_AT = time.time()


def _setup_detail_logger() -> logging.Logger:
    logger = logging.getLogger("dark_jutsu_api_detail")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    log_path = Path(_env("DARK_JUTSU_API_DETAIL_LOG", r"C:\DarkJutsu\logs\api_detalhado.log"))
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.FileHandler(log_path, encoding="utf-8")
    except Exception:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


DETAIL_LOG = _setup_detail_logger()


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


def _firebase_like_key(value: Any, default: str = "desconhecido") -> str:
    text = _clean_text(value)
    if not text:
        return default
    return re.sub(r"[^0-9A-Za-z_-]+", "_", text.lower()).strip("_") or default


def _decode_legacy_key(value: str) -> str:
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8") or value
    except Exception:
        return value


def _inventory_legacy_key(item: dict[str, Any], dead: bool = False) -> str:
    key = _clean_text(item.get("protheusKey")) or _clean_text(item.get("protheus")) or _clean_text(item.get("cooperat"))
    if key:
        return key
    fallback = _clean_text(item.get("descricao")) or "unknown"
    return ("MORTO|" if dead else "ITEM|") + fallback


def _encode_legacy_key(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _inventory_aliases(item: dict[str, Any]) -> set[str]:
    aliases = {
        _clean_text(item.get("protheusKey")),
        _clean_text(item.get("protheus")),
        _clean_text(item.get("cooperat")),
    }
    return {alias for alias in aliases if alias}


def _strip_legacy_automatic_policy(item: dict[str, Any]) -> None:
    item.pop("sugestaoEstoque", None)
    item.pop("sugestaoEstoqueLegada", None)
    origins = {
        str(item.get("limitesOrigem") or "").strip().lower(),
        str(item.get("minimoOrigem") or "").strip().lower(),
        str(item.get("maximoOrigem") or "").strip().lower(),
        str(item.get("reposicaoOrigem") or "").strip().lower(),
    }
    if "manual" in origins or "cooperat" in origins:
        return
    if origins.intersection({"automatico", "calculada", "gerenciador_critico"}):
        for field in ("minimo", "maximo", "reposicao", "minimoOrigem", "maximoOrigem", "reposicaoOrigem", "limitesOrigem"):
            item.pop(field, None)


def _merge_automus_payload(incoming: dict[str, Any], previous: dict[str, Any], imported_at: datetime) -> dict[str, Any]:
    merged = copy.deepcopy(incoming)

    previous_adjustments = previous.get("ajustesItens") if isinstance(previous.get("ajustesItens"), dict) else {}
    incoming_adjustments = merged.get("ajustesItens") if isinstance(merged.get("ajustesItens"), dict) else {}
    adjustments = {**previous_adjustments, **incoming_adjustments}
    merged["ajustesItens"] = adjustments

    previous_history = previous.get("historicoSaldo") if isinstance(previous.get("historicoSaldo"), dict) else {}
    incoming_history = merged.get("historicoSaldo") if isinstance(merged.get("historicoSaldo"), dict) else {}
    history: dict[str, list[dict[str, Any]]] = {}
    for source in (previous_history, incoming_history):
        for raw_key, raw_events in source.items():
            if not isinstance(raw_events, list):
                continue
            item_key = _decode_legacy_key(str(raw_key))
            encoded_key = _encode_legacy_key(item_key)
            events = history.setdefault(encoded_key, [])
            known = {
                (event.get("timestamp"), event.get("delta"), event.get("saldoAnterior"), event.get("saldoAtual"))
                for event in events
                if isinstance(event, dict)
            }
            for raw_event in raw_events:
                if not isinstance(raw_event, dict):
                    continue
                signature = (
                    raw_event.get("timestamp"),
                    raw_event.get("delta"),
                    raw_event.get("saldoAnterior"),
                    raw_event.get("saldoAtual"),
                )
                if signature not in known:
                    events.append(copy.deepcopy(raw_event))
                    known.add(signature)

    previous_items = previous.get("dados") if isinstance(previous.get("dados"), list) else []
    previous_by_alias: dict[str, dict[str, Any]] = {}
    for item in previous_items:
        if not isinstance(item, dict):
            continue
        for alias in _inventory_aliases(item):
            previous_by_alias.setdefault(alias, item)

    current_items = merged.get("dados") if isinstance(merged.get("dados"), list) else []
    current_by_alias: dict[str, dict[str, Any]] = {}
    for item in current_items:
        if not isinstance(item, dict):
            continue
        _strip_legacy_automatic_policy(item)
        aliases = _inventory_aliases(item)
        for alias in aliases:
            current_by_alias.setdefault(alias, item)
        previous_item = next((previous_by_alias[alias] for alias in aliases if alias in previous_by_alias), None)
        if not previous_item:
            continue
        previous_balance = _decimal_value(previous_item.get("saldo"))
        current_balance = _decimal_value(item.get("saldo"))
        if previous_balance is None or current_balance is None or previous_balance == current_balance:
            continue
        item_key = _inventory_legacy_key(item)
        encoded_key = _encode_legacy_key(item_key)
        delta = current_balance - previous_balance
        event = {
            "data": imported_at.strftime("%d/%m/%Y %H:%M"),
            "timestamp": int(imported_at.timestamp() * 1000),
            "delta": float(delta),
            "tipo": "entrada" if delta > 0 else "saida",
            "saldoAnterior": float(previous_balance),
            "saldoAtual": float(current_balance),
        }
        events = history.setdefault(encoded_key, [])
        signature = (event["timestamp"], event["delta"], event["saldoAnterior"], event["saldoAtual"])
        if not any(
            isinstance(existing, dict)
            and (existing.get("timestamp"), existing.get("delta"), existing.get("saldoAnterior"), existing.get("saldoAtual")) == signature
            for existing in events
        ):
            events.append(event)

    merged["historicoSaldo"] = {key: events[-300:] for key, events in history.items()}

    for legacy_key, adjustment in adjustments.items():
        if not isinstance(adjustment, dict):
            continue
        item_key = _clean_text(adjustment.get("itemKey")) or _decode_legacy_key(str(legacy_key))
        item = current_by_alias.get(item_key or "")
        if not item:
            continue
        changed = False
        for field, origin_field in (("minimo", "minimoOrigem"), ("maximo", "maximoOrigem"), ("reposicao", "reposicaoOrigem")):
            if field in adjustment and adjustment.get(field) is not None:
                item[field] = adjustment[field]
                item[origin_field] = "manual"
                changed = True
        if changed:
            item["limitesOrigem"] = "manual"

    if not isinstance(merged.get("movimentacoesMata185"), dict) or not merged.get("movimentacoesMata185"):
        previous_movements = previous.get("movimentacoesMata185")
        if isinstance(previous_movements, dict):
            merged["movimentacoesMata185"] = copy.deepcopy(previous_movements)
    return merged


def _json_hash(payload: Any) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=_json_default).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _local_ipv4_addresses() -> list[str]:
    addresses: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in addresses:
                addresses.append(ip)
    except Exception:
        pass
    return addresses


def _chat_password_hash(room_id: str, password: Any) -> str | None:
    text = _clean_text(password)
    if not text:
        return None
    salt = hashlib.sha256(f"dark-jutsu:{room_id}".encode("utf-8")).hexdigest()[:16]
    digest = hashlib.pbkdf2_hmac("sha256", text.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()
    return f"pbkdf2_sha256$200000${salt}${digest}"


def _verify_chat_password(room_id: str, password: Any, stored_hash: Any) -> bool:
    expected = _clean_text(stored_hash)
    if not expected:
        return False
    return expected == _chat_password_hash(room_id, password)


def _password_hash(password: Any) -> str:
    text = _clean_text(password)
    if not text or len(text) < 4:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Senha muito curta.")
    salt = secrets.token_urlsafe(18)
    rounds = 260_000
    digest = hashlib.pbkdf2_hmac("sha256", text.encode("utf-8"), salt.encode("utf-8"), rounds).hex()
    return f"pbkdf2_sha256${rounds}${salt}${digest}"


def _verify_password(password: Any, stored_hash: Any) -> bool:
    encoded = _clean_text(stored_hash)
    if not encoded:
        return False
    try:
        algo, rounds_raw, salt, digest = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        rounds = int(rounds_raw)
        actual = hashlib.pbkdf2_hmac("sha256", str(password or "").encode("utf-8"), salt.encode("utf-8"), rounds).hex()
        return hmac.compare_digest(actual, digest)
    except Exception:
        return False


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode((data + "=" * (-len(data) % 4)).encode("ascii"))


def _sign_auth_payload(payload: dict[str, Any]) -> str:
    body = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(AUTH_SECRET.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    return f"dj1.{body}.{_b64url(signature)}"


def _verify_auth_token(token: str) -> dict[str, Any]:
    parts = str(token or "").split(".")
    if len(parts) != 3 or parts[0] != "dj1":
        raise ApiError(HTTPStatus.UNAUTHORIZED, "Token SQL invalido.")
    expected = _b64url(hmac.new(AUTH_SECRET.encode("utf-8"), parts[1].encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, parts[2]):
        raise ApiError(HTTPStatus.UNAUTHORIZED, "Token SQL invalido.")
    try:
        payload = json.loads(_b64url_decode(parts[1]).decode("utf-8"))
    except Exception as exc:
        raise ApiError(HTTPStatus.UNAUTHORIZED, "Token SQL invalido.") from exc
    exp = int(payload.get("exp") or 0)
    if exp <= int(time.time()):
        raise ApiError(HTTPStatus.UNAUTHORIZED, "Sessao expirada.")
    return payload if isinstance(payload, dict) else {}


def _rate_limit_allow(key: str, maximum: int, window_seconds: int) -> bool:
    now = time.time()
    cutoff = now - max(1, window_seconds)
    with _RATE_LIMIT_LOCK:
        attempts = [stamp for stamp in _RATE_LIMIT_BUCKETS.get(key, []) if stamp >= cutoff]
        if len(attempts) >= max(1, maximum):
            _RATE_LIMIT_BUCKETS[key] = attempts
            return False
        attempts.append(now)
        _RATE_LIMIT_BUCKETS[key] = attempts
        return True


def _rate_limit_clear(key: str) -> None:
    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_BUCKETS.pop(key, None)


def _public_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "uid": row.get("id"),
        "id": row.get("id"),
        "email": f"{row.get('nickname') or row.get('id')}@sistema.local",
        "nickname": row.get("nickname") or "",
        "cracha": row.get("badge") or "",
        "badge": row.get("badge") or "",
        "setor": row.get("sector") or "",
        "sector": row.get("sector") or "",
        "nivel": row.get("role") or "op",
        "role": row.get("role") or "op",
        "ativo": bool(row.get("active")),
        "active": bool(row.get("active")),
        "senha": row.get("password_status") or "",
        "senhaReset": bool(row.get("password_reset_required")) or row.get("password_status") == "reset_required",
    }


def _connect():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class AuthContext:
    def __init__(
        self,
        authenticated: bool = False,
        user_id: str | None = None,
        role: str = "anon",
        service: bool = False,
        claims: dict[str, Any] | None = None,
    ):
        self.authenticated = authenticated
        self.user_id = user_id
        self.role = role
        self.service = service
        self.claims = claims or {}


class Handler(BaseHTTPRequestHandler):
    server_version = "DarkJutsuSQL/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        message = fmt % args
        print("%s - %s" % (self.address_string(), message))
        DETAIL_LOG.info("HTTP client=%s msg=%s", self._client_ip(), message)

    def _request_log_context(self, started: float, status: int | HTTPStatus, error: str = "") -> None:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        auth = getattr(self, "auth_context", AuthContext())
        DETAIL_LOG.info(
            "REQ method=%s path=%s status=%s elapsed_ms=%s client=%s origin=%s referer=%s ua=%s role=%s user=%s service=%s pid=%s thread=%s error=%s",
            self.command,
            self.path,
            int(status),
            elapsed_ms,
            self._client_ip(),
            self.headers.get("Origin", ""),
            self.headers.get("Referer", ""),
            self.headers.get("User-Agent", ""),
            auth.role,
            auth.user_id or "",
            auth.service,
            os.getpid(),
            threading.current_thread().name,
            error,
        )

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=_json_default).encode("utf-8")
        raw_len = len(body)
        accept_encoding = self.headers.get("Accept-Encoding", "")
        usar_gzip = "gzip" in accept_encoding.lower() and raw_len > 2048
        if usar_gzip:
            body = gzip.compress(body, compresslevel=5)
        origin = self.headers.get("Origin", "").rstrip("/")
        allow_origin = ""
        if ALLOWED_ORIGINS and ALLOWED_ORIGINS != ["*"]:
            allow_origin = origin if origin in ALLOWED_ORIGINS else ""
        elif not PUBLIC_TUNNEL_MODE:
            allow_origin = "*"
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            if usar_gzip:
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
            if allow_origin:
                self.send_header("Access-Control-Allow-Origin", allow_origin)
                self.send_header("Vary", "Origin, Accept-Encoding" if usar_gzip else "Origin")
            self.send_header("Access-Control-Allow-Headers", "authorization, content-type, x-api-token")
            self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, PATCH, DELETE, OPTIONS")
            self.end_headers()
            self.wfile.write(body)
            if raw_len > 100000:
                DETAIL_LOG.info(
                    "JSON_PAYLOAD path=%s raw_bytes=%s sent_bytes=%s gzip=%s",
                    self.path,
                    raw_len,
                    len(body),
                    usar_gzip,
                )
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError) as exc:
            DETAIL_LOG.warning(
                "SEND_ABORT method=%s path=%s client=%s status=%s error=%s",
                self.command,
                self.path,
                self._client_ip(),
                int(status),
                exc,
            )
            return

    def _send_file(self, path: Path) -> None:
        origin = self.headers.get("Origin", "").rstrip("/")
        allow_origin = ""
        if ALLOWED_ORIGINS and ALLOWED_ORIGINS != ["*"]:
            allow_origin = origin if origin in ALLOWED_ORIGINS else ""
        elif not PUBLIC_TUNNEL_MODE:
            allow_origin = "*"
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        try:
            stat = path.stat()
            etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
            if self.headers.get("If-None-Match") == etag:
                self.send_response(HTTPStatus.NOT_MODIFIED)
                self.send_header("ETag", etag)
                if allow_origin:
                    self.send_header("Access-Control-Allow-Origin", allow_origin)
                    self.send_header("Vary", "Origin")
                self.end_headers()
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(stat.st_size))
            self.send_header("ETag", etag)
            suffix = path.suffix.lower()
            if suffix == ".html":
                self.send_header("Cache-Control", "no-cache, must-revalidate")
            elif suffix in {".js", ".css"}:
                self.send_header("Cache-Control", "public, max-age=300, must-revalidate")
            elif suffix in {".png", ".ico", ".webmanifest", ".woff", ".woff2", ".ttf"}:
                self.send_header("Cache-Control", "public, max-age=604800")
            elif suffix in {".xlsx", ".json"}:
                self.send_header("Cache-Control", "public, max-age=1800, must-revalidate")
            if allow_origin:
                self.send_header("Access-Control-Allow-Origin", allow_origin)
                self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "authorization, content-type, x-api-token")
            self.send_header("Access-Control-Allow-Methods", "GET, PUT, POST, PATCH, DELETE, OPTIONS")
            self.end_headers()
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError) as exc:
            DETAIL_LOG.warning(
                "SEND_FILE_ABORT method=%s path=%s file=%s client=%s error=%s",
                self.command,
                self.path,
                path,
                self._client_ip(),
                exc,
            )
            return

    def _send_app_file(self, parts: list[str]) -> None:
        filename = "index.html"
        if parts and parts != ["app"]:
            filename = parts[-1] or "index.html"
        if filename in {"", ".", ".."}:
            filename = "index.html"
        if "/" in filename or "\\" in filename or filename not in APP_PUBLIC_FILES:
            raise ApiError(HTTPStatus.NOT_FOUND, "Arquivo do app nao encontrado.")
        roots = [
            APP_WEB_ROOT,
            ROOT,
            ROOT.parent / "app",
        ]
        for root in roots:
            path = (root / filename).resolve()
            try:
                base = root.resolve()
            except Exception:
                base = root
            if path.is_file() and (path == base / filename or base in path.parents):
                self._send_file(path)
                return
        raise ApiError(HTTPStatus.NOT_FOUND, "Arquivo do app nao encontrado.")

    def do_OPTIONS(self) -> None:
        if not self._request_origin_allowed():
            self._send_json({"ok": False, "error": "Origem nao autorizada."}, HTTPStatus.FORBIDDEN)
            return
        self._send_json({"ok": True})

    def do_GET(self) -> None:
        started = time.perf_counter()
        try:
            if not self._request_origin_allowed():
                raise ApiError(HTTPStatus.FORBIDDEN, "Origem nao autorizada.")
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
            if not parts or parts[:1] == ["app"] or (len(parts) == 1 and parts[0] in APP_PUBLIC_FILES):
                self._send_app_file(parts)
                self._request_log_context(started, HTTPStatus.OK)
                return
            if len(parts) == 2 and parts[0] in {"downloads", "data"}:
                self._send_project_file(parts[0], parts[1])
                self._request_log_context(started, HTTPStatus.OK)
                return
            if parts == ["api", "mobile-link"]:
                self._send_json(self._mobile_link())
                self._request_log_context(started, HTTPStatus.OK)
                return
            self.auth_context = self._authenticate()
            if len(parts) == 4 and parts[:2] == ["api", "files"]:
                self._send_project_file(parts[2], parts[3])
                self._request_log_context(started, HTTPStatus.OK)
                return
            payload = self._route(parts, query)
            self._send_json(payload)
            self._request_log_context(started, HTTPStatus.OK)
        except ApiError as exc:
            self._send_json({"ok": False, "error": exc.message}, exc.status)
            self._request_log_context(started, exc.status, exc.message)
        except Exception as exc:
            DETAIL_LOG.error("UNHANDLED method=GET path=%s client=%s error=%s\n%s", self.path, self._client_ip(), exc, traceback.format_exc())
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            self._request_log_context(started, HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_PUT(self) -> None:
        self._handle_write("PUT")

    def do_POST(self) -> None:
        self._handle_write("POST")

    def do_PATCH(self) -> None:
        self._handle_write("PATCH")

    def do_DELETE(self) -> None:
        self._handle_write("DELETE")

    def _handle_write(self, method: str) -> None:
        started = time.perf_counter()
        try:
            if not self._request_origin_allowed():
                raise ApiError(HTTPStatus.FORBIDDEN, "Origem nao autorizada.")
            self.auth_context = self._authenticate()
            parsed = urlparse(self.path)
            parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
            payload = self._read_json_body()
            result = self._write_route(method, parts, payload)
            self._send_json(result)
            self._request_log_context(started, HTTPStatus.OK)
        except ApiError as exc:
            self._send_json({"ok": False, "error": exc.message}, exc.status)
            self._request_log_context(started, exc.status, exc.message)
        except Exception as exc:
            DETAIL_LOG.error("UNHANDLED method=%s path=%s client=%s error=%s\n%s", method, self.path, self._client_ip(), exc, traceback.format_exc())
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            self._request_log_context(started, HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def _request_origin_allowed(self) -> bool:
        origin = self.headers.get("Origin", "").rstrip("/")
        if not origin:
            return True
        if ALLOWED_ORIGINS and ALLOWED_ORIGINS != ["*"]:
            return origin in ALLOWED_ORIGINS
        return not PUBLIC_TUNNEL_MODE

    def _client_ip(self) -> str:
        if PUBLIC_TUNNEL_MODE:
            cf_ip = _clean_text(self.headers.get("CF-Connecting-IP"))
            if cf_ip:
                return cf_ip
            forwarded = _clean_text(self.headers.get("X-Forwarded-For"))
            if forwarded:
                return forwarded.split(",", 1)[0].strip()
        return str(self.client_address[0] if self.client_address else "")

    def _authenticate(self) -> AuthContext:
        if self.path.startswith("/health") or self.path.startswith("/live"):
            return AuthContext(authenticated=True, role="service", service=True)
        parsed = urlparse(self.path)
        parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
        if self.command == "POST" and parts == ["api", "signup-requests"]:
            return AuthContext(authenticated=True, role="anon")
        if self.command == "POST" and parts[:2] == ["api", "auth"]:
            return AuthContext(authenticated=True, role="anon")
        if self.command == "GET" and len(parts) == 4 and parts[:2] == ["api", "nicknames"] and parts[3] == "status":
            return AuthContext(authenticated=True, role="anon")
        bearer = self.headers.get("Authorization", "")
        token = self.headers.get("X-API-Token", "")
        if API_TOKEN and (bearer == f"Bearer {API_TOKEN}" or token == API_TOKEN):
            return AuthContext(authenticated=True, role="service", service=True)
        if bearer.startswith("Bearer "):
            raw_token = bearer.removeprefix("Bearer ").strip()
            if raw_token:
                return self._auth_context_from_sql_token(raw_token)
        if not REQUIRE_AUTH:
            return AuthContext(authenticated=True, role="service", service=True)
        raise ApiError(HTTPStatus.UNAUTHORIZED, "Autenticacao obrigatoria.")

    def _auth_context_from_sql_token(self, raw_token: str) -> AuthContext:
        claims = _verify_auth_token(raw_token)
        uid = _clean_text(claims.get("sub"))
        if not uid:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Token SQL sem usuario.")
        rows = self._query_as_service(
            """
            select u.id, u.role, u.active, u.token_version, b.user_id as banned_user_id
            from users u
            left join banned_users b on b.user_id = u.id
            where u.id = %s
            limit 1
            """,
            (uid,),
        )
        if not rows:
            raise ApiError(HTTPStatus.FORBIDDEN, "Usuario autenticado nao existe no SQL.")
        user = rows[0]
        if not user.get("active"):
            raise ApiError(HTTPStatus.FORBIDDEN, "Usuario inativo.")
        if user.get("banned_user_id"):
            raise ApiError(HTTPStatus.FORBIDDEN, "Usuario banido.")
        if int(user.get("token_version") or 0) != int(claims.get("ver") or 0):
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Sessao revogada.")
        role = _clean_text(user.get("role")) or "op"
        return AuthContext(authenticated=True, user_id=uid, role=role, claims=claims)

    def _require_auth(self) -> AuthContext:
        auth = getattr(self, "auth_context", AuthContext())
        if not auth.authenticated:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Autenticacao obrigatoria.")
        return auth

    def _require_roles(self, *roles: str) -> AuthContext:
        auth = self._require_auth()
        if auth.service:
            return auth
        allowed = set(roles)
        if auth.role not in allowed:
            raise ApiError(HTTPStatus.FORBIDDEN, "Permissao insuficiente.")
        return auth

    def _require_staff(self) -> AuthContext:
        return self._require_roles("mod", "admin")

    def _require_admin(self) -> AuthContext:
        return self._require_roles("admin")

    def _route(self, parts: list[str], query: dict[str, list[str]]) -> Any:
        if parts == ["live"]:
            return self._live()
        if parts == ["health"]:
            return self._health()
        if parts[:1] != ["api"]:
            raise ApiError(HTTPStatus.NOT_FOUND, "Endpoint nao encontrado.")
        if parts == ["api", "me"]:
            return self._me()
        if parts == ["api", "auth", "me"]:
            return self._me()
        if parts == ["api", "ops", "status"]:
            self._require_staff()
            return self._ops_status()
        if parts == ["api", "system", "update-status"]:
            self._require_admin()
            return self._system_update_status()
        if parts == ["api", "inventory"]:
            return self._inventory(query)
        if parts == ["api", "inventory", "automus-state"]:
            self._require_admin()
            return {"ok": True, "inventory": self._inventory_legacy_snapshot()}
        if len(parts) == 3 and parts[:2] == ["api", "inventory"]:
            return self._inventory_item(parts[2])
        if parts == ["api", "users"]:
            self._require_staff()
            return self._users(query)
        if len(parts) == 3 and parts[:2] == ["api", "users"]:
            self._require_staff()
            return self._user(parts[2])
        if parts == ["api", "signup-requests"]:
            self._require_staff()
            return self._signup_requests(query)
        if len(parts) == 3 and parts[:2] == ["api", "signup-requests"]:
            self._require_staff()
            return self._signup_request(parts[2])
        if len(parts) == 4 and parts[:2] == ["api", "nicknames"] and parts[3] == "status":
            return self._nickname_status(parts[2], query)
        if parts == ["api", "banned-users"]:
            self._require_staff()
            return self._banned_users(query)
        if parts == ["api", "dashboard"]:
            return self._dashboard()
        if parts == ["api", "dashboard", "snapshot"]:
            return self._dashboard_snapshot(query)
        if parts == ["api", "counting", "sessions"]:
            return self._counting_sessions(query)
        if parts == ["api", "counting", "history"]:
            return self._counting_history(query)
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
        if len(parts) == 5 and parts[:3] == ["api", "chat", "rooms"] and parts[4] == "password-status":
            return self._chat_room_password_status(parts[3])
        if len(parts) == 5 and parts[:3] == ["api", "chat", "rooms"] and parts[4] == "messages":
            return self._chat_messages(parts[3], query)
        if len(parts) == 4 and parts[:3] == ["api", "chat", "read-state"]:
            return self._chat_read_state(parts[3])
        if len(parts) == 4 and parts[:3] == ["api", "automus", "releases"]:
            return self._automus_release(parts[3])
        raise ApiError(HTTPStatus.NOT_FOUND, "Endpoint nao encontrado.")

    def _send_project_file(self, folder: str, filename: str) -> None:
        allowed_folders = {"downloads", "data"}
        allowed_suffixes = {".xlsx", ".json", ".png", ".ttf"}
        if folder not in allowed_folders:
            raise ApiError(HTTPStatus.NOT_FOUND, "Pasta nao autorizada.")
        if "/" in filename or "\\" in filename or filename in {"", ".", ".."}:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Nome de arquivo invalido.")
        path = (ROOT / folder / filename).resolve()
        base = (ROOT / folder).resolve()
        if base not in path.parents or path.suffix.lower() not in allowed_suffixes or not path.is_file():
            raise ApiError(HTTPStatus.NOT_FOUND, "Arquivo nao encontrado.")
        self._send_file(path)

    def _write_route(self, method: str, parts: list[str], payload: dict[str, Any]) -> Any:
        if method == "POST" and parts == ["api", "auth", "login"]:
            return self._auth_login(payload)
        if method == "POST" and parts == ["api", "auth", "change-password"]:
            self._require_auth()
            return self._auth_change_password(payload)
        if method == "POST" and parts == ["api", "auth", "logout"]:
            self._require_auth()
            return {"ok": True}
        if method == "POST" and parts == ["api", "system", "update-from-github"]:
            self._require_admin()
            return self._post_system_update_from_github(payload)
        if method == "PUT" and len(parts) == 4 and parts[:3] == ["api", "dashboard", "panels"]:
            self._require_staff()
            return self._put_dashboard_panel(parts[3], payload)
        if method == "PUT" and len(parts) == 4 and parts[:3] == ["api", "dashboard", "evaluations"]:
            self._require_staff()
            return self._put_dashboard_evaluation(parts[3], payload)
        if method == "DELETE" and len(parts) == 4 and parts[:3] == ["api", "dashboard", "evaluations"]:
            self._require_staff()
            return self._delete_dashboard_evaluation(parts[3])
        if method == "POST" and parts == ["api", "inventory", "automus-update"]:
            self._require_admin()
            return self._post_inventory_automus_update(payload)
        if method in {"PUT", "PATCH"} and len(parts) == 4 and parts[:2] == ["api", "inventory"] and parts[3] == "adjustment":
            self._require_staff()
            return self._put_inventory_adjustment(parts[2], payload)
        if method == "POST" and parts == ["api", "occurrences"]:
            return self._post_occurrence(payload)
        if method == "PATCH" and len(parts) == 3 and parts[:2] == ["api", "occurrences"]:
            return self._patch_occurrence(parts[2], payload)
        if method == "POST" and len(parts) == 5 and parts[:3] == ["api", "chat", "rooms"] and parts[4] == "messages":
            return self._post_chat_message(parts[3], payload)
        if method == "DELETE" and len(parts) == 5 and parts[:3] == ["api", "chat", "rooms"] and parts[4] == "messages":
            self._require_admin()
            return self._delete_chat_messages(parts[3])
        if method in {"PUT", "PATCH"} and len(parts) == 5 and parts[:3] == ["api", "chat", "rooms"] and parts[4] == "password":
            self._require_admin()
            return self._put_chat_room_password(parts[3], payload)
        if method == "POST" and len(parts) == 5 and parts[:3] == ["api", "chat", "rooms"] and parts[4] == "verify-password":
            return self._verify_chat_room_password(parts[3], payload)
        if method in {"PUT", "PATCH"} and parts == ["api", "chat", "read-state"]:
            return self._put_chat_read_state(payload)
        if method == "POST" and parts == ["api", "labels", "jobs"]:
            return self._post_label_job(payload)
        if method == "POST" and parts == ["api", "counting", "sessions"]:
            return self._post_counting_session(payload)
        if method == "PATCH" and len(parts) == 5 and parts[:3] == ["api", "counting", "sessions"] and parts[4] == "user":
            self._require_admin()
            return self._patch_counting_session_user(parts[3], payload)
        if method in {"PUT", "POST", "PATCH"} and parts == ["api", "counting", "drafts"]:
            return self._put_counting_draft(payload)
        if method == "DELETE" and len(parts) == 4 and parts[:3] == ["api", "counting", "drafts"]:
            return self._delete_counting_draft(parts[3])
        if method in {"PUT", "POST", "PATCH"} and parts == ["api", "counting", "machine-status"]:
            return self._put_counting_machine_status(payload)
        if method == "POST" and parts == ["api", "counting", "reset"]:
            self._require_admin()
            return self._post_counting_reset(payload)
        if method in {"PUT", "PATCH"} and len(parts) == 3 and parts[:2] == ["api", "settings"]:
            self._require_staff()
            return self._put_setting(parts[2], payload)
        if method in {"POST", "PUT"} and len(parts) == 4 and parts[:3] == ["api", "automus", "releases"]:
            self._require_admin()
            return self._put_automus_release(parts[3], payload)
        if method == "PATCH" and len(parts) == 3 and parts[:2] == ["api", "users"]:
            self._require_staff()
            return self._patch_user(parts[2], payload)
        if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "users"] and parts[3] == "ban":
            self._require_staff()
            return self._ban_user(parts[2], payload)
        if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "users"] and parts[3] == "reset-password":
            self._require_staff()
            return self._reset_user_password(parts[2], payload)
        if method == "DELETE" and len(parts) == 3 and parts[:2] == ["api", "banned-users"]:
            self._require_staff()
            return self._delete_banned_user(parts[2])
        if method == "PATCH" and len(parts) == 3 and parts[:2] == ["api", "signup-requests"]:
            self._require_staff()
            return self._patch_signup_request(parts[2], payload)
        if method == "POST" and parts == ["api", "signup-requests"]:
            return self._post_signup_request(payload)
        if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "signup-requests"] and parts[3] == "approve":
            self._require_staff()
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
        auth = getattr(self, "auth_context", AuthContext(role="service", service=True))
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select set_config('app.role', %s, true)", (auth.role,))
                cur.execute("select set_config('app.user_id', %s, true)", (auth.user_id or "",))
                cur.execute(sql, params)
                return list(cur.fetchall())

    def _execute_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
        auth = getattr(self, "auth_context", AuthContext(role="service", service=True))
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select set_config('app.role', %s, true)", (auth.role,))
                cur.execute("select set_config('app.user_id', %s, true)", (auth.user_id or "",))
                cur.execute(sql, params)
                row = cur.fetchone()
                if row is None:
                    return {}
                return dict(row)

    def _query_as_service(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select set_config('app.role', 'service', true)")
                cur.execute("select set_config('app.user_id', '', true)")
                cur.execute(sql, params)
                return list(cur.fetchall())

    def _health(self) -> dict[str, Any]:
        started = time.perf_counter()
        rows = self._query_as_service(
            """
            select
              now() as database_time,
              to_regclass('public.users') is not null as users_table,
              to_regclass('public.inventory_items') is not null as inventory_table,
              to_regclass('public.chat_messages') is not null as chat_table,
              to_regclass('public.app_settings') is not null as settings_table
            """
        )
        db_ms = int((time.perf_counter() - started) * 1000)
        table_status = {
            "users": bool(rows[0]["users_table"]),
            "inventory_items": bool(rows[0]["inventory_table"]),
            "chat_messages": bool(rows[0]["chat_table"]),
            "app_settings": bool(rows[0]["settings_table"]),
        }
        if not all(table_status.values()):
            DETAIL_LOG.error("HEALTH_SCHEMA_MISSING tables=%s pid=%s", table_status, os.getpid())
            raise RuntimeError(f"Schema SQL incompleto: {table_status}")
        if db_ms >= 1000:
            DETAIL_LOG.warning("HEALTH_SLOW db_ms=%s pid=%s", db_ms, os.getpid())
        snapshot_rows = self._query_as_service(
            """
            select saved_at, updated_by
            from inventory_snapshots
            order by saved_at desc nulls last, id desc
            limit 1
            """
        )
        latest_snapshot = snapshot_rows[0] if snapshot_rows else None
        return {
            "ok": True,
            "database_time": rows[0]["database_time"],
            "database_url": "configured",
            "db_ms": db_ms,
            "tables": table_status,
            "pid": os.getpid(),
            "uptime_seconds": int(time.time() - API_STARTED_AT),
            "latest_inventory_snapshot": latest_snapshot,
        }

    def _live(self) -> dict[str, Any]:
        return {
            "ok": True,
            "pid": os.getpid(),
            "uptime_seconds": int(time.time() - API_STARTED_AT),
            "threads": threading.active_count(),
        }

    def _ops_status(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for table in (
            "users",
            "signup_requests",
            "banned_users",
            "inventory_items",
            "inventory_snapshots",
            "counting_sessions",
            "counting_drafts",
            "counting_machine_status",
            "label_print_jobs",
            "occurrences",
            "chat_rooms",
            "chat_messages",
            "chat_read_states",
            "dashboard_panels",
            "purchase_evaluations",
            "app_settings",
            "automus_releases",
        ):
            rows = self._query_as_service(f"select count(*)::int as count from {table}")
            counts[table] = int(rows[0]["count"]) if rows else 0
        snapshot_rows = self._query_as_service(
            """
            select source, saved_at, item_count, dead_item_count
            from inventory_snapshots
            order by saved_at desc nulls last, id desc
            limit 1
            """
        )
        settings_rows = self._query_as_service(
            """
            select key, updated_at
            from app_settings
            where key in (
              'occurrences.fields',
              'occurrences.evaluator_password',
              'inventory.countingConfig',
              'label.config',
              'counting.resetGlobal'
            )
            order by key
            """
        )
        db_rows = self._query_as_service("select now() as database_time, current_database() as database_name")
        return {
            "ok": True,
            "database": db_rows[0] if db_rows else {},
            "api": {
                "host": API_HOST,
                "port": API_PORT,
                "require_auth": REQUIRE_AUTH,
                "allowed_origins": ALLOWED_ORIGINS,
                "service_token_configured": bool(API_TOKEN),
            },
            "counts": counts,
            "latest_inventory_snapshot": snapshot_rows[0] if snapshot_rows else None,
            "settings": settings_rows,
        }

    def _me(self) -> dict[str, Any]:
        auth = getattr(self, "auth_context", AuthContext())
        user = None
        if auth.user_id:
            rows = self._query(
                """
                select id, firebase_uid, nickname, nickname_key, badge, sector, role,
                       active, password_status, password_reset_required, created_at, updated_at
                from users
                where id = %s
                limit 1
                """,
                (auth.user_id,),
            )
            if rows:
                user = self._legacy_user(rows[0])
        return {
            "authenticated": auth.authenticated,
            "service": auth.service,
            "user_id": auth.user_id,
            "role": auth.role,
            "firebase_uid": None,
            "email": auth.claims.get("email"),
            "user": user,
        }

    def _mobile_link(self) -> dict[str, Any]:
        def lan_fallback(message: str = "Tunnel publico indisponivel; use este QR na mesma rede Wi-Fi.") -> dict[str, Any]:
            addresses = _local_ipv4_addresses()
            lan_port = 8765 if API_PORT != 8765 else API_PORT
            if addresses:
                return {
                    "ok": True,
                    "status": "lan",
                    "url": f"http://{addresses[0]}:{lan_port}",
                    "message": message,
                    "updatedAt": "",
                }
            return {"ok": False, "status": "offline", "url": "", "message": message}

        path = ROOT / "data" / "mobile_tunnel_url.json"
        if not path.is_file():
            return lan_fallback("Tunnel de celular ainda nao iniciado; QR local para mesma rede Wi-Fi.")
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            return {"ok": False, "status": "error", "url": "", "message": str(exc)}
        if not isinstance(payload, dict):
            return {"ok": False, "status": "error", "url": "", "message": "Arquivo de tunnel invalido."}
        url = _clean_text(payload.get("url")) or ""
        if not url:
            return lan_fallback(_clean_text(payload.get("message")) or "Tunnel publico indisponivel; QR local para mesma rede Wi-Fi.")
        return {
            "ok": bool(payload.get("ok")),
            "status": _clean_text(payload.get("status")) or "unknown",
            "url": url,
            "message": _clean_text(payload.get("message")) or "",
            "updatedAt": _clean_text(payload.get("updatedAt")) or "",
        }

    def _make_auth_response(self, row: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        user = _public_user(row)
        payload = {
            "sub": row["id"],
            "role": row.get("role") or "op",
            "nick": row.get("nickname") or row["id"],
            "ver": int(row.get("token_version") or 0),
            "iat": now,
            "exp": now + AUTH_TOKEN_TTL_SECONDS,
        }
        return {
            "ok": True,
            "token": _sign_auth_payload(payload),
            "expires_at": payload["exp"],
            "user": user,
        }

    def _auth_login(self, payload: dict[str, Any]) -> dict[str, Any]:
        login = (_clean_text(payload.get("login") or payload.get("nickname") or payload.get("email")) or "").lower()
        password = payload.get("password", payload.get("senha"))
        if "@" in login:
            login = login.split("@", 1)[0]
        if not login or not password:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Login e senha obrigatorios.")
        rate_key = f"login:{self._client_ip()}:{login}"
        if not _rate_limit_allow(rate_key, LOGIN_RATE_LIMIT_MAX, LOGIN_RATE_LIMIT_WINDOW_SECONDS):
            raise ApiError(HTTPStatus.TOO_MANY_REQUESTS, "Muitas tentativas de login. Aguarde alguns minutos.")
        rows = self._query_as_service(
            """
            select u.id, u.nickname, u.badge, u.sector, u.role, u.active,
                   u.password_hash, u.password_status, u.password_reset_required,
                   u.token_version, b.user_id as banned_user_id
            from users u
            left join banned_users b on b.user_id = u.id
            where lower(u.id) = %s or u.nickname_key = lower(trim(%s))
            order by u.active desc
            limit 1
            """,
            (login, login),
        )
        if not rows:
            status = self._nickname_status(login, {"badge": [""]})
            if status.get("pending"):
                raise ApiError(HTTPStatus.FORBIDDEN, "Cadastro pendente de aprovacao.")
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Login ou senha invalido.")
        row = rows[0]
        password_ok = _verify_password(password, row.get("password_hash"))
        if not password_ok and row.get("password_reset_required"):
            temporary_passwords = {"654321"}
            badge = _clean_text(row.get("badge"))
            if badge:
                temporary_passwords.add(badge)
            password_ok = _clean_text(password) in temporary_passwords
        if not password_ok:
            raise ApiError(HTTPStatus.UNAUTHORIZED, "Login ou senha invalido.")
        if not row.get("active"):
            raise ApiError(HTTPStatus.FORBIDDEN, "Usuario inativo.")
        if row.get("banned_user_id"):
            raise ApiError(HTTPStatus.FORBIDDEN, "Usuario banido.")
        _rate_limit_clear(rate_key)
        return self._make_auth_response(row)

    def _auth_change_password(self, payload: dict[str, Any]) -> dict[str, Any]:
        auth = self._require_auth()
        new_password = payload.get("new_password", payload.get("novaSenha", payload.get("password", payload.get("senha"))))
        current_password = payload.get("current_password", payload.get("senhaAtual"))
        rows = self._query_as_service(
            """
            select id, nickname, badge, sector, role, active, password_hash,
                   password_status, password_reset_required, token_version
            from users
            where id = %s
            limit 1
            """,
            (auth.user_id,),
        )
        if not rows:
            raise ApiError(HTTPStatus.NOT_FOUND, "Usuario nao encontrado.")
        row = rows[0]
        if not row.get("password_reset_required") and row.get("password_hash"):
            if not _verify_password(current_password, row.get("password_hash")):
                raise ApiError(HTTPStatus.UNAUTHORIZED, "Senha atual invalida.")
        updated = self._execute_one(
            """
            update users
            set password_hash = %s,
                password_status = 'definida',
                password_reset_required = false,
                password_changed_at = now(),
                token_version = token_version + 1,
                raw_data = raw_data || %s::jsonb
            where id = %s
            returning id, nickname, badge, sector, role, active,
                      password_status, password_reset_required, token_version
            """,
            (
                _password_hash(new_password),
                json.dumps({"senha": "definida", "senhaReset": False}, ensure_ascii=False),
                auth.user_id,
            ),
        )
        return self._make_auth_response(updated)

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

    def _inventory_legacy_snapshot(self) -> dict[str, Any]:
        rows = self._query(
            """
            select payload, saved_at, raw_metadata, updated_by
            from inventory_snapshots
            order by saved_at desc
            limit 1
            """
        )
        latest_snapshot = rows[0] if rows else {}
        payload = latest_snapshot.get("payload") if isinstance(latest_snapshot.get("payload"), dict) else {}
        metadata = latest_snapshot.get("raw_metadata") if isinstance(latest_snapshot.get("raw_metadata"), dict) else {}
        if not payload:
            items = self._query("select raw_data from inventory_items where not is_dead order by description nulls last")
            dead_items = self._query("select raw_data from inventory_items where is_dead order by description nulls last")
            payload = {
                "dados": [row.get("raw_data") or {} for row in items],
                "dadosMortos": [row.get("raw_data") or {} for row in dead_items],
            }
        ultima_atualizacao = (
            payload.get("ultimaAtualizacao")
            or payload.get("ultima_atualizacao")
            or metadata.get("ultimaAtualizacao")
            or metadata.get("ultima_atualizacao")
            or latest_snapshot.get("saved_at")
        )
        ultima_dt = _timestamp(ultima_atualizacao)
        if ultima_dt:
            payload = {
                **payload,
                "ultimaAtualizacao": int(ultima_dt.timestamp() * 1000),
                "ultimaAtualizacaoIso": ultima_dt.isoformat(),
            }
        if not payload.get("atualizadoPor") and (metadata.get("atualizadoPor") or latest_snapshot.get("updated_by")):
            payload = {**payload, "atualizadoPor": metadata.get("atualizadoPor") or latest_snapshot.get("updated_by")}
        ajustes = self._query(
            """
            select legacy_key, item_legacy_key, min_qty, max_qty, reorder_qty, updated_by_name, updated_at, raw_data
            from inventory_adjustments
            order by updated_at desc nulls last, id desc
            """
        )
        ajustes_map: dict[str, Any] = {}
        for row in ajustes:
            legacy_key = _clean_text(row.get("legacy_key") or row.get("item_legacy_key"))
            if not legacy_key or legacy_key in ajustes_map:
                continue
            raw = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
            ajustes_map[legacy_key] = {
                **raw,
                "itemKey": raw.get("itemKey") or row.get("item_legacy_key"),
                "minimo": raw.get("minimo", row.get("min_qty")),
                "maximo": raw.get("maximo", row.get("max_qty")),
                "reposicao": raw.get("reposicao", row.get("reorder_qty")),
                "atualizadoPor": raw.get("atualizadoPor") or row.get("updated_by_name"),
                "atualizadoEm": raw.get("atualizadoEm") or row.get("updated_at"),
            }
        if ajustes_map:
            payload = {**payload, "ajustesItens": ajustes_map}
        historico_atual = payload.get("historicoSaldo")
        if not isinstance(historico_atual, dict) or not historico_atual:
            historico_rows = self._query(
                """
                select item_legacy_key, event_at, event_date_label, previous_balance,
                       current_balance, delta, event_type, raw_data
                from inventory_balance_history
                order by item_legacy_key nulls last, event_at nulls last, id
                """
            )
            historico_map: dict[str, list[Any]] = {}
            for row in historico_rows:
                item_key = _clean_text(row.get("item_legacy_key"))
                if not item_key:
                    continue
                raw = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
                evento = {
                    **raw,
                    "data": raw.get("data") or row.get("event_date_label"),
                    "saldoAnterior": raw.get("saldoAnterior", row.get("previous_balance")),
                    "saldoAtual": raw.get("saldoAtual", row.get("current_balance")),
                    "delta": raw.get("delta", row.get("delta")),
                    "tipo": raw.get("tipo") or row.get("event_type"),
                }
                if not evento.get("timestamp") and row.get("event_at"):
                    evento["timestamp"] = int(row["event_at"].timestamp() * 1000)
                historico_map.setdefault(item_key, []).append(evento)
            if historico_map:
                payload = {**payload, "historicoSaldo": historico_map}
        return payload

    def _put_inventory_adjustment(self, code: str, payload: dict[str, Any]) -> dict[str, Any]:
        item_key = _clean_text(payload.get("itemKey") or payload.get("item_key") or code)
        legacy_key = _clean_text(payload.get("legacy_key") or payload.get("chave") or payload.get("key")) or item_key
        updated_at = _timestamp(payload.get("atualizadoEm") or payload.get("updated_at")) or datetime.now(timezone.utc)
        updated_by = _clean_text(payload.get("atualizadoPor") or payload.get("updated_by"))
        raw_data = {
            **payload,
            "itemKey": item_key,
            "atualizadoEm": int(updated_at.timestamp() * 1000),
            "atualizadoPor": updated_by,
        }
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("set local app.role = 'service'")
                cur.execute("delete from inventory_adjustments where legacy_key = %s", (legacy_key,))
                cur.execute(
                    """
                    insert into inventory_adjustments (
                      item_id, item_legacy_key, legacy_key, min_qty, max_qty, reorder_qty,
                      reason, updated_by_name, updated_at, raw_data
                    )
                    values (
                      (select id from inventory_items where protheus_code = %s or cooperat_code = %s or legacy_key = %s order by is_dead asc limit 1),
                      %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                    )
                    returning id, item_legacy_key, legacy_key, min_qty, max_qty, reorder_qty, updated_by_name, updated_at, raw_data
                    """,
                    (
                        item_key,
                        item_key,
                        item_key,
                        item_key,
                        legacy_key,
                        _decimal_value(payload.get("minimo") or payload.get("min_qty")),
                        _decimal_value(payload.get("maximo") or payload.get("max_qty")),
                        _decimal_value(payload.get("reposicao") or payload.get("reorder_qty")),
                        _clean_text(payload.get("motivo") or payload.get("reason")) or "dashboard",
                        updated_by,
                        updated_at,
                        json.dumps(raw_data, ensure_ascii=False, default=_json_default),
                    ),
                )
                row = dict(cur.fetchone())
        return {"ok": True, "adjustment": row}

    def _post_inventory_automus_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        incoming_payload = payload
        previous_payload = self._inventory_legacy_snapshot()
        imported_at = _timestamp(incoming_payload.get("ultimaAtualizacao")) or datetime.now(timezone.utc)
        payload = _merge_automus_payload(incoming_payload, previous_payload, imported_at)
        dados = payload.get("dados") if isinstance(payload.get("dados"), list) else []
        dados_mortos = payload.get("dadosMortos") if isinstance(payload.get("dadosMortos"), list) else []
        if not dados:
            raise ApiError(HTTPStatus.BAD_REQUEST, "`dados` nao pode estar vazio.")
        hash_after = _json_hash(payload)
        updated_by = _clean_text(payload.get("atualizadoPor") or payload.get("updated_by"))
        auth = getattr(self, "auth_context", AuthContext(role="service", service=True))

        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute("select set_config('app.role', 'service', true)")
                cur.execute("select set_config('app.user_id', %s, true)", (auth.user_id or "",))
                cur.execute("delete from inventory_movements")
                cur.execute("delete from inventory_balance_history")
                cur.execute("delete from inventory_adjustments")
                cur.execute("delete from inventory_item_limits")
                cur.execute("delete from inventory_item_addresses")
                cur.execute("delete from inventory_items")

                cur.execute(
                    """
                    insert into inventory_snapshots (
                      source, saved_at, hash_before, hash_after, updated_by,
                      item_count, dead_item_count, payload, raw_metadata
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                    returning id
                    """,
                    (
                        "api:inventory/automus-update",
                        imported_at,
                        _clean_text(payload.get("hashAntes") or payload.get("hash_before")),
                        hash_after,
                        updated_by,
                        len(dados),
                        len(dados_mortos),
                        json.dumps(payload, ensure_ascii=False, default=_json_default),
                        json.dumps(
                            {
                                "ultimaAtualizacao": payload.get("ultimaAtualizacao"),
                                "ultimaAtualizacaoAutomatica": payload.get("ultimaAtualizacaoAutomatica"),
                                "mapeamentoArquivos": payload.get("mapeamentoArquivos"),
                                "automus": payload.get("automus"),
                            },
                            ensure_ascii=False,
                            default=_json_default,
                        ),
                    ),
                )
                snapshot_id = str(cur.fetchone()["id"])

                item_ids: dict[str, int] = {}
                addresses_loaded = 0
                limits_loaded = 0
                for item, dead in [(i, False) for i in dados if isinstance(i, dict)] + [(i, True) for i in dados_mortos if isinstance(i, dict)]:
                    legacy_key = _inventory_legacy_key(item, dead)
                    cur.execute(
                        """
                        insert into inventory_items (
                          legacy_key, protheus_code, protheus_key, cooperat_code, description,
                          primary_address, primary_warehouse, balance, min_qty, max_qty, reorder_qty,
                          limit_source, min_source, max_source, reorder_source, is_dead, status,
                          updated_at, raw_data
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        returning id
                        """,
                        (
                            legacy_key,
                            _clean_text(item.get("protheus")),
                            _clean_text(item.get("protheusKey")),
                            _clean_text(item.get("cooperat")),
                            _clean_text(item.get("descricao")),
                            _clean_text(item.get("enderecoPrincipal")),
                            _clean_text(item.get("armazemPrincipal")),
                            _decimal_value(item.get("saldo")),
                            _decimal_value(item.get("minimo")),
                            _decimal_value(item.get("maximo")),
                            _decimal_value(item.get("reposicao")),
                            _clean_text(item.get("limitesOrigem")),
                            _clean_text(item.get("minimoOrigem")),
                            _clean_text(item.get("maximoOrigem")),
                            _clean_text(item.get("reposicaoOrigem")),
                            bool(item.get("morto") or dead),
                            "dead" if bool(item.get("morto") or dead) else "active",
                            imported_at,
                            json.dumps(item, ensure_ascii=False, default=_json_default),
                        ),
                    )
                    item_id = int(cur.fetchone()["id"])
                    item_ids[legacy_key] = item_id
                    for alias in (_clean_text(item.get("protheus")), _clean_text(item.get("protheusKey")), _clean_text(item.get("cooperat"))):
                        if alias:
                            item_ids.setdefault(alias, item_id)

                    for address in item.get("enderecos") if isinstance(item.get("enderecos"), list) else []:
                        if not isinstance(address, dict):
                            continue
                        cur.execute(
                            """
                            insert into inventory_item_addresses (
                              item_id, item_legacy_key, address, warehouse, balance, source, raw_data
                            )
                            values (%s, %s, %s, %s, %s, %s, %s::jsonb)
                            """,
                            (
                                item_id,
                                legacy_key,
                                _clean_text(address.get("endereco")),
                                _clean_text(address.get("armazem")),
                                _decimal_value(address.get("saldo")),
                                "api:inventory/automus-update/enderecos",
                                json.dumps(address, ensure_ascii=False, default=_json_default),
                            ),
                        )
                        addresses_loaded += 1

                    limites = item.get("limitesCooperat")
                    if isinstance(limites, dict):
                        cur.execute(
                            """
                            insert into inventory_item_limits (
                              item_id, item_legacy_key, source, min_qty, max_qty, reorder_qty,
                              previous_balance, applied, imported_at, raw_data
                            )
                            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                            """,
                            (
                                item_id,
                                legacy_key,
                                "cooperat",
                                _decimal_value(limites.get("minimo")),
                                _decimal_value(limites.get("maximo")),
                                _decimal_value(limites.get("reposicao")),
                                _decimal_value(limites.get("saldoAnterior")),
                                item.get("limitesOrigem") == "cooperat",
                                imported_at,
                                json.dumps(limites, ensure_ascii=False, default=_json_default),
                            ),
                        )
                        limits_loaded += 1

                adjustments_loaded = self._insert_inventory_adjustments(cur, payload, item_ids, imported_at)
                history_loaded = self._insert_inventory_history(cur, payload, item_ids)
                movements_loaded = self._insert_inventory_movements(cur, payload)

        return {
            "ok": True,
            "snapshot_id": snapshot_id,
            "hash_after": hash_after,
            "items_loaded": len(dados) + len(dados_mortos),
            "active_items": len(dados),
            "dead_items": len(dados_mortos),
            "addresses_loaded": addresses_loaded,
            "limits_loaded": limits_loaded,
            "adjustments_loaded": adjustments_loaded,
            "balance_history_loaded": history_loaded,
            "movements_loaded": movements_loaded,
        }

    def _insert_inventory_adjustments(self, cur: Any, payload: dict[str, Any], item_ids: dict[str, int], imported_at: datetime) -> int:
        ajustes = payload.get("ajustesItens") if isinstance(payload.get("ajustesItens"), dict) else {}
        loaded = 0
        for legacy_key, ajuste in ajustes.items():
            if not isinstance(ajuste, dict):
                continue
            item_key = _clean_text(ajuste.get("itemKey")) or _decode_legacy_key(str(legacy_key))
            cur.execute(
                """
                insert into inventory_adjustments (
                  item_id, item_legacy_key, legacy_key, min_qty, max_qty, reorder_qty,
                  reason, updated_by_name, updated_at, raw_data
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    item_ids.get(item_key or ""),
                    item_key,
                    str(legacy_key),
                    _decimal_value(ajuste.get("minimo")),
                    _decimal_value(ajuste.get("maximo")),
                    _decimal_value(ajuste.get("reposicao")),
                    "api:inventory/automus-update/ajustesItens",
                    _clean_text(ajuste.get("atualizadoPor")),
                    _timestamp(ajuste.get("atualizadoEm")) or imported_at,
                    json.dumps(ajuste, ensure_ascii=False, default=_json_default),
                ),
            )
            loaded += 1
        return loaded

    def _insert_inventory_history(self, cur: Any, payload: dict[str, Any], item_ids: dict[str, int]) -> int:
        historico = payload.get("historicoSaldo") if isinstance(payload.get("historicoSaldo"), dict) else {}
        loaded = 0
        for encoded_key, events in historico.items():
            item_key = _decode_legacy_key(str(encoded_key))
            if not isinstance(events, list):
                continue
            for event in events:
                if not isinstance(event, dict):
                    continue
                cur.execute(
                    """
                    insert into inventory_balance_history (
                      item_id, item_legacy_key, event_at, event_date_label, previous_balance,
                      current_balance, delta, event_type, source, raw_data
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        item_ids.get(item_key),
                        item_key,
                        _timestamp(event.get("timestamp")),
                        _clean_text(event.get("data")),
                        _decimal_value(event.get("saldoAnterior")),
                        _decimal_value(event.get("saldoAtual")),
                        _decimal_value(event.get("delta")),
                        _clean_text(event.get("tipo")),
                        "api:inventory/automus-update/historicoSaldo",
                        json.dumps(event, ensure_ascii=False, default=_json_default),
                    ),
                )
                loaded += 1
        return loaded

    def _insert_inventory_movements(self, cur: Any, payload: dict[str, Any]) -> int:
        movimentacoes = payload.get("movimentacoesMata185")
        if not isinstance(movimentacoes, dict):
            return 0
        cur.execute(
            """
            insert into inventory_movements (
              source, source_document, movement_at, movement_type, status, raw_data
            )
            values (%s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                "api:inventory/automus-update/movimentacoesMata185",
                "movimentacoesMata185",
                _timestamp(movimentacoes.get("atualizadoEm")),
                "snapshot",
                "raw",
                json.dumps(movimentacoes, ensure_ascii=False, default=_json_default),
            ),
        )
        return 1

    def _users(self, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 100, 500)
        offset = _offset(query)
        rows = self._query(
            """
            select id, firebase_uid, nickname, nickname_key, badge, sector, role,
                   active, password_status, password_reset_required, created_at, updated_at
            from users
            order by nickname nulls last
            limit %s offset %s
            """,
            (limit, offset),
        )
        return {"users": [self._legacy_user(row) for row in rows], "limit": limit, "offset": offset}

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
        return {"signup_requests": [self._legacy_signup_request(row) for row in rows], "limit": limit}

    def _signup_request(self, request_id: str) -> dict[str, Any]:
        rows = self._query(
            """
            select id, requested_uid, nickname, nickname_key, badge, sector,
                   status, duplicated, created_at, decided_at, decided_by
            from signup_requests
            where id = %s
            limit 1
            """,
            (request_id,),
        )
        if not rows:
            raise ApiError(HTTPStatus.NOT_FOUND, "Solicitacao nao encontrada.")
        return {"signup_request": self._legacy_signup_request(rows[0])}

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
        return {"banned_users": [self._legacy_banned_user(row) for row in rows], "limit": limit}

    def _legacy_user(self, row: dict[str, Any]) -> dict[str, Any]:
        created_at = row.get("created_at")
        return {
            **row,
            "uid": row.get("id"),
            "nickname": row.get("nickname") or "",
            "cracha": row.get("badge") or "",
            "setor": row.get("sector") or "",
            "nivel": row.get("role") or "op",
            "ativo": bool(row.get("active")),
            "senha": row.get("password_status") or "",
            "senhaReset": bool(row.get("password_reset_required")) or row.get("password_status") == "reset_required",
            "criadoEm": int(created_at.timestamp() * 1000) if isinstance(created_at, datetime) else 0,
        }

    def _user(self, user_id: str) -> dict[str, Any]:
        rows = self._query(
            """
            select id, firebase_uid, nickname, nickname_key, badge, sector, role,
                   active, password_status, password_reset_required, created_at, updated_at
            from users
            where id = %s or firebase_uid = %s
            limit 1
            """,
            (user_id, user_id),
        )
        if not rows:
            raise ApiError(HTTPStatus.NOT_FOUND, "Usuario nao encontrado.")
        return {"user": self._legacy_user(rows[0])}

    def _legacy_signup_request(self, row: dict[str, Any]) -> dict[str, Any]:
        created_at = row.get("created_at")
        decided_at = row.get("decided_at")
        return {
            **row,
            "uid": row.get("requested_uid") or "",
            "nickname": row.get("nickname") or "",
            "cracha": row.get("badge") or "",
            "setor": row.get("sector") or "",
            "status": row.get("status") or "pendente",
            "duplicado": bool(row.get("duplicated")),
            "criadoEm": int(created_at.timestamp() * 1000) if isinstance(created_at, datetime) else 0,
            "decididoEm": int(decided_at.timestamp() * 1000) if isinstance(decided_at, datetime) else 0,
        }

    def _legacy_banned_user(self, row: dict[str, Any]) -> dict[str, Any]:
        banned_at = row.get("banned_at")
        nickname = row.get("nickname") or ""
        return {
            **row,
            "uid": row.get("user_id"),
            "nickname": nickname,
            "cracha": row.get("badge") or "",
            "setor": row.get("sector") or "",
            "emailLogin": f"{nickname}@sistema.com" if nickname else "",
            "senha": "[redacted]",
            "banidoEm": int(banned_at.timestamp() * 1000) if isinstance(banned_at, datetime) else 0,
        }

    def _nickname_status(self, nickname: str, query: dict[str, list[str]]) -> dict[str, Any]:
        nick = _clean_text(nickname)
        if not nick:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Nickname obrigatorio.")
        badge = _clean_text(query.get("badge", [""])[0])
        user_rows = self._query_as_service(
            """
            select count(*)::int as count
            from users
            where nickname_key = lower(trim(%s)) and active
            """,
            (nick,),
        )
        pending_rows = self._query_as_service(
            """
            select id
            from signup_requests
            where nickname_key = lower(trim(%s))
              and status = 'pendente'
              and (%s::text is null or badge = %s)
            order by created_at desc nulls last
            limit 1
            """,
            (nick, badge, badge),
        )
        banned_rows = self._query_as_service(
            """
            select count(*)::int as count
            from banned_users
            where lower(trim(nickname)) = lower(trim(%s))
            """,
            (nick,),
        )
        return {
            "nickname": nick,
            "used": bool(user_rows and user_rows[0]["count"] > 0),
            "banned": bool(banned_rows and banned_rows[0]["count"] > 0),
            "pending": bool(pending_rows),
            "pending_request_id": pending_rows[0]["id"] if pending_rows else "",
        }

    def _post_signup_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        nickname = _clean_text(payload.get("nickname"))
        badge = _clean_text(payload.get("badge") or payload.get("cracha"))
        sector = _clean_text(payload.get("sector") or payload.get("setor"))
        password = _clean_text(payload.get("password") or payload.get("senha"))
        if not nickname or not badge or not sector:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Nickname, cracha e setor sao obrigatorios.")
        if not password:
            raise ApiError(HTTPStatus.BAD_REQUEST, "Senha obrigatoria.")
        if not re.match(r"^[A-Za-z0-9_.-]{3,20}$", nickname):
            raise ApiError(HTTPStatus.BAD_REQUEST, "Nickname invalido.")
        status = self._nickname_status(nickname, {"badge": [badge]})
        if status["pending"] and status["pending_request_id"]:
            return {"ok": True, "duplicate": True, "signup_request": {"id": status["pending_request_id"], "status": "pendente"}}
        request_id = _clean_text(payload.get("id")) or f"sql_{int(datetime.now(timezone.utc).timestamp() * 1000)}_{_firebase_like_key(nickname)}"
        duplicated = bool(status["used"] or status["banned"])
        created_at = _timestamp(payload.get("created_at") or payload.get("criadoEm")) or datetime.now(timezone.utc)
        raw_data = {
            "uid": _clean_text(payload.get("uid")) or "",
            "nickname": nickname,
            "cracha": badge,
            "setor": sector,
            "status": "pendente",
            "duplicado": duplicated,
            "criadoEm": int(created_at.timestamp() * 1000),
            "senha": "[redacted]" if password else "",
            "source": "api:signup-requests",
        }
        row = self._query_as_service(
            """
            insert into signup_requests (
              id, requested_uid, nickname, password_plain_legacy, password_hash, badge, sector,
              status, duplicated, created_at, raw_data
            )
            values (%s, %s, %s, null, %s, %s, %s, 'pendente', %s, %s, %s::jsonb)
            on conflict (id) do update set
              nickname = excluded.nickname,
              password_hash = excluded.password_hash,
              badge = excluded.badge,
              sector = excluded.sector,
              duplicated = excluded.duplicated,
              raw_data = excluded.raw_data
            returning id, requested_uid, nickname, nickname_key, badge, sector,
                      status, duplicated, created_at, decided_at, decided_by
            """,
            (
                request_id,
                _clean_text(payload.get("uid")) or request_id,
                nickname,
                _password_hash(password),
                badge,
                sector,
                duplicated,
                created_at,
                json.dumps(raw_data, ensure_ascii=False),
            ),
        )
        return {"ok": True, "signup_request": self._legacy_signup_request(row[0])}

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
                password_reset_required = coalesce(%s, password_reset_required),
                sector = coalesce(%s, sector),
                badge = coalesce(%s, badge),
                raw_data = %s::jsonb
            where id = %s
            returning id, firebase_uid, nickname, badge, sector, role,
                      active, password_status, password_reset_required, created_at, updated_at
            """,
            (
                _clean_text(payload.get("role") or payload.get("nivel")),
                payload.get("active") if isinstance(payload.get("active"), bool) else payload.get("ativo") if isinstance(payload.get("ativo"), bool) else None,
                _clean_text(payload.get("password_status") or payload.get("senha")),
                payload.get("password_reset_required") if isinstance(payload.get("password_reset_required"), bool) else payload.get("senhaReset") if isinstance(payload.get("senhaReset"), bool) else None,
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
            set password_hash = coalesce(%s, password_hash),
                password_status = 'reset_required',
                password_reset_required = true,
                token_version = token_version + 1,
                raw_data = raw_data || %s::jsonb
            where id = %s
            returning id, nickname, role, active, password_status, password_reset_required
            """,
            (
                _password_hash(payload.get("password") or payload.get("senha")) if (payload.get("password") or payload.get("senha")) else None,
                json.dumps({"senha": "", "senhaReset": True, **payload}, ensure_ascii=False),
                user_id,
            ),
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
              password_hash, password_status, password_reset_required, created_at, updated_at, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, true, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (id) do update set
              nickname = excluded.nickname,
              badge = excluded.badge,
              sector = excluded.sector,
              role = excluded.role,
              active = true,
              password_hash = coalesce(excluded.password_hash, users.password_hash),
              password_status = excluded.password_status,
              password_reset_required = excluded.password_reset_required,
              updated_at = excluded.updated_at,
              raw_data = excluded.raw_data
            returning id, firebase_uid, nickname, badge, sector, role, active,
                      password_status, password_reset_required, token_version
            """,
            (
                user_id,
                user_id,
                req.get("nickname"),
                req.get("badge"),
                req.get("sector"),
                role,
                req.get("password_hash"),
                "definida" if req.get("password_hash") else "reset_required",
                not bool(req.get("password_hash")),
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

    def _dashboard_snapshot(self, query: dict[str, list[str]]) -> dict[str, Any]:
        inventory = self._inventory_legacy_snapshot()
        panels = self._query("select id, row_limit, hidden_codes, raw_data from dashboard_panels order by id")
        evaluations = self._query("select legacy_key, raw_data from purchase_evaluations order by updated_at desc nulls last, id desc limit 2000")
        panel_config: dict[str, Any] = {}
        for row in panels:
            raw = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
            panel_config[str(row["id"])] = {
                **raw,
                "limite": raw.get("limite", row.get("row_limit")),
                "codigosOcultos": raw.get("codigosOcultos", ",".join(row.get("hidden_codes") or [])),
            }
        evaluation_config: dict[str, Any] = {}
        for row in evaluations:
            raw = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
            evaluation_config[str(row["legacy_key"])] = raw

        counting = self._counting_history({"limit": query.get("counting_limit", query.get("limit", ["1000"]))})
        label_rows = self._query(
            """
            select legacy_path, user_name, job_date, created_at, total_labels,
                   total_codes_submitted, raw_data
            from label_print_jobs
            order by created_at desc nulls last
            limit %s
            """,
            (_limit(query, 500, 5000),),
        )
        etiquetas: dict[str, dict[str, dict[str, Any]]] = {}
        ranking: dict[str, Any] = {}
        for row in label_rows:
            raw = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
            data_key = _clean_text(raw.get("data"))
            if not data_key and row.get("job_date"):
                data_key = row["job_date"].isoformat()
            data_key = data_key or "sem_data"
            user_name = _clean_text(raw.get("usuario") or row.get("user_name")) or "desconhecido"
            user_key = _firebase_like_key(user_name)
            legacy_path = _clean_text(row.get("legacy_path")) or f"api:labels/{data_key}/{user_key}/{int((row.get('created_at') or datetime.now(timezone.utc)).timestamp() * 1000)}"
            record_key = legacy_path.rstrip("/").split("/")[-1]
            payload = {
                **raw,
                "usuario": user_name,
                "data": data_key,
                "timestamp": raw.get("timestamp") or int((row.get("created_at") or datetime.now(timezone.utc)).timestamp() * 1000),
                "totalEtiquetas": raw.get("totalEtiquetas", row.get("total_labels")),
                "totalCodigosInformados": raw.get("totalCodigosInformados", row.get("total_codes_submitted")),
            }
            etiquetas.setdefault(data_key, {}).setdefault(user_key, {})[record_key] = payload
            current = ranking.setdefault(user_key, {"usuario": user_name, "eventos": 0, "totalEtiquetas": 0})
            current["eventos"] += 1
            current["totalEtiquetas"] += _int_value(payload.get("totalEtiquetas"), 0)

        return {
            "inventory": inventory,
            "dashboardConfig": {
                "paineis": panel_config,
                "avaliadorPedidos": evaluation_config,
            },
            "contagens": counting.get("contagens", {}),
            "contagemRascunhos": counting.get("rascunhos", {}),
            "etiquetasGeradas": etiquetas,
            "rankingEtiquetas": ranking,
        }

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

    def _delete_dashboard_evaluation(self, legacy_key: str) -> dict[str, Any]:
        row = self._execute_one(
            "delete from purchase_evaluations where legacy_key = %s returning legacy_key",
            (legacy_key,),
        )
        return {"ok": True, "deleted": bool(row), "legacy_key": legacy_key}

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

    def _counting_history(self, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 500, 5000)
        session_rows = self._query(
            """
            select id, legacy_path, session_date, user_id, user_name, uid, machine,
                   started_at, created_at, total_items, total_quantity_items,
                   total_empty_checks, is_draft, source, raw_data
            from counting_sessions
            order by session_date desc nulls last, created_at desc nulls last
            limit %s
            """,
            (limit,),
        )
        contagens: dict[str, dict[str, dict[str, Any]]] = {}
        for row in session_rows:
            raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
            raw_data = {
                **raw_data,
                "_sqlSessionId": str(row.get("id")),
                "_sqlLegacyPath": row.get("legacy_path"),
            }
            session_date = _clean_text(raw_data.get("data"))
            if not session_date and row.get("session_date"):
                session_date = row["session_date"].isoformat()
            session_date = session_date or "sem_data"
            user_name = _clean_text(raw_data.get("usuario") or row.get("user_name") or row.get("uid")) or "desconhecido"
            user_key = _firebase_like_key(user_name)
            legacy_path = _clean_text(row.get("legacy_path")) or str(row.get("id"))
            record_key = legacy_path.rstrip("/").split("/")[-1] or str(row.get("id"))
            contagens.setdefault(session_date, {}).setdefault(user_key, {})[record_key] = raw_data

        draft_rows = self._query(
            """
            select id, user_id, uid, user_name, cycle, machine, updated_at,
                   values_json, empty_checks_json, system_balances_json, session_json, raw_data
            from counting_drafts
            order by updated_at desc nulls last
            limit %s
            """,
            (limit,),
        )
        rascunhos: dict[str, Any] = {}
        for row in draft_rows:
            raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
            if not raw_data:
                raw_data = {
                    "uid": row.get("uid"),
                    "usuario": row.get("user_name"),
                    "maquina": row.get("machine"),
                    "ciclo": row.get("cycle"),
                    "updatedAt": row.get("updated_at"),
                    "valores": row.get("values_json") or {},
                    "verificacoesVazio": row.get("empty_checks_json") or {},
                    "saldosSistema": row.get("system_balances_json") or {},
                    "sessao": row.get("session_json") or {},
                }
            draft_key = _clean_text(row.get("uid")) or _firebase_like_key(row.get("user_name"), str(row.get("id")))
            rascunhos[draft_key] = raw_data

        return {
            "contagens": contagens,
            "rascunhos": rascunhos,
            "sessions": session_rows,
            "drafts": draft_rows,
            "limit": limit,
        }

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

    def _patch_counting_session_user(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        new_user = _clean_text(payload.get("usuario") or payload.get("user_name"))
        if not new_user:
            raise ApiError(HTTPStatus.BAD_REQUEST, "`usuario` e obrigatorio.")
        corrected_by = _clean_text(payload.get("corrigidoPor") or payload.get("corrected_by"))
        corrected_at = _timestamp(payload.get("corrigidoEm") or payload.get("corrected_at")) or datetime.now(timezone.utc)
        user_rows = self._query(
            """
            select id, firebase_uid, nickname
            from users
            where lower(nickname) = lower(%s) or id = %s or firebase_uid = %s
            order by active desc nulls last
            limit 1
            """,
            (new_user, new_user, new_user),
        )
        user_id = user_rows[0]["id"] if user_rows else None
        resolved_uid = user_rows[0].get("firebase_uid") or user_id if user_rows else None
        row = self._execute_one(
            """
            update counting_sessions
            set user_id = %s,
                user_name = %s,
                uid = coalesce(%s, uid),
                raw_data = coalesce(raw_data, '{}'::jsonb) || %s::jsonb
            where id = %s
            returning id, legacy_path, session_date, user_id, user_name, uid, machine,
                      created_at, total_items, total_empty_checks
            """,
            (
                user_id,
                new_user,
                resolved_uid,
                json.dumps(
                    {
                        "usuario": new_user,
                        "uid": resolved_uid,
                        "corrigidoPor": corrected_by,
                        "corrigidoEm": int(corrected_at.timestamp() * 1000),
                        "usuarioAnterior": payload.get("usuarioAnterior"),
                    },
                    ensure_ascii=False,
                    default=_json_default,
                ),
                session_id,
            ),
        )
        if not row:
            raise ApiError(HTTPStatus.NOT_FOUND, "Sessao de contagem nao encontrada.")
        return {"ok": True, "session": row}

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
        self._execute_one("delete from counting_drafts returning id")
        return {"ok": True, "reset": setting["setting"]}

    def _system_update_script(self) -> Path:
        candidates = [
            Path(_env("DARK_JUTSU_UPDATE_SCRIPT")),
            ROOT / "scripts" / "atualizar_darkjutsu_do_github.bat",
            ROOT.parent / "scripts" / "atualizar_darkjutsu_do_github.bat",
            ROOT.parent.parent / "scripts" / "atualizar_darkjutsu_do_github.bat",
            Path(r"\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\scripts\atualizar_darkjutsu_do_github.bat"),
        ]
        for candidate in candidates:
            if str(candidate) and candidate.is_file():
                return candidate
        raise ApiError(HTTPStatus.NOT_FOUND, "Script de atualizacao GitHub nao encontrado.")

    def _system_update_status(self) -> dict[str, Any]:
        commit = ""
        log_tail = ""
        try:
            if SYSTEM_UPDATE_VERSION_FILE.is_file():
                commit = SYSTEM_UPDATE_VERSION_FILE.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            commit = ""
        try:
            if SYSTEM_UPDATE_LOG.is_file():
                lines = SYSTEM_UPDATE_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
                log_tail = "\n".join(lines[-25:])
        except Exception:
            log_tail = ""
        return {
            "ok": True,
            "running": SYSTEM_UPDATE_RUNNING,
            "last": SYSTEM_UPDATE_LAST,
            "commit": commit,
            "log_tail": log_tail,
        }

    def _post_system_update_from_github(self, payload: dict[str, Any]) -> dict[str, Any]:
        global SYSTEM_UPDATE_RUNNING, SYSTEM_UPDATE_LAST
        with SYSTEM_UPDATE_LOCK:
            if SYSTEM_UPDATE_RUNNING:
                return self._system_update_status()
            SYSTEM_UPDATE_RUNNING = True
        started = datetime.now(timezone.utc)
        script = self._system_update_script()
        cmd = ["cmd.exe", "/c", str(script)]
        if bool(payload.get("force") or payload.get("forcar")):
            cmd.append("--force")
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(script.parent),
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
            SYSTEM_UPDATE_LAST = {
                "started_at": started.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "returncode": completed.returncode,
                "forced": bool(payload.get("force") or payload.get("forcar")),
                "stdout": (completed.stdout or "")[-4000:],
                "stderr": (completed.stderr or "")[-4000:],
            }
            return {**self._system_update_status(), "ok": completed.returncode == 0}
        except subprocess.TimeoutExpired as exc:
            SYSTEM_UPDATE_LAST = {
                "started_at": started.isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "returncode": 124,
                "forced": bool(payload.get("force") or payload.get("forcar")),
                "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                "stderr": "Tempo limite excedido ao atualizar pelo GitHub.",
            }
            raise ApiError(HTTPStatus.GATEWAY_TIMEOUT, "Atualizacao GitHub excedeu o tempo limite.")
        finally:
            with SYSTEM_UPDATE_LOCK:
                SYSTEM_UPDATE_RUNNING = False

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
        rows = self._query(
            """
            select id, label, public, password_hash is not null as has_password, updated_at
            from chat_rooms
            order by public desc, id
            """
        )
        return {"rooms": rows}

    def _chat_room_password_status(self, room_id: str) -> dict[str, Any]:
        rows = self._query(
            "select id, public, password_hash is not null as has_password from chat_rooms where id = %s",
            (room_id,),
        )
        if not rows:
            raise ApiError(HTTPStatus.NOT_FOUND, "Sala de chat nao encontrada.")
        return {"room_id": room_id, "public": rows[0]["public"], "has_password": rows[0]["has_password"]}

    def _chat_messages(self, room_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
        limit = _limit(query, 100, 500)
        rows = self._query(
            """
            select id, legacy_key, room_id, user_id, name, text, time_label,
                   created_at, message_type, event, session_id, raw_data
            from chat_messages
            where room_id = %s
            order by created_at desc nulls last, id desc
            limit %s
            """,
            (room_id, limit),
        )
        return {"messages": rows, "limit": limit}

    def _chat_read_state(self, user_id: str) -> dict[str, Any]:
        rows = self._query(
            """
            select room_id, last_seen_at
            from chat_read_states
            where user_id = %s
            """,
            (user_id,),
        )
        states = {
            row["room_id"]: int(row["last_seen_at"].timestamp() * 1000) if row.get("last_seen_at") else 0
            for row in rows
        }
        return {"user_id": user_id, "read_state": states}

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

    def _put_chat_room_password(self, room_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        password = _clean_text(payload.get("password") or payload.get("senha"))
        if room_id == "publica":
            raise ApiError(HTTPStatus.BAD_REQUEST, "Sala publica nao usa senha.")
        if not password or not re.match(r"^\d{6}$", password):
            raise ApiError(HTTPStatus.BAD_REQUEST, "A senha deve ter 6 digitos.")
        row = self._execute_one(
            """
            update chat_rooms
            set password_hash = %s,
                raw_data = jsonb_set(raw_data - 'senha' - 'password', '{passwordStatus}', '"defined"', true)
            where id = %s
            returning id, password_hash is not null as has_password, updated_at
            """,
            (_chat_password_hash(room_id, password), room_id),
        )
        if not row:
            raise ApiError(HTTPStatus.NOT_FOUND, "Sala de chat nao encontrada.")
        return {"ok": True, "room": row}

    def _verify_chat_room_password(self, room_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        password = payload.get("password", payload.get("senha"))
        rows = self._query(
            "select id, public, password_hash from chat_rooms where id = %s",
            (room_id,),
        )
        if not rows:
            raise ApiError(HTTPStatus.NOT_FOUND, "Sala de chat nao encontrada.")
        room = rows[0]
        valid = bool(room.get("public")) or _verify_chat_password(room_id, password, room.get("password_hash"))
        return {"ok": True, "room_id": room_id, "valid": valid, "has_password": bool(room.get("password_hash"))}

    def _delete_chat_messages(self, room_id: str) -> dict[str, Any]:
        if not self._query("select 1 from chat_rooms where id = %s", (room_id,)):
            raise ApiError(HTTPStatus.NOT_FOUND, "Sala de chat nao encontrada.")
        rows = self._query_as_service(
            "delete from chat_messages where room_id = %s returning id",
            (room_id,),
        )
        return {"ok": True, "room_id": room_id, "deleted": len(rows)}

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
    print(f"Dark-Jutsu SQL API em http://{API_HOST}:{API_PORT}", flush=True)
    if API_HOST in {"0.0.0.0", "::"}:
        for lan_ip in _local_ipv4_addresses():
            print(f"Acesso pelo celular: http://{lan_ip}:{API_PORT}", flush=True)
    print(f"Banco: {DATABASE_URL}", flush=True)
    DETAIL_LOG.info(
        "START pid=%s host=%s port=%s require_auth=%s public_tunnel=%s allowed_origins=%s",
        os.getpid(),
        API_HOST,
        API_PORT,
        REQUIRE_AUTH,
        PUBLIC_TUNNEL_MODE,
        ",".join(ALLOWED_ORIGINS),
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Encerrando API...")
        DETAIL_LOG.info("STOP_KEYBOARD pid=%s", os.getpid())
    finally:
        server.server_close()
        DETAIL_LOG.info("STOP pid=%s uptime_seconds=%s", os.getpid(), int(time.time() - API_STARTED_AT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
