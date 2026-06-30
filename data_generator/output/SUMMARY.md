# SUMMARY — Crestmount Refinery Synthetic Dataset

> Generated on 2026-06-30. Seed: (stored in run config).

## Row counts

| Entity | Rows |
|---|---|
| assets | 500 |
| operations_calendar | 730 |
| spare_parts | 5000 |
| crews | 30 |
| permits | 10 |
| planners | 6 |
| notifications (total) | 12000 |
| notifications (open backlog) | 1869 |
| work_orders | 8565 |
| failure_events | 1200 |
| sensors | 940 |
| sensor_readings | 676800 |
| asset_connections | 1581 |
| weather | 730 |
| production | 730 |

## The bottleneck in numbers

| Metric | Value |
|---|---|
| Open notifications at run date | 1,869 |
| Oldest open notification (days) | 89 |
| Tier-1 critical assets in open backlog | 15 |
| Tier-2 critical assets in open backlog | 343 |
| Estimated planner capacity (notifications/week) | 1,260 |
| Estimated weekly notification inflow | 104 |
| Weekly backlog growth | 0 |

## Open backlog age distribution

| Age bucket | Count |
|---|---|
| 0–7 days | 262 |
| 8–30 days | 871 |
| 31–60 days | 373 |
| 61–90 days | 363 |
| >90 days | 0 |

## Notification sources

| Source | Count |
|---|---|
| operator | 4,890 |
| sensor | 3,498 |
| inspection_round | 2,414 |
| predictive_model | 1,198 |

## Notification statuses

| Status | Count |
|---|---|
| converted_to_wo | 8,065 |
| rejected_false_positive | 1,442 |
| open | 1,084 |
| in_review | 785 |
| rejected_duplicate | 624 |

## Financial summary

| Metric | Value |
|---|---|
| Total failure downtime cost (24-month dataset) | $48,870,405 |
| Rolling 12-month failure downtime cost | $25,830,833 |
| Cumulative avoided downtime (preventive/predictive WOs) | 26,228 h |

## Sample open notifications (first 10)

| notification_id | asset_id | raised_at | source | observed_severity | raw_text |
|---|---|---|---|---|---|
| NTF-0010001 | AST-00342 | 2026-04-01 | sensor | 2 | Coupling guard on AST-00342 warm — possible misalignment.… |
| NTF-0010002 | AST-00374 | 2026-04-01 | operator | 4 | After last PM on AST-00374, vibration has been slightly elevated. Coupling align… |
| NTF-0010003 | AST-00447 | 2026-04-01 | sensor | 1 | AST-00447 showing some deterioration — unclear if structural or cosmetic.… |
| NTF-0010004 | AST-00232 | 2026-04-01 | operator | 5 | Operator reported unusual noise from AST-00232 area. Investigated — noise was fr… |
| NTF-0010005 | AST-00346 | 2026-04-01 | operator | 2 | Abnormal noise from AST-00346 bearing area — grinding / rumbling sound noted by … |
| NTF-0010006 | AST-00217 | 2026-04-01 | operator | 4 | Heat duty dropping on AST-00217 — clean up required.… |
| NTF-0010007 | AST-00259 | 2026-04-01 | operator | 4 | Inspection crew found external corrosion on AST-00259 in isolation valve. Corros… |
| NTF-0010008 | AST-00291 | 2026-04-01 | sensor | 1 | Paint breakdown and rust observed on AST-00291 during walkaround. Surface prepar… |
| NTF-0010009 | AST-00146 | 2026-04-01 | inspection_round | 5 | Operator found fluid on ground under AST-00146 in flare. Appears to be a flange … |
| NTF-0010011 | AST-00176 | 2026-04-01 | operator | 4 | AST-00176 showing a seep at the body-to-bonnet joint. Flagged by inspection on r… |

## Criticality distribution (assets)

| Tier | Count | % |
|---|---|---|
| T1 | 25 | 5.0% |
| T2 | 74 | 14.8% |
| T3 | 120 | 24.0% |
| T4 | 163 | 32.6% |
| T5 | 118 | 23.6% |

## Evaluation columns

`notifications.csv` contains two columns marked **evaluation-only** that participants should not feed to their agents:

- `ground_truth_severity` — the actual severity (vs `observed_severity`)
- `ground_truth_category` — the actual root-cause category

These are documented in `notifications_schema.md`. Do not lead the workshop with them.
