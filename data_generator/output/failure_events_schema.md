# failure_events_schema.md

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
