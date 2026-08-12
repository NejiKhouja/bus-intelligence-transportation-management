"""Read-only MongoDB access for the optimization project.

This project never writes to the operational database. It only reads,
samples, and extracts data into local normalized files (see src/data/).
"""

from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database

from config.settings import settings


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    return MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=8000)


def get_db(name: str) -> Database:
    return get_client()[name]


def operational_db() -> Database:
    return get_db(settings.db_operational)


def tickets_archive_db() -> Database:
    return get_db(settings.db_tickets_archive)


def pos_archive_db() -> Database:
    return get_db(settings.db_pos_archive)


def opendata_db() -> Database:
    return get_db(settings.db_opendata)


def ping() -> bool:
    get_client().admin.command("ping")
    return True
