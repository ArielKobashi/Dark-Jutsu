import argparse
import getpass
import hashlib
import secrets
import sys
from pathlib import Path


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key and key not in __import__("os").environ:
            __import__("os").environ[key] = value


def password_hash(password: str) -> str:
    if len(password) < 4:
        raise ValueError("Senha muito curta.")
    salt = secrets.token_urlsafe(18)
    rounds = 260_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), rounds).hex()
    return f"pbkdf2_sha256${rounds}${salt}${digest}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Resetar senha SQL de um usuario Dark-Jutsu.")
    parser.add_argument("login", help="Nickname ou id do usuario.")
    parser.add_argument("--password", help="Nova senha. Se omitida, sera perguntada no terminal.")
    parser.add_argument("--database-url", help="DATABASE_URL; padrao vem do env local.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    load_env_file(root / "_local_secrets" / "sql_auth_runtime.env")

    database_url = args.database_url or __import__("os").environ.get("DATABASE_URL")
    if not database_url:
        database_url = "postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"

    password = args.password
    if not password:
        password = getpass.getpass("Nova senha: ")
        confirm = getpass.getpass("Confirmar senha: ")
        if password != confirm:
            print("ERRO: senhas diferentes.", file=sys.stderr)
            return 2

    try:
        import psycopg
        rows_mode = None
        try:
            from psycopg.rows import dict_row
            rows_mode = dict_row
        except Exception:
            rows_mode = None
    except Exception as exc:
        print(f"ERRO: psycopg nao disponivel neste Python: {exc}", file=sys.stderr)
        return 3

    login = args.login.strip().lower()
    hashed = password_hash(password)
    sql = """
        update users
           set password_hash = %s,
               password_status = 'definida',
               password_reset_required = false,
               password_changed_at = now(),
               token_version = token_version + 1
         where lower(id) = %s or nickname_key = %s
     returning id, nickname, role, active, password_status, password_hash is not null as has_hash
    """
    with psycopg.connect(database_url, row_factory=rows_mode) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (hashed, login, login))
            row = cur.fetchone()
            if not row:
                print(f"ERRO: usuario nao encontrado: {args.login}", file=sys.stderr)
                return 4
            conn.commit()
    print("OK: senha SQL redefinida.")
    print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
