from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.migration.config import load_config
from scripts.migration.integrity import automus, chat, cooperat, counting, dashboard, inventory, occurrences, users
from scripts.migration.integrity.base import max_severity, should_fail
from scripts.migration.utils import ensure_dir, run_id_now


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verificador de integridade pos-migracao.")
    parser.add_argument("--domain", choices=["cooperat", "inventory", "users", "dashboard", "counting", "occurrences", "chat", "automus"], required=True)
    parser.add_argument("--run-id", help="Run id existente ou novo.")
    parser.add_argument("--raw", help="Arquivo raw JSON ou pasta raw da execucao.")
    parser.add_argument("--database-url", help="DATABASE_URL para comparar com SQL.")
    parser.add_argument("--fail-on", choices=["low", "medium", "high", "critical"], default="high")
    return parser


def resolve_raw(config, domain: str, raw_arg: str | None, run_dir: Path) -> Path:
    if raw_arg:
        raw = Path(raw_arg)
        if not raw.is_absolute():
            raw = config.root / raw
        if raw.is_dir():
            filename = {
                "cooperat": "historicoComprasCooperat.json",
                "inventory": "estoqueGlobal.json",
                "users": "users-domain.json",
                "dashboard": "dashboardConfig.json",
                "counting": "counting-domain.json",
                "occurrences": "occurrences-domain.json",
                "chat": "chat-domain.json",
                "automus": "automus-domain.json",
            }[domain]
            return raw / filename
        return raw
    filename = {
        "cooperat": "historicoComprasCooperat.json",
        "inventory": "estoqueGlobal.json",
        "users": "users-domain.json",
        "dashboard": "dashboardConfig.json",
        "counting": "counting-domain.json",
        "occurrences": "occurrences-domain.json",
        "chat": "chat-domain.json",
        "automus": "automus-domain.json",
    }[domain]
    candidate = run_dir / "raw" / filename
    if candidate.exists():
        return candidate
    if domain in {"inventory", "users", "dashboard", "counting", "occurrences", "chat", "automus"}:
        raise FileNotFoundError(f"Arquivo raw de {domain} nao encontrado: {candidate}")
    return config.cooperat_json


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    run_id = args.run_id or run_id_now()
    run_dir = ensure_dir(config.run_dir_root / run_id)
    raw_path = resolve_raw(config, args.domain, args.raw, run_dir)
    database_url = args.database_url or config.database_url

    if args.domain == "cooperat":
        if database_url:
            summary, results = cooperat.check_sql(raw_path, database_url)
            mode = "raw-vs-sql"
        else:
            summary, results = cooperat.check_raw(raw_path)
            mode = "raw-only"
        cooperat.write_report(run_dir, summary, results, mode)
    elif args.domain == "inventory":
        if database_url:
            summary, results = inventory.check_sql(raw_path, database_url)
            mode = "raw-vs-sql"
        else:
            summary, results = inventory.check_raw(raw_path)
            mode = "raw-only"
        inventory.write_report(run_dir, summary, results, mode)
    elif args.domain == "users":
        if database_url:
            summary, results = users.check_sql(raw_path, database_url)
            mode = "raw-vs-sql"
        else:
            summary, results = users.check_raw(raw_path)
            mode = "raw-only"
        users.write_report(run_dir, summary, results, mode)
    elif args.domain == "dashboard":
        if database_url:
            summary, results = dashboard.check_sql(raw_path, database_url)
            mode = "raw-vs-sql"
        else:
            summary, results = dashboard.check_raw(raw_path)
            mode = "raw-only"
        dashboard.write_report(run_dir, summary, results, mode)
    elif args.domain == "counting":
        if database_url:
            summary, results = counting.check_sql(raw_path, database_url)
            mode = "raw-vs-sql"
        else:
            summary, results = counting.check_raw(raw_path)
            mode = "raw-only"
        counting.write_report(run_dir, summary, results, mode)
    elif args.domain == "occurrences":
        if database_url:
            summary, results = occurrences.check_sql(raw_path, database_url)
            mode = "raw-vs-sql"
        else:
            summary, results = occurrences.check_raw(raw_path)
            mode = "raw-only"
        occurrences.write_report(run_dir, summary, results, mode)
    elif args.domain == "chat":
        if database_url:
            summary, results = chat.check_sql(raw_path, database_url)
            mode = "raw-vs-sql"
        else:
            summary, results = chat.check_raw(raw_path)
            mode = "raw-only"
        chat.write_report(run_dir, summary, results, mode)
    elif args.domain == "automus":
        if database_url:
            summary, results = automus.check_sql(raw_path, database_url)
            mode = "raw-vs-sql"
        else:
            summary, results = automus.check_raw(raw_path)
            mode = "raw-only"
        automus.write_report(run_dir, summary, results, mode)
    else:
        raise RuntimeError(f"Dominio nao implementado: {args.domain}")

    print(f"run_dir={run_dir}")
    print(f"domain={args.domain} mode={mode}")
    print(f"findings={len(results)} max_severity={max_severity(results)}")
    return 1 if should_fail(results, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
