"""Main entry point for the Crestmount Refinery synthetic data generator.

Usage:
    python generate_data.py --seed 42 --output-dir ./output
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

from generators.assets import generate_assets
from generators.operations_calendar import generate_operations_calendar
from generators.parts import generate_parts
from generators.crews import generate_crews
from generators.permits import generate_permits
from generators.planners import generate_planners
from generators.notifications import generate_notifications
from generators.work_orders import generate_work_orders
from generators.failures import generate_failures
from generators.common import make_rng


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate Crestmount Refinery synthetic data")
    p.add_argument("--seed", type=int, default=42, help="Master RNG seed (default 42)")
    p.add_argument("--output-dir", type=Path, default=Path("./output"),
                   help="Directory for generated CSVs (default ./output)")
    return p.parse_args()


def _validate_foreign_keys(dfs: dict) -> None:
    """Fail-fast FK integrity check across all DataFrames."""
    import pandas as pd

    errors: list[str] = []

    asset_ids    = set(dfs["assets"]["asset_id"])
    planner_ids  = set(dfs["planners"]["planner_id"])
    part_ids     = set(dfs["spare_parts"]["part_id"])
    permit_codes = set(dfs["permits"]["permit_code"])
    notif_ids    = set(dfs["notifications"]["notification_id"])
    wo_ids       = set(dfs["work_orders"]["wo_id"])

    # Notifications → assets
    bad = set(dfs["notifications"]["asset_id"]) - asset_ids
    if bad:
        errors.append(f"notifications.asset_id has {len(bad)} unresolved FK(s): {list(bad)[:5]}")

    # Notifications → planners (nullable)
    assigned = dfs["notifications"]["assigned_planner_id"].dropna()
    bad = set(assigned) - planner_ids
    if bad:
        errors.append(f"notifications.assigned_planner_id has {len(bad)} unresolved FK(s)")

    # Work orders → assets
    bad = set(dfs["work_orders"]["asset_id"]) - asset_ids
    if bad:
        errors.append(f"work_orders.asset_id has {len(bad)} unresolved FK(s)")

    # Work orders → planners
    bad = set(dfs["work_orders"]["planner_id"]) - planner_ids
    if bad:
        errors.append(f"work_orders.planner_id has {len(bad)} unresolved FK(s)")

    # Work orders → notifications (nullable)
    wo_notif = dfs["work_orders"]["notification_id"].dropna()
    bad = set(wo_notif) - notif_ids
    if bad:
        errors.append(f"work_orders.notification_id has {len(bad)} unresolved FK(s)")

    # Notifications.converted_to_wo_id → work_orders (nullable)
    ntf_wo = dfs["notifications"]["converted_to_wo_id"].dropna()
    bad = set(ntf_wo) - wo_ids
    if bad:
        errors.append(f"notifications.converted_to_wo_id has {len(bad)} unresolved FK(s)")

    # Validate parts in work_orders.required_parts_json
    import json as _json
    for raw in dfs["work_orders"]["required_parts_json"]:
        try:
            parts_list = _json.loads(raw) if raw else []
        except Exception:
            errors.append(f"work_orders.required_parts_json contains invalid JSON: {raw[:60]}")
            break
        for item in parts_list:
            if item.get("part_id") not in part_ids:
                errors.append(f"required_parts_json references unknown part_id: {item.get('part_id')}")
                break

    # Validate permit codes in work_orders.required_permits
    for raw in dfs["work_orders"]["required_permits"]:
        if not raw:
            continue
        for code in raw.split(";"):
            if code and code not in permit_codes:
                errors.append(f"work_orders.required_permits references unknown code: {code}")
                break

    # Failure events → work_orders
    bad = set(dfs["failure_events"]["wo_id"]) - wo_ids
    if bad:
        errors.append(f"failure_events.wo_id has {len(bad)} unresolved FK(s)")

    # Failure events → assets
    bad = set(dfs["failure_events"]["asset_id"]) - asset_ids
    if bad:
        errors.append(f"failure_events.asset_id has {len(bad)} unresolved FK(s)")

    if errors:
        print("\n[VALIDATION FAILED]")
        for e in errors:
            print(f"  ERROR: {e}")
        sys.exit(1)
    else:
        print("[VALIDATION] All foreign key checks passed.")


def _write_summary(dfs: dict, output_dir: Path, run_date: date) -> str:
    """Write SUMMARY.md and return the facilitator paragraph."""
    import pandas as pd

    notifs     = dfs["notifications"]
    work_orders = dfs["work_orders"]
    failures   = dfs["failure_events"]
    assets     = dfs["assets"]

    open_notifs = notifs[notifs["status"].isin(["open", "in_review"])]
    n_open = len(open_notifs)

    open_notifs_ts = pd.to_datetime(open_notifs["raised_at"])
    run_ts = pd.Timestamp(run_date)
    ages_days = ((run_ts - open_notifs_ts).dt.total_seconds() / 86400).round(1)
    oldest_days = int(ages_days.max())

    # Tier-1 criticals in open backlog
    open_with_tier = open_notifs.merge(assets[["asset_id", "criticality_tier"]], on="asset_id", how="left")
    n_t1_open = int((open_with_tier["criticality_tier"] == 1).sum())
    n_t2_open = int((open_with_tier["criticality_tier"] == 2).sum())

    # Backlog age brackets
    age_0_7    = int((ages_days <= 7).sum())
    age_8_30   = int(((ages_days > 7) & (ages_days <= 30)).sum())
    age_31_60  = int(((ages_days > 30) & (ages_days <= 60)).sum())
    age_61_90  = int(((ages_days > 60) & (ages_days <= 90)).sum())
    age_90plus = int((ages_days > 90).sum())

    # Financial
    total_downtime_cost = failures["downtime_cost_usd"].sum()
    recent_failures = failures[
        pd.to_datetime(failures["failed_at"]) >= (run_ts - pd.Timedelta(days=365))
    ]
    rolling_12mo_cost = recent_failures["downtime_cost_usd"].sum()

    wo_preventive = work_orders[work_orders["work_type"].isin(["preventive", "predictive"])]
    avoided_hours = wo_preventive["avoided_downtime_hours"].dropna().sum()

    # Notification distribution by source
    src_counts = notifs["source"].value_counts().to_dict()
    # Notification distribution by status
    status_counts = notifs["status"].value_counts().to_dict()

    # Planner throughput
    planners_df = dfs["planners"]
    weekly_capacity = int(planners_df["avg_notifications_per_day"].sum() * 5)
    # Weekly inflow estimate (total historical / 104 weeks)
    historical = notifs[notifs["status"] != "open"]
    weekly_inflow = int(len(historical) / 104)

    lines: list[str] = [
        "# SUMMARY — Crestmount Refinery Synthetic Dataset",
        "",
        f"> Generated on {run_date}. Seed: (stored in run config).",
        "",
        "## Row counts",
        "",
        "| Entity | Rows |",
        "|---|---|",
        f"| assets | {len(dfs['assets'])} |",
        f"| operations_calendar | {len(dfs['operations_calendar'])} |",
        f"| spare_parts | {len(dfs['spare_parts'])} |",
        f"| crews | {len(dfs['crews'])} |",
        f"| permits | {len(dfs['permits'])} |",
        f"| planners | {len(dfs['planners'])} |",
        f"| notifications (total) | {len(notifs)} |",
        f"| notifications (open backlog) | {n_open} |",
        f"| work_orders | {len(work_orders)} |",
        f"| failure_events | {len(failures)} |",
        "",
        "## The bottleneck in numbers",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Open notifications at run date | {n_open:,} |",
        f"| Oldest open notification (days) | {oldest_days} |",
        f"| Tier-1 critical assets in open backlog | {n_t1_open} |",
        f"| Tier-2 critical assets in open backlog | {n_t2_open} |",
        f"| Estimated planner capacity (notifications/week) | {weekly_capacity:,} |",
        f"| Estimated weekly notification inflow | {weekly_inflow:,} |",
        f"| Weekly backlog growth | {max(0, weekly_inflow - weekly_capacity):,} |",
        "",
        "## Open backlog age distribution",
        "",
        "| Age bucket | Count |",
        "|---|---|",
        f"| 0–7 days | {age_0_7:,} |",
        f"| 8–30 days | {age_8_30:,} |",
        f"| 31–60 days | {age_31_60:,} |",
        f"| 61–90 days | {age_61_90:,} |",
        f"| >90 days | {age_90plus:,} |",
        "",
        "## Notification sources",
        "",
        "| Source | Count |",
        "|---|---|",
    ]
    for src, cnt in sorted(src_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {src} | {cnt:,} |")

    lines += [
        "",
        "## Notification statuses",
        "",
        "| Status | Count |",
        "|---|---|",
    ]
    for st, cnt in sorted(status_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {st} | {cnt:,} |")

    lines += [
        "",
        "## Financial summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total failure downtime cost (24-month dataset) | ${total_downtime_cost:,.0f} |",
        f"| Rolling 12-month failure downtime cost | ${rolling_12mo_cost:,.0f} |",
        f"| Cumulative avoided downtime (preventive/predictive WOs) | {avoided_hours:,.0f} h |",
        "",
        "## Sample open notifications (first 10)",
        "",
        "| notification_id | asset_id | raised_at | source | observed_severity | raw_text |",
        "|---|---|---|---|---|---|",
    ]
    sample = open_notifs.head(10)
    for _, row in sample.iterrows():
        text = str(row["raw_text"])[:80].replace("|", "/")
        lines.append(f"| {row['notification_id']} | {row['asset_id']} | {str(row['raised_at'])[:10]} "
                     f"| {row['source']} | {row['observed_severity']} | {text}… |")

    lines += [
        "",
        "## Criticality distribution (assets)",
        "",
        "| Tier | Count | % |",
        "|---|---|---|",
    ]
    for tier in range(1, 6):
        cnt = int((dfs["assets"]["criticality_tier"] == tier).sum())
        pct = 100.0 * cnt / len(dfs["assets"])
        lines.append(f"| T{tier} | {cnt} | {pct:.1f}% |")

    lines += [
        "",
        "## Evaluation columns",
        "",
        "`notifications.csv` contains two columns marked **evaluation-only** that participants "
        "should not feed to their agents:",
        "",
        "- `ground_truth_severity` — the actual severity (vs `observed_severity`)",
        "- `ground_truth_category` — the actual root-cause category",
        "",
        "These are documented in `notifications_schema.md`. Do not lead the workshop with them.",
    ]

    summary_path = output_dir / "SUMMARY.md"
    summary_path.write_text("\n".join(lines) + "\n")

    # Facilitator paragraph
    para = (
        f"On the current snapshot date ({run_date}), {n_open:,} notifications are open in the "
        f"backlog; the oldest is {oldest_days} days old. Of these, {n_t1_open} are on tier-1 "
        f"critical assets and {n_t2_open} on tier-2 — assets that by Crestmount policy should be "
        f"processed within 24 hours of notification. The planner team has a combined capacity of "
        f"~{weekly_capacity:,} notifications/week against an inflow of ~{weekly_inflow:,}/week, "
        f"producing a structural backlog growth of ~{max(0, weekly_inflow - weekly_capacity):,} "
        f"notifications/week. Rolling 12-month unplanned downtime cost is "
        f"${rolling_12mo_cost/1e6:.1f}M; preventive and predictive work orders account for "
        f"{avoided_hours:,.0f} hours of avoided downtime across the dataset. "
        f"The bottleneck is visible and the cost of leaving it unaddressed is quantifiable."
    )
    return para


def main() -> None:
    args = _parse_args()
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    run_date = date.today()
    master_rng = np.random.default_rng(args.seed)

    print(f"Crestmount Refinery data generator — seed={args.seed}, run_date={run_date}")
    t0 = time.perf_counter()

    # ------------------------------------------------------------------ #
    # Phase 1: Independent entities
    # ------------------------------------------------------------------ #
    print("  Generating assets …")
    assets_df = generate_assets(make_rng(master_rng, 0), run_date)
    assets_df.to_csv(output_dir / "assets.csv", index=False)

    print("  Generating operations calendar …")
    cal_df = generate_operations_calendar(make_rng(master_rng, 1), run_date)
    cal_df.to_csv(output_dir / "operations_calendar.csv", index=False)

    print("  Generating spare parts …")
    parts_df = generate_parts(make_rng(master_rng, 2))
    parts_df.to_csv(output_dir / "spare_parts.csv", index=False)

    print("  Generating crews …")
    crews_df = generate_crews(make_rng(master_rng, 3))
    crews_df.to_csv(output_dir / "crews.csv", index=False)

    print("  Generating permits …")
    permits_df = generate_permits()
    permits_df.to_csv(output_dir / "permits.csv", index=False)

    print("  Generating planners …")
    planners_df = generate_planners()
    planners_df.to_csv(output_dir / "planners.csv", index=False)

    # ------------------------------------------------------------------ #
    # Phase 2: Dependent entities
    # ------------------------------------------------------------------ #
    print("  Generating notifications …")
    notifs_df = generate_notifications(make_rng(master_rng, 4), assets_df, planners_df, cal_df, run_date)
    notifs_df.to_csv(output_dir / "notifications.csv", index=False)

    print("  Generating work orders …")
    wo_df = generate_work_orders(make_rng(master_rng, 5), notifs_df, assets_df, planners_df,
                                 crews_df, parts_df, permits_df, run_date)
    wo_df.to_csv(output_dir / "work_orders.csv", index=False)

    # Backfill converted_to_wo_id into notifications
    notif_to_wo = wo_df[wo_df["notification_id"].notna()].set_index("notification_id")["wo_id"]
    notifs_df["converted_to_wo_id"] = notifs_df["notification_id"].map(notif_to_wo)
    notifs_df.to_csv(output_dir / "notifications.csv", index=False)

    print("  Generating failure events …")
    failures_df = generate_failures(make_rng(master_rng, 6), wo_df, notifs_df, assets_df)
    failures_df.to_csv(output_dir / "failure_events.csv", index=False)

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    print("  Validating foreign keys …")
    dfs = {
        "assets": assets_df,
        "operations_calendar": cal_df,
        "spare_parts": parts_df,
        "crews": crews_df,
        "permits": permits_df,
        "planners": planners_df,
        "notifications": notifs_df,
        "work_orders": wo_df,
        "failure_events": failures_df,
    }
    _validate_foreign_keys(dfs)

    # ------------------------------------------------------------------ #
    # SUMMARY
    # ------------------------------------------------------------------ #
    print("  Writing SUMMARY.md …")
    para = _write_summary(dfs, output_dir, run_date)

    elapsed = time.perf_counter() - t0
    print(f"\nDone in {elapsed:.1f}s")
    print(f"\nOutput: {output_dir / 'SUMMARY.md'}\n")
    print(para)


if __name__ == "__main__":
    main()
