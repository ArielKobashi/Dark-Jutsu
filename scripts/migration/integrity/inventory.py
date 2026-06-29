from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.migration.domains.inventory import deterministic_sample, inspect, load_raw
from scripts.migration.integrity.base import CheckResult
from scripts.migration.sql_client import MissingSqlDriver, connect
from scripts.migration.utils import sha256_file


DOMAIN = "inventory"


def _raw_summary(raw_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_hash = sha256_file(raw_path)
    raw = load_raw(raw_path)
    return raw, inspect(raw, source_hash), deterministic_sample(raw, 50)


def _raw_extra_counts(raw: dict[str, Any]) -> dict[str, int]:
    addresses = 0
    limits = 0
    for key in ("dados", "dadosMortos"):
        items = raw.get(key) if isinstance(raw.get(key), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            enderecos = item.get("enderecos") if isinstance(item.get("enderecos"), list) else []
            addresses += len([entry for entry in enderecos if isinstance(entry, dict)])
            if isinstance(item.get("limitesCooperat"), dict):
                limits += 1
    return {"addresses": addresses, "limits": limits, "total_items": int(len(raw.get("dados") or []) + len(raw.get("dadosMortos") or []))}


def check_raw(raw_path: Path) -> tuple[dict[str, Any], list[CheckResult]]:
    raw, summary, _sample = _raw_summary(raw_path)
    results: list[CheckResult] = []
    if not isinstance(raw.get("dados"), list):
        results.append(CheckResult(DOMAIN, "critical", "estoqueGlobal/dados", "type", "Lista de itens ativos ausente."))
    if not isinstance(raw.get("dadosMortos"), list):
        results.append(CheckResult(DOMAIN, "medium", "estoqueGlobal/dadosMortos", "type", "Lista de itens mortos ausente."))
    if not isinstance(raw.get("historicoSaldo"), dict):
        results.append(CheckResult(DOMAIN, "medium", "estoqueGlobal/historicoSaldo", "type", "Historico de saldo ausente."))
    return summary | {"raw_extra": _raw_extra_counts(raw)}, results


def _fetch_sql_summary(database_url: str) -> dict[str, Any]:
    with connect(database_url) as (_driver_name, _driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        cur.execute(
            """
            select
              count(*) filter (where is_dead = false)::int,
              count(*) filter (where is_dead = true)::int,
              count(*)::int
            from inventory_items
            """
        )
        active, dead, total = cur.fetchone()
        counts = {"active_items": int(active), "dead_items": int(dead), "total_items": int(total)}
        for table, key in [
            ("inventory_item_addresses", "addresses"),
            ("inventory_item_limits", "limits"),
            ("inventory_adjustments", "adjustments"),
            ("inventory_balance_history", "balance_history"),
            ("inventory_movements", "movements"),
        ]:
            cur.execute(f"select count(*)::int from {table}")
            counts[key] = int(cur.fetchone()[0])
        cur.execute("select legacy_key, balance, is_dead from inventory_items")
        counts["items_by_key"] = {str(row[0]): {"balance": row[1], "is_dead": row[2]} for row in cur.fetchall()}
    return counts


def check_sql(raw_path: Path, database_url: str) -> tuple[dict[str, Any], list[CheckResult]]:
    raw, summary, sample = _raw_summary(raw_path)
    raw_counts = _raw_extra_counts(raw)
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
        ("inventory_items.active", "active_items", summary["active_items"], sql["active_items"]),
        ("inventory_items.dead", "dead_items", summary["dead_items"], sql["dead_items"]),
        ("inventory_items.total", "total_items", raw_counts["total_items"], sql["total_items"]),
        ("inventory_item_addresses", "count", raw_counts["addresses"], sql["addresses"]),
        ("inventory_item_limits", "count", raw_counts["limits"], sql["limits"]),
        ("inventory_adjustments", "count", summary["adjustments"], sql["adjustments"]),
        ("inventory_balance_history", "count", summary["balance_history_events"], sql["balance_history"]),
    ]
    for key, field, raw_value, sql_value in comparisons:
        if raw_value != sql_value:
            results.append(
                CheckResult(
                    DOMAIN,
                    "critical",
                    key,
                    field,
                    "Total SQL diverge do raw.",
                    raw_value,
                    sql_value,
                )
            )

    items_by_key = sql.get("items_by_key", {})
    for item in sample.get("items", [])[:50]:
        key = str(item.get("key") or "")
        if key and key not in items_by_key:
            results.append(CheckResult(DOMAIN, "high", key, "legacy_key", "Item da amostra ausente no SQL."))

    return summary | {"raw_extra": raw_counts, "sql": {k: v for k, v in sql.items() if k != "items_by_key"}}, results


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
    (reports_dir / "integrity-inventory.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with (reports_dir / "integrity-inventory-differences.jsonl").open("w", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
    md = [
        "# Inventory integrity report",
        "",
        f"Mode: `{mode}`",
        f"Status: `{status}`",
        "",
        "## Totals",
        "",
        f"- Raw active items: {summary.get('active_items')}",
        f"- Raw dead items: {summary.get('dead_items')}",
        f"- Raw addresses: {summary.get('raw_extra', {}).get('addresses')}",
        f"- Raw limits: {summary.get('raw_extra', {}).get('limits')}",
        f"- Raw adjustments: {summary.get('adjustments')}",
        f"- Raw balance history events: {summary.get('balance_history_events')}",
    ]
    if "sql" in summary:
        sql = summary["sql"]
        md.extend(
            [
                f"- SQL active items: {sql.get('active_items')}",
                f"- SQL dead items: {sql.get('dead_items')}",
                f"- SQL addresses: {sql.get('addresses')}",
                f"- SQL limits: {sql.get('limits')}",
                f"- SQL adjustments: {sql.get('adjustments')}",
                f"- SQL balance history events: {sql.get('balance_history')}",
            ]
        )
    md.extend(["", "## Findings", ""])
    if not results:
        md.append("- No findings.")
    else:
        for item in results[:100]:
            md.append(f"- `{item.severity}` `{item.key}` `{item.field}`: {item.message}")
    (reports_dir / "integrity-inventory.md").write_text("\n".join(md) + "\n", encoding="utf-8")
