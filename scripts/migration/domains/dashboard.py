from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.migration.sql_client import connect, json_param
from scripts.migration.utils import ensure_dir, sha256_file, utc_now, write_json


DOMAIN = "dashboard"


def load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo Firebase export nao encontrado: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    dashboard = data.get("dashboardConfig")
    if isinstance(dashboard, dict):
        return dashboard
    return data if any(key in data for key in ("paineis", "avaliadorPedidos", "ocorrenciasCampos")) else {}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except Exception:
        return default


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, int | float):
        raw = float(value)
        if raw > 100000000000:
            raw = raw / 1000
        return datetime.fromtimestamp(raw, timezone.utc)
    return None


def _decode_legacy_key(value: str) -> str:
    try:
        padded = value + "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8") or value
    except Exception:
        return value


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


def inspect(raw: dict[str, Any], source_hash: str) -> dict[str, Any]:
    paineis = raw.get("paineis") if isinstance(raw.get("paineis"), dict) else {}
    avaliacoes = raw.get("avaliadorPedidos") if isinstance(raw.get("avaliadorPedidos"), dict) else {}
    settings = 1 if isinstance(raw.get("ocorrenciasCampos"), dict) else 0
    return {
        "domain": DOMAIN,
        "source_hash": source_hash,
        "root_keys": sorted(raw.keys()),
        "dashboard_panels": len(paineis),
        "purchase_evaluations": len(avaliacoes),
        "app_settings": settings,
        "has_occurrence_fields": isinstance(raw.get("ocorrenciasCampos"), dict),
        "has_occurrence_evaluator_password": isinstance(raw.get("ocorrenciasAvaliadorSenha"), dict),
    }


def deterministic_sample(raw: dict[str, Any], sample_size: int = 20) -> dict[str, Any]:
    paineis = raw.get("paineis") if isinstance(raw.get("paineis"), dict) else {}
    avaliacoes = raw.get("avaliadorPedidos") if isinstance(raw.get("avaliadorPedidos"), dict) else {}
    return {
        "panels": [
            {"id": key, "limit": (value or {}).get("limite"), "hidden_codes": len(_hidden_codes((value or {}).get("codigosOcultos")))}
            for key, value in list(sorted(paineis.items()))[:sample_size]
            if isinstance(value, dict)
        ],
        "purchase_evaluations": [
            {
                "legacy_key": key,
                "decoded_key": _decode_legacy_key(str(key)),
                "codigo": (value or {}).get("codigo"),
                "decisao": (value or {}).get("decisao"),
                "statusManual": (value or {}).get("statusManual"),
            }
            for key, value in list(sorted(avaliacoes.items()))[:sample_size]
            if isinstance(value, dict)
        ],
    }


