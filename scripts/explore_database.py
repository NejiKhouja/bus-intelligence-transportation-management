#!/usr/bin/env python
"""Reusable MongoDB exploration CLI for this project.

Safe by design: never dumps a full collection, never modifies data.
Uses estimated_document_count (metadata), $sample (bounded random sample),
and sort+limit(1) for min/max instead of full scans.

Examples:
    python scripts/explore_database.py list-databases
    python scripts/explore_database.py list-collections --db winicari
    python scripts/explore_database.py stats --db winicari
    python scripts/explore_database.py sample --db winicari --collection bus -n 3
    python scripts/explore_database.py fields --db winicari --collection ligne
    python scripts/explore_database.py range --db winicari --collection position --field date
    python scripts/explore_database.py distinct --db winicari --collection bus --field societe
    python scripts/explore_database.py daily-span --db Historique_pos
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bson import ObjectId  # noqa: E402

from src.database import explorer  # noqa: E402
from src.database.mongo_client import get_db, ping  # noqa: E402


def _default(o):
    if isinstance(o, ObjectId):
        return f"ObjectId({o})"
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


def _print(obj):
    print(json.dumps(obj, default=_default, ensure_ascii=False, indent=2))


def cmd_list_databases(args):
    _print(explorer.list_databases())


def cmd_list_collections(args):
    db = get_db(args.db)
    _print(explorer.list_collections(db))


def cmd_stats(args):
    db = get_db(args.db)
    rows = [explorer.collection_stats(db, c) for c in explorer.list_collections(db)]
    rows.sort(key=lambda r: r["estimated_count"], reverse=True)
    _print(rows)


def cmd_sample(args):
    db = get_db(args.db)
    _print(explorer.sample_documents(db, args.collection, args.n))


def cmd_fields(args):
    db = get_db(args.db)
    docs = explorer.sample_documents(db, args.collection, args.n)
    freq = explorer.field_type_frequencies(docs, max_depth=args.depth)
    _print({k: dict(v) for k, v in freq.items()})


def cmd_range(args):
    db = get_db(args.db)
    _print(explorer.timestamp_range(db, args.collection, args.field))


def cmd_distinct(args):
    db = get_db(args.db)
    _print(explorer.distinct_values(db, args.collection, args.field, args.limit))


def cmd_daily_span(args):
    db = get_db(args.db)
    _print(explorer.daily_collections_span(db, args.prefix))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ping").set_defaults(func=lambda a: _print(ping()))

    sub.add_parser("list-databases").set_defaults(func=cmd_list_databases)

    p = sub.add_parser("list-collections")
    p.add_argument("--db", required=True)
    p.set_defaults(func=cmd_list_collections)

    p = sub.add_parser("stats")
    p.add_argument("--db", required=True)
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("sample")
    p.add_argument("--db", required=True)
    p.add_argument("--collection", required=True)
    p.add_argument("-n", type=int, default=3)
    p.set_defaults(func=cmd_sample)

    p = sub.add_parser("fields")
    p.add_argument("--db", required=True)
    p.add_argument("--collection", required=True)
    p.add_argument("-n", type=int, default=200, help="documents to sample")
    p.add_argument("--depth", type=int, default=1, help="nested-document depth to flatten")
    p.set_defaults(func=cmd_fields)

    p = sub.add_parser("range")
    p.add_argument("--db", required=True)
    p.add_argument("--collection", required=True)
    p.add_argument("--field", required=True)
    p.set_defaults(func=cmd_range)

    p = sub.add_parser("distinct")
    p.add_argument("--db", required=True)
    p.add_argument("--collection", required=True)
    p.add_argument("--field", required=True)
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_distinct)

    p = sub.add_parser("daily-span", help="For date-sharded DBs like Historique_pos")
    p.add_argument("--db", required=True)
    p.add_argument("--prefix", default="d")
    p.set_defaults(func=cmd_daily_span)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
