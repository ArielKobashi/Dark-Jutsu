from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class MigrationConfig:
    root: Path
    run_dir_root: Path
    database_url: str
    cooperat_json: Path


def load_config() -> MigrationConfig:
    run_dir = Path(os.environ.get("MIGRATION_RUN_DIR") or (ROOT / "_migration_runs"))
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    return MigrationConfig(
        root=ROOT,
        run_dir_root=run_dir,
        database_url=os.environ.get("DATABASE_URL", ""),
        cooperat_json=Path(os.environ.get("COOPERAT_JSON") or (ROOT / "data" / "historico_cooperat_antigo.json")),
    )
