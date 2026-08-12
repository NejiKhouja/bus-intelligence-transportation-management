"""Smoke tests against the live MongoDB instance. Skip if unreachable."""

import pytest

from src.database.mongo_client import ping
from src.database import explorer


@pytest.fixture(scope="module")
def mongo_available():
    try:
        return ping()
    except Exception:
        pytest.skip("MongoDB not reachable at MONGODB_URI")


def test_ping(mongo_available):
    assert mongo_available is True


def test_expected_databases_present(mongo_available):
    dbs = set(explorer.list_databases())
    expected = {"winicari", "Historique_Tickets", "Historique_pos", "OpenData"}
    assert expected.issubset(dbs)
