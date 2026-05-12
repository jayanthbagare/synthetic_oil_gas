# Synthetic Data Generator — Refinery Maintenance Agent Workshop

> Prompt for Claude Code. Paste into a fresh, empty repository and let it work.

---

## Context

You are generating realistic synthetic data for a hands-on agent-building workshop run by SAP for its product managers and engineering managers.

The scenario: a fictional mid-sized refinery called **Crestmount Refinery** in West Texas, producing ~100,000 barrels/day at design capacity. Maintenance work flows through a pipeline of stations:

  Notification (operator / sensor / inspection / predictive model)
  → Maintenance Planner (triage, classify, scope, parts, crew, permits, schedule)
  → Scheduler (fit into operating window)
  → Crew (execute with permits and parts)
  → Closure (record outcomes, feed back to asset history)

The workshop has taught the participants that the **constraint** in this pipeline is the **planner** — a small team performing cognitively-intensive judgment work that paces the entire system. Notifications arrive faster than the planning team can process them. The backlog grows. Critical work ages. Unplanned downtime rises.

In the workshop, teams will build agents that operate at the planner station and demonstrate throughput improvement against the throughput equation:

  Δ(T − OE) − ΔI/payback > 0 ?

Your job is to generate the data they work with. Realistic enough to be meaningful; structured enough to be approachable in a 3–4 hour workshop.

---

## What to build

```
data_generator/
├── README.md                  # how to install, run, regenerate; what files are produced
├── PLAN.md                    # written first, before any code
├── pyproject.toml             # or requirements.txt
├── generate_data.py           # main entry point
├── generators/
│   ├── __init__.py
│   ├── common.py              # RNG seeding, helpers, shared vocabularies
│   ├── assets.py
│   ├── operations_calendar.py
│   ├── parts.py
│   ├── crews.py
│   ├── permits.py
│   ├── planners.py
│   ├── notifications.py
│   ├── work_orders.py
│   └── failures.py
├── tests/
│   └── test_data_quality.py   # spot checks: row counts, FK integrity, distributions
└── output/                    # generated CSVs land here
    └── .gitkeep
```

Begin by writing `PLAN.md` summarising the approach, generation order (some entities depend on others — generate assets first, then calendar, then crews/parts/permits/planners, then notifications, then work orders, then failures as a derived view). Then implement.

---

## Reproducibility

Single `--seed` argument controls **all** randomness across all generators. Same seed → byte-identical output.

```
python generate_data.py --seed 42 --output-dir ./output
```

A run with `--seed 42` should produce the workshop's canonical dataset.

---

## Volume (target)

These numbers are intentionally workable on a laptop:

| Entity | Count |
|---|---|
| Assets | ~500 |
| Operations calendar | 730 days (24 months) |
| Spare parts SKUs | ~5,000 |
| Crews | ~30 |
| Permit types | ~10 |
| Planners | 6 |
| Notifications (24-month history) | ~10,000 |
| Notifications (current open backlog) | ~2,000 |
| Work orders (closed historical) | ~8,000 |
| Work orders (in flight) | ~500 |
| Failure events | ~1,200 |

---

## Time scope

Generate **24 months ending today** (the run date is "today"). The "current state" backlog is what's open as of the run date.

---

## Schemas

All CSVs go in `output/`. Each CSV has a sibling `{name}_schema.md` with column descriptions.

### `assets.csv`

- `asset_id` — `AST-NNNNN`
- `asset_class` — one of: `centrifugal_pump`, `reciprocating_pump`, `compressor`, `heat_exchanger`, `fired_heater`, `column`, `vessel`, `control_valve`, `isolation_valve`, `instrument`, `piping`, `electrical_motor`, `transformer`, `cooling_tower`, `flare`
- `asset_name` — descriptive (e.g., "Crude Charge Pump A")
- `location_unit` — one of: `Crude_Distillation`, `Catalytic_Cracking`, `Hydrotreating`, `Reforming`, `Utilities`, `Tankage`
- `criticality_tier` — 1 (highest) to 5 (lowest). Distribution: ~5% T1, ~15% T2, ~25% T3, ~30% T4, ~25% T5
- `install_date` — between 5 and 35 years ago
- `last_major_overhaul_date` — nullable, more recent than install
- `mtbf_days` — mean time between failures; varies by class (pumps ~180–365, heat exchangers ~365–730, valves ~730–1460, etc.)
- `replacement_cost_usd` — varies by class and criticality (T1 assets cost more)

### `operations_calendar.csv`

- `date`
- `plant_state` — `running` | `derate` | `turnaround` | `startup` | `shutdown`
- `production_rate_pct` — 0–100; 0 during turnaround/shutdown; reduced during derate
- `maintenance_window_hours` — hours of maintenance work the plant can absorb that day
- `notes` — occasional (e.g., "scheduled turnaround day 3 of 14")

