from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.migration.domains.automus import deterministic_sample, inspect, load_raw
from scripts.migration.integrity.base import CheckResult
from scripts.migration.sql_client import MissingSqlDriver, connect
from scripts.migration.utils import sha256_file


DOMAIN = "automus"


def _raw_summary(raw_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_hash = sha256_file(raw_path)
    raw = load_raw(raw_path)
    return raw, inspect(raw, source_hash), deterministic_sample(raw, 50)


def check_raw(raw_path: Path) -> tuple[dict[str, Any], list[CheckResult]]:
    raw, summary, _sample = _raw_summary(raw_path)
    results: list[CheckResult] = []
    if not isinstance(raw.get("releases"), dict):
        results.append(CheckResult(DOMAIN, "medium", "releases", "type", "Mapa de releases ausente."))
    for channel, manifest in (raw.get("releases") or {}).items():
        if not isinstance(manifest, dict):
            results.append(CheckResult(DOMAIN, "high", str(channel), "manifest", "Manifest de release invalido."))
            continue
        if not manifest.get("version"):
            results.append(CheckResult(DOMAIN, "high", str(channel), "version", "Release sem versao."))
        if not (manifest.get("packageUrl") or manifest.get("package")):
            results.append(CheckResult(DOMAIN, "medium", str(channel), "packageUrl", "Release sem pacote ou URL de pacote."))
        if not manifest.get("sha256"):
            results.append(CheckResult(DOMAIN, "medium", str(channel), "sha256", "Release sem hash sha256 do pacote."))
    return summary, results


def _fetch_sql_summary(database_url: str) -> dict[str, Any]:
    with connect(database_url) as (_driver_name, _driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        cur.execute("select count(*)::int from automus_releases")
        total = int(cur.fetchone()[0])
        cur.execute(
            """
            select channel, version, package_url, raw_manifest
            from automus_releases
            """
        )
        rows = cur.fetchall()
    by_channel = {
        str(row[0]): {
            "version": row[1],
            "package_url": row[2],
            "raw_manifest": row[3],
        }
        for row in rows
    }
    return {"automus_releases": total, "by_channel": by_channel}


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

    if summary["automus_releases"] > sql["automus_releases"]:
        results.append(
            CheckResult(
                DOMAIN,
                "critical",
                "automus_releases",
                "count",
                "Total SQL menor que o raw.",
                summary["automus_releases"],
                sql["automus_releases"],
            )
        )

    by_channel = sql.get("by_channel", {})
    releases = raw.get("releases") if isinstance(raw.get("releases"), dict) else {}
    for item in sample.get("releases", [])[:50]:
        channel = str(item.get("channel"))
        raw_manifest = releases.get(channel) if isinstance(releases.get(channel), dict) else {}
        row = by_channel.get(channel)
        if not row:
            results.append(CheckResult(DOMAIN, "critical", channel, "channel", "Canal de release ausente no SQL."))
            continue
        if str(raw_manifest.get("version") or "unknown") != str(row.get("version")):
            results.append(CheckResult(DOMAIN, "critical", channel, "version", "Versao SQL diverge do raw.", raw_manifest.get("version"), row.get("version")))
        expected_url = raw_manifest.get("packageUrl") or raw_manifest.get("updateManifestUrl") or raw_manifest.get("package")
        if str(expected_url or "") != str(row.get("package_url") or ""):
            results.append(CheckResult(DOMAIN, "high", channel, "package_url", "URL de pacote SQL diverge do raw.", expected_url, row.get("package_url")))
        sql_manifest = row.get("raw_manifest") if isinstance(row.get("raw_manifest"), dict) else {}
        if raw_manifest.get("sha256") and raw_manifest.get("sha256") != sql_manifest.get("sha256"):
            results.append(CheckResult(DOMAIN, "high", channel, "sha256", "SHA256 no manifesto SQL diverge do raw."))

    return summary | {"sql": {"automus_releases": sql["automus_releases"]}}, results


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
    (reports_dir / "integrity-automus.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with (reports_dir / "integrity-automus-differences.jsonl").open("w", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
    md = [
        "# Automus integrity report",
        "",
        f"Mode: `{mode}`",
        f"Status: `{status}`",
        "",
        "## Totals",
        "",
        f"- Raw releases: {summary.get('automus_releases')}",
    ]
    if "sql" in summary:
        md.append(f"- SQL releases: {summary['sql'].get('automus_releases')}")
    md.extend(["", "## Findings", ""])
    if not results:
        md.append("- No findings.")
    else:
        for item in results[:100]:
            md.append(f"- `{item.severity}` `{item.key}` `{item.field}`: {item.message}")
    (reports_dir / "integrity-automus.md").write_text("\n".join(md) + "\n", encoding="utf-8")
