from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.migration.domains.occurrences import deterministic_sample, inspect, load_raw
from scripts.migration.integrity.base import CheckResult
from scripts.migration.sql_client import MissingSqlDriver, connect
from scripts.migration.utils import sha256_file


DOMAIN = "occurrences"


def _raw_summary(raw_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_hash = sha256_file(raw_path)
    raw = load_raw(raw_path)
    return raw, inspect(raw, source_hash), deterministic_sample(raw, 50)


def check_raw(raw_path: Path) -> tuple[dict[str, Any], list[CheckResult]]:
    raw, summary, _sample = _raw_summary(raw_path)
    results: list[CheckResult] = []
    if not isinstance(raw.get("ocorrencias"), dict):
        results.append(CheckResult(DOMAIN, "medium", "ocorrencias", "type", "Mapa de ocorrencias ausente."))
    return summary, results


def _fetch_sql_summary(database_url: str) -> dict[str, Any]:
    with connect(database_url) as (_driver_name, _driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        cur.execute("select count(*)::int from occurrences")
        occurrences_count = int(cur.fetchone()[0])
        cur.execute("select count(*)::int from occurrence_history")
        history_count = int(cur.fetchone()[0])
        cur.execute("select id from occurrences")
        ids = {str(row[0]) for row in cur.fetchall()}
    return {"merged_occurrences": occurrences_count, "occurrence_history": history_count, "ids": ids}


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

    for key in ("merged_occurrences", "occurrence_history"):
        if summary[key] != sql[key]:
            results.append(CheckResult(DOMAIN, "critical", key, "count", "Total SQL diverge do raw.", summary[key], sql[key]))
    ids = sql.get("ids", set())
    for item in sample.get("occurrences", [])[:50]:
        oid = str(item.get("id") or "")
        if oid and oid not in ids:
            results.append(CheckResult(DOMAIN, "high", oid, "id", "Ocorrencia da amostra ausente no SQL."))
    return summary | {"sql": {k: v for k, v in sql.items() if k != "ids"}}, results


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
    (reports_dir / "integrity-occurrences.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with (reports_dir / "integrity-occurrences-differences.jsonl").open("w", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
    md = [
        "# Occurrences integrity report",
        "",
        f"Mode: `{mode}`",
        f"Status: `{status}`",
        "",
        "## Totals",
        "",
        f"- Raw primary occurrences: {summary.get('primary_occurrences')}",
        f"- Raw fallback occurrences: {summary.get('fallback_occurrences')}",
        f"- Raw merged occurrences: {summary.get('merged_occurrences')}",
        f"- Raw history events: {summary.get('occurrence_history')}",
    ]
    if "sql" in summary:
        sql = summary["sql"]
        md.extend(
            [
                f"- SQL occurrences: {sql.get('merged_occurrences')}",
                f"- SQL history events: {sql.get('occurrence_history')}",
            ]
        )
    md.extend(["", "## Findings", ""])
    if not results:
        md.append("- No findings.")
    else:
        for item in results[:100]:
            md.append(f"- `{item.severity}` `{item.key}` `{item.field}`: {item.message}")
    (reports_dir / "integrity-occurrences.md").write_text("\n".join(md) + "\n", encoding="utf-8")
