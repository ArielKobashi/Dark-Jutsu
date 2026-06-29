from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.migration.config import load_config
from scripts.migration.firebase_client import FirebaseClient, FirebaseConfig
from scripts.migration.utils import ensure_dir, run_id_now, write_json


DEFAULT_PATHS = [
    "estoqueGlobal",
    "usuarios",
    "solicitacoesCadastro",
    "usuariosBanidos",
    "contagens",
    "contagemRascunhos",
    "contagemAtual",
    "contagemStatusMaquinas",
    "contagemControle",
    "etiquetasGeradas",
    "rankingEtiquetas",
    "dashboardConfig",
    "historicoComprasCooperat",
    "ocorrencias",
    "chatGlobal/ocorrencias",
    "chatRooms",
    "chatReadState",
    "automus/releases",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Exporta caminhos do Firebase Realtime Database para JSON raw.")
    parser.add_argument("--run-id", default=run_id_now())
    parser.add_argument("--path", action="append", help="Caminho Firebase. Pode repetir.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    run_dir = ensure_dir(config.run_dir_root / args.run_id)
    raw_dir = ensure_dir(run_dir / "raw")
    fb = FirebaseClient(
        FirebaseConfig(
            api_key=os.environ.get("FIREBASE_API_KEY", ""),
            database_url=os.environ.get("FIREBASE_DATABASE_URL", ""),
            email=os.environ.get("FIREBASE_EMAIL", ""),
            password=os.environ.get("FIREBASE_PASSWORD", ""),
            id_token=os.environ.get("FIREBASE_ID_TOKEN", ""),
        )
    )
    paths = args.path or DEFAULT_PATHS
    manifest = {"run_id": args.run_id, "paths": []}
    for path in paths:
        print(f"exporting {path}...")
        data = fb.get_path(path)
        filename = path.strip("/").replace("/", "__") + ".json"
        out = raw_dir / filename
        write_json(out, data)
        manifest["paths"].append({"path": path, "file": str(out), "exists": data is not None})
    write_json(run_dir / "firebase-export-manifest.json", manifest)
    print(f"run_dir={run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
