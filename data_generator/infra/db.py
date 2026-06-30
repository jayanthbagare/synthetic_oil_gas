"""SQLite database layer — loads generated CSVs into a queryable relational DB.

This gives workshop agents (and the dashboard) a single query interface
instead of juggling pandas DataFrames. Foreign keys are declared and enforced
so that referential integrity holds at query time.

Usage:
    from infra.db import build_database, RefineryDB
    build_database("./output")                       # creates ./output/crestmount.db
    db = RefineryDB("./output/crestmount.db")
    rows = db.query("SELECT * FROM notifications WHERE status='open' LIMIT 5")
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

# --------------------------------------------------------------------------
# Table DDL — column types mirror the schema docs. Foreign keys are declared
# so PRAGMA foreign_keys = ON enforces integrity at insert time.
# --------------------------------------------------------------------------

_DDL: list[str] = [
    # ---- independent entities ----
    """CREATE TABLE IF NOT EXISTS assets (
        asset_id                TEXT PRIMARY KEY,
        asset_class             TEXT NOT NULL,
        asset_name              TEXT NOT NULL,
        location_unit           TEXT NOT NULL,
        criticality_tier        INTEGER NOT NULL,
        install_date            TEXT,
        last_major_overhaul_date TEXT,
        mtbf_days               INTEGER,
        replacement_cost_usd    INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS operations_calendar (
        date                     TEXT PRIMARY KEY,
        plant_state              TEXT NOT NULL,
        production_rate_pct      REAL,
        maintenance_window_hours REAL,
        notes                    TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS spare_parts (
        part_id                TEXT PRIMARY KEY,
        part_name              TEXT NOT NULL,
        part_category          TEXT NOT NULL,
        compatible_asset_classes TEXT,
        supplier_id            TEXT,
        lead_time_days_mean    REAL,
        lead_time_days_stdev   REAL,
        unit_cost_usd          REAL,
        in_stock_qty           INTEGER,
        reorder_point          INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS crews (
        crew_id                   TEXT PRIMARY KEY,
        crew_name                 TEXT NOT NULL,
        skill_codes               TEXT,
        size                      INTEGER,
        shift                     TEXT,
        available_hours_per_week  REAL
    )""",
    """CREATE TABLE IF NOT EXISTS permits (
        permit_code              TEXT PRIMARY KEY,
        permit_name              TEXT NOT NULL,
        typical_lead_time_hours  INTEGER,
        prerequisites            TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS planners (
        planner_id   TEXT PRIMARY KEY,
        planner_name TEXT NOT NULL,
        experience_years REAL,
        specialization TEXT,
        avg_notifications_per_day REAL,
        shift TEXT
    )""",
    # ---- dependent entities ----
    """CREATE TABLE IF NOT EXISTS work_orders (
        wo_id              TEXT PRIMARY KEY,
        asset_id           TEXT NOT NULL REFERENCES assets(asset_id),
        notification_id    TEXT REFERENCES notifications(notification_id),
        planner_id         TEXT NOT NULL REFERENCES planners(planner_id),
        created_at         TEXT,
        scheduled_start    TEXT,
        actual_start       TEXT,
        actual_end         TEXT,
        status             TEXT,
        priority           INTEGER,
        estimated_hours    REAL,
        actual_hours       REAL,
        work_type          TEXT,
        required_crew_skills TEXT,
        required_parts_json TEXT,
        required_permits   TEXT,
        description        TEXT,
        closure_notes      TEXT,
        avoided_downtime_hours REAL
    )""",
    """CREATE TABLE IF NOT EXISTS notifications (
        notification_id          TEXT PRIMARY KEY,
        asset_id                 TEXT NOT NULL REFERENCES assets(asset_id),
        raised_at                TEXT NOT NULL,
        source                   TEXT,
        raw_text                 TEXT,
        observed_severity        INTEGER,
        status                   TEXT,
        assigned_planner_id      TEXT REFERENCES planners(planner_id),
        planning_started_at      TEXT,
        planning_completed_at    TEXT,
        planning_duration_minutes REAL,
        converted_to_wo_id       TEXT REFERENCES work_orders(wo_id),
        ground_truth_severity    INTEGER,
        ground_truth_category    TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS failure_events (
        failure_id        TEXT PRIMARY KEY,
        asset_id          TEXT NOT NULL REFERENCES assets(asset_id),
        wo_id             TEXT NOT NULL REFERENCES work_orders(wo_id),
        failed_at         TEXT NOT NULL,
        root_cause        TEXT,
        root_cause_category TEXT,
        downtime_hours    REAL,
        downtime_cost_usd REAL
    )""",
    # ---- Phase 2 datasets ----
    """CREATE TABLE IF NOT EXISTS sensors (
        sensor_id     TEXT PRIMARY KEY,
        asset_id      TEXT NOT NULL REFERENCES assets(asset_id),
        sensor_type   TEXT NOT NULL,
        measurement   TEXT NOT NULL,
        unit          TEXT,
        baseline_value REAL,
        alarm_high     REAL,
        alarm_low      REAL
    )""",
    """CREATE TABLE IF NOT EXISTS sensor_readings (
        reading_id   TEXT PRIMARY KEY,
        sensor_id    TEXT NOT NULL REFERENCES sensors(sensor_id),
        asset_id     TEXT NOT NULL REFERENCES assets(asset_id),
        timestamp    TEXT NOT NULL,
        value        REAL,
        is_anomalous INTEGER DEFAULT 0,
        anomaly_type TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS asset_connections (
        edge_id          TEXT PRIMARY KEY,
        source_asset_id  TEXT NOT NULL REFERENCES assets(asset_id),
        target_asset_id  TEXT NOT NULL REFERENCES assets(asset_id),
        connection_type  TEXT NOT NULL,
        process_stream   TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS weather (
        date            TEXT PRIMARY KEY,
        temp_high_c     REAL,
        temp_low_c      REAL,
        temp_avg_c      REAL,
        wind_speed_kmh  REAL,
        precipitation_mm REAL,
        condition       TEXT,
        has_storm       INTEGER DEFAULT 0,
        has_freeze      INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS production (
        date                 TEXT PRIMARY KEY,
        barrels_produced     REAL,
        gasoline_bbl         REAL,
        diesel_bbl           REAL,
        jet_fuel_bbl         REAL,
        lpg_bbl              REAL,
        fuel_oil_bbl         REAL,
        other_bbl            REAL,
        on_spec_pct          REAL,
        notes                TEXT
    )""",
    # ---- indexes for common agent/dashboard queries ----
    "CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_asset ON notifications(asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_notifications_raised ON notifications(raised_at)",
    "CREATE INDEX IF NOT EXISTS idx_wo_asset ON work_orders(asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_wo_status ON work_orders(status)",
    "CREATE INDEX IF NOT EXISTS idx_failures_asset ON failure_events(asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_readings_sensor_ts ON sensor_readings(sensor_id, timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_readings_asset_ts ON sensor_readings(asset_id, timestamp)",
]

# CSV file name → table name mapping (only files that exist are loaded)
_CSV_MAP: dict[str, str] = {
    "assets.csv": "assets",
    "operations_calendar.csv": "operations_calendar",
    "spare_parts.csv": "spare_parts",
    "crews.csv": "crews",
    "permits.csv": "permits",
    "planners.csv": "planners",
    "notifications.csv": "notifications",
    "work_orders.csv": "work_orders",
    "failure_events.csv": "failure_events",
    "sensors.csv": "sensors",
    "sensor_readings.csv": "sensor_readings",
    "asset_connections.csv": "asset_connections",
    "weather.csv": "weather",
    "production.csv": "production",
}


def build_database(output_dir: str | Path, db_path: str | Path | None = None) -> Path:
    """Build (or rebuild) a SQLite DB from the CSVs in ``output_dir``.

    Drops and recreates all tables so the DB always reflects the latest CSVs.
    Returns the path to the created DB.
    """
    output_dir = Path(output_dir)
    if db_path is None:
        db_path = output_dir / "crestmount.db"
    else:
        db_path = Path(db_path)

    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    # Load with FK enforcement OFF — table insertion order doesn't respect the
    # circular notifications↔work_orders reference, but the data is already
    # FK-validated by generate_data._validate_foreign_keys. We re-enable FKs
    # and run an integrity check after loading.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for ddl in _DDL:
            conn.execute(ddl)
        conn.commit()

        for csv_name, table in _CSV_MAP.items():
            csv_path = output_dir / csv_name
            if not csv_path.exists():
                continue
            df = pd.read_csv(csv_path)
            # Empty nullable FK cells come through as NaN; keep them as NULL.
            df.to_sql(table, conn, if_exists="append", index=False)
        conn.commit()

        # Re-enable FKs and verify referential integrity holds.
        conn.execute("PRAGMA foreign_keys = ON")
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            names = ", ".join(v[0] for v in violations[:5])
            raise RuntimeError(f"FK integrity check failed after load: {names}")
    finally:
        conn.close()

    return db_path


class RefineryDB:
    """Thin convenience wrapper over a sqlite3 connection."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        """Run a SELECT and return rows as a list of dicts."""
        cur = self._conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def query_df(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        """Run a query and return a pandas DataFrame."""
        return pd.read_sql_query(sql, self._conn, params=params)

    def iter_query(self, sql: str, params: tuple = (), chunksize: int = 1000) -> Iterator[list[dict]]:
        """Stream large result sets in chunks."""
        cur = self._conn.execute(sql, params)
        while True:
            rows = [dict(r) for r in cur.fetchmany(chunksize)]
            if not rows:
                break
            yield rows

    def execute(self, sql: str, params: tuple = ()) -> None:
        """Run a DML/DDL statement."""
        self._conn.execute(sql, params)
        self._conn.commit()

    def table_rowcounts(self) -> dict[str, int]:
        """Return row counts for every populated table (useful for dashboards)."""
        out: dict[str, int] = {}
        cur = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = [r[0] for r in cur.fetchall()]
        for t in tables:
            out[t] = self._conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        return out

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "RefineryDB":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
