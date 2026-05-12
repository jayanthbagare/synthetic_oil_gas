"""Generate the notifications table (~12,000 rows).

Ground-truth is generated first; observed fields are derived with controlled noise.
Historical notifications (>90 days old) always have closed statuses.
Open backlog notifications (<90 days) have open/in_review status.
T1/T2 open-backlog items are capped at realistic levels (10–20 T1, 30–60 T2).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from .common import (
    ASSET_FAILURE_MODES,
    RAW_TEXT_TEMPLATES,
    SHIFT_NAMES,
    TEMPLATE_VALUES,
)

# Volume targets
N_HISTORICAL = 10_000   # closed / resolved historical notifications (>90 days old)
N_OPEN = 2_000          # open backlog as of run_date (<90 days old)

# Noise rates
SEVERITY_MISMATCH_RATE = 0.15
FALSE_POSITIVE_RATE = 0.10
DUPLICATE_RATE = 0.05

SOURCES = ["operator", "sensor", "inspection_round", "predictive_model"]
SOURCE_WEIGHTS = [0.40, 0.30, 0.20, 0.10]

# Weekday multiplier (Mon=0 … Sun=6)
WEEKDAY_WEIGHT = [1.0, 1.0, 1.0, 1.0, 0.9, 0.6, 0.5]
# Hour-of-day multiplier (0–23)
HOUR_WEIGHT = [
    0.3, 0.2, 0.2, 0.2, 0.3, 0.5,
    0.8, 1.0, 1.0, 1.0, 1.0, 1.0,
    1.0, 1.0, 0.9, 0.9, 0.9, 0.9,
    0.7, 0.6, 0.5, 0.4, 0.4, 0.3,
]

# Max T1/T2 open-backlog items (policy: these should be processed quickly)
MAX_T1_OPEN = 15
MAX_T2_OPEN = 50


def generate_notifications(
    rng: np.random.Generator,
    assets_df: pd.DataFrame,
    planners_df: pd.DataFrame,
    cal_df: pd.DataFrame,
    run_date: date,
) -> pd.DataFrame:
    run_ts = datetime.combine(run_date, datetime.min.time())
    start_ts = run_ts - timedelta(days=730)
    open_cutoff = run_ts - timedelta(days=90)   # open backlog = raised within last 90 days

    asset_ids = assets_df["asset_id"].values
    asset_classes = assets_df["asset_class"].values
    criticality_tiers = assets_df["criticality_tier"].values
    mtbf_days = assets_df["mtbf_days"].values.astype(float)
    planner_ids = planners_df["planner_id"].values

    # Build reverse lookup: asset_id → criticality tier
    asset_tier_map: dict[str, int] = dict(zip(asset_ids, criticality_tiers))

    # Asset sampling weight: inverse MTBF (higher failure rate → more notifications)
    asset_weights = 1.0 / mtbf_days
    asset_weights /= asset_weights.sum()

    # ------------------------------------------------------------------ #
    # Generate HISTORICAL rows (timestamps before open_cutoff)
    # ------------------------------------------------------------------ #
    hist_chosen = rng.choice(len(asset_ids), size=N_HISTORICAL, p=asset_weights)
    hist_rows = _build_rows(rng, hist_chosen, asset_ids, asset_classes)
    hist_ts = _sample_timestamps(rng, N_HISTORICAL, start_ts, open_cutoff)
    for i, row in enumerate(hist_rows):
        row["raised_at"] = hist_ts[i]

    # Assign closed statuses to historical rows (nothing remains "open")
    _assign_hist_status(rng, hist_rows, planner_ids)

    # ------------------------------------------------------------------ #
    # Generate OPEN backlog rows (timestamps within last 90 days)
    # ------------------------------------------------------------------ #
    open_chosen = rng.choice(len(asset_ids), size=N_OPEN, p=asset_weights)
    open_rows = _build_rows(rng, open_chosen, asset_ids, asset_classes)
    open_ts = _sample_open_timestamps(rng, N_OPEN, run_ts)
    for i, row in enumerate(open_rows):
        row["raised_at"] = open_ts[i]

    # Assign open/in_review statuses
    _assign_open_status(rng, open_rows, planner_ids)

    # Cap T1/T2 in the open backlog — excess get fast-tracked (in_review with planner)
    _cap_critical_open(open_rows, asset_tier_map, rng, planner_ids)

    # ------------------------------------------------------------------ #
    # Combine, sort, assign IDs, and compute planning times
    # ------------------------------------------------------------------ #
    all_rows = hist_rows + open_rows
    df = pd.DataFrame(all_rows)
    df = df.sort_values("raised_at").reset_index(drop=True)

    df["notification_id"] = [f"NTF-{i+1:07d}" for i in range(len(df))]

    # Planning timestamps for historical closed rows
    df = _assign_planning_times(rng, df)

    # Near-duplicate raw_text for ~5% of open rows
    df = _mark_duplicates(rng, df)

    df["converted_to_wo_id"] = None  # backfilled by generate_data.py

    _write_schema()

    cols = [
        "notification_id", "asset_id", "raised_at", "source", "raw_text",
        "observed_severity", "status", "assigned_planner_id",
        "planning_started_at", "planning_completed_at", "planning_duration_minutes",
        "converted_to_wo_id", "ground_truth_severity", "ground_truth_category",
    ]
    return df[cols]


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------

def _build_rows(
    rng: np.random.Generator,
    chosen_indices: np.ndarray,
    asset_ids: np.ndarray,
    asset_classes: np.ndarray,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx in chosen_indices:
        asset_id = asset_ids[idx]
        asset_class = asset_classes[idx]

        # Ground-truth category from asset class failure mode distribution
        mode_map = ASSET_FAILURE_MODES.get(asset_class, {"leak": 1.0})
        mode_cats = list(mode_map.keys())
        mode_wts = np.array(list(mode_map.values()), dtype=float)
        mode_wts /= mode_wts.sum()
        gt_cat = rng.choice(mode_cats, p=mode_wts)

        # False positives (~10% of all notifications)
        if rng.random() < FALSE_POSITIVE_RATE:
            gt_cat = "false_positive"

        # Ground-truth severity
        # We need tier for this — but tier isn't passed here; use a fixed mid-range
        # Tier-based adjustment is applied via observed mismatch; GT severity is 1-5 uniform
        gt_sev = int(rng.integers(1, 6))

        source = rng.choice(SOURCES, p=SOURCE_WEIGHTS)
        obs_sev = _add_severity_noise(rng, gt_sev)
        raw_text = _render_template(rng, gt_cat, asset_id, asset_class)

        rows.append({
            "asset_id":              asset_id,
            "source":                source,
            "raw_text":              raw_text,
            "observed_severity":     obs_sev,
            "ground_truth_severity": gt_sev,
            "ground_truth_category": gt_cat,
            "raised_at":             None,
            "status":                "open",
            "assigned_planner_id":   None,
            "planning_started_at":   None,
            "planning_completed_at": None,
            "planning_duration_minutes": None,
        })
    return rows


def _add_severity_noise(rng: np.random.Generator, gt_sev: int) -> int:
    if rng.random() < SEVERITY_MISMATCH_RATE:
        delta = int(rng.choice([-2, -1, 1, 2]))
        return int(np.clip(gt_sev + delta, 1, 5))
    return gt_sev


def _render_template(
    rng: np.random.Generator,
    gt_cat: str,
    asset_id: str,
    asset_class: str,
) -> str:
    templates = RAW_TEXT_TEMPLATES.get(gt_cat, ["{asset_name} issue noted."])
    tmpl = templates[rng.integers(0, len(templates))]
    shift = SHIFT_NAMES[rng.integers(0, len(SHIFT_NAMES))]

    def rv(lo: float, hi: float) -> str:
        return f"{rng.uniform(lo, hi):.1f}"

    text = tmpl.format(
        asset_name=asset_id,
        unit=asset_class.replace("_", " "),
        shift=shift,
        value=rv(*TEMPLATE_VALUES["vibe_mm_s"]),
        baseline=rv(*TEMPLATE_VALUES["vibe_baseline"]),
    )
    return text


def _sample_timestamps(
    rng: np.random.Generator,
    n: int,
    start_ts: datetime,
    end_ts: datetime,
) -> list[datetime]:
    """Sample n timestamps with weekday/hour seasonality, strictly within [start, end)."""
    total_seconds = int((end_ts - start_ts).total_seconds())
    oversample = int(n * 2.5)
    raw_offsets = rng.integers(0, total_seconds, size=oversample)

    hour_arr = np.array(HOUR_WEIGHT)
    hour_arr /= hour_arr.sum()
    wd_arr = np.array(WEEKDAY_WEIGHT)
    wd_arr /= wd_arr.sum()

    result: list[datetime] = []
    for off in raw_offsets:
        ts = start_ts + timedelta(seconds=int(off))
        w = WEEKDAY_WEIGHT[ts.weekday()] * HOUR_WEIGHT[ts.hour]
        if rng.random() < w:
            result.append(ts)
        if len(result) >= n:
            break

    # Top up if needed (rejection sampling might miss)
    while len(result) < n:
        off = rng.integers(0, total_seconds)
        result.append(start_ts + timedelta(seconds=int(off)))

    return result[:n]


def _sample_open_timestamps(rng: np.random.Generator, n: int, run_ts: datetime) -> list[datetime]:
    """Open backlog: 60% 0–30 days old, 20% 30–60 days, 15% 60–90 days, 5% >90 days.

    The >90-day bucket represents notifications that were raised just before the
    'open era' started but never got picked up. In practice these will look like
    the oldest items in the backlog tail.
    """
    buckets = [
        (0.60, 0,  30),
        (0.20, 30, 60),
        (0.15, 60, 80),
        (0.05, 80, 90),   # oldest should be 60–90 days per workshop targets
    ]
    result: list[datetime] = []
    for frac, lo_d, hi_d in buckets:
        count = int(round(frac * n))
        lo_s = lo_d * 86400
        hi_s = hi_d * 86400
        for _ in range(count):
            off = rng.integers(lo_s, hi_s)
            ts = run_ts - timedelta(seconds=int(off))
            hour = int(rng.integers(0, 24))
            ts = ts.replace(hour=hour, minute=int(rng.integers(0, 60)),
                            second=0, microsecond=0)
            result.append(ts)

    while len(result) < n:
        off = rng.integers(0, 30 * 86400)
        result.append(run_ts - timedelta(seconds=int(off)))

    rng.shuffle(result)
    return result[:n]


def _assign_hist_status(
    rng: np.random.Generator,
    rows: list[dict[str, Any]],
    planner_ids: np.ndarray,
) -> None:
    """Historical rows only get fully-resolved statuses (no open or in_review).

    Notifications older than 90 days have had ample time to be processed.
    """
    choices = rng.choice(
        ["converted_to_wo", "rejected_duplicate", "rejected_false_positive"],
        size=len(rows),
        p=[0.80, 0.06, 0.14],
    )
    for row, status in zip(rows, choices):
        row["status"] = status
        row["assigned_planner_id"] = str(planner_ids[rng.integers(0, len(planner_ids))])


def _assign_open_status(
    rng: np.random.Generator,
    rows: list[dict[str, Any]],
    planner_ids: np.ndarray,
) -> None:
    """Open rows: 70% open (unassigned), 30% in_review (assigned)."""
    for row in rows:
        if rng.random() < 0.30:
            row["status"] = "in_review"
            row["assigned_planner_id"] = str(planner_ids[rng.integers(0, len(planner_ids))])
        else:
            row["status"] = "open"
            row["assigned_planner_id"] = None


def _cap_critical_open(
    rows: list[dict[str, Any]],
    asset_tier_map: dict[str, int],
    rng: np.random.Generator,
    planner_ids: np.ndarray,
) -> None:
    """Ensure T1/T2 open+in_review notifications are capped at realistic levels.

    Policy: T1 criticals must be processed within 24h. So T1 notifications in the
    backlog represent a policy violation — should be rare (10–15 items total).
    Excess T1/T2 notifications are converted directly to WO (fast-tracked by supervisor).
    """
    # Cap ALL unresolved T1 (both open and in_review)
    t1_unresolved = [
        i for i, r in enumerate(rows)
        if asset_tier_map.get(r["asset_id"], 3) == 1
    ]
    t2_unresolved = [
        i for i, r in enumerate(rows)
        if asset_tier_map.get(r["asset_id"], 3) == 2
    ]

    if len(t1_unresolved) > MAX_T1_OPEN:
        # Keep MAX_T1_OPEN; convert the rest to "converted_to_wo" (fast-tracked)
        keep = set(rng.choice(t1_unresolved, size=MAX_T1_OPEN, replace=False).tolist())
        for i in t1_unresolved:
            if i not in keep:
                rows[i]["status"] = "converted_to_wo"
                rows[i]["assigned_planner_id"] = str(planner_ids[rng.integers(0, len(planner_ids))])

    if len(t2_unresolved) > MAX_T2_OPEN:
        keep = set(rng.choice(t2_unresolved, size=MAX_T2_OPEN, replace=False).tolist())
        for i in t2_unresolved:
            if i not in keep:
                rows[i]["status"] = "in_review"
                rows[i]["assigned_planner_id"] = str(planner_ids[rng.integers(0, len(planner_ids))])


def _assign_planning_times(
    rng: np.random.Generator,
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Populate planning timestamps and duration for closed notifications."""
    df = df.copy()
    closed_mask = df["status"].isin(["converted_to_wo", "rejected_duplicate",
                                      "rejected_false_positive"])
    reject_mask = df["status"].isin(["rejected_duplicate", "rejected_false_positive"])

    n_closed = closed_mask.sum()
    n_reject = reject_mask.sum()
    if n_closed == 0:
        return df

    # Log-normal duration: mu=3.2, sigma=0.6 → mean≈29min, median≈24min, p95≈74min
    durations = np.exp(rng.normal(3.2, 0.6, size=n_closed)).round(1)

    # Rejects faster: 5–10 min
    reject_positions = np.where(reject_mask[closed_mask].values)[0]
    if len(reject_positions) > 0:
        durations[reject_positions] = rng.uniform(5, 10, size=n_reject).round(1)

    raised_times = pd.to_datetime(df.loc[closed_mask, "raised_at"])
    lag_hours = rng.uniform(1, 72, size=n_closed)

    # Use timedelta arithmetic to avoid datetime64 unit ambiguity (µs vs ns)
    started_times = raised_times + pd.to_timedelta(lag_hours, unit="h")
    completed_times = started_times + pd.to_timedelta(durations, unit="m")

    df.loc[closed_mask, "planning_started_at"] = started_times
    df.loc[closed_mask, "planning_completed_at"] = completed_times
    df.loc[closed_mask, "planning_duration_minutes"] = durations
    return df


