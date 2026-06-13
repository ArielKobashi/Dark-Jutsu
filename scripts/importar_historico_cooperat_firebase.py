from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = ROOT / "data" / "historico_cooperat_antigo.json"
DEFAULT_INDEX = ROOT / "index.html"
FIREBASE_PATH = "historicoComprasCooperat"


def _extract(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text)
    if not match:
        raise RuntimeError(f"Nao encontrei {label} no index.html.")
    return match.group(1)


def load_firebase_config(index_path: Path = DEFAULT_INDEX) -> tuple[str, str]:
    text = index_path.read_text(encoding="utf-8", errors="ignore")
    api_key = _extract(r'apiKey\s*:\s*"([^"]+)"', text, "apiKey")
    db_url = _extract(r'databaseURL\s*:\s*"([^"]+)"', text, "databaseURL").rstrip("/")
    return api_key, db_url


def request_json(url: str, payload: dict | None = None, method: str = "POST") -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Firebase HTTP {exc.code}: {body}") from exc


def login(api_key: str, email: str, password: str) -> str:
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    data = request_json(
        url,
        {
            "email": email,
            "password": password,
            "returnSecureToken": True,
        },
    )
    token = data.get("idToken")
    if not token:
        raise RuntimeError("Login Firebase nao retornou idToken.")
    return token


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importa o historico Cooperat antigo para o Firebase Realtime Database."
    )
    parser.add_argument("--json", default=str(DEFAULT_JSON), help="Arquivo JSON gerado.")
    parser.add_argument("--email", help="Email admin do Firebase.")
    parser.add_argument("--login", help="Login curto. Ex.: davi vira davi@sistema.com.")
    parser.add_argument("--senha", help="Senha do usuario admin. Se omitida, usa FIREBASE_PASSWORD ou prompt.")
    parser.add_argument(
        "--path",
        default=FIREBASE_PATH,
        help="Caminho no Realtime Database. Padrao: historicoComprasCooperat.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida o arquivo e o login, mas nao envia ao Firebase.",
    )
    args = parser.parse_args()

    json_path = Path(args.json)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("codigos"), dict):
        raise RuntimeError("JSON invalido: campo codigos ausente.")

    email = (args.email or "").strip()
    if not email and args.login:
        login_name = args.login.strip()
        email = login_name if "@" in login_name else f"{login_name}@sistema.com"
    if not email:
        raise RuntimeError("Informe --email ou --login.")

    password = args.senha or os.environ.get("FIREBASE_PASSWORD") or getpass.getpass("Senha Firebase: ")
    if not password:
        raise RuntimeError("Senha Firebase vazia.")

    api_key, db_url = load_firebase_config()
    token = login(api_key, email, password)
    print(f"Login OK. Codigos: {payload.get('totalCodigos')} | eventos: {payload.get('totalEventos')}")

    if args.dry_run:
        print("Dry-run ativo: nada foi enviado.")
        return 0

    path = args.path.strip("/")
    url = f"{db_url}/{path}.json?auth={token}"
    request_json(url, payload, method="PUT")
    print(f"Historico enviado para Firebase: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
