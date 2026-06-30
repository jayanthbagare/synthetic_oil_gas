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
import pandas as pd

from generators.assets import generate_assets
from generators.operations_calendar import generate_operations_calendar
from generators.parts import generate_parts
from generators.crews import generate_crews
from generators.permits import generate_permits
from generators.planners import generate_planners
from generators.notifications import generate_notifications
from generators.work_orders import generate_work_orders
from generators.failures import generate_failures
from generators.weather import generate_weather
from generators.production import generate_production
from generators.asset_connectivity import generate_asset_connections
from generators.sensors import generate_sensors
from generators.common import make_rng
from infra.config import load_config
from infra.logging_setup import configure_logging, get_logger
from infra.db import build_database


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate Crestmount Refinery synthetic data")
    p.add_argument("--seed", type=int, default=None, help="Master RNG seed (overrides config)")
    p.add_argument("--output-dir", type=Path, default=None,
                   help="Directory for generated CSVs (overrides config)")
    p.add_argument("--config", type=str, default=None,
                   help="Path to a YAML config file (merged over defaults)")
    p.add_argument("--build-db", action="store_true",
                   help="Build a SQLite DB from the generated CSVs")
    p.add_argument("--no-sensors", action="store_true",
                   help="Skip the (large) sensor telemetry dataset")
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
        f"| sensors | {len(dfs.get('sensors', pd.DataFrame()))} |",
        f"| sensor_readings | {len(dfs.get('sensor_readings', pd.DataFrame()))} |",
        f"| asset_connections | {len(dfs.get('asset_connections', pd.DataFrame()))} |",
        f"| weather | {len(dfs.get('weather', pd.DataFrame()))} |",
        f"| production | {len(dfs.get('production', pd.DataFrame()))} |",
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

    # ---- config + logging ---------------------------------------------- #
    cfg = load_config(args.config)
    if args.seed is not None:
        cfg.override(seed=args.seed)
    if args.output_dir is not None:
        cfg.override(output_dir=str(args.output_dir))
    seed = cfg.seed
    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    configure_logging(cfg.get("logging.level", "INFO"), cfg.get("logging.format", "structured"))
    log = get_logger("generator")

    run_date = date.today()
    master_rng = np.random.default_rng(seed)

    log.info("Crestmount Refinery data generator starting",
             extra={"seed": seed, "entity": "all", "phase": "start"})
    t0 = time.perf_counter()

    # ------------------------------------------------------------------ #
    # Phase 1: Independent entities
    # ------------------------------------------------------------------ #
    log.info("Generating assets", extra={"phase": "assets"})
    assets_df = generate_assets(make_rng(master_rng, 0), run_date)
    assets_df.to_csv(output_dir / "assets.csv", index=False)

    log.info("Generating operations calendar", extra={"phase": "calendar"})
    cal_df = generate_operations_calendar(make_rng(master_rng, 1), run_date)
    cal_df.to_csv(output_dir / "operations_calendar.csv", index=False)

    log.info("Generating spare parts", extra={"phase": "parts"})
    parts_df = generate_parts(make_rng(master_rng, 2))
    parts_df.to_csv(output_dir / "spare_parts.csv", index=False)

    log.info("Generating crews", extra={"phase": "crews"})
    crews_df = generate_crews(make_rng(master_rng, 3))
    crews_df.to_csv(output_dir / "crews.csv", index=False)

    log.info("Generating permits", extra={"phase": "permits"})
    permits_df = generate_permits()
    permits_df.to_csv(output_dir / "permits.csv", index=False)

    log.info("Generating planners", extra={"phase": "planners"})
    planners_df = generate_planners()
    planners_df.to_csv(output_dir / "planners.csv", index=False)

    # ---- Phase 2 new datasets (independent of notifications/WOs) ------- #
    log.info("Generating weather", extra={"phase": "weather"})
    weather_df = generate_weather(make_rng(master_rng, 7), run_date, cfg.section("weather"))
    weather_df.to_csv(output_dir / "weather.csv", index=False)

    log.info("Generating production", extra={"phase": "production"})
    production_df = generate_production(make_rng(master_rng, 8), cal_df, run_date,
                                       cfg.section("production"))
    production_df.to_csv(output_dir / "production.csv", index=False)

    log.info("Generating asset connectivity graph", extra={"phase": "connectivity"})
    connectivity_df = generate_asset_connections(make_rng(master_rng, 9), assets_df,
                                                 cfg.section("asset_connectivity"))
    connectivity_df.to_csv(output_dir / "asset_connections.csv", index=False)

    # ------------------------------------------------------------------ #
    # Phase 2: Dependent entities
    # ------------------------------------------------------------------ #
    log.info("Generating notifications", extra={"phase": "notifications"})
    notifs_df = generate_notifications(make_rng(master_rng, 4), assets_df, planners_df, cal_df, run_date)
    notifs_df.to_csv(output_dir / "notifications.csv", index=False)

    log.info("Generating work orders", extra={"phase": "work_orders"})
    wo_df = generate_work_orders(make_rng(master_rng, 5), notifs_df, assets_df, planners_df,
                                 crews_df, parts_df, permits_df, run_date)
    wo_df.to_csv(output_dir / "work_orders.csv", index=False)

    # Backfill converted_to_wo_id into notifications
    notif_to_wo = wo_df[wo_df["notification_id"].notna()].set_index("notification_id")["wo_id"]
    notifs_df["converted_to_wo_id"] = notifs_df["notification_id"].map(notif_to_wo)
    notifs_df.to_csv(output_dir / "notifications.csv", index=False)

    log.info("Generating failure events", extra={"phase": "failures"})
    failures_df = generate_failures(make_rng(master_rng, 6), wo_df, notifs_df, assets_df)
    failures_df.to_csv(output_dir / "failure_events.csv", index=False)

    # ------------------------------------------------------------------ #
    # Phase 2: Sensor telemetry (depends on assets + failures)
    # ------------------------------------------------------------------ #
    sensors_df = pd.DataFrame()
    readings_df = pd.DataFrame()
    if not args.no_sensors:
        log.info("Generating sensor catalog + telemetry", extra={"phase": "sensors"})
        sensors_df, readings_df = generate_sensors(
            make_rng(master_rng, 10), assets_df, failures_df, run_date,
            cfg.section("sensors"))
        sensors_df.to_csv(output_dir / "sensors.csv", index=False)
        readings_df.to_csv(output_dir / "sensor_readings.csv", index=False)
        log.info("Sensor telemetry complete",
                 extra={"phase": "sensors", "rows": len(readings_df)})

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
        "weather": weather_df,
        "production": production_df,
        "asset_connections": connectivity_df,
        "sensors": sensors_df,
        "sensor_readings": readings_df,
    }
    _validate_foreign_keys(dfs)

    # ------------------------------------------------------------------ #
    # SUMMARY
    # ------------------------------------------------------------------ #
    log.info("Writing SUMMARY.md", extra={"phase": "summary"})
    para = _write_summary(dfs, output_dir, run_date)

    # ------------------------------------------------------------------ #
    # SQLite database (optional)
    # ------------------------------------------------------------------ #
    if args.build_db:
        log.info("Building SQLite database", extra={"phase": "db"})
        db_path = build_database(output_dir, cfg.get("database.sqlite_path"))
        print(f"  SQLite DB: {db_path}")

    elapsed = time.perf_counter() - t0
    log.info("Generation complete", extra={"phase": "end", "elapsed_s": round(elapsed, 1)})
    print(f"\nDone in {elapsed:.1f}s")
    print(f"\nOutput: {output_dir / 'SUMMARY.md'}\n")
    print(para)


if __name__ == "__main__":
    main()
