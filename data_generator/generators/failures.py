"""Generate failure_events as a derived view of completed corrective work orders."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common import DOWNTIME_COST_RATE

ROOT_CAUSE_PHRASES: dict[str, str] = {
    "seal_failure":          "mechanical seal face wear and leakage",
    "bearing_wear":          "rolling element bearing fatigue failure",
    "vibration_abnormal":    "excessive rotor vibration from imbalance",
    "temperature_high":      "elevated process temperature from reduced cooling",
    "pressure_abnormal":     "system pressure excursion beyond design limits",
    "flow_abnormal":         "process flow restriction from partial blockage",
    "control_drift":         "valve positioner calibration drift",
    "instrument_failure":    "transmitter electronic failure",
    "lubrication_low":       "lubricant film breakdown from low oil level",
    "coupling_misalignment": "angular and parallel shaft misalignment",
    "process_fouling":       "deposit buildup reducing heat transfer area",
    "corrosion":             "external corrosion under insulation (CUI)",
    "electrical_fault":      "motor winding insulation breakdown",
    "leak":                  "flange joint leak from gasket failure",
}


def generate_failures(
    rng: np.random.Generator,
    wo_df: pd.DataFrame,
    notifs_df: pd.DataFrame,
    assets_df: pd.DataFrame,
) -> pd.DataFrame:
    # Join ground_truth_category from notifications into work orders
    notif_gt = notifs_df[["notification_id", "ground_truth_category"]].dropna(subset=["notification_id"])
    wo_with_gt = wo_df.merge(notif_gt, on="notification_id", how="left")

    # Filter: completed corrective WOs where ground_truth is a real failure
    mask = (
        (wo_with_gt["status"] == "completed") &
        (wo_with_gt["work_type"] == "corrective") &
        (wo_with_gt["ground_truth_category"].notna()) &
        (~wo_with_gt["ground_truth_category"].isin(["false_positive", "duplicate"]))
    )
    source = wo_with_gt[mask].copy().reset_index(drop=True)

    # Sample ~1,200 failures (target volume from PLAN.md)
    TARGET = 1_200
    if len(source) > TARGET:
        source = source.sample(n=TARGET, random_state=int(rng.integers(0, 2**31))).reset_index(drop=True)

    n = len(source)

    # Asset criticality for cost calculation
    tier_map: dict[str, int] = dict(zip(assets_df["asset_id"], assets_df["criticality_tier"]))

    # Downtime hours: log-normal, mean ~4h, p95 ~18h; T1 assets skew longer
    base_hours = np.exp(rng.normal(1.0, 0.8, size=n))  # log-normal: mean≈4h

    # T1/T2 assets get a longer tail
    tiers = np.array([tier_map.get(aid, 3) for aid in source["asset_id"]])
    # Smaller tier multiplier — T1 failures are caught quickly due to criticality
    tier_multiplier = np.where(tiers == 1, 1.3, np.where(tiers == 2, 1.15, 1.0))
    downtime_hours = (base_hours * tier_multiplier).round(1)
    downtime_hours = np.clip(downtime_hours, 0.5, 120.0)

    # Downtime cost: hours × rate sampled from tier range
    downtime_costs: list[float] = []
    for i, (hours, tier) in enumerate(zip(downtime_hours, tiers)):
        lo, hi = DOWNTIME_COST_RATE[int(tier)]
        rate = rng.uniform(lo, hi)
        downtime_costs.append(round(float(hours * rate), 0))

    # failed_at: the actual_start of the WO (when problem was first addressed)
    failed_at = pd.to_datetime(source["actual_start"])

    # Root cause text and category
    gt_cats = source["ground_truth_category"].values
    root_cause_texts = [ROOT_CAUSE_PHRASES.get(c, c.replace("_", " ")) for c in gt_cats]

    failure_ids = [f"FLR-{i+1:06d}" for i in range(n)]

    df = pd.DataFrame({
        "failure_id":          failure_ids,
        "asset_id":            source["asset_id"].values,
        "wo_id":               source["wo_id"].values,
        "failed_at":           failed_at.values,
        "root_cause":          root_cause_texts,
        "root_cause_category": gt_cats,
        "downtime_hours":      downtime_hours,
        "downtime_cost_usd":   downtime_costs,
    })

    _write_schema()
    return df


def _write_schema() -> None:
    from pathlib import Path
    schema = """# failure_events_schema.md

A derived view of completed corrective work orders where ground_truth_category is a
real failure (not false_positive or duplicate).

| Column | Type | Description |
|---|---|---|
| failure_id | string | Primary key. Format: FLR-NNNNNN |
| asset_id | string | FK → assets.asset_id |
| wo_id | string | FK → work_orders.wo_id |
| failed_at | timestamp | Approximate time of failure (actual_start of the work order) |
| root_cause | string | Free-text root cause description (5–10 words) |
| root_cause_category | string | Canonical failure category (same vocabulary as ground_truth_category) |
| downtime_hours | float | Actual downtime hours |
| downtime_cost_usd | float | Estimated cost of downtime in USD (scaled by criticality tier) |

## Cost rates by criticality tier

| Tier | Range (USD/hour) |
|---|---|
| T1 | $200,000–$500,000 |
| T2 | $50,000–$200,000 |
| T3 | $10,000–$50,000 |
| T4 | $1,000–$10,000 |
| T5 | $0–$1,000 |
"""
    out = Path(__file__).parent.parent / "output" / "failure_events_schema.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(schema)
