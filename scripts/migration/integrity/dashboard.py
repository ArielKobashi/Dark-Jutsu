from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.migration.domains.dashboard import deterministic_sample, inspect, load_raw
from scripts.migration.integrity.base import CheckResult
from scripts.migration.sql_client import MissingSqlDriver, connect
from scripts.migration.utils import sha256_file


DOMAIN = "dashboard"


def _raw_summary(raw_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_hash = sha256_file(raw_path)
    raw = load_raw(raw_path)
    return raw, inspect(raw, source_hash), deterministic_sample(raw, 50)


def check_raw(raw_path: Path) -> tuple[dict[str, Any], list[CheckResult]]:
    raw, summary, _sample = _raw_summary(raw_path)
    results: list[CheckResult] = []
    if not isinstance(raw.get("paineis"), dict):
        results.append(CheckResult(DOMAIN, "medium", "dashboardConfig/paineis", "type", "Mapa de paineis ausente."))
    if not isinstance(raw.get("avaliadorPedidos"), dict):
        results.append(CheckResult(DOMAIN, "medium", "dashboardConfig/avaliadorPedidos", "type", "Mapa de avaliacoes ausente."))
    if not isinstance(raw.get("ocorrenciasCampos"), dict):
        results.append(CheckResult(DOMAIN, "low", "dashboardConfig/ocorrenciasCampos", "type", "Campos de ocorrencia ausentes."))
    return summary, results


def _fetch_sql_summary(database_url: str) -> dict[str, Any]:
    with connect(database_url) as (_driver_name, _driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        counts: dict[str, Any] = {}
        for table, key in [
            ("dashboard_panels", "dashboard_panels"),
            ("purchase_evaluations", "purchase_evaluations"),
        ]:
            cur.execute(f"select count(*)::int from {table}")
            counts[key] = int(cur.fetchone()[0])
        cur.execute("select count(*)::int from app_settings where key in ('occurrences.fields', 'occurrences.evaluator_password')")
        counts["app_settings"] = int(cur.fetchone()[0])
        cur.execute("select legacy_key, item_code, decision from purchase_evaluations")
        counts["evaluations_by_key"] = {str(row[0]): {"item_code": row[1], "decision": row[2]} for row in cur.fetchall()}
        cur.execute("select id, row_limit from dashboard_panels")
        counts["panels_by_id"] = {str(row[0]): int(row[1]) for row in cur.fetchall()}
    return counts


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

    for key in ("dashboard_panels", "purchase_evaluations", "app_settings"):
        if summary[key] != sql[key]:
            results.append(CheckResult(DOMAIN, "critical", key, "count", "Total SQL diverge do raw.", summary[key], sql[key]))

    panels_by_id = sql.get("panels_by_id", {})
    for item in sample.get("panels", [])[:50]:
        panel_id = str(item.get("id") or "")
        if panel_id and panel_id not in panels_by_id:
            results.append(CheckResult(DOMAIN, "high", panel_id, "id", "Painel da amostra ausente no SQL."))

    evaluations_by_key = sql.get("evaluations_by_key", {})
    for item in sample.get("purchase_evaluations", [])[:50]:
        key = str(item.get("legacy_key") or "")
        if key and key not in evaluations_by_key:
            results.append(CheckResult(DOMAIN, "high", key, "legacy_key", "Avaliacao da amostra ausente no SQL."))

    return summary | {"sql": {k: v for k, v in sql.items() if k not in {"panels_by_id", "evaluations_by_key"}}}, results


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
    (reports_dir / "integrity-dashboard.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with (reports_dir / "integrity-dashboard-differences.jsonl").open("w", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
    md = [
        "# Dashboard integrity report",
        "",
        f"Mode: `{mode}`",
        f"Status: `{status}`",
        "",
        "## Totals",
        "",
        f"- Raw dashboard panels: {summary.get('dashboard_panels')}",
        f"- Raw purchase evaluations: {summary.get('purchase_evaluations')}",
        f"- Raw app settings: {summary.get('app_settings')}",
    ]
    if "sql" in summary:
        sql = summary["sql"]
        md.extend(
            [
                f"- SQL dashboard panels: {sql.get('dashboard_panels')}",
                f"- SQL purchase evaluations: {sql.get('purchase_evaluations')}",
                f"- SQL app settings: {sql.get('app_settings')}",
            ]
        )
    md.extend(["", "## Findings", ""])
    if not results:
        md.append("- No findings.")
    else:
        for item in results[:100]:
            md.append(f"- `{item.severity}` `{item.key}` `{item.field}`: {item.message}")
    (reports_dir / "integrity-dashboard.md").write_text("\n".join(md) + "\n", encoding="utf-8")
