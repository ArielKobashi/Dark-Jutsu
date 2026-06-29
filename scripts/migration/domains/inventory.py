from __future__ import annotations

import json
import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.migration.sql_client import connect, json_param
from scripts.migration.utils import ensure_dir, sha256_file, utc_now, write_json


DOMAIN = "inventory"


def load_raw(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo estoqueGlobal nao encontrado: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    estoque = data.get("estoqueGlobal")
    if isinstance(estoque, dict):
        return estoque
    return data


def _map_len(value: Any) -> int:
    return len(value) if isinstance(value, dict) else 0


def _list_len(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _history_event_count(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    total = 0
    for events in value.values():
        if isinstance(events, list):
            total += len(events)
    return total


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


def _decode_legacy_key(value: str) -> str:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        return decoded or value
    except Exception:
        return value


def item_legacy_key(item: dict[str, Any], dead: bool = False) -> str:
    key = _clean_text(item.get("protheusKey")) or _clean_text(item.get("protheus")) or _clean_text(item.get("cooperat"))
    if key:
        return key
    fallback = _clean_text(item.get("descricao")) or "unknown"
    prefix = "MORTO|" if dead else "ITEM|"
    return prefix + fallback


def inspect(raw: dict[str, Any], source_hash: str) -> dict[str, Any]:
    dados = raw.get("dados")
    dados_mortos = raw.get("dadosMortos")
    ajustes = raw.get("ajustesItens")
    historico = raw.get("historicoSaldo")
    movimentacoes = raw.get("movimentacoesMata185")
    return {
        "domain": DOMAIN,
        "source_hash": source_hash,
        "root_keys": sorted(raw.keys()),
        "active_items": _list_len(dados),
        "dead_items": _list_len(dados_mortos),
        "adjustments": _map_len(ajustes),
        "balance_history_keys": _map_len(historico),
        "balance_history_events": _history_event_count(historico),
        "mata185_keys": _map_len(movimentacoes),
        "has_label_config": isinstance(raw.get("configuracoesEtiquetas"), dict),
        "has_counting_config": isinstance(raw.get("configContagem"), dict),
        "ultimaAtualizacao": raw.get("ultimaAtualizacao"),
        "atualizadoPor": raw.get("atualizadoPor"),
    }


def deterministic_sample(raw: dict[str, Any], sample_size: int = 20) -> dict[str, Any]:
    items = raw.get("dados") if isinstance(raw.get("dados"), list) else []
    dead = raw.get("dadosMortos") if isinstance(raw.get("dadosMortos"), list) else []
    combined = [*items[:3], *items[-3:], *dead[:3], *dead[-3:]]
    step = max(1, len(items) // max(1, sample_size)) if items else 1
    combined.extend(items[::step][:sample_size])
    seen = set()
    samples = []
    for item in combined:
        if not isinstance(item, dict):
            continue
        key = str(item.get("protheusKey") or item.get("protheus") or item.get("cooperat") or item.get("descricao") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        samples.append(
            {
                "key": key,
                "protheus": item.get("protheus"),
                "cooperat": item.get("cooperat"),
                "descricao": item.get("descricao"),
                "saldo": item.get("saldo"),
                "enderecoPrincipal": item.get("enderecoPrincipal"),
                "armazemPrincipal": item.get("armazemPrincipal"),
                "enderecos": _list_len(item.get("enderecos")),
                "morto": bool(item.get("morto")),
            }
        )
    return {"items": samples[:sample_size]}


def write_reports(run_dir: Path, inspection: dict[str, Any], sample: dict[str, Any], mode: str) -> None:
    reports_dir = ensure_dir(run_dir / "reports")
    write_json(reports_dir / "inventory-summary.json", {"mode": mode, "inspection": inspection, "sample": sample})
    md = [
        "# Inventory migration report",
        "",
        f"Mode: `{mode}`",
        f"Source hash: `{inspection['source_hash']}`",
        "",
        "## Totals",
        "",
        f"- Active items: {inspection['active_items']}",
        f"- Dead items: {inspection['dead_items']}",
        f"- Adjustments: {inspection['adjustments']}",
        f"- Balance history keys: {inspection['balance_history_keys']}",
        f"- Balance history events: {inspection['balance_history_events']}",
        f"- Mata185 keys: {inspection['mata185_keys']}",
        "",
        "## Sample items",
        "",
    ]
    for item in sample.get("items", [])[:20]:
        md.append(
            f"- `{item.get('key')}` saldo={item.get('saldo')} enderecos={item.get('enderecos')} morto={item.get('morto')}"
        )
    (reports_dir / "inventory-summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def _iter_items(raw: dict[str, Any]) -> list[tuple[dict[str, Any], bool]]:
    active = raw.get("dados") if isinstance(raw.get("dados"), list) else []
    dead = raw.get("dadosMortos") if isinstance(raw.get("dadosMortos"), list) else []
    return [(item, False) for item in active if isinstance(item, dict)] + [
        (item, True) for item in dead if isinstance(item, dict)
    ]


def apply_to_sql(raw: dict[str, Any], database_url: str, source_hash: str) -> dict[str, Any]:
    imported_at = _timestamp(raw.get("ultimaAtualizacao")) or datetime.now(timezone.utc)
    with connect(database_url) as (driver_name, driver, conn):
        cur = conn.cursor()
        cur.execute("set local app.role = 'service'")

        cur.execute("delete from inventory_movements")
        cur.execute("delete from inventory_balance_history")
        cur.execute("delete from inventory_adjustments")
        cur.execute("delete from inventory_item_limits")
        cur.execute("delete from inventory_item_addresses")
        cur.execute("delete from inventory_items")

        cur.execute(
            """
            insert into inventory_snapshots (
              source, saved_at, hash_after, updated_by, item_count, dead_item_count, payload, raw_metadata
            )
            values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
            returning id
            """,
            (
                "firebase:estoqueGlobal",
                imported_at,
                source_hash,
                raw.get("atualizadoPor"),
                _list_len(raw.get("dados")),
                _list_len(raw.get("dadosMortos")),
                json_param(driver_name, driver, raw),
                json_param(
                    driver_name,
                    driver,
                    {
                        "ultimaAtualizacao": raw.get("ultimaAtualizacao"),
                        "ultimaAtualizacaoAutomatica": raw.get("ultimaAtualizacaoAutomatica"),
                        "root_keys": sorted(raw.keys()),
                    },
                ),
            ),
        )
        snapshot_id = str(cur.fetchone()[0])

        item_sql = """
            insert into inventory_items (
              legacy_key, protheus_code, protheus_key, cooperat_code, description,
              primary_address, primary_warehouse, balance, min_qty, max_qty, reorder_qty,
              limit_source, min_source, max_source, reorder_source, is_dead, status,
              updated_at, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict (legacy_key) do update set
              protheus_code = excluded.protheus_code,
              protheus_key = excluded.protheus_key,
              cooperat_code = excluded.cooperat_code,
              description = excluded.description,
              primary_address = excluded.primary_address,
              primary_warehouse = excluded.primary_warehouse,
              balance = excluded.balance,
              min_qty = excluded.min_qty,
              max_qty = excluded.max_qty,
              reorder_qty = excluded.reorder_qty,
              limit_source = excluded.limit_source,
              min_source = excluded.min_source,
              max_source = excluded.max_source,
              reorder_source = excluded.reorder_source,
              is_dead = excluded.is_dead,
              status = excluded.status,
              updated_at = excluded.updated_at,
              raw_data = excluded.raw_data
            returning id
        """
        address_sql = """
            insert into inventory_item_addresses (
              item_id, item_legacy_key, address, warehouse, balance, source, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s::jsonb)
        """
        limit_sql = """
            insert into inventory_item_limits (
              item_id, item_legacy_key, source, min_qty, max_qty, reorder_qty,
              previous_balance, applied, imported_at, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """

        item_ids: dict[str, int] = {}
        addresses_loaded = 0
        limits_loaded = 0
        for item, dead in _iter_items(raw):
            legacy_key = item_legacy_key(item, dead)
            cur.execute(
                item_sql,
                (
                    legacy_key,
                    _clean_text(item.get("protheus")),
                    _clean_text(item.get("protheusKey")),
                    _clean_text(item.get("cooperat")),
                    _clean_text(item.get("descricao")),
                    _clean_text(item.get("enderecoPrincipal")),
                    _clean_text(item.get("armazemPrincipal")),
                    _num(item.get("saldo")),
                    _num(item.get("minimo")),
                    _num(item.get("maximo")),
                    _num(item.get("reposicao")),
                    _clean_text(item.get("limitesOrigem")),
                    _clean_text(item.get("minimoOrigem")),
                    _clean_text(item.get("maximoOrigem")),
                    _clean_text(item.get("reposicaoOrigem")),
                    bool(item.get("morto") or dead),
                    "dead" if bool(item.get("morto") or dead) else "active",
                    imported_at,
                    json_param(driver_name, driver, item),
                ),
            )
            item_id = int(cur.fetchone()[0])
            item_ids[legacy_key] = item_id
            protheus = _clean_text(item.get("protheus"))
            if protheus:
                item_ids.setdefault(protheus, item_id)

            for address in item.get("enderecos") if isinstance(item.get("enderecos"), list) else []:
                if not isinstance(address, dict):
                    continue
                cur.execute(
                    address_sql,
                    (
                        item_id,
                        legacy_key,
                        _clean_text(address.get("endereco")),
                        _clean_text(address.get("armazem")),
                        _num(address.get("saldo")),
                        "firebase:estoqueGlobal/enderecos",
                        json_param(driver_name, driver, address),
                    ),
                )
                addresses_loaded += 1

            limites = item.get("limitesCooperat")
            if isinstance(limites, dict):
                cur.execute(
                    limit_sql,
                    (
                        item_id,
                        legacy_key,
                        "cooperat",
                        _num(limites.get("minimo")),
                        _num(limites.get("maximo")),
                        _num(limites.get("reposicao")),
                        _num(limites.get("saldoAnterior")),
                        item.get("limitesOrigem") == "cooperat",
                        imported_at,
                        json_param(driver_name, driver, limites),
                    ),
                )
                limits_loaded += 1

        adjustments_loaded = 0
        adjustment_sql = """
            insert into inventory_adjustments (
              item_id, item_legacy_key, legacy_key, min_qty, max_qty, reorder_qty,
              reason, updated_by_name, updated_at, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """
        ajustes = raw.get("ajustesItens") if isinstance(raw.get("ajustesItens"), dict) else {}
        for legacy_key, ajuste in ajustes.items():
            if not isinstance(ajuste, dict):
                continue
            item_key = _clean_text(ajuste.get("itemKey")) or _decode_legacy_key(str(legacy_key))
            cur.execute(
                adjustment_sql,
                (
                    item_ids.get(item_key or ""),
                    item_key,
                    str(legacy_key),
                    _num(ajuste.get("minimo")),
                    _num(ajuste.get("maximo")),
                    _num(ajuste.get("reposicao")),
                    "firebase:estoqueGlobal/ajustesItens",
                    _clean_text(ajuste.get("atualizadoPor")),
                    _timestamp(ajuste.get("atualizadoEm")) or imported_at,
                    json_param(driver_name, driver, ajuste),
                ),
            )
            adjustments_loaded += 1

        history_loaded = 0
        history_sql = """
            insert into inventory_balance_history (
              item_id, item_legacy_key, event_at, event_date_label, previous_balance,
              current_balance, delta, event_type, source, raw_data
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """
        historico = raw.get("historicoSaldo") if isinstance(raw.get("historicoSaldo"), dict) else {}
        for encoded_key, events in historico.items():
            item_key = _decode_legacy_key(str(encoded_key))
            if not isinstance(events, list):
                continue
            for event in events:
                if not isinstance(event, dict):
                    continue
                cur.execute(
                    history_sql,
                    (
                        item_ids.get(item_key),
                        item_key,
                        _timestamp(event.get("timestamp")),
                        _clean_text(event.get("data")),
                        _num(event.get("saldoAnterior")),
                        _num(event.get("saldoAtual")),
                        _num(event.get("delta")),
                        _clean_text(event.get("tipo")),
                        "firebase:estoqueGlobal/historicoSaldo",
                        json_param(driver_name, driver, event),
                    ),
                )
                history_loaded += 1

        movement_loaded = 0
        movimentacoes = raw.get("movimentacoesMata185")
        if isinstance(movimentacoes, dict):
            cur.execute(
                """
                insert into inventory_movements (
                  source, source_document, movement_at, movement_type, status, raw_data
                )
                values (%s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    "firebase:estoqueGlobal/movimentacoesMata185",
                    "movimentacoesMata185",
                    _timestamp(movimentacoes.get("atualizadoEm")),
                    "snapshot",
                    "raw",
                    json_param(driver_name, driver, movimentacoes),
                ),
            )
            movement_loaded = 1

        return {
            "snapshot_id": snapshot_id,
            "items_loaded": len(_iter_items(raw)),
            "addresses_loaded": addresses_loaded,
            "limits_loaded": limits_loaded,
            "adjustments_loaded": adjustments_loaded,
            "balance_history_loaded": history_loaded,
            "movements_loaded": movement_loaded,
        }


def run(source: Path, run_dir: Path, mode: str, database_url: str = "", sample_size: int = 20) -> dict[str, Any]:
    raw_dir = ensure_dir(run_dir / "raw")
    source_hash = sha256_file(source)
    raw = load_raw(source)
    copied_raw = raw_dir / "estoqueGlobal.json"
    if copied_raw.resolve() != source.resolve():
        write_json(copied_raw, raw)
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
    write_json(run_dir / "manifest-inventory.json", result)
    return result