Include at least one full turnaround (~14 days) in the 24-month window.

### `spare_parts.csv`

- `part_id` — `PRT-NNNNNN`
- `part_name`
- `part_category` — `bearing` | `seal` | `gasket` | `valve_trim` | `motor` | `instrument` | `lubricant` | `coupling` | `electrical` | `fitting`
- `compatible_asset_classes` — semicolon-separated list of asset_class values
- `supplier_id` — `SUP-NNN`
- `lead_time_days_mean` — varies by category (bearings 3–7, custom valve trims 30–90, etc.)
- `lead_time_days_stdev`
- `unit_cost_usd`
- `in_stock_qty`
- `reorder_point`

### `crews.csv`

- `crew_id`
- `crew_name`
- `skill_codes` — semicolon-separated from: `mechanical`, `rotating_equipment`, `static_equipment`, `welding`, `electrical`, `instrumentation`, `rigging`, `scaffolding`, `confined_space`, `hot_work`, `inspection`
- `size`
- `shift` — `day` | `night` | `rotation`
- `available_hours_per_week`

### `permits.csv`

- `permit_code` — `PMT-XX`
- `permit_name` — e.g., `Hot Work`, `Confined Space Entry`, `Energy Isolation (LOTO)`, `Line Break`, `Excavation`, `Working at Height`, `Radiation`, `Cold Work`, `Vehicle Entry`, `Bypass`
- `typical_lead_time_hours`
- `prerequisites` — semicolon-separated permit_codes or empty

### `planners.csv`

- `planner_id` — `PLN-X`
- `planner_name` — anonymised (`Planner-A` through `Planner-F`)
- `experience_years`
- `specialization` — `rotating_equipment` | `static_equipment` | `instrumentation` | `electrical` | `generalist`
- `avg_notifications_per_day` — 18–35; seniors more thorough but slower
- `shift`

### `notifications.csv`

The most important file. This is what the agent reads.

- `notification_id` — `NTF-NNNNNNN`
- `asset_id` — FK
- `raised_at` — timestamp
- `source` — `operator` | `sensor` | `inspection_round` | `predictive_model`
- `raw_text` — **unstructured free text**, 1–3 sentences. See generation rules below.
- `observed_severity` — 1 (worst) to 5; what the reporter thought
- `status` — `open` | `in_review` | `converted_to_wo` | `rejected_duplicate` | `rejected_false_positive`
- `assigned_planner_id` — FK, nullable for `open`
- `planning_started_at` — nullable
- `planning_completed_at` — nullable
- `planning_duration_minutes` — nullable; populated when status is `converted_to_wo` or `rejected_*`
- `converted_to_wo_id` — FK to work_orders, nullable
- `ground_truth_severity` — 1–5, the "real" severity. **Evaluation only. Generators must mark this clearly in schema docs.**
- `ground_truth_category` — one of: `leak`, `vibration_abnormal`, `temperature_high`, `pressure_abnormal`, `flow_abnormal`, `control_drift`, `instrument_failure`, `lubrication_low`, `seal_failure`, `bearing_wear`, `coupling_misalignment`, `process_fouling`, `corrosion`, `electrical_fault`, `false_positive`, `duplicate`. **Evaluation only.**

**raw_text generation:**

Generate the structured truth first (asset, ground_truth_category, ground_truth_severity), then synthesise raw_text from templates with controlled noise.

- Maintain 3–5 templates per category. Mix styles:
  - **Terse**: "PMP-103 seal weep noted"
  - **Verbose**: "Operator on day shift reports significant noise from the discharge side of P-2412 starting around 04:00. Sounds like cavitation but could also be a coupling alignment issue — needs eyes."
  - **Misleading**: "Temperature high on E-301" when the real issue is fouling (operator sees the symptom, not the cause).
- About **15%** of notifications should have an `observed_severity` that disagrees with `ground_truth_severity` (operators get severity wrong sometimes).
- About **20%** of notifications should have an `observed_category` mismatch with `ground_truth_category` (operators name symptoms, not root causes).
- About **10%** should be true false positives (`ground_truth_category = false_positive`). The raw_text reads like a real notification.
- About **5%** should be near-duplicates of another recent notification on the same asset. `ground_truth_category = duplicate` for these.
- Use realistic plant vocabulary. Hard-code small per-category vocabularies in `generators/common.py`.

### `work_orders.csv`

