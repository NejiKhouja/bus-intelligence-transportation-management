# data/

This project never writes to the operational MongoDB. Extracted and
derived datasets are persisted locally here instead, so ML/optimization
work is reproducible without re-querying MongoDB every time.

- `raw/` — extraction.py output, as close to the MongoDB documents as a
  flat table allows (one file per dataset per extraction run, e.g.
  `tickets_2025.parquet`, `gps_20260601.parquet`).
- `processed/` — cleaned/validated versions of `raw/` (bad rows dropped
  or flagged, dates parsed, coordinates normalized).
- `features/` — model-ready feature tables from `src/features/`.

Nothing in this directory is committed to version control (see
`.gitignore`) — regenerate it from MongoDB via `scripts/explore_database.py`
and `src/data/extraction.py` rather than relying on a checked-in copy.
