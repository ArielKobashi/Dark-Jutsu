from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importador legado desativado pela migracao SQL."
    )
    parser.parse_args()
    raise SystemExit(
        "Importador direto para o banco legado foi desativado. "
        "Use o export JSON e o motor SQL em scripts/migration/run_transfer.py."
    )


if __name__ == "__main__":
    raise SystemExit(main())
