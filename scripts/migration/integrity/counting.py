from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.migration.domains.counting import deterministic_sample, inspect, load_raw
from scripts.migration.integrity.base import CheckResult
from scripts.migration.sql_client import MissingSqlDriver, connect
from scripts.migration.utils import sha256_file


DOMAIN = "counting"


def _raw_summary(raw_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_hash = sha256_file(raw_path)
    raw = load_raw(raw_path)
    return raw, inspect(raw, source_hash), deterministic_sample(raw, 50)


def check_raw(raw_path: Path) -> tuple[dict[str, Any], list[CheckResult]]:
    raw, summary, _sample = _raw_summary(raw_path)
    results: list[CheckResult] = []
    if not isinstance(raw.get("contagens"), dict):
        results.append(CheckResult(DOMAIN, "critical", "contagens", "type", "Mapa de contagens ausente."))
    return summary, results


def _fetch_sql_summary(database_url: str) -> dict[str, Any]:
    with connect(database_url) as (_driver_name, _driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        counts: dict[str, Any] = {}
        for table, key in [
            ("counting_sessions", "counting_sessions"),
            ("counting_items", "counting_items"),
            ("counting_empty_checks", "counting_empty_checks"),
            ("counting_drafts", "counting_drafts"),
            ("counting_machine_status", "machine_status"),
            ("label_print_jobs", "label_print_jobs"),
            ("label_user_ranking", "label_ranking"),
        ]:
            cur.execute(f"select count(*)::int from {table}")
            counts[key] = int(cur.fetchone()[0])
        cur.execute("select legacy_path from counting_sessions")
        counts["sessions_by_path"] = {str(row[0]) for row in cur.fetchall()}
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

    comparisons = [
        ("counting_sessions", summary["counting_sessions"], sql["counting_sessions"]),
        ("counting_items", summary["counting_items"], sql["counting_items"]),
        ("counting_empty_checks", summary["counting_empty_checks"], sql["counting_empty_checks"]),
        ("counting_drafts", summary["counting_drafts"], sql["counting_drafts"]),
        ("machine_status", summary["machine_status"], sql["machine_status"]),
        ("label_print_jobs", summary["label_print_jobs"], sql["label_print_jobs"]),
        ("label_ranking", summary["label_ranking"], sql["label_ranking"]),
    ]
    for key, raw_value, sql_value in comparisons:
        if raw_value != sql_value:
            results.append(CheckResult(DOMAIN, "critical", key, "count", "Total SQL diverge do raw.", raw_value, sql_value))

    sessions_by_path = sql.get("sessions_by_path", set())
    for item in sample.get("sessions", [])[:50]:
        path = str(item.get("legacy_path") or "")
        if path and path not in sessions_by_path:
            results.append(CheckResult(DOMAIN, "high", path, "legacy_path", "Sessao da amostra ausente no SQL."))

    return summary | {"sql": {k: v for k, v in sql.items() if k != "sessions_by_path"}}, results


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
    (reports_dir / "integrity-counting.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with (reports_dir / "integrity-counting-differences.jsonl").open("w", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
    md = [
        "# Counting integrity report",
        "",
        f"Mode: `{mode}`",
        f"Status: `{status}`",
        "",
        "## Totals",
        "",
        f"- Raw sessions: {summary.get('counting_sessions')}",
        f"- Raw items: {summary.get('counting_items')}",
        f"- Raw empty checks: {summary.get('counting_empty_checks')}",
        f"- Raw drafts: {summary.get('counting_drafts')}",
        f"- Raw machine status: {summary.get('machine_status')}",
        f"- Raw label print jobs: {summary.get('label_print_jobs')}",
    ]
    if "sql" in summary:
        sql = summary["sql"]
        md.extend(
            [
                f"- SQL sessions: {sql.get('counting_sessions')}",
                f"- SQL items: {sql.get('counting_items')}",
                f"- SQL empty checks: {sql.get('counting_empty_checks')}",
                f"- SQL drafts: {sql.get('counting_drafts')}",
                f"- SQL machine status: {sql.get('machine_status')}",
                f"- SQL label print jobs: {sql.get('label_print_jobs')}",
            ]
        )
    md.extend(["", "## Findings", ""])
    if not results:
        md.append("- No findings.")
    else:
        for item in results[:100]:
            md.append(f"- `{item.severity}` `{item.key}` `{item.field}`: {item.message}")
    (reports_dir / "integrity-counting.md").write_text("\n".join(md) + "\n", encoding="utf-8")
