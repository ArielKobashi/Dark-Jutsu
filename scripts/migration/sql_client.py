from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator


class MissingSqlDriver(RuntimeError):
    pass


def _load_driver():
    try:
        import psycopg  # type: ignore

        return "psycopg", psycopg
    except Exception:
        pass
    try:
        import psycopg2  # type: ignore
        from psycopg2.extras import Json  # type: ignore

        return "psycopg2", (psycopg2, Json)
    except Exception as exc:
        raise MissingSqlDriver(
            "Nenhum driver PostgreSQL encontrado. Instale psycopg ou psycopg2 para usar --mode apply."
        ) from exc


def json_param(driver_name: str, driver: Any, value: Any) -> Any:
    if driver_name == "psycopg":
        return json.dumps(value, ensure_ascii=False)
    _psycopg2, Json = driver
    return Json(value)


@contextmanager
def connect(database_url: str) -> Iterator[Any]:
    if not database_url:
        raise RuntimeError("DATABASE_URL nao definido.")
    driver_name, driver = _load_driver()
    if driver_name == "psycopg":
        conn = driver.connect(database_url)
    else:
        psycopg2, _Json = driver
        conn = psycopg2.connect(database_url)
    try:
        yield driver_name, driver, conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
