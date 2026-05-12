# notifications_schema.md

| Column | Type | Description |
|---|---|---|
| notification_id | string | Primary key. Format: NTF-NNNNNNN |
| asset_id | string | FK → assets.asset_id |
| raised_at | timestamp | When the notification was raised |
| source | string | operator \| sensor \| inspection_round \| predictive_model |
| raw_text | string | Unstructured free text as reported (1–3 sentences) |
| observed_severity | int | Severity as assessed by reporter (1=worst, 5=least) |
| status | string | open \| in_review \| converted_to_wo \| rejected_duplicate \| rejected_false_positive |
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
