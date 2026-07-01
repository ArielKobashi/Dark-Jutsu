from __future__ import annotations

import json
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any

from scripts.migration.sql_client import connect, json_param
from scripts.migration.utils import ensure_dir, sha256_file, utc_now, write_json


DOMAIN = "automus"


def load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo Firebase export nao encontrado: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    automus = data.get("automus")
    if isinstance(automus, dict):
        return automus
    return data if "releases" in data else {}


def _releases(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    releases = raw.get("releases") if isinstance(raw.get("releases"), dict) else {}
    return {str(channel): manifest for channel, manifest in releases.items() if isinstance(manifest, dict)}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _notes(value: Any) -> str | None:
    if isinstance(value, list):
        parts = [_clean_text(item) for item in value]
        return "\n".join(part for part in parts if part) or None
    return _clean_text(value)


def _timestamp(value: Any) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.combine(datetime.strptime(text, fmt).date(), time.min, tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def inspect(raw: dict[str, Any], source_hash: str) -> dict[str, Any]:
    releases = _releases(raw)
    manifests_with_package = len([item for item in releases.values() if _clean_text(item.get("package") or item.get("packageUrl"))])
    manifests_with_sha256 = len([item for item in releases.values() if _clean_text(item.get("sha256"))])
    return {
        "domain": DOMAIN,
        "source_hash": source_hash,
        "root_keys": sorted(raw.keys()),
        "release_channels": len(releases),
        "automus_releases": len(releases),
        "manifests_with_package": manifests_with_package,
        "manifests_with_sha256": manifests_with_sha256,
        "channels": sorted(releases.keys()),
    }


def deterministic_sample(raw: dict[str, Any], sample_size: int = 20) -> dict[str, Any]:
    sample = []
    for channel, manifest in list(sorted(_releases(raw).items()))[:sample_size]:
        sample.append(
            {
                "channel": channel,
                "app": manifest.get("app"),
                "version": manifest.get("version"),
                "package": manifest.get("package"),
                "packageUrl": manifest.get("packageUrl"),
                "sha256": manifest.get("sha256"),
                "releasedAt": manifest.get("releasedAt"),
                "packagedAt": manifest.get("packagedAt"),
            }
        )
    return {"releases": sample}


def write_reports(run_dir: Path, inspection: dict[str, Any], sample: dict[str, Any], mode: str) -> None:
    reports_dir = ensure_dir(run_dir / "reports")
    write_json(reports_dir / "automus-summary.json", {"mode": mode, "inspection": inspection, "sample": sample})
    md = [
        "# Automus migration report",
        "",
        f"Mode: `{mode}`",
        f"Source hash: `{inspection['source_hash']}`",
        "",
        "## Totals",
        "",
        f"- Release channels: {inspection['release_channels']}",
        f"- Releases: {inspection['automus_releases']}",
        f"- Manifests with package: {inspection['manifests_with_package']}",
        f"- Manifests with sha256: {inspection['manifests_with_sha256']}",
        "",
        "## Sample releases",
        "",
    ]
    for item in sample.get("releases", [])[:20]:
        md.append(f"- `{item.get('channel')}` version={item.get('version')} package={item.get('package')}")
    (reports_dir / "automus-summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def apply_to_sql(raw: dict[str, Any], database_url: str) -> dict[str, int]:
    releases = _releases(raw)
    with connect(database_url) as (driver_name, driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        loaded = 0
        for channel, manifest in releases.items():
            version = _clean_text(manifest.get("version")) or "unknown"
            published_at = _timestamp(manifest.get("packagedAt")) or _timestamp(manifest.get("releasedAt")) or datetime.now(timezone.utc)
            cur.execute(
                """
                insert into automus_releases (channel, version, package_url, notes, published_at, published_by, raw_manifest)
                values (%s, %s, %s, %s, %s, %s, %s::jsonb)
                on conflict (channel, version) do update set
                  package_url = excluded.package_url,
                  notes = excluded.notes,
                  published_at = excluded.published_at,
                  published_by = excluded.published_by,
                  raw_manifest = excluded.raw_manifest
                """,
                (
                    channel,
                    version,
                    _clean_text(manifest.get("packageUrl") or manifest.get("updateManifestUrl") or manifest.get("package")),
                    _notes(manifest.get("notes")),
                    published_at,
                    _clean_text(manifest.get("publishedBy") or manifest.get("app")),
                    json_param(driver_name, driver, manifest),
                ),
            )
            loaded += 1
        return {"automus_releases_loaded": loaded}


def run(source: Path, run_dir: Path, mode: str, database_url: str = "", sample_size: int = 20) -> dict[str, Any]:
    raw_dir = ensure_dir(run_dir / "raw")
    source_hash = sha256_file(source)
    raw = load_raw(source)
    write_json(raw_dir / "automus-domain.json", raw)
    inspection = inspect(raw, source_hash)
    sample = deterministic_sample(raw, sample_size)
    apply_result = apply_to_sql(raw, database_url) if mode == "apply" else None
    write_reports(run_dir, inspection, sample, mode)
    result = {
        "domain": DOMAIN,
        "mode": mode,
        "source": str(source),
        "run_dir": str(run_dir),
        "source_hash": source_hash,
        "inspection": inspection,
        "sample_size": sample_size,
        "apply_result": apply_result,
        "finished_at": utc_now().isoformat(),
    }
    write_json(run_dir / "manifest-automus.json", result)
    return result