def _mark_duplicates(rng: np.random.Generator, df: pd.DataFrame) -> pd.DataFrame:
    """Replace ~5% of open notifications with near-duplicate raw_text."""
    df = df.copy()
    open_mask = df["status"] == "open"
    open_indices = df.index[open_mask].tolist()
    n_dupes = max(1, int(len(open_indices) * DUPLICATE_RATE))
    if len(open_indices) < n_dupes:
        return df

    dupe_indices = rng.choice(open_indices, size=n_dupes, replace=False)
    for idx in dupe_indices:
        asset_id = df.at[idx, "asset_id"]
        dup_templates = RAW_TEXT_TEMPLATES.get("duplicate", ["{asset_name} — follow-up."])
        tmpl = dup_templates[rng.integers(0, len(dup_templates))]
        df.at[idx, "raw_text"] = tmpl.format(
            asset_name=asset_id, unit="", value="", baseline="", shift="day"
        )
        df.at[idx, "ground_truth_category"] = "duplicate"
    return df


def _write_schema() -> None:
    from pathlib import Path
    schema = """# notifications_schema.md

| Column | Type | Description |
|---|---|---|
| notification_id | string | Primary key. Format: NTF-NNNNNNN |
| asset_id | string | FK → assets.asset_id |
| raised_at | timestamp | When the notification was raised |
| source | string | operator \\| sensor \\| inspection_round \\| predictive_model |
| raw_text | string | Unstructured free text as reported (1–3 sentences) |
| observed_severity | int | Severity as assessed by reporter (1=worst, 5=least) |
| status | string | open \\| in_review \\| converted_to_wo \\| rejected_duplicate \\| rejected_false_positive |
| assigned_planner_id | string | FK → planners.planner_id (nullable) |
| planning_started_at | timestamp | When planner began work (nullable) |
| planning_completed_at | timestamp | When planner finished (nullable) |
| planning_duration_minutes | float | Elapsed planning time in minutes (nullable) |
| converted_to_wo_id | string | FK → work_orders.wo_id (nullable) |
| ground_truth_severity | int | **EVALUATION ONLY.** Actual severity. Do not feed to agents. |
| ground_truth_category | string | **EVALUATION ONLY.** Actual root-cause category. Do not feed to agents. |

## Noise characteristics

- ~15% of rows: `observed_severity` ≠ `ground_truth_severity`
- ~10% of rows: `ground_truth_category = false_positive`
- ~5% of open rows: `ground_truth_category = duplicate`

## Evaluation columns

`ground_truth_severity` and `ground_truth_category` are labelled ground truth for
post-hoc agent evaluation only. Do not include these in agent prompts.
"""
    out = Path(__file__).parent.parent / "output" / "notifications_schema.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(schema)
