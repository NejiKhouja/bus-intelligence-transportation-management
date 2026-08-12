"""Read-only access to the sibling winicari repo's SQLite reference DB.
See docs/reference_db_integration.md. Never write to it."""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

import pandas as pd

from config.settings import settings


class ReferenceDbUnavailable(RuntimeError):
    """Reference DB not found on this machine — fall back to raw-Mongo
    extraction instead of crashing."""


@lru_cache(maxsize=1)
def _connect() -> sqlite3.Connection:
    path = Path(settings.reference_db_path).resolve()
    if not path.exists():
        raise ReferenceDbUnavailable(
            f"Reference DB not found at {path}. Set REFERENCE_DB_PATH in .env "
            "to point at the winicari repo's data/reference/winicari_reference_slim.db, "
            "or use src.data.extraction's raw-MongoDB functions instead."
        )
    # uri=True + mode=ro: this project must never write to another
    # project's database, even by accident.
    uri = f"file:{path.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def is_available() -> bool:
    try:
        _connect()
        return True
    except ReferenceDbUnavailable:
        return False


def read_table(table: str, where: str | None = None, params: tuple = ()) -> pd.DataFrame:
    sql = f"SELECT * FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return pd.read_sql_query(sql, _connect(), params=params)


def read_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    return pd.read_sql_query(sql, _connect(), params=params)


def list_tables() -> list[str]:
    return read_query("SELECT name FROM sqlite_master WHERE type='table'")["name"].tolist()


def table_row_counts() -> dict[str, int]:
    return {t: int(read_query(f"SELECT COUNT(*) AS n FROM {t}").iloc[0]["n"]) for t in list_tables()}
