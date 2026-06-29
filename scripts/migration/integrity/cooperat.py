from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.migration.domains.cooperat import deterministic_sample, inspect, load_raw
from scripts.migration.integrity.base import CheckResult
from scripts.migration.sql_client import MissingSqlDriver, connect
from scripts.migration.utils import sha256_file


DOMAIN = "cooperat"


def _raw_summary(raw_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_hash = sha256_file(raw_path)
    raw = load_raw(raw_path)
    return raw, inspect(raw, source_hash), deterministic_sample(raw, 50)


def check_raw(raw_path: Path) -> tuple[dict[str, Any], list[CheckResult]]:
    raw, summary, _sample = _raw_summary(raw_path)
    results: list[CheckResult] = []
    if not summary["codes_match"]:
        results.append(
            CheckResult(
                DOMAIN,
                "critical",
                "historicoComprasCooperat",
                "totalCodigos",
                "Total de codigos declarado diverge da contagem real no JSON.",
                summary["total_codes_declared"],
                summary["total_codes_counted"],
            )
        )
    if not summary["events_match"]:
        results.append(
            CheckResult(
                DOMAIN,
                "critical",
                "historicoComprasCooperat",
                "totalEventos",
                "Total de eventos declarado diverge da contagem real no JSON.",
                summary["total_events_declared"],
                summary["total_events_counted"],
            )
        )
    codigos = raw.get("codigos") if isinstance(raw.get("codigos"), dict) else {}
    for code, item in codigos.items():
        if not isinstance(item, dict):
            results.append(CheckResult(DOMAIN, "high", str(code), "codigo", "Registro de codigo nao e objeto."))
            continue
        eventos = item.get("eventos") if isinstance(item.get("eventos"), list) else []
        declared = int(item.get("totalEventos") or 0)
        if declared != len(eventos):
            results.append(
                CheckResult(
                    DOMAIN,
                    "high",
                    str(code),
                    "totalEventos",
                    "Total de eventos do codigo diverge da lista de eventos.",
                    declared,
                    len(eventos),
                )
            )
            if len(results) >= 100:
                break
    return summary, results


def _fetch_sql_summary(database_url: str) -> dict[str, Any]:
    with connect(database_url) as (_driver_name, _driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        cur.execute("select count(*) from cooperat_purchase_codes")
        code_count = int(cur.fetchone()[0])
        cur.execute("select count(*) from cooperat_purchase_events")
        event_count = int(cur.fetchone()[0])
        cur.execute(
            """
            select code, total_events
            from cooperat_purchase_codes
            order by code
            """
        )
        code_events = {str(row[0]): int(row[1] or 0) for row in cur.fetchall()}
        cur.execute(
            """
            select code, count(*)::int
            from cooperat_purchase_events
            group by code
            """
        )
        event_counts = {str(row[0]): int(row[1] or 0) for row in cur.fetchall()}
    return {"code_count": code_count, "event_count": event_count, "code_events": code_events, "event_counts": event_counts}


def check_sql(raw_path: Path, database_url: str) -> tuple[dict[str, Any], list[CheckResult]]:
    raw, summary, sample = _raw_summary(raw_path)
    results = check_raw(raw_path)[1]
    try:
        sql = _fetch_sql_summary(database_url)
    except MissingSqlDriver as exc:
        results.append(CheckResult(DOMAIN, "critical", "sql", "driver", str(exc)))
        return summary, results
    except Exception as exc:
        results.append(CheckResult(DOMAIN, "critical", "sql", "connection", f"Falha ao consultar SQL: {exc}"))
        return summary, results

    if summary["total_codes_counted"] != sql["code_count"]:
        results.append(
            CheckResult(
                DOMAIN,
                "critical",
                "cooperat_purchase_codes",
                "count",
                "Total de codigos no SQL diverge do raw.",
                summary["total_codes_counted"],
                sql["code_count"],
            )
        )
    if summary["total_events_counted"] != sql["event_count"]:
        results.append(
            CheckResult(
                DOMAIN,
                "critical",
                "cooperat_purchase_events",
                "count",
                "Total de eventos no SQL diverge do raw.",
                summary["total_events_counted"],
                sql["event_count"],
            )
        )

    codigos = raw.get("codigos") if isinstance(raw.get("codigos"), dict) else {}
    for item in sample.get("codes", []):
        code = str(item.get("codigo") or "")
        if not code:
            continue
        raw_item = codigos.get(code) if isinstance(codigos.get(code), dict) else {}
        raw_total = int(raw_item.get("totalEventos") or item.get("eventosContados") or 0)
        sql_total = sql["event_counts"].get(code)
        if sql_total is None:
            results.append(CheckResult(DOMAIN, "critical", code, "code", "Codigo da amostra ausente no SQL.", raw_total, None))
        elif raw_total != sql_total:
            results.append(
                CheckResult(
                    DOMAIN,
                    "high",
                    code,
                    "totalEventos",
                    "Total de eventos por codigo diverge na amostra.",
                    raw_total,
                    sql_total,
                )
            )
    return summary | {"sql": {k: v for k, v in sql.items() if k not in {"code_events", "event_counts"}}}, results


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
    (reports_dir / "integrity-cooperat.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with (reports_dir / "integrity-differences.jsonl").open("w", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
    md = [
        "# Cooperat integrity report",
        "",
        f"Mode: `{mode}`",
        f"Status: `{status}`",
        "",
        "## Totals",
        "",
        f"- Raw codes: {summary.get('total_codes_counted')}",
        f"- Raw events: {summary.get('total_events_counted')}",
    ]
    if "sql" in summary:
        md.extend(
            [
                f"- SQL codes: {summary['sql'].get('code_count')}",
                f"- SQL events: {summary['sql'].get('event_count')}",
            ]
        )
    md.extend(["", "## Findings", ""])
    if not results:
        md.append("- No findings.")
    else:
        for item in results[:100]:
            md.append(f"- `{item.severity}` `{item.key}` `{item.field}`: {item.message}")
    (reports_dir / "integrity-cooperat.md").write_text("\n".join(md) + "\n", encoding="utf-8")
