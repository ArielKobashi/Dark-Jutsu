from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.migration.config import load_config
from scripts.migration.domains import cooperat, inventory
from scripts.migration.utils import ensure_dir, run_id_now


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Motor de transferencia Firebase -> SQL.")
    sub = parser.add_subparsers(dest="command", required=True)

    transfer = sub.add_parser("transfer", help="Executa transferencia de um dominio.")
    transfer.add_argument("--domain", choices=["cooperat", "inventory"], required=True)
    transfer.add_argument("--mode", choices=["dry-run", "apply"], default="dry-run")
    transfer.add_argument("--source", help="Arquivo raw/local de origem.")
    transfer.add_argument("--run-id", help="Identificador da execucao.")
    transfer.add_argument("--sample-size", type=int, default=20)

    inspect = sub.add_parser("inspect", help="Inspeciona um dominio sem gravar SQL.")
    inspect.add_argument("--domain", choices=["cooperat", "inventory"], required=True)
    inspect.add_argument("--source", help="Arquivo raw/local de origem.")
    inspect.add_argument("--run-id", help="Identificador da execucao.")
    inspect.add_argument("--sample-size", type=int, default=20)
    return parser


def resolve_source(domain: str, source_arg: str | None, run_dir: Path, root: Path, cooperat_json: Path) -> Path:
    if source_arg:
        source = Path(source_arg)
    elif domain == "cooperat":
        source = cooperat_json
    elif domain == "inventory":
        source = run_dir / "raw" / "estoqueGlobal.json"
    else:
        raise RuntimeError(f"Dominio nao implementado: {domain}")
    return source if source.is_absolute() else root / source


def print_summary(result: dict) -> int:
    inspection = result["inspection"]
    print(f"run_dir={result['run_dir']}")
    print(f"domain={result['domain']} mode={result['mode']}")
    if result["domain"] == "cooperat":
        print(f"codes={inspection['total_codes_counted']} events={inspection['total_events_counted']}")
        print(f"codes_match={inspection['codes_match']} events_match={inspection['events_match']}")
        if result.get("apply_result"):
            print(f"apply_result={result['apply_result']}")
        return 0 if inspection["codes_match"] and inspection["events_match"] else 2
    if result["domain"] == "inventory":
        print(
            "active_items={active_items} dead_items={dead_items} "
            "adjustments={adjustments} balance_history_events={balance_history_events}".format(**inspection)
        )
        print(f"mata185_keys={inspection['mata185_keys']}")
        if result.get("apply_result"):
            print(f"apply_result={result['apply_result']}")
        return 0
    raise RuntimeError(f"Dominio nao implementado: {result['domain']}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    run_id = args.run_id or run_id_now()
    run_dir = ensure_dir(config.run_dir_root / run_id)

    mode = "dry-run" if args.command == "inspect" else args.mode
    source = resolve_source(args.domain, args.source, run_dir, config.root, config.cooperat_json)

    if args.domain == "cooperat":
        result = cooperat.run(
            source=source,
            run_dir=run_dir,
            mode=mode,
            database_url=config.database_url,
            sample_size=max(1, args.sample_size),
        )
    elif args.domain == "inventory":
        result = inventory.run(
            source=source,
            run_dir=run_dir,
            mode=mode,
            database_url=config.database_url,
            sample_size=max(1, args.sample_size),
        )
    else:
        raise RuntimeError(f"Dominio nao implementado: {args.domain}")

    return print_summary(result)


if __name__ == "__main__":
    raise SystemExit(main())
