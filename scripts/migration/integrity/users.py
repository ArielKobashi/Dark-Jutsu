from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.migration.domains.users import inspect, load_raw
from scripts.migration.integrity.base import CheckResult
from scripts.migration.sql_client import MissingSqlDriver, connect
from scripts.migration.utils import sha256_file


DOMAIN = "users"


def _raw_summary(raw_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    source_hash = sha256_file(raw_path)
    raw = load_raw(raw_path)
    return raw, inspect(raw, source_hash)


def check_raw(raw_path: Path) -> tuple[dict[str, Any], list[CheckResult]]:
    raw, summary = _raw_summary(raw_path)
    results: list[CheckResult] = []
    if not isinstance(raw.get("usuarios"), dict):
        results.append(CheckResult(DOMAIN, "critical", "usuarios", "type", "Mapa de usuarios ausente."))
    if not isinstance(raw.get("usuariosBanidos"), dict):
        results.append(CheckResult(DOMAIN, "medium", "usuariosBanidos", "type", "Mapa de usuarios banidos ausente."))
    if summary["signup_requests"] == 0:
        results.append(CheckResult(DOMAIN, "medium", "solicitacoesCadastro", "count", "Nenhuma solicitacao encontrada."))
    return summary, results


def _fetch_sql_summary(database_url: str) -> dict[str, Any]:
    with connect(database_url) as (_driver_name, _driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        counts: dict[str, Any] = {}
        for table, key in [
            ("users", "users"),
            ("banned_users", "banned_users"),
            ("signup_requests", "signup_requests"),
        ]:
            cur.execute(f"select count(*)::int from {table}")
            counts[key] = int(cur.fetchone()[0])
        cur.execute("select count(*)::int from signup_requests where password_plain_legacy is not null")
        counts["signup_plain_passwords"] = int(cur.fetchone()[0])
        cur.execute(
            """
            select count(*)::int
            from users
            where raw_data ? 'senhaAntiga'
              and raw_data->>'senhaAntiga' <> '[redacted]'
            """
        )
        counts["users_unredacted_legacy_passwords"] = int(cur.fetchone()[0])
        cur.execute(
            """
            select count(*)::int
            from signup_requests
            where raw_data ? 'senha'
              and raw_data->>'senha' <> '[redacted]'
            """
        )
        counts["signup_unredacted_passwords"] = int(cur.fetchone()[0])
        cur.execute("select id, nickname from users")
        counts["users_by_id"] = {str(row[0]): str(row[1]) for row in cur.fetchall()}
    return counts


def check_sql(raw_path: Path, database_url: str) -> tuple[dict[str, Any], list[CheckResult]]:
    raw, summary = _raw_summary(raw_path)
    results = check_raw(raw_path)[1]
    try:
        sql = _fetch_sql_summary(database_url)
    except MissingSqlDriver as exc:
        results.append(CheckResult(DOMAIN, "critical", "sql", "driver", str(exc)))
        return summary, results
    except Exception as exc:
        results.append(CheckResult(DOMAIN, "critical", "sql", "connection", f"Falha ao consultar SQL: {exc}"))
        return summary, results

    for key in ("users", "banned_users", "signup_requests"):
        if summary[key] != sql[key]:
            results.append(CheckResult(DOMAIN, "critical", key, "count", "Total SQL diverge do raw.", summary[key], sql[key]))

    security_checks = [
        ("signup_requests", "password_plain_legacy", sql["signup_plain_passwords"]),
        ("users", "raw_data.senhaAntiga", sql["users_unredacted_legacy_passwords"]),
        ("signup_requests", "raw_data.senha", sql["signup_unredacted_passwords"]),
    ]
    for key, field, count in security_checks:
        if count:
            results.append(CheckResult(DOMAIN, "critical", key, field, "Senha legada nao sanitizada no SQL.", 0, count))

    usuarios = raw.get("usuarios") if isinstance(raw.get("usuarios"), dict) else {}
    users_by_id = sql.get("users_by_id", {})
    for uid in list(sorted(usuarios))[:50]:
        if uid not in users_by_id:
            results.append(CheckResult(DOMAIN, "high", uid, "id", "Usuario da amostra ausente no SQL."))

    return summary | {"sql": {k: v for k, v in sql.items() if k != "users_by_id"}}, results


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
    (reports_dir / "integrity-users.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with (reports_dir / "integrity-users-differences.jsonl").open("w", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
    md = [
        "# Users integrity report",
        "",
        f"Mode: `{mode}`",
        f"Status: `{status}`",
        "",
        "## Totals",
        "",
        f"- Raw users: {summary.get('users')}",
        f"- Raw banned users: {summary.get('banned_users')}",
        f"- Raw signup requests: {summary.get('signup_requests')}",
    ]
    if "sql" in summary:
        sql = summary["sql"]
        md.extend(
            [
                f"- SQL users: {sql.get('users')}",
                f"- SQL banned users: {sql.get('banned_users')}",
                f"- SQL signup requests: {sql.get('signup_requests')}",
                f"- SQL plain signup passwords: {sql.get('signup_plain_passwords')}",
                f"- SQL unredacted user legacy passwords: {sql.get('users_unredacted_legacy_passwords')}",
                f"- SQL unredacted signup passwords: {sql.get('signup_unredacted_passwords')}",
            ]
        )
    md.extend(["", "## Findings", ""])
    if not results:
        md.append("- No findings.")
    else:
        for item in results[:100]:
            md.append(f"- `{item.severity}` `{item.key}` `{item.field}`: {item.message}")
    (reports_dir / "integrity-users.md").write_text("\n".join(md) + "\n", encoding="utf-8")
