"""Tests for the Phase 2 domain datasets: weather, production, asset_connections,
sensors + sensor_readings.

These run against generated CSVs in output/ — generate first with:
    python generate_data.py --seed 42 --build-db
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _load(name: str) -> pd.DataFrame:
    p = OUTPUT_DIR / f"{name}.csv"
    if not p.exists():
        pytest.skip(f"{name}.csv not found — run generate_data.py first")
    return pd.read_csv(p)


# ---------------------------------------------------------------------------
# Weather dataset
# ---------------------------------------------------------------------------

def test_weather_row_count() -> None:
    w = _load("weather")
    assert len(w) == 730, f"Expected 730 weather rows, got {len(w)}"


def test_weather_temp_ranges_plausible() -> None:
    """West Texas: highs should be within a believable annual range."""
    w = _load("weather")
    assert w["temp_high_c"].min() >= -10, "Implausibly cold high temp"
    assert w["temp_high_c"].max() <= 55, "Implausibly hot high temp"
    assert w["temp_low_c"].min() >= w["temp_high_c"].min() - 20
    assert (w["temp_high_c"] >= w["temp_low_c"]).all(), "high < low somewhere"


def test_weather_has_storms_and_freezes() -> None:
    """The generator injects summer storms and winter freezes."""
    w = _load("weather")
    assert w["has_storm"].sum() >= 1, "Expected at least one storm day"
    assert w["has_freeze"].sum() >= 1, "Expected at least one freeze day"
    # Storms should only be flagged on summer months
    w["date"] = pd.to_datetime(w["date"])
    storm_months = w.loc[w["has_storm"] == 1, "date"].dt.month
    assert storm_months.between(6, 8).all(), "Storms outside Jun–Aug"


def test_weather_condition_values() -> None:
    w = _load("weather")
    allowed = {"clear", "partly_cloudy", "cloudy", "rain", "storm", "dust", "fog"}
    actual = set(w["condition"].dropna().unique())
    assert actual.issubset(allowed), f"Unknown conditions: {actual - allowed}"


# ---------------------------------------------------------------------------
# Production dataset
# ---------------------------------------------------------------------------

def test_production_row_count() -> None:
    p = _load("production")
    assert len(p) == 730, f"Expected 730 production rows, got {len(p)}"


def test_production_yields_sum_to_total() -> None:
    """Sum of product yields should equal barrels_produced (within rounding)."""
    p = _load("production")
    yield_cols = ["gasoline_bbl", "diesel_bbl", "jet_fuel_bbl",
                  "lpg_bbl", "fuel_oil_bbl", "other_bbl"]
    total_yields = p[yield_cols].sum(axis=1)
    diff = (total_yields - p["barrels_produced"]).abs()
    assert (diff <= 2).all(), f"Yields don't sum to total; max diff {diff.max()}"


def test_production_respects_calendar_states() -> None:
    """Production must be zero on turnaround/shutdown days."""
    cal = _load("operations_calendar")
    prod = _load("production")
    merged = cal.merge(prod, on="date", how="inner")
    off_states = merged[merged["plant_state"].isin(["turnaround", "shutdown"])]
    assert (off_states["barrels_produced"] == 0).all(), "Non-zero production during turnaround/shutdown"


def test_production_on_spec_dips_during_derate() -> None:
    cal = _load("operations_calendar")
    prod = _load("production")
    merged = cal.merge(prod, on="date", how="inner")
    running_spec = merged.loc[merged["plant_state"] == "running", "on_spec_pct"].mean()
    derate_spec = merged.loc[merged["plant_state"] == "derate", "on_spec_pct"].mean()
    assert derate_spec < running_spec, "On-spec should dip during derate periods"


def test_production_capacity_not_exceeded() -> None:
    p = _load("production")
    assert p["barrels_produced"].max() <= 100_000 + 1, "Production exceeds design capacity"


# ---------------------------------------------------------------------------
# Asset connectivity (P&ID graph)
# ---------------------------------------------------------------------------

def test_asset_connections_fk_integrity() -> None:
    c = _load("asset_connections")
    assets = _load("assets")
    asset_ids = set(assets["asset_id"])
    bad_src = set(c["source_asset_id"]) - asset_ids
    bad_tgt = set(c["target_asset_id"]) - asset_ids
    assert not bad_src, f"Unknown source_asset_id: {list(bad_src)[:5]}"
    assert not bad_tgt, f"Unknown target_asset_id: {list(bad_tgt)[:5]}"


def test_asset_connections_no_self_loops() -> None:
    c = _load("asset_connections")
    self_loops = c[c["source_asset_id"] == c["target_asset_id"]]
    assert len(self_loops) == 0, f"{len(self_loops)} self-loop edges found"


def test_asset_connections_connection_types() -> None:
    c = _load("asset_connections")
    allowed = {"feed", "return", "utility", "parallel", "standby"}
    actual = set(c["connection_type"].dropna().unique())
    assert actual.issubset(allowed), f"Unknown connection types: {actual - allowed}"


def test_asset_connections_has_edges() -> None:
    c = _load("asset_connections")
    assert len(c) >= 500, f"Expected ≥500 connections, got {len(c)}"


# ---------------------------------------------------------------------------
# Sensors + sensor readings
# ---------------------------------------------------------------------------

def test_sensors_fk_integrity() -> None:
    s = _load("sensors")
    assets = _load("assets")
    asset_ids = set(assets["asset_id"])
    bad = set(s["asset_id"]) - asset_ids
    assert not bad, f"Unknown asset_id in sensors: {list(bad)[:5]}"


def test_sensors_only_on_instrumented_classes() -> None:
    s = _load("sensors")
    assets = _load("assets").set_index("asset_id")
    instrumented = {"centrifugal_pump", "reciprocating_pump", "compressor",
                    "electrical_motor", "heat_exchanger", "fired_heater"}
    classes = assets.loc[s["asset_id"], "asset_class"]
    assert set(classes.unique()).issubset(instrumented), \
        f"Sensors on non-instrumented classes: {set(classes) - instrumented}"


def test_sensors_sensor_types() -> None:
    s = _load("sensors")
    allowed = {"vibration", "temperature", "pressure", "flow"}
    actual = set(s["sensor_type"].unique())
    assert actual.issubset(allowed), f"Unknown sensor types: {actual - allowed}"


def test_sensor_readings_fk_integrity() -> None:
    r = _load("sensor_readings")
    s = _load("sensors")
    sensor_ids = set(s["sensor_id"])
    bad = set(r["sensor_id"]) - sensor_ids
    assert not bad, f"Unknown sensor_id in readings: {list(bad)[:5]}"


def test_sensor_readings_has_anomalies() -> None:
    r = _load("sensor_readings")
    n_anom = int(r["is_anomalous"].sum())
    assert n_anom > 0, "No anomalous readings generated"


def test_sensor_readings_anomaly_types() -> None:
    r = _load("sensor_readings")
    anom = r[r["is_anomalous"] == 1]
    allowed = {"pre_failure", "spurious", ""}
    actual = set(anom["anomaly_type"].fillna(""))
    assert actual.issubset(allowed), f"Unknown anomaly types: {actual - allowed}"


def test_sensor_readings_has_pre_failure_anomalies() -> None:
    """The generator seeds pre-failure anomalies before each failure event."""
    r = _load("sensor_readings")
    n_pre = int((r["anomaly_type"] == "pre_failure").sum())
    assert n_pre > 0, "No pre_failure anomalies — predictive signal missing"
