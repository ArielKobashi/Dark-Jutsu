from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.migration.sql_client import connect, json_param
from scripts.migration.utils import ensure_dir, sha256_file, utc_now, write_json


DOMAIN = "counting"


def load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo Firebase export nao encontrado: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return data


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


def _int(value: Any, default: int = 0) -> int:
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


def _date(value: Any) -> str | None:
    text = _clean_text(value)
    return text if text and len(text) >= 10 else None


def _iter_sessions(raw: dict[str, Any]) -> list[tuple[str, str, str, dict[str, Any]]]:
    rows: list[tuple[str, str, str, dict[str, Any]]] = []
    for date_key, users in _node(raw, "contagens").items():
        if not isinstance(users, dict):
            continue
        for user_key, sessions in users.items():
            if not isinstance(sessions, dict):
                continue
            for session_key, session in sessions.items():
                if str(session_key).startswith("_") or not isinstance(session, dict):
                    continue
                rows.append((str(date_key), str(user_key), str(session_key), session))
    return rows


def _iter_label_jobs(raw: dict[str, Any]) -> list[tuple[str, str, str, dict[str, Any], str]]:
    rows: list[tuple[str, str, str, dict[str, Any], str]] = []
    for date_key, users in _node(raw, "contagens").items():
        if not isinstance(users, dict):
            continue
        for user_key, sessions in users.items():
            if isinstance(sessions, dict) and isinstance(sessions.get("_etiquetas"), dict):
                for job_key, job in sessions["_etiquetas"].items():
                    if isinstance(job, dict):
                        rows.append((str(date_key), str(user_key), str(job_key), job, "contagens/_etiquetas"))
    for date_key, users in _node(raw, "etiquetasGeradas").items():
        if not isinstance(users, dict):
            continue
        for user_key, jobs in users.items():
            if not isinstance(jobs, dict):
                continue
            for job_key, job in jobs.items():
                if isinstance(job, dict):
                    rows.append((str(date_key), str(user_key), str(job_key), job, "etiquetasGeradas"))
    return rows


def _machine_status_count(raw: dict[str, Any]) -> int:
    total = 0
    for _cycle, machines in _node(raw, "contagemStatusMaquinas").items():
        if not isinstance(machines, dict):
            continue
        for _machine, users in machines.items():
            if isinstance(users, dict):
                total += len([v for v in users.values() if isinstance(v, dict)])
    return total


def inspect(raw: dict[str, Any], source_hash: str) -> dict[str, Any]:
    sessions = _iter_sessions(raw)
    labels = _iter_label_jobs(raw)
    items = 0
    empty_checks = 0
    for _date_key, _user_key, _session_key, session in sessions:
        items += len(session.get("itens") if isinstance(session.get("itens"), dict) else {})
        empty_checks += len(session.get("verificacoesVazio") if isinstance(session.get("verificacoesVazio"), dict) else {})
    return {
        "domain": DOMAIN,
        "source_hash": source_hash,
        "counting_dates": len(_node(raw, "contagens")),
        "counting_sessions": len(sessions),
        "counting_items": items,
        "counting_empty_checks": empty_checks,
        "counting_drafts": len(_node(raw, "contagemRascunhos")),
        "machine_status": _machine_status_count(raw),
        "label_print_jobs": len(labels),
        "label_ranking": len(_node(raw, "rankingEtiquetas")),
        "control_events": len(_node(raw, "contagemControle")),
        "has_live_counting": bool(_node(raw, "contagemAtual")),
    }


def deterministic_sample(raw: dict[str, Any], sample_size: int = 20) -> dict[str, Any]:
    sessions = []
    for date_key, user_key, session_key, session in _iter_sessions(raw)[:sample_size]:
        sessions.append(
            {
                "legacy_path": f"contagens/{date_key}/{user_key}/{session_key}",
                "user": session.get("usuario") or user_key,
                "items": len(session.get("itens") if isinstance(session.get("itens"), dict) else {}),
                "empty_checks": len(session.get("verificacoesVazio") if isinstance(session.get("verificacoesVazio"), dict) else {}),
            }
        )
    return {"sessions": sessions}


