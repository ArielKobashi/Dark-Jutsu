from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.migration.sql_client import connect, json_param
from scripts.migration.utils import ensure_dir, sha256_file, utc_now, write_json


DOMAIN = "cooperat"


def load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo Cooperat nao encontrado: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def inspect(raw: dict[str, Any], source_hash: str) -> dict[str, Any]:
    codigos = raw.get("codigos") if isinstance(raw.get("codigos"), dict) else {}
    code_values = list(codigos.values())
    event_counts = [
        len(item.get("eventos") if isinstance(item.get("eventos"), list) else [])
        for item in code_values
        if isinstance(item, dict)
    ]
    total_events_counted = sum(event_counts)
    max_events = max(event_counts) if event_counts else 0
    max_code = ""
    for code, item in codigos.items():
        if isinstance(item, dict) and len(item.get("eventos") if isinstance(item.get("eventos"), list) else []) == max_events:
            max_code = str(code)
            break
    root_total_codes = int(raw.get("totalCodigos") or 0)
    root_total_events = int(raw.get("totalEventos") or 0)
    return {
        "domain": DOMAIN,
        "source_hash": source_hash,
        "root_keys": list(raw.keys()),
        "total_codes_declared": root_total_codes,
        "total_codes_counted": len(codigos),
        "total_events_declared": root_total_events,
        "total_events_counted": total_events_counted,
        "max_events_per_code": max_events,
        "max_events_code": max_code,
        "codes_match": root_total_codes == len(codigos),
        "events_match": root_total_events == total_events_counted,
        "generated_at": raw.get("geradoEm"),
        "description": raw.get("descricao"),
    }