def write_reports(run_dir: Path, inspection: dict[str, Any], sample: dict[str, Any], mode: str) -> None:
    reports_dir = ensure_dir(run_dir / "reports")
    write_json(reports_dir / "dashboard-summary.json", {"mode": mode, "inspection": inspection, "sample": sample})
    md = [
        "# Dashboard migration report",
        "",
        f"Mode: `{mode}`",
        f"Source hash: `{inspection['source_hash']}`",
        "",
        "## Totals",
        "",
        f"- Dashboard panels: {inspection['dashboard_panels']}",
        f"- Purchase evaluations: {inspection['purchase_evaluations']}",
        f"- App settings: {inspection['app_settings']}",
        f"- Occurrence fields: {inspection['has_occurrence_fields']}",
        "",
        "## Sample panels",
        "",
    ]
    for item in sample.get("panels", [])[:20]:
        md.append(f"- `{item.get('id')}` limit={item.get('limit')} hidden_codes={item.get('hidden_codes')}")
    md.extend(["", "## Sample purchase evaluations", ""])
    for item in sample.get("purchase_evaluations", [])[:20]:
        md.append(f"- `{item.get('codigo')}` decision={item.get('decisao')} status={item.get('statusManual')}")
    (reports_dir / "dashboard-summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def apply_to_sql(raw: dict[str, Any], database_url: str) -> dict[str, Any]:
    paineis = raw.get("paineis") if isinstance(raw.get("paineis"), dict) else {}
    avaliacoes = raw.get("avaliadorPedidos") if isinstance(raw.get("avaliadorPedidos"), dict) else {}
    settings_loaded = 0
    with connect(database_url) as (driver_name, driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        cur.execute("delete from purchase_evaluations")
        cur.execute("delete from dashboard_panels")
        cur.execute("delete from app_settings where key in ('occurrences.fields', 'occurrences.evaluator_password')")

        panel_sql = """
            insert into dashboard_panels (id, title, row_limit, hidden_codes, updated_at, updated_by, raw_data)
            values (%s, %s, %s, %s, now(), null, %s::jsonb)
            on conflict (id) do update set
              title = excluded.title,
              row_limit = excluded.row_limit,
              hidden_codes = excluded.hidden_codes,
              updated_at = excluded.updated_at,
              raw_data = excluded.raw_data
        """
        panels_loaded = 0
        for key, value in paineis.items():
            if not isinstance(value, dict):
                continue
            cur.execute(
                panel_sql,
                (
                    str(key),
                    str(key).replace("_", " ").title(),
                    _int(value.get("limite"), 8),
                    _hidden_codes(value.get("codigosOcultos")),
                    json_param(driver_name, driver, value),
                ),
            )
            panels_loaded += 1

        eval_sql = """
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
        """
        evaluations_loaded = 0
        for key, value in avaliacoes.items():
            if not isinstance(value, dict):
                continue
            item_code = _clean_text(value.get("codigo")) or _decode_legacy_key(str(key))
            evaluated_at = _timestamp(value.get("avaliadoEm"))
            updated_at = _timestamp(value.get("atualizadoEm")) or evaluated_at or datetime.now(timezone.utc)
            cur.execute(
                eval_sql,
                (
                    str(key),
                    item_code,
                    item_code,
                    _clean_text(value.get("decisao")) or "indefinido",
                    _clean_text(value.get("statusManual")),
                    _clean_text(value.get("observacao")),
                    evaluated_at,
                    _clean_text(value.get("avaliadoPor")),
                    updated_at,
                    _clean_text(value.get("atualizadoPor")),
                    json_param(driver_name, driver, value),
                ),
            )
            evaluations_loaded += 1

        fields = raw.get("ocorrenciasCampos")
        if isinstance(fields, dict):
            cur.execute(
                """
                insert into app_settings (key, value, updated_at, updated_by, raw_data)
                values (%s, %s::jsonb, %s, %s, %s::jsonb)
                on conflict (key) do update set
                  value = excluded.value,
                  updated_at = excluded.updated_at,
                  updated_by = excluded.updated_by,
                  raw_data = excluded.raw_data
                """,
                (
                    "occurrences.fields",
                    json_param(driver_name, driver, fields),
                    _timestamp(fields.get("atualizadoEm")) or datetime.now(timezone.utc),
                    _clean_text(fields.get("atualizadoPor")),
                    json_param(driver_name, driver, fields),
                ),
            )
            settings_loaded += 1

        evaluator_password = raw.get("ocorrenciasAvaliadorSenha")
        if isinstance(evaluator_password, dict):
            safe = dict(evaluator_password)
            for key in ("senha", "password"):
                if key in safe:
                    safe[key] = "[redacted]"
            cur.execute(
                """
                insert into app_settings (key, value, updated_at, updated_by, raw_data)
                values (%s, %s::jsonb, now(), null, %s::jsonb)
                on conflict (key) do update set
                  value = excluded.value,
                  updated_at = excluded.updated_at,
                  raw_data = excluded.raw_data
                """,
                (
                    "occurrences.evaluator_password",
                    json_param(driver_name, driver, safe),
                    json_param(driver_name, driver, safe),
                ),
            )
            settings_loaded += 1

        return {
            "dashboard_panels_loaded": panels_loaded,
            "purchase_evaluations_loaded": evaluations_loaded,
            "app_settings_loaded": settings_loaded,
        }


def run(source: Path, run_dir: Path, mode: str, database_url: str = "", sample_size: int = 20) -> dict[str, Any]:
    raw_dir = ensure_dir(run_dir / "raw")
    source_hash = sha256_file(source)
    raw = load_raw(source)
    write_json(raw_dir / "dashboardConfig.json", raw)
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
    write_json(run_dir / "manifest-dashboard.json", result)
    return result
