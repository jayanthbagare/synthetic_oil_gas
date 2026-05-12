"""Generate the work orders table (~8,500 rows)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from .common import (
    PART_CATEGORY_COMPATIBLE_CLASSES,
    required_permits_for,
    required_skills_for,
)

N_INFLIGHT = 500   # WOs with status planned/scheduled/in_progress at run date

WO_STATUSES_HIST = ["completed", "cancelled"]
WO_STATUSES_HIST_WEIGHTS = [0.95, 0.05]

WORK_TYPES = ["corrective", "preventive", "predictive", "regulatory"]
WORK_TYPE_WEIGHTS = [0.55, 0.30, 0.10, 0.05]

INFLIGHT_STATUSES = ["planned", "scheduled", "in_progress"]
INFLIGHT_WEIGHTS = [0.40, 0.35, 0.25]

CLOSURE_NOTE_TEMPLATES = [
    "Work completed as planned. {asset} returned to service.",
    "Found {issue} — replaced {part}. Asset restored to normal operation.",
    "Inspection confirmed root cause was {issue}. Repair completed, tested and handed back.",
    "More damage than expected — extended scope to include {extra}. Completed and closed.",
    "Completed with minor variation to scope. {asset} running within spec at handback.",
]

ISSUE_WORDS = [
    "seal wear", "bearing spalling", "coupling misalignment",
    "fouled heat transfer surface", "valve seat leak", "instrument drift",
    "winding insulation degradation", "corrosion under insulation",
    "plugged strainer", "failing mechanical seal",
]

EXTRA_SCOPE = [
    "lube oil flush", "alignment check", "gasket replacement",
    "cleaning and inspection of internals", "UT thickness survey",
]


def generate_work_orders(
    rng: np.random.Generator,
    notifs_df: pd.DataFrame,
    assets_df: pd.DataFrame,
    planners_df: pd.DataFrame,
    crews_df: pd.DataFrame,
    parts_df: pd.DataFrame,
    permits_df: pd.DataFrame,
    run_date: date,
) -> pd.DataFrame:
    run_ts = datetime.combine(run_date, datetime.min.time())

    # Build lookup structures
    asset_class_map: dict[str, str] = dict(zip(assets_df["asset_id"], assets_df["asset_class"]))
    asset_tier_map: dict[str, int] = dict(zip(assets_df["asset_id"], assets_df["criticality_tier"]))
    planner_ids = planners_df["planner_id"].values
    permit_codes = list(permits_df["permit_code"])

    # Parts lookup: asset_class → list of compatible part_ids
    class_to_parts: dict[str, list[str]] = {}
    for _, row in parts_df.iterrows():
        for cls in str(row["compatible_asset_classes"]).split(";"):
            cls = cls.strip()
            if cls:
                class_to_parts.setdefault(cls, []).append(row["part_id"])

    # ------------------------------------------------------------------ #
    # Historical WOs: one per converted_to_wo notification
    # ------------------------------------------------------------------ #
    converted = notifs_df[notifs_df["status"] == "converted_to_wo"].copy()
    hist_rows = _build_historical_wos(rng, converted, asset_class_map, asset_tier_map,
                                       planner_ids, class_to_parts, permit_codes, run_ts)

    # ------------------------------------------------------------------ #
    # In-flight WOs (~500 open)
    # ------------------------------------------------------------------ #
    # Sample from all assets
    all_asset_ids = assets_df["asset_id"].values
    inflight_rows = _build_inflight_wos(rng, N_INFLIGHT, all_asset_ids, asset_class_map,
                                         asset_tier_map, planner_ids, class_to_parts,
                                         permit_codes, run_ts)

    all_rows = hist_rows + inflight_rows
    df = pd.DataFrame(all_rows)
    df["wo_id"] = [f"WO-{i+1:07d}" for i in range(len(df))]

    _write_schema()

    cols = [
        "wo_id", "asset_id", "notification_id", "planner_id",
        "created_at", "scheduled_start", "actual_start", "actual_end",
        "status", "priority", "estimated_hours", "actual_hours",
        "work_type", "required_crew_skills", "required_parts_json",
        "required_permits", "description", "closure_notes",
        "avoided_downtime_hours",
    ]
    return df[cols]


def _build_historical_wos(
    rng: np.random.Generator,
    converted: pd.DataFrame,
    asset_class_map: dict[str, str],
    asset_tier_map: dict[str, int],
    planner_ids: np.ndarray,
    class_to_parts: dict[str, list[str]],
    permit_codes: list[str],
    run_ts: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    n = len(converted)

    work_types = rng.choice(WORK_TYPES, size=n, p=WORK_TYPE_WEIGHTS)
    statuses = rng.choice(WO_STATUSES_HIST, size=n, p=WO_STATUSES_HIST_WEIGHTS)

    for i, (_, notif) in enumerate(converted.iterrows()):
        asset_id = notif["asset_id"]
        asset_class = asset_class_map.get(asset_id, "centrifugal_pump")
        tier = asset_tier_map.get(asset_id, 3)
        work_type = work_types[i]
        status = statuses[i]

        # Timing: created_at = planning_completed_at (or raised_at + lag)
        pc_at = notif.get("planning_completed_at")
        if pd.isna(pc_at) or pc_at is None:
            created_at = pd.to_datetime(notif["raised_at"]) + timedelta(hours=float(rng.uniform(4, 48)))
        else:
            created_at = pd.to_datetime(pc_at)

        sched_lag_days = float(rng.uniform(1, 14))
        scheduled_start = created_at + timedelta(days=sched_lag_days)

        if status == "completed":
            actual_start = scheduled_start + timedelta(hours=float(rng.uniform(-4, 8)))
            est_hours = round(float(rng.lognormal(2.0, 0.7)), 1)
            actual_hours = round(est_hours * float(rng.uniform(0.7, 1.6)), 1)
            actual_end = actual_start + timedelta(hours=float(actual_hours))
        else:
            actual_start = None
            est_hours = round(float(rng.lognormal(2.0, 0.7)), 1)
            actual_hours = None
            actual_end = None

        priority = max(1, min(5, int(tier) + int(rng.integers(-1, 2))))

        required_skills = required_skills_for(asset_class)
        required_permits_list = required_permits_for(asset_class, work_type)
        required_parts = _sample_parts(rng, asset_class, class_to_parts)

        avoided_hours = None
        if work_type in ("preventive", "predictive"):
            avoided_hours = round(float(rng.lognormal(1.5, 1.0)), 1)

        closure_notes = None
        if status == "completed":
            tmpl = CLOSURE_NOTE_TEMPLATES[rng.integers(0, len(CLOSURE_NOTE_TEMPLATES))]
            closure_notes = tmpl.format(
                asset=asset_id,
                issue=ISSUE_WORDS[rng.integers(0, len(ISSUE_WORDS))],
                part="replacement component",
                extra=EXTRA_SCOPE[rng.integers(0, len(EXTRA_SCOPE))],
            )

        rows.append({
            "asset_id":             asset_id,
            "notification_id":      notif["notification_id"],
            "planner_id":           notif.get("assigned_planner_id") or planner_ids[rng.integers(0, len(planner_ids))],
            "created_at":           created_at,
            "scheduled_start":      scheduled_start,
            "actual_start":         actual_start,
            "actual_end":           actual_end,
            "status":               status,
            "priority":             priority,
            "estimated_hours":      est_hours,
            "actual_hours":         actual_hours,
            "work_type":            work_type,
            "required_crew_skills": ";".join(required_skills),
            "required_parts_json":  json.dumps(required_parts),
            "required_permits":     ";".join(required_permits_list),
            "description":          f"{work_type.capitalize()} work on {asset_id} ({asset_class.replace('_', ' ')})",
            "closure_notes":        closure_notes,
            "avoided_downtime_hours": avoided_hours,
        })
    return rows


def _build_inflight_wos(
    rng: np.random.Generator,
    n: int,
    all_asset_ids: np.ndarray,
    asset_class_map: dict[str, str],
    asset_tier_map: dict[str, int],
    planner_ids: np.ndarray,
    class_to_parts: dict[str, list[str]],
    permit_codes: list[str],
    run_ts: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    asset_ids = rng.choice(all_asset_ids, size=n)
    work_types = rng.choice(WORK_TYPES, size=n, p=WORK_TYPE_WEIGHTS)
    statuses = rng.choice(INFLIGHT_STATUSES, size=n, p=INFLIGHT_WEIGHTS)

    for i in range(n):
        asset_id = asset_ids[i]
        asset_class = asset_class_map.get(asset_id, "centrifugal_pump")
        tier = asset_tier_map.get(asset_id, 3)
        work_type = work_types[i]
        status = statuses[i]

        created_at = run_ts - timedelta(days=float(rng.uniform(1, 30)))
        scheduled_start = run_ts + timedelta(days=float(rng.uniform(-5, 14)))

        if status == "in_progress":
            actual_start = run_ts - timedelta(hours=float(rng.uniform(1, 48)))
        else:
            actual_start = None

        est_hours = round(float(rng.lognormal(2.0, 0.7)), 1)
        priority = max(1, min(5, tier + int(rng.integers(-1, 2))))

        required_skills = required_skills_for(asset_class)
        required_permits_list = required_permits_for(asset_class, work_type)
        required_parts = _sample_parts(rng, asset_class, class_to_parts)

        avoided_hours = None
        if work_type in ("preventive", "predictive"):
            avoided_hours = round(float(rng.lognormal(1.5, 1.0)), 1)

        rows.append({
            "asset_id":             asset_id,
            "notification_id":      None,
            "planner_id":           planner_ids[rng.integers(0, len(planner_ids))],
            "created_at":           created_at,
            "scheduled_start":      scheduled_start,
            "actual_start":         actual_start,
            "actual_end":           None,
            "status":               status,
            "priority":             priority,
            "estimated_hours":      est_hours,
            "actual_hours":         None,
            "work_type":            work_type,
            "required_crew_skills": ";".join(required_skills),
            "required_parts_json":  json.dumps(required_parts),
            "required_permits":     ";".join(required_permits_list),
            "description":          f"{work_type.capitalize()} work on {asset_id} ({asset_class.replace('_', ' ')})",
            "closure_notes":        None,
            "avoided_downtime_hours": avoided_hours,
        })
    return rows


def _sample_parts(
    rng: np.random.Generator,
    asset_class: str,
    class_to_parts: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Return 1–4 part records as dicts for JSON serialisation."""
    compatible = class_to_parts.get(asset_class, [])
    if not compatible:
        return []
    n_parts = int(rng.integers(1, 5))
    chosen = rng.choice(compatible, size=min(n_parts, len(compatible)), replace=False)
    return [{"part_id": pid, "qty": int(rng.integers(1, 5))} for pid in chosen]