def deterministic_sample(raw: dict[str, Any], sample_size: int = 20) -> dict[str, Any]:
    codigos = raw.get("codigos") if isinstance(raw.get("codigos"), dict) else {}
    keys = sorted(str(k) for k in codigos.keys())
    if not keys:
        return {"codes": [], "events": []}
    selected: list[str] = []
    selected.extend(keys[:3])
    selected.extend(keys[-3:])
    step = max(1, len(keys) // max(1, sample_size))
    selected.extend(keys[::step][:sample_size])
    selected = sorted(set(selected), key=lambda k: keys.index(k) if k in keys else 0)

    code_samples = []
    event_samples = []
    for key in selected:
        item = codigos.get(key) or {}
        if not isinstance(item, dict):
            continue
        eventos = item.get("eventos") if isinstance(item.get("eventos"), list) else []
        code_samples.append(
            {
                "codigo": item.get("codigo") or key,
                "descricaoMaisRecente": item.get("descricaoMaisRecente"),
                "totalEventos": item.get("totalEventos"),
                "primeiraData": item.get("primeiraData"),
                "ultimaData": item.get("ultimaData"),
                "eventosContados": len(eventos),
            }
        )
        if eventos:
            event_samples.append(eventos[0])
            if len(eventos) > 1:
                event_samples.append(eventos[-1])
    return {"codes": code_samples, "events": event_samples[: sample_size * 2]}


def write_reports(run_dir: Path, inspection: dict[str, Any], sample: dict[str, Any], mode: str) -> None:
    reports_dir = ensure_dir(run_dir / "reports")
    write_json(reports_dir / "cooperat-summary.json", {"mode": mode, "inspection": inspection, "sample": sample})
    status = "ok" if inspection["codes_match"] and inspection["events_match"] else "failed"
    md = [
        "# Cooperat migration report",
        "",
        f"Mode: `{mode}`",
        f"Status: `{status}`",
        f"Source hash: `{inspection['source_hash']}`",
        "",
        "## Totals",
        "",
        f"- Codes declared: {inspection['total_codes_declared']}",
        f"- Codes counted: {inspection['total_codes_counted']}",
        f"- Events declared: {inspection['total_events_declared']}",
        f"- Events counted: {inspection['total_events_counted']}",
        f"- Max events per code: {inspection['max_events_per_code']} (`{inspection['max_events_code']}`)",
        "",
        "## Sample codes",
        "",
    ]
    for item in sample.get("codes", [])[:20]:
        md.append(
            f"- `{item.get('codigo')}`: {item.get('eventosContados')} events, "
            f"{item.get('primeiraData')} -> {item.get('ultimaData')}"
        )
    (reports_dir / "cooperat-summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def _event_tuple(code: str, event: dict[str, Any], import_run_id: str, json_value: Any) -> tuple[Any, ...]:
    return (
        code,
        event.get("requisicao"),
        event.get("data") or None,
        event.get("dataBr"),
        event.get("descricao"),
        event.get("unidade"),
        event.get("qtdSolicitada"),
        event.get("qtdFornecida"),
        event.get("valorBaixa"),
        event.get("quantidadeCompra"),
        event.get("fonte"),
        event.get("origem"),
        import_run_id,
        json_value,
    )


def apply_to_sql(raw: dict[str, Any], database_url: str, source_hash: str) -> dict[str, Any]:
    codigos = raw.get("codigos") if isinstance(raw.get("codigos"), dict) else {}
    with connect(database_url) as (driver_name, driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        cur.execute(
            """
            insert into cooperat_import_runs (
              generated_at, description, quantity_rule, value_rule, event_limit_per_code,
              source_files, total_codes, total_events, source_hash, raw_data
            )
            values (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb)
            returning id
            """,
            (
                raw.get("geradoEm"),
                raw.get("descricao"),
                raw.get("regraQuantidade"),
                raw.get("regraValor"),
                raw.get("limiteEventosPorCodigo"),
                json.dumps(raw.get("fontes") or [], ensure_ascii=False),
                raw.get("totalCodigos"),
                raw.get("totalEventos"),
                source_hash,
                json.dumps({k: raw.get(k) for k in raw.keys() if k != "codigos"}, ensure_ascii=False),
            ),
        )
        import_run_id = str(cur.fetchone()[0])

        code_sql = """
            insert into cooperat_purchase_codes (
              code, latest_description, total_events, total_purchase_qty,
              total_requested_qty, total_supplied_qty, total_low_value,
              first_date, last_date, avg_purchase_qty, avg_requested_qty,
              avg_supplied_qty, avg_low_value, import_run_id, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (code) do update set
              latest_description = excluded.latest_description,
              total_events = excluded.total_events,
              total_purchase_qty = excluded.total_purchase_qty,
              total_requested_qty = excluded.total_requested_qty,
              total_supplied_qty = excluded.total_supplied_qty,
              total_low_value = excluded.total_low_value,
              first_date = excluded.first_date,
              last_date = excluded.last_date,
              avg_purchase_qty = excluded.avg_purchase_qty,
              avg_requested_qty = excluded.avg_requested_qty,
              avg_supplied_qty = excluded.avg_supplied_qty,
              avg_low_value = excluded.avg_low_value,
              import_run_id = excluded.import_run_id,
              raw_data = excluded.raw_data
        """
        event_sql = """
            insert into cooperat_purchase_events (
              code, requisition, event_date, event_date_label, description,
              unit, requested_qty, supplied_qty, low_value, purchase_qty,
              source, origin, import_run_id, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """

        event_total = 0
        cur.execute("delete from cooperat_purchase_codes")
        for code, item in codigos.items():
            if not isinstance(item, dict):
                continue
            raw_code = dict(item)
            raw_code.pop("eventos", None)
            raw_code_param = json_param(driver_name, driver, raw_code)
            cur.execute(
                code_sql,
                (
                    item.get("codigo") or str(code),
                    item.get("descricaoMaisRecente"),
                    item.get("totalEventos") or 0,
                    item.get("totalQuantidadeCompra"),
                    item.get("totalQuantidadeSolicitada"),
                    item.get("totalQuantidadeFornecida"),
                    item.get("totalValorBaixa"),
                    item.get("primeiraData") or None,
                    item.get("ultimaData") or None,
                    item.get("mediaQuantidadeCompra"),
                    item.get("mediaQuantidadeSolicitada"),
                    item.get("mediaQuantidadeFornecida"),
                    item.get("mediaValorBaixa"),
                    import_run_id,
                    raw_code_param,
                ),
            )
            eventos = item.get("eventos") if isinstance(item.get("eventos"), list) else []
            for event in eventos:
                if not isinstance(event, dict):
                    continue
                cur.execute(
                    event_sql,
                    _event_tuple(item.get("codigo") or str(code), event, import_run_id, json_param(driver_name, driver, event)),
                )
                event_total += 1
        return {"import_run_id": import_run_id, "codes_loaded": len(codigos), "events_loaded": event_total}


def run(source: Path, run_dir: Path, mode: str, database_url: str = "", sample_size: int = 20) -> dict[str, Any]:
    raw_dir = ensure_dir(run_dir / "raw")
    ensure_dir(run_dir / "reports")
    source_hash = sha256_file(source)
    raw = load_raw(source)
    copied_raw = raw_dir / "historicoComprasCooperat.json"
    if copied_raw.resolve() != source.resolve():
        copied_raw.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    inspection = inspect(raw, source_hash)
    sample = deterministic_sample(raw, sample_size)
    apply_result = None
    if mode == "apply":
        apply_result = apply_to_sql(raw, database_url, source_hash)
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
    write_json(run_dir / "manifest.json", result)
    return result
