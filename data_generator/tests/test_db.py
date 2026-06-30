"""Tests for the SQLite database layer (infra/db.py).

Requires the DB to be built first:
    python generate_data.py --seed 42 --build-db
"""
from __future__ import annotations

from pathlib import Path

import pytest

from infra.db import RefineryDB, build_database

DB_PATH = Path(__file__).parent.parent / "output" / "crestmount.db"
OUTPUT_DIR = Path(__file__).parent.parent / "output"


@pytest.fixture(scope="module")
def db() -> RefineryDB:
    if not DB_PATH.exists():
        pytest.skip("crestmount.db not found — run generate_data.py --build-db")
    return RefineryDB(DB_PATH)


def test_db_all_tables_populated(db: RefineryDB) -> None:
    counts = db.table_rowcounts()
    expected = ["assets", "operations_calendar", "spare_parts", "crews",
                "permits", "planners", "notifications", "work_orders",
                "failure_events", "sensors", "sensor_readings",
                "asset_connections", "weather", "production"]
    for t in expected:
        assert t in counts, f"Table {t} missing from DB"
        assert counts[t] > 0, f"Table {t} is empty"


def test_db_referential_integrity(db: RefineryDB) -> None:
    """foreign_key_check returns no violations when FKs are enforced."""
    rows = db.query("PRAGMA foreign_key_check")
    assert rows == [], f"FK violations: {rows[:5]}"


def test_db_open_backlog_query(db: RefineryDB) -> None:
    rows = db.query(
        "SELECT COUNT(*) AS c FROM notifications WHERE status IN ('open','in_review')"
    )
    assert 1_500 <= rows[0]["c"] <= 2_500


def test_db_t1_open_query(db: RefineryDB) -> None:
    rows = db.query("""
        SELECT COUNT(*) AS c FROM notifications n
        JOIN assets a ON a.asset_id = n.asset_id
        WHERE n.status IN ('open','in_review') AND a.criticality_tier = 1
    """)
    assert 5 <= rows[0]["c"] <= 30


def test_db_query_df_returns_dataframe(db: RefineryDB) -> None:
    import pandas as pd
    df = db.query_df("SELECT * FROM assets LIMIT 10")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 10


def test_db_iter_query_chunks(db: RefineryDB) -> None:
    chunks = list(db.iter_query("SELECT * FROM assets", chunksize=100))
    assert len(chunks) >= 5
    assert all(len(c) <= 100 for c in chunks)
    assert sum(len(c) for c in chunks) == db.table_rowcounts()["assets"]


def test_build_database_rebuilds_cleanly() -> None:
    """build_database should be idempotent — dropping and recreating."""
    if not (OUTPUT_DIR / "assets.csv").exists():
        pytest.skip("CSVs not present")
    p = build_database(OUTPUT_DIR, OUTPUT_DIR / "test_rebuild.db")
    assert p.exists()
    db = RefineryDB(p)
    assert db.table_rowcounts()["assets"] > 0
    db.close()
    p.unlink()  # cleanup