def _write_schema() -> None:
    from pathlib import Path
    schema = """# work_orders_schema.md

| Column | Type | Description |
|---|---|---|
| wo_id | string | Primary key. Format: WO-NNNNNNN |
| asset_id | string | FK → assets.asset_id |
| notification_id | string | FK → notifications.notification_id (nullable for PM/regulatory WOs) |
| planner_id | string | FK → planners.planner_id |
| created_at | timestamp | When the WO was created |
| scheduled_start | timestamp | Planned start date |
| actual_start | timestamp | Actual start (nullable if not yet started) |
| actual_end | timestamp | Actual completion (nullable) |
| status | string | planned \\| scheduled \\| in_progress \\| completed \\| cancelled |
| priority | int | 1 (highest) to 5 (lowest) |
| estimated_hours | float | Planner's estimated work hours |
| actual_hours | float | Actual hours taken (nullable) |
| work_type | string | corrective \\| preventive \\| predictive \\| regulatory |
| required_crew_skills | string | Semicolon-separated skill codes |
| required_parts_json | string | JSON list of {part_id, qty} objects |
| required_permits | string | Semicolon-separated permit_codes |
| description | string | One-line WO description |
| closure_notes | string | Free-text from crew at job completion (nullable) |
| avoided_downtime_hours | float | Estimated avoided downtime for PM/predictive WOs (nullable) |
"""
    out = Path(__file__).parent.parent / "output" / "work_orders_schema.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(schema)