- `wo_id` — `WO-NNNNNNN`
- `asset_id` — FK
- `notification_id` — FK to the originating notification (one notification → at most one WO)
- `planner_id` — FK
- `created_at`
- `scheduled_start`
- `actual_start` — nullable for not-yet-started
- `actual_end` — nullable
- `status` — `planned` | `scheduled` | `in_progress` | `completed` | `cancelled`
- `priority` — 1–5, set by planner (correlates with but is not identical to severity)
- `estimated_hours`
- `actual_hours` — nullable
- `work_type` — `corrective` | `preventive` | `predictive` | `regulatory`
- `required_crew_skills` — semicolon-separated skill_codes
- `required_parts_json` — JSON list of `{"part_id": str, "qty": int}`
- `required_permits` — semicolon-separated permit_codes
- `description` — 1–2 sentences
- `closure_notes` — nullable; free text from crew on what they actually did
- `avoided_downtime_hours` — nullable; estimated avoided downtime if this is a preventive/predictive WO

### `failure_events.csv`

A derived view: the subset of completed work orders that reflect a real failure (i.e., `work_type = corrective` and `ground_truth_category != false_positive`).

- `failure_id`
- `asset_id` — FK
- `wo_id` — FK
- `failed_at`
- `root_cause` — free text, 5–10 words
- `root_cause_category` — canonical category (same vocabulary as `ground_truth_category`)
- `downtime_hours` — actual
- `downtime_cost_usd` — estimated; scaled by `criticality_tier` (T1 ~$200K–$500K/hour, T5 ~$0–$1K/hour)

---

## Realism constraints

These are what separate this from random data:

1. **Asset-failure correlations.** Older assets fail more. Recently-failed assets are more likely to fail again soon. Asset classes have characteristic failure modes:
   - Pumps → `seal_failure`, `bearing_wear`, `coupling_misalignment`, `vibration_abnormal`
   - Heat exchangers → `process_fouling`, `leak`, `corrosion`
   - Valves → `leak`, `control_drift`, `instrument_failure`
   - Compressors → `vibration_abnormal`, `bearing_wear`, `temperature_high`

2. **Notification volume seasonality.** Weekday volume > weekend. Daytime > nighttime. Spikes around plant state changes (startup, shutdown).

3. **The backlog reveals the bottleneck.** Open notifications should show realistic age distribution: many recent, but a long tail of older items. Tier-3 and Tier-4 criticals should appear in the older tail — that's the "criticals aging in the queue" pattern that motivates the workshop.

4. **Planning time per notification.** Log-normal distribution, mean ~30 min, median ~22 min, p95 ~75 min. High-criticality and unfamiliar-class items take longer. False-positive rejects take 5–10 min.

5. **Planner throughput should clearly be the bottleneck.** Total weekly inflow > total weekly planner capacity. The 24-month history should show backlog growth.

6. **Costs and downtime.** `downtime_cost_usd` should plausibly reflect that T1 assets disrupt $1–5M/day of operation; T5 are essentially free to be down. Total preventive `avoided_downtime_hours × cost-rate-of-asset` summed across the dataset should be in the tens of millions — this is the ΔT that an effective agent can unlock.

7. **Ground-truth integrity.** Generate ground_truth fields **first**, then derive observed/raw fields from them with controlled noise. This ensures the eval signal is honest.

---

## Outputs

- All CSVs in `output/`
- `output/{name}_schema.md` for each CSV
- `output/SUMMARY.md` with row counts, key distributions, sample of notifications, distribution charts (as markdown tables, not images). The SUMMARY should let a workshop facilitator sanity-check a fresh run in 30 seconds.
- Top-level `README.md` with install/run instructions

In `SUMMARY.md`, **do not lead with** the ground-truth columns. Mention them briefly under an "evaluation columns" subsection so participants discover them via the workshop README, not via the data summary.

---

## Quality bar

- Type-hint everything (`from __future__ import annotations` is fine)
- `pandas` for CSV writing
- `numpy` for distributions
- `faker` is optional — use it for plausible names and identifiers if it helps; do not use it for maintenance-specific text (hard-code small vocabularies in `common.py`)
- Foreign keys must resolve. Write a final validation pass that fails the run if any FK is dangling.
- 5–10 unit tests for data quality: row counts within tolerance of targets, criticality distribution within expected bands, no orphan FKs, planning-time distribution shape, raw_text non-empty, ground-truth fields populated where required.
- The run should complete in **under 60 seconds** on a laptop. If a generator is slow, vectorise it.

---

## What to avoid

- This is **data generation**, not simulation. Don't model timesteps or physics.
- No ML dependencies (`scikit-learn`, transformers, LLM clients).
- Don't make the data too clean. Participants need to feel real plant data has noise.
- Don't expose ground-truth fields prominently. They are evaluation columns.
- Don't generate Markdown narratives in the data itself. Keep CSVs tabular.

---

## When you're done

Print to stdout:

- The path to `output/SUMMARY.md`
- A one-paragraph plain-English summary of what the dataset shows about the bottleneck (e.g., "On the current snapshot date, 2,047 notifications are open; the oldest is 87 days old; 14 of these are tier-1 critical assets that should have been processed within 24 hours")

That paragraph is what the workshop facilitator reads first to confirm the dataset tells the right story.

Begin.