def write_reports(run_dir: Path, inspection: dict[str, Any], sample: dict[str, Any], mode: str) -> None:
    reports_dir = ensure_dir(run_dir / "reports")
    write_json(reports_dir / "counting-summary.json", {"mode": mode, "inspection": inspection, "sample": sample})
    md = [
        "# Counting migration report",
        "",
        f"Mode: `{mode}`",
        f"Source hash: `{inspection['source_hash']}`",
        "",
        "## Totals",
        "",
        f"- Counting dates: {inspection['counting_dates']}",
        f"- Counting sessions: {inspection['counting_sessions']}",
        f"- Counting items: {inspection['counting_items']}",
        f"- Empty checks: {inspection['counting_empty_checks']}",
        f"- Drafts: {inspection['counting_drafts']}",
        f"- Machine status rows: {inspection['machine_status']}",
        f"- Label print jobs: {inspection['label_print_jobs']}",
        f"- Label ranking rows: {inspection['label_ranking']}",
        "",
        "## Sample sessions",
        "",
    ]
    for item in sample.get("sessions", [])[:20]:
        md.append(f"- `{item['legacy_path']}` items={item['items']} empty_checks={item['empty_checks']}")
    (reports_dir / "counting-summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def apply_to_sql(raw: dict[str, Any], database_url: str) -> dict[str, int]:
    with connect(database_url) as (driver_name, driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")
        cur.execute("delete from label_user_ranking")
        cur.execute("delete from label_print_jobs")
        cur.execute("delete from counting_control_events")
        cur.execute("delete from counting_machine_status")
        cur.execute("delete from counting_drafts")
        cur.execute("delete from counting_sessions")

        session_sql = """
            insert into counting_sessions (
              legacy_path, session_date, user_id, user_name, uid, machine,
              started_at, created_at, total_items, total_quantity_items,
              total_empty_checks, is_draft, source, raw_data
            )
            values (%s, %s, null, %s, %s, %s, %s, %s, %s, %s, %s, false, %s, %s::jsonb)
            returning id
        """
        item_sql = """
            insert into counting_items (
              session_id, item_id, item_legacy_key, protheus_code, cooperat_code,
              description, warehouse, address, system_balance, reorder_qty,
              counted_qty, diverges, raw_data
            )
            values (
              %s,
              (select id from inventory_items where protheus_code = %s order by is_dead asc limit 1),
              %s, %s, %s, %s, %s, %s, %s, %s, %s,
              case when %s is null or %s is null then null else %s <> %s end,
              %s::jsonb
            )
        """
        check_sql = """
            insert into counting_empty_checks (
              session_id, address, warehouse, status, machine, section, shelf, box, description, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """

        sessions_loaded = items_loaded = checks_loaded = 0
        for date_key, user_key, session_key, session in _iter_sessions(raw):
            itens = session.get("itens") if isinstance(session.get("itens"), dict) else {}
            checks = session.get("verificacoesVazio") if isinstance(session.get("verificacoesVazio"), dict) else {}
            legacy_path = f"contagens/{date_key}/{user_key}/{session_key}"
            cur.execute(
                session_sql,
                (
                    legacy_path,
                    _date(session.get("data") or date_key),
                    _clean_text(session.get("usuario")) or user_key,
                    _clean_text(session.get("uid")),
                    _clean_text(session.get("maquina")),
                    _timestamp(session.get("inicioEm")),
                    _timestamp(session.get("timestamp")),
                    _int(session.get("totalItens"), len(itens)),
                    len(itens),
                    len(checks),
                    "firebase:contagens",
                    json_param(driver_name, driver, {k: v for k, v in session.items() if k not in {"itens", "verificacoesVazio"}}),
                ),
            )
            session_id = cur.fetchone()[0]
            sessions_loaded += 1
            for item_key, item in itens.items():
                if not isinstance(item, dict):
                    continue
                system_balance = _num(item.get("saldoSistema"))
                counted = _num(item.get("contado"))
                cur.execute(
                    item_sql,
                    (
                        session_id,
                        _clean_text(item.get("protheus")),
                        str(item_key),
                        _clean_text(item.get("protheus")),
                        _clean_text(item.get("cooperat")),
                        _clean_text(item.get("descricao")),
                        _clean_text(item.get("armazem")),
                        _clean_text(item.get("endereco")),
                        system_balance,
                        _num(item.get("reposicao")),
                        counted,
                        counted,
                        system_balance,
                        counted,
                        system_balance,
                        json_param(driver_name, driver, item),
                    ),
                )
                items_loaded += 1
            for check_key, check in checks.items():
                if not isinstance(check, dict):
                    continue
                cur.execute(
                    check_sql,
                    (
                        session_id,
                        _clean_text(check.get("endereco")),
                        _clean_text(check.get("armazem")),
                        _clean_text(check.get("status")),
                        _clean_text(check.get("maquina")),
                        _clean_text(check.get("secao")),
                        _clean_text(check.get("prateleira")),
                        _clean_text(check.get("caixa")),
                        _clean_text(check.get("descricao") or check_key),
                        json_param(driver_name, driver, check),
                    ),
                )
                checks_loaded += 1

        drafts_loaded = 0
        for uid, draft in _node(raw, "contagemRascunhos").items():
            if not isinstance(draft, dict):
                continue
            presenca = draft.get("presenca") if isinstance(draft.get("presenca"), dict) else {}
            cur.execute(
                """
                insert into counting_drafts (
                  user_id, uid, user_name, cycle, machine, updated_at,
                  values_json, empty_checks_json, system_balances_json, session_json, raw_data
                )
                values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
                """,
                (
                    str(uid) if str(uid) else None,
                    str(uid),
                    _clean_text(presenca.get("usuario") or draft.get("usuario")),
                    "atual",
                    _clean_text(presenca.get("maquina")),
                    _timestamp(presenca.get("updatedAt")) or datetime.now(timezone.utc),
                    json_param(driver_name, driver, draft.get("valores") or {}),
                    json_param(driver_name, driver, draft.get("verificacoesVazio") or {}),
                    json_param(driver_name, driver, draft.get("saldosSistema") or {}),
                    json_param(driver_name, driver, presenca),
                    json_param(driver_name, driver, draft),
                ),
            )
            drafts_loaded += 1

        status_loaded = 0
        for cycle, machines in _node(raw, "contagemStatusMaquinas").items():
            if not isinstance(machines, dict):
                continue
            for machine_key, users in machines.items():
                if not isinstance(users, dict):
                    continue
                for user_key, status in users.items():
                    if not isinstance(status, dict):
                        continue
                    cur.execute(
                        """
                        insert into counting_machine_status (
                          cycle, machine_key, user_key, user_id, user_name, open, stage,
                          group_name, machine_label, counted, total, completed, item_key,
                          item_index, updated_at, raw_data
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        (
                            str(cycle),
                            str(machine_key),
                            str(user_key),
                            str(status.get("uid") or user_key),
                            _clean_text(status.get("usuario")),
                            bool(status.get("aberta")) if status.get("aberta") is not None else None,
                            _clean_text(status.get("etapa")),
                            _clean_text(status.get("grupo")),
                            _clean_text(status.get("maquinaLabel")),
                            _int(status.get("contados"), 0),
                            _int(status.get("total"), 0),
                            bool(status.get("concluida")) if status.get("concluida") is not None else None,
                            _clean_text(status.get("itemKey")),
                            _int(status.get("indice"), 0),
                            _timestamp(status.get("updatedAt")) or datetime.now(timezone.utc),
                            json_param(driver_name, driver, status),
                        ),
                    )
                    status_loaded += 1

        labels_loaded = 0
        for date_key, user_key, job_key, job, source in _iter_label_jobs(raw):
            cur.execute(
                """
                insert into label_print_jobs (
                  legacy_path, user_id, user_name, job_date, created_at, total_labels,
                  total_codes_submitted, by_size, had_missing_codes, source, raw_data
                )
                values (%s, null, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
                """,
                (
                    f"{source}/{date_key}/{user_key}/{job_key}",
                    _clean_text(job.get("usuario")) or user_key,
                    _date(job.get("data") or date_key),
                    _timestamp(job.get("timestamp")),
                    _int(job.get("totalEtiquetas"), 0),
                    _int(job.get("totalCodigosInformados"), 0),
                    json_param(driver_name, driver, job.get("porTamanho") or {}),
                    bool(job.get("teveNaoEncontrados", False)),
                    f"firebase:{source}",
                    json_param(driver_name, driver, job),
                ),
            )
            labels_loaded += 1

        ranking_loaded = 0
        for key, item in _node(raw, "rankingEtiquetas").items():
            if not isinstance(item, dict):
                continue
            cur.execute(
                """
                insert into label_user_ranking (user_key, user_name, total_labels, events, updated_at)
                values (%s, %s, %s, %s, %s)
                """,
                (
                    str(key),
                    _clean_text(item.get("usuario") or item.get("user_name") or key),
                    _int(item.get("totalEtiquetas"), 0),
                    _int(item.get("eventos"), 0),
                    _timestamp(item.get("atualizadoEm")),
                ),
            )
            ranking_loaded += 1

        return {
            "counting_sessions_loaded": sessions_loaded,
            "counting_items_loaded": items_loaded,
            "counting_empty_checks_loaded": checks_loaded,
            "counting_drafts_loaded": drafts_loaded,
            "machine_status_loaded": status_loaded,
            "label_print_jobs_loaded": labels_loaded,
            "label_user_ranking_loaded": ranking_loaded,
        }


def run(source: Path, run_dir: Path, mode: str, database_url: str = "", sample_size: int = 20) -> dict[str, Any]:
    raw_dir = ensure_dir(run_dir / "raw")
    source_hash = sha256_file(source)
    raw = load_raw(source)
    write_json(raw_dir / "counting-domain.json", {key: raw.get(key) for key in [
        "contagens", "contagemAtual", "contagemRascunhos", "contagemStatusMaquinas",
        "contagemControle", "etiquetasGeradas", "rankingEtiquetas"
    ] if key in raw})
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
    write_json(run_dir / "manifest-counting.json", result)
    return result
