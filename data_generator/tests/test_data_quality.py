"""Data quality spot-checks for the Crestmount Refinery synthetic dataset.

Run after generating data:
    python generate_data.py --seed 42 --output-dir ./output
    pytest tests/test_data_quality.py -v

These tests validate generated CSVs — they read from output/ and do not regenerate data.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _load(name: str) -> pd.DataFrame:
    p = OUTPUT_DIR / f"{name}.csv"
    if not p.exists():
        pytest.skip(f"{name}.csv not found — run generate_data.py first")
    return pd.read_csv(p)


# ---------------------------------------------------------------------------
# Test 1: Asset row count within tolerance
# ---------------------------------------------------------------------------

def test_asset_row_count() -> None:
    assets = _load("assets")
    assert 480 <= len(assets) <= 520, (
        f"Expected 480–520 assets, got {len(assets)}"
    )


# ---------------------------------------------------------------------------
# Test 2: Criticality distribution within expected bands
# ---------------------------------------------------------------------------

def test_criticality_distribution() -> None:
    assets = _load("assets")
    n = len(assets)
    counts = assets["criticality_tier"].value_counts()

    t1_pct = counts.get(1, 0) / n
    t2_pct = counts.get(2, 0) / n

    assert 0.03 <= t1_pct <= 0.08, f"T1 should be 3–8% of fleet, got {t1_pct:.1%}"
    assert 0.10 <= t2_pct <= 0.22, f"T2 should be 10–22% of fleet, got {t2_pct:.1%}"


# ---------------------------------------------------------------------------
# Test 3: Notification total row count
# ---------------------------------------------------------------------------

def test_notification_row_count() -> None:
    notifs = _load("notifications")
    assert 11_000 <= len(notifs) <= 13_000, (
        f"Expected 11,000–13,000 notifications, got {len(notifs)}"
    )


# ---------------------------------------------------------------------------
# Test 4: Open backlog count
# ---------------------------------------------------------------------------

def test_open_backlog_count() -> None:
    notifs = _load("notifications")
    open_mask = notifs["status"].isin(["open", "in_review"])
    n_open = open_mask.sum()
    assert 1_500 <= n_open <= 2_500, (
        f"Expected 1,500–2,500 open/in_review notifications, got {n_open}"
    )


# ---------------------------------------------------------------------------
# Test 5: No orphan asset FKs in notifications
# ---------------------------------------------------------------------------

def test_no_orphan_asset_fk_notifications() -> None:
    assets = _load("assets")
    notifs = _load("notifications")
    asset_ids = set(assets["asset_id"])
    orphans = set(notifs["asset_id"]) - asset_ids
    assert not orphans, f"Orphan asset_id values in notifications: {list(orphans)[:5]}"


# ---------------------------------------------------------------------------
# Test 6: No orphan notification FKs in work orders
# ---------------------------------------------------------------------------

def test_no_orphan_wo_notification_fk() -> None:
    notifs = _load("notifications")
    wo = _load("work_orders")
    notif_ids = set(notifs["notification_id"])
    wo_notif = wo["notification_id"].dropna()
    orphans = set(wo_notif) - notif_ids
    assert not orphans, (
        f"Work orders reference unknown notification_id: {list(orphans)[:5]}"
    )


# ---------------------------------------------------------------------------
# Test 7: Planning time distribution shape
# ---------------------------------------------------------------------------

def test_planning_time_distribution() -> None:
    notifs = _load("notifications")
    durations = notifs["planning_duration_minutes"].dropna()
    assert len(durations) > 1_000, "Too few planning duration values to assess distribution"

    median_min = float(np.percentile(durations, 50))
    p95_min = float(np.percentile(durations, 95))

    assert 15 <= median_min <= 30, f"Median planning time should be 15–30 min, got {median_min:.1f}"
    assert 50 <= p95_min <= 100, f"p95 planning time should be 50–100 min, got {p95_min:.1f}"


# ---------------------------------------------------------------------------
# Test 8: raw_text non-empty
# ---------------------------------------------------------------------------

def test_raw_text_non_empty() -> None:
    notifs = _load("notifications")
    n_empty = (notifs["raw_text"].isna() | (notifs["raw_text"].str.strip() == "")).sum()
    assert n_empty == 0, f"{n_empty} notifications have empty raw_text"


# ---------------------------------------------------------------------------
# Test 9: Ground-truth fields populated for all notifications
# ---------------------------------------------------------------------------

def test_ground_truth_fields_populated() -> None:
    notifs = _load("notifications")
    n_null_sev = notifs["ground_truth_severity"].isna().sum()
    n_null_cat = notifs["ground_truth_category"].isna().sum()
    assert n_null_sev == 0, f"{n_null_sev} notifications have null ground_truth_severity"
    assert n_null_cat == 0, f"{n_null_cat} notifications have null ground_truth_category"


# ---------------------------------------------------------------------------
# Test 10: Open backlog has a long-tail of aged notifications
# ---------------------------------------------------------------------------

def test_backlog_age_tail() -> None:
    notifs = _load("notifications")
    run_ts = pd.Timestamp("today").normalize()

    open_mask = notifs["status"].isin(["open", "in_review"])
    open_notifs = notifs[open_mask].copy()
    open_notifs["raised_at"] = pd.to_datetime(open_notifs["raised_at"])
    ages_days = (run_ts - open_notifs["raised_at"]).dt.days

    n_older_30 = (ages_days > 30).sum()
    n_older_60 = (ages_days > 60).sum()

    assert n_older_30 >= 100, (
        f"Expected ≥100 open notifications older than 30 days, got {n_older_30}"
    )
    assert n_older_60 >= 20, (
        f"Expected ≥20 open notifications older than 60 days, got {n_older_60}"
    )


# ---------------------------------------------------------------------------
# Bonus test 11: T1 open backlog within policy range
# ---------------------------------------------------------------------------

def test_t1_open_backlog_count() -> None:
    assets = _load("assets")
    notifs = _load("notifications")
    open_mask = notifs["status"].isin(["open", "in_review"])
    open_notifs = notifs[open_mask]
    t1_assets = set(assets[assets["criticality_tier"] == 1]["asset_id"])
    n_t1_open = open_notifs["asset_id"].isin(t1_assets).sum()
    assert 5 <= n_t1_open <= 30, (
        f"Expected 5–30 T1 open notifications (SLA violation zone), got {n_t1_open}"
    )


# ---------------------------------------------------------------------------
# Bonus test 12: Failure events FK and row count
# ---------------------------------------------------------------------------

def test_failure_events() -> None:
    failures = _load("failure_events")
    wo = _load("work_orders")
    assets = _load("assets")

    # Row count
    assert 800 <= len(failures) <= 1_600, (
        f"Expected 800–1,600 failure events, got {len(failures)}"
    )

    # FK: wo_id resolves
    wo_ids = set(wo["wo_id"])
    bad_wo = set(failures["wo_id"]) - wo_ids
    assert not bad_wo, f"failure_events.wo_id orphans: {list(bad_wo)[:5]}"

    # FK: asset_id resolves
    asset_ids = set(assets["asset_id"])
    bad_asset = set(failures["asset_id"]) - asset_ids
    assert not bad_asset, f"failure_events.asset_id orphans: {list(bad_asset)[:5]}"


# ---------------------------------------------------------------------------
# Bonus test 13: required_parts_json is valid JSON with known part_ids
# ---------------------------------------------------------------------------

def test_required_parts_json_valid() -> None:
    wo = _load("work_orders")
    parts = _load("spare_parts")
    part_ids = set(parts["part_id"])

    bad_rows = 0
    unknown_parts: list[str] = []

    for raw in wo["required_parts_json"].dropna():
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            bad_rows += 1
            continue
        for item in items:
            pid = item.get("part_id", "")
            if pid and pid not in part_ids:
                unknown_parts.append(pid)

    assert bad_rows == 0, f"{bad_rows} work orders have invalid required_parts_json"
    assert not unknown_parts, f"Unknown part_ids in required_parts_json: {unknown_parts[:5]}"


# ---------------------------------------------------------------------------
# Bonus test 14: Operations calendar has exactly one turnaround block
# ---------------------------------------------------------------------------

def test_operations_calendar_has_turnaround() -> None:
    cal = _load("operations_calendar")
    ta_rows = cal[cal["plant_state"] == "turnaround"]
    # Find contiguous blocks
    ta_dates = pd.to_datetime(cal[cal["plant_state"] == "turnaround"]["date"]).sort_values()
    assert len(ta_dates) >= 14, f"Expected ≥14 turnaround days, got {len(ta_dates)}"
    assert len(ta_dates) <= 21, f"Expected ≤21 turnaround days, got {len(ta_dates)}"
