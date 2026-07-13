from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.migration.sql_client import connect, json_param
from scripts.migration.utils import ensure_dir, sha256_file, utc_now, write_json


DOMAIN = "occurrences"


def load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo Firebase export nao encontrado: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    if "ocorrencias" in data or "chatGlobal" in data:
        return data
    return {"ocorrencias": data}


def _node(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _num(value: Any) -> Any:
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, int | float):
        raw = float(value)
        if raw > 100000000000:
            raw = raw / 1000
        return datetime.fromtimestamp(raw, timezone.utc)
    return None


def _primary_occurrences(raw: dict[str, Any]) -> dict[str, Any]:
    return _node(raw, "ocorrencias")


def _fallback_occurrences(raw: dict[str, Any]) -> dict[str, Any]:
    chat = _node(raw, "chatGlobal")
    fallback = chat.get("ocorrencias")
    return fallback if isinstance(fallback, dict) else {}


def _merged_occurrences(raw: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    rows: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for key, value in _fallback_occurrences(raw).items():
        if isinstance(value, dict):
            oid = str(value.get("id") or key)
            rows[oid] = (f"chatGlobal/ocorrencias/{key}", "fallback", value)
    for key, value in _primary_occurrences(raw).items():
        if isinstance(value, dict):
            oid = str(value.get("id") or key)
            rows[oid] = (f"ocorrencias/{key}", "primary", value)
    return list(rows.values())


def inspect(raw: dict[str, Any], source_hash: str) -> dict[str, Any]:
    merged = _merged_occurrences(raw)
    history = 0
    for _path, _source, item in merged:
        history += len(item.get("historico") if isinstance(item.get("historico"), dict) else {})
    return {
        "domain": DOMAIN,
        "source_hash": source_hash,
        "primary_occurrences": len(_primary_occurrences(raw)),
        "fallback_occurrences": len(_fallback_occurrences(raw)),
        "merged_occurrences": len(merged),
        "occurrence_history": history,
    }


def deterministic_sample(raw: dict[str, Any], sample_size: int = 20) -> dict[str, Any]:
    samples = []
    for path, source, item in _merged_occurrences(raw)[:sample_size]:
        samples.append(
            {
                "id": item.get("id") or path.rsplit("/", 1)[-1],
                "source": source,
                "status": item.get("status"),
                "severity": item.get("gravidade"),
                "type": item.get("tipo"),
                "item_code": item.get("codigoItem"),
            }
        )
    return {"occurrences": samples}


def write_reports(run_dir: Path, inspection: dict[str, Any], sample: dict[str, Any], mode: str) -> None:
    reports_dir = ensure_dir(run_dir / "reports")
    write_json(reports_dir / "occurrences-summary.json", {"mode": mode, "inspection": inspection, "sample": sample})
    md = [
        "# Occurrences migration report",
        "",
        f"Mode: `{mode}`",
        f"Source hash: `{inspection['source_hash']}`",
        "",
        "## Totals",
        "",
        f"- Primary occurrences: {inspection['primary_occurrences']}",
        f"- Fallback occurrences: {inspection['fallback_occurrences']}",
        f"- Merged occurrences: {inspection['merged_occurrences']}",
        f"- History events: {inspection['occurrence_history']}",
        "",
        "## Sample occurrences",
        "",
    ]
    for item in sample.get("occurrences", [])[:20]:
        md.append(f"- `{item.get('id')}` status={item.get('status')} severity={item.get('severity')} type={item.get('type')}")
    (reports_dir / "occurrences-summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def apply_to_sql(raw: dict[str, Any], database_url: str) -> dict[str, int]:
    with connect(database_url) as (driver_name, driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        cur.execute("delete from occurrence_history")
        cur.execute("delete from occurrences")
        occurrence_sql = """
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
        """
        history_sql = """
            insert into occurrence_history (
              occurrence_id, legacy_key, event_at, by_user_id, by_name, action, value, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """
        occurrences_loaded = 0
        history_loaded = 0
        for path, _source, item in _merged_occurrences(raw):
            oid = str(item.get("id") or path.rsplit("/", 1)[-1])
            cur.execute(
                occurrence_sql,
                (
                    oid,
                    path,
                    _timestamp(item.get("criadoEm")),
                    _clean_text(item.get("data")),
                    _clean_text(item.get("hora")),
                    _clean_text(item.get("operadorUid")),
                    _clean_text(item.get("operadorNome")),
                    _clean_text(item.get("operadorCracha")),
                    _clean_text(item.get("operadorSetor")),
                    _clean_text(item.get("acusadoNome")),
                    _clean_text(item.get("acusadoCracha")),
                    _clean_text(item.get("acusadoSetor")),
                    _clean_text(item.get("tipo")),
                    _clean_text(item.get("gravidade")),
                    _clean_text(item.get("codigoItem")),
                    _clean_text(item.get("descricaoItem")),
                    _num(item.get("quantidade")),
                    _clean_text(item.get("descricao")),
                    _clean_text(item.get("status")),
                    _clean_text(item.get("responsavelUid")),
                    _clean_text(item.get("responsavelNome")),
                    _clean_text(item.get("responsavelCracha")),
                    _clean_text(item.get("responsavelSetor")),
                    _timestamp(item.get("responsavelAtribuidoEm")),
                    _clean_text(item.get("tratativaRealizada")),
                    _clean_text(item.get("tratativaAssinatura")),
                    _timestamp(item.get("tratativaEm")),
                    _clean_text(item.get("tratativaPorUid")),
                    _clean_text(item.get("tratativaPorNome")),
                    json_param(driver_name, driver, item.get("documentoTratativa") or {}),
                    _timestamp(item.get("atualizadoEm")),
                    _clean_text(item.get("atualizadoPor")),
                    json_param(driver_name, driver, item),
                ),
            )
            cur.execute("delete from occurrence_history where occurrence_id = %s", (oid,))
            occurrences_loaded += 1
            historico = item.get("historico") if isinstance(item.get("historico"), dict) else {}
            for hkey, event in historico.items():
                if not isinstance(event, dict):
                    continue
                cur.execute(
                    history_sql,
                    (
                        oid,
                        str(hkey),
                        _timestamp(event.get("em")),
                        _clean_text(event.get("porUid")),
                        _clean_text(event.get("porNome")),
                        _clean_text(event.get("acao")),
                        _clean_text(event.get("valor")),
                        json_param(driver_name, driver, event),
                    ),
                )
                history_loaded += 1
        return {"occurrences_loaded": occurrences_loaded, "occurrence_history_loaded": history_loaded}


def run(source: Path, run_dir: Path, mode: str, database_url: str = "", sample_size: int = 20) -> dict[str, Any]:
    raw_dir = ensure_dir(run_dir / "raw")
    source_hash = sha256_file(source)
    raw = load_raw(source)
    write_json(raw_dir / "occurrences-domain.json", {"ocorrencias": _primary_occurrences(raw), "chatGlobal_ocorrencias": _fallback_occurrences(raw)})
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
    write_json(run_dir / "manifest-occurrences.json", result)
    return result
