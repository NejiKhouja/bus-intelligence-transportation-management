"""Generic, read-only MongoDB exploration helpers.

Every function here is safe to run against large collections: sampling
uses $sample or bounded .find().limit(), never a full collection scan
unless the caller explicitly asks for exact counts.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Iterable

from bson import ObjectId
from pymongo.collection import Collection
from pymongo.database import Database

from .mongo_client import get_client


def list_databases(exclude_system: bool = True) -> list[str]:
    names = get_client().list_database_names()
    if exclude_system:
        names = [n for n in names if n not in ("admin", "config", "local")]
    return names


def list_collections(db: Database) -> list[str]:
    return db.list_collection_names()


def collection_stats(db: Database, collection: str) -> dict[str, Any]:
    """Cheap stats: estimated count (metadata-based, no scan) + sample size used."""
    coll = db[collection]
    return {
        "database": db.name,
        "collection": collection,
        "estimated_count": coll.estimated_document_count(),
    }


def sample_documents(db: Database, collection: str, n: int = 5) -> list[dict]:
    """Random sample via $sample — avoids bias toward insertion order and
    avoids scanning the whole collection for large collections."""
    return list(db[collection].aggregate([{"$sample": {"size": n}}]))


def _type_name(value: Any) -> str:
    if isinstance(value, ObjectId):
        return "ObjectId"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "embedded_document"
    return type(value).__name__


def field_type_frequencies(docs: Iterable[dict], max_depth: int = 1, prefix: str = "") -> dict[str, Counter]:
    """Field name -> Counter of observed types, from a small set of sample
    documents. Nested documents are flattened up to `max_depth` levels so
    embedded structure (e.g. service.bus.societe) is visible."""
    freq: dict[str, Counter] = {}

    def walk(d: dict, depth: int, path: str):
        for k, v in d.items():
            full = f"{path}.{k}" if path else k
            freq.setdefault(full, Counter())[_type_name(v)] += 1
            if isinstance(v, dict) and depth < max_depth:
                walk(v, depth + 1, full)

    for doc in docs:
        walk(doc, 1, prefix)
    return freq


def distinct_values(db: Database, collection: str, field: str, limit: int | None = 50) -> list:
    values = db[collection].distinct(field)
    return values[:limit] if limit else values


def timestamp_range(db: Database, collection: str, field: str) -> dict[str, Any]:
    """Min/max of a field, using an index-friendly sort+limit(1) instead of
    an aggregation min/max over the whole collection."""
    coll: Collection = db[collection]
    first = list(coll.find({field: {"$exists": True}}, {field: 1}).sort(field, 1).limit(1))
    last = list(coll.find({field: {"$exists": True}}, {field: 1}).sort(field, -1).limit(1))
    return {
        "field": field,
        "min": first[0].get(field) if first else None,
        "max": last[0].get(field) if last else None,
    }


def daily_collections_span(db: Database, prefix: str = "d") -> dict[str, Any]:
    """For date-sharded databases like Historique_pos, where each day is its
    own collection named e.g. d20260601."""
    names = sorted(n for n in db.list_collection_names() if n.startswith(prefix))
    return {
        "count": len(names),
        "earliest": names[0] if names else None,
        "latest": names[-1] if names else None,
    }
