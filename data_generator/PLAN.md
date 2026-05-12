# PLAN.md — Crestmount Refinery Synthetic Data Generator

> Written before any code. This document is the authoritative reference for generation logic and design decisions.

---

## 1. What We Are Building

A reproducible synthetic data generator that produces realistic maintenance data for a 24-month window ending on the run date. The output is a set of CSVs used in a 3–4 hour agent-building workshop. Workshop participants build agents that operate at the **planner station** — the bottleneck in the maintenance pipeline.

The data must be realistic enough to produce meaningful agent behaviour, yet structured enough to be understandable in a half-day session. The bottleneck must be **visible in the numbers**.

---

## 2. Entity Dependency Graph

```
assets ──────────────────────────────────────────────────┐
operations_calendar ─────────────────────────────────────┤
spare_parts (refs asset_class vocab) ────────────────────┤
crews ───────────────────────────────────────────────────┤──► notifications ──► work_orders ──► failure_events
permits ─────────────────────────────────────────────────┤
planners ────────────────────────────────────────────────┘
```

**Generation order (strictly enforced):**

1. `assets` — no dependencies
2. `operations_calendar` — no dependencies
3. `spare_parts` — uses asset_class vocabulary from common.py
4. `crews` — no dependencies
5. `permits` — no dependencies
6. `planners` — no dependencies
7. `notifications` — depends on assets, planners, operations_calendar
8. `work_orders` — depends on notifications, assets, planners, crews, spare_parts, permits
9. `failure_events` — derived view of completed corrective work_orders

---

## 3. Reproducibility Strategy

A single `--seed` integer seeds a `numpy.random.default_rng(seed)` master RNG. Each generator receives a **child RNG** spawned from the master via `rng.spawn(1)[0]`. This means:
- Each generator is internally deterministic.
- Generator output is independent of insertion order of other generators.
- Same seed → byte-identical CSVs every run.

---

## 4. Time Window

All timestamps are relative to `run_date = date.today()` at generation time. The 24-month window is `[run_date - 730 days, run_date]`. Open backlog items have `raised_at` within the last 90 days with no `converted_to_wo_id`.

---

## 5. Generator Designs

### 5.1 Assets (`assets.py`)

Target: **~500 assets**.

**Asset classes and their approximate population:**
| Class | Count | Characteristic MTBF (days) |
|---|---|---|
| centrifugal_pump | 90 | 180–280 |
| reciprocating_pump | 40 | 200–320 |
| compressor | 30 | 250–400 |
| heat_exchanger | 70 | 365–550 |
| fired_heater | 15 | 400–600 |
| column | 20 | 500–730 |
| vessel | 40 | 450–700 |
| control_valve | 60 | 730–1095 |
| isolation_valve | 50 | 900–1460 |
| instrument | 50 | 730–1095 |
| piping | 30 | 600–900 |
| electrical_motor | 25 | 365–600 |
| transformer | 10 | 730–1460 |
| cooling_tower | 10 | 400–600 |
| flare | 10 | 600–900 |

**Criticality distribution:**
- T1: ~5% (25 assets) — MTBF multiplied by 0.7 (pushed to fail more)
- T2: ~15% (75 assets)
- T3: ~25% (125 assets)
- T4: ~30% (150 assets)
- T5: ~25% (125 assets) — MTBF multiplied by 1.3

**Replacement cost by class × criticality:** T1 pumps ~$500K–$2M, T5 instruments ~$500–$5K. Implemented as a lookup table in `common.py`.

**Install date:** uniform between 5 and 35 years before run_date.
**Last major overhaul:** 30% of assets have one; always between install_date and run_date.

### 5.2 Operations Calendar (`operations_calendar.py`)

Target: **730 rows**, one per day.

**Plant state machine:**
- Baseline state: `running` (production_rate 85–100%)
- Two `derate` periods (~7 days each) at random points; production_rate 50–80%
- One **full turnaround** (~14 days), placed 8–18 months ago; production_rate 0%
  - Preceded by `shutdown` (2 days), followed by `startup` (3 days)
- Sporadic single-day derates for instrument calibration
- `maintenance_window_hours`: 2–4 h/day running; 8–12 h/day derate; 20–24 h/day turnaround; 0 h/day shutdown

**Notes column:** populated only during turnaround (e.g., "scheduled turnaround day 3 of 14").

### 5.3 Spare Parts (`parts.py`)

Target: **~5,000 SKUs**.

**Categories and lead times:**
| Category | Lead Time Mean (days) | Unit Cost Range |
|---|---|---|
| bearing | 4 | $50–$800 |
| seal | 7 | $100–$2,000 |
| gasket | 3 | $10–$500 |
| valve_trim | 45 | $500–$15,000 |
| motor | 21 | $2,000–$50,000 |
| instrument | 14 | $200–$8,000 |
| lubricant | 2 | $20–$200 |
| coupling | 10 | $300–$5,000 |
| electrical | 7 | $100–$3,000 |
| fitting | 5 | $20–$1,000 |

**Compatible asset classes:** each part has 1–3 compatible asset classes selected from the vocabulary. Bearings/seals/lubricants are broad; valve trims are narrow.

**Stock:** `in_stock_qty` drawn from Poisson(λ=20); `reorder_point` = floor(lead_time_mean × 0.5).

### 5.4 Crews (`crews.py`)

Target: **~30 crews**.

- 10 day-shift, 10 night-shift, 10 rotation
- Size: 3–8 people
- Skills: each crew has 2–5 skill codes; rotating equipment crews always have `mechanical` + `rotating_equipment`
- `available_hours_per_week`: `size × 40 × 0.85` (allow for 15% unavailability)

### 5.5 Permits (`permits.py`)

**Fixed set of 10 permits:**

| Code | Name | Lead Time (h) | Prerequisites |
|---|---|---|---|
| PMT-HW | Hot Work | 2 | PMT-CW |
| PMT-CS | Confined Space Entry | 4 | PMT-EI |
| PMT-EI | Energy Isolation (LOTO) | 1 | — |
| PMT-LB | Line Break | 2 | PMT-EI |
| PMT-EX | Excavation | 3 | — |
| PMT-WH | Working at Height | 2 | — |
| PMT-RA | Radiation | 8 | PMT-EI |
| PMT-CW | Cold Work | 1 | — |
| PMT-VE | Vehicle Entry | 1 | — |
| PMT-BP | Bypass | 2 | PMT-EI |

### 5.6 Planners (`planners.py`)

**Fixed set of 6 planners:**

| ID | Name | Experience (yr) | Specialization | avg_notif/day |
|---|---|---|---|---|
| PLN-A | Planner-A | 22 | rotating_equipment | 20 |
| PLN-B | Planner-B | 15 | static_equipment | 24 |
| PLN-C | Planner-C | 8 | instrumentation | 28 |
| PLN-D | Planner-D | 5 | electrical | 32 |
| PLN-E | Planner-E | 12 | generalist | 26 |
| PLN-F | Planner-F | 3 | generalist | 35 |

Senior planners are slower (more thorough), junior planners faster. Planning duration log-normal parameters are planner-specific.

**Total daily capacity:** 20+24+28+32+26+35 = 165 notifications/day × 5 working days = **825/week** (7-day basis: ~165 × 7 × 5/7 ≈ 825). 

Wait — target is 1,260/week. Let me recalculate. The prompt says planners work 5-day weeks. 6 planners × avg ~35/day × 5 days = 1,050/week (lower bound). Use a range of 18–35 so that the **total is around 180 notifications/day × 5 days = ~900/week**, still clearly below the ~1,900/week inflow. The bottleneck is visible.

Actually the README says 1,260/week capacity vs 1,900/week inflow. Let's target 6 planners × ~42/day × 5 days = 1,260/week. avg_notif/day range: 30–50 for the 6 planners.

### 5.7 Notifications (`notifications.py`) — Most Complex

Target: **~12,000 total** (10,000 historical + 2,000 open backlog).

**Generation sequence (ground-truth first):**

1. For each notification:
   a. Pick a random asset (weighted by `1/MTBF` — busier assets generate more notifications)
   b. Pick `ground_truth_category` from the asset class's characteristic failure modes
   c. Pick `ground_truth_severity` (1–5), weighted by criticality tier (T1 assets skew to 1–2)
   d. Pick source (operator 40%, sensor 30%, inspection_round 20%, predictive_model 10%)
   e. Pick a raw_text template for the category+source; instantiate with asset details and vocabulary
   f. Set `observed_severity` = ground_truth_severity, then flip 15% of cases by ±1–2
   g. 10% become `false_positive` — raw_text reads real, ground_truth_category = false_positive
   h. 5% become near-duplicates of a recent notification on the same asset

2. **Timestamp generation:**
   - Historical (8,000 over months 1–22): Poisson arrivals with weekday/hour seasonality
   - Spike at each plant state transition (startup/shutdown)
   - Open backlog (2,000): concentrated in recent 90 days, with a long tail

3. **Status assignment:**
   - Historical: `converted_to_wo` (~70%), `rejected_duplicate` (~5%), `rejected_false_positive` (~10%), `in_review` (~2%), remaining `open`
   - Open backlog: all `open` or `in_review`

4. **Backlog age distribution (key realism constraint):**
   - Many recent (60% raised within last 30 days)
   - Long tail: 20% are 30–60 days old, 15% are 60–90 days old, 5% are >90 days
   - T3/T4 criticals disproportionately in the older tail — this is the "criticals aging" story

5. **Planner assignment:** historical notifications have assigned_planner_id; open backlog has ~30% assigned (in_review)

**Raw text templates:** hard-coded in `common.py`, 3–5 per category, across terse/verbose/misleading styles.

**Category × asset class mapping:**

| Asset class | Probable ground_truth_categories |
|---|---|
| centrifugal_pump, reciprocating_pump | seal_failure, bearing_wear, coupling_misalignment, vibration_abnormal, leak |
| compressor | vibration_abnormal, bearing_wear, temperature_high, seal_failure |
| heat_exchanger | process_fouling, leak, corrosion, temperature_high |
| control_valve, isolation_valve | leak, control_drift, instrument_failure |
| instrument | instrument_failure, control_drift |
| fired_heater | temperature_high, leak, corrosion |
| column, vessel | corrosion, leak, process_fouling, pressure_abnormal |
| electrical_motor | electrical_fault, bearing_wear, vibration_abnormal |
| transformer | electrical_fault |
| piping | leak, corrosion, pressure_abnormal |
| cooling_tower | process_fouling, flow_abnormal, corrosion |
| flare | leak, temperature_high |

### 5.8 Work Orders (`work_orders.py`)

Target: **~8,500** (8,000 closed historical + 500 in-flight).

**Generation:**
- One WO per `converted_to_wo` notification (direct FK)
- Additional ~500 WOs from `preventive` / `regulatory` sources (not tied to notifications — notification_id nullable for these)
- In-flight: ~500 WOs with status `planned`, `scheduled`, or `in_progress`

**Planning duration** (log-normal): mean=30 min, σ=0.6 on log scale. Adjusted by:
- criticality T1/T2: ×1.4
- false positive rejects: 5–10 min flat
- planner experience: senior planners take longer per notification

**Work type distribution:** corrective 55%, preventive 30%, predictive 10%, regulatory 5%.

**Required parts:** 1–4 parts per WO, sampled from compatible parts for the asset class.

**Required permits:** based on work type and asset class (hot work for fired heater, LOTO for electrical, etc.).

**Closure notes:** templated free text, populated only for `completed` WOs.

**Avoided downtime hours:** populated for preventive/predictive WOs; 0.5–48 hours, skewed by criticality.

### 5.9 Failure Events (`failures.py`)

Target: **~1,200**.

**Derived from:** completed corrective work orders where ground_truth_category ≠ false_positive and ≠ duplicate.

**Downtime cost by criticality tier:**
| Tier | $/hour range |
|---|---|
| T1 | $200,000–$500,000 |
| T2 | $50,000–$200,000 |
| T3 | $10,000–$50,000 |
| T4 | $1,000–$10,000 |
| T5 | $0–$1,000 |

**Downtime hours:** log-normal, mean=8 h, p95=36 h. T1 assets skew longer (harder to restart).

---

## 6. Vocabularies (in `common.py`)

### Raw text templates (sample — full list in code)

**seal_failure:**
- Terse: `"{asset_name} seal weep noted on routine walkdown."`
- Verbose: `"Operator on {shift} shift reports fluid weeping from the mechanical seal on {asset_name}. Started approximately {hours} hours ago. Rate appears to be increasing."`
- Misleading: `"Puddle forming under {asset_name}, possible drain line issue."`

**vibration_abnormal:**
- Terse: `"High vibe alarm on {asset_name}, {value} mm/s."`
- Verbose: `"Abnormal vibration noted on {asset_name} during rounds. Overall vibration elevated to {value} mm/s vs normal baseline of {baseline} mm/s. Sounds like it could be cavitation or bearing issue."`
- Misleading: `"Unusual noise from {asset_name} area — may be nearby equipment."`

*(... full vocabulary hard-coded in generators/common.py)*

### Plant vocabulary (asset names by class and unit)
Examples:
- centrifugal_pump + Crude_Distillation → ["Crude Charge Pump A", "Crude Charge Pump B", "Overhead Reflux Pump", ...]
- heat_exchanger + Hydrotreating → ["Feed/Effluent Exchanger", "Stripper Overhead Condenser", ...]

---

## 7. Outputs

| File | Description |
|---|---|
| `output/assets.csv` + `assets_schema.md` | 500 assets |
| `output/operations_calendar.csv` + `_schema.md` | 730-day calendar |
| `output/spare_parts.csv` + `_schema.md` | 5,000 SKUs |
| `output/crews.csv` + `_schema.md` | 30 crews |
| `output/permits.csv` + `_schema.md` | 10 permit types |
| `output/planners.csv` + `_schema.md` | 6 planners |
| `output/notifications.csv` + `_schema.md` | ~12,000 notifications |
| `output/work_orders.csv` + `_schema.md` | ~8,500 work orders |
| `output/failure_events.csv` + `_schema.md` | ~1,200 failure events |
| `output/SUMMARY.md` | Row counts, key distributions, sample notifications |

---

## 8. Validation Pass

After all generators run, a validation pass checks:

1. All `asset_id` FKs in notifications/work_orders resolve to assets.csv
2. All `planner_id` FKs resolve to planners.csv
3. All `notification_id` FKs in work_orders resolve to notifications.csv
4. All `part_id` values in required_parts_json resolve to spare_parts.csv
5. All `permit_code` values in required_permits resolve to permits.csv
6. All `wo_id` FKs in failure_events resolve to work_orders.csv
7. No `converted_to_wo_id` in notifications without a matching work_order
8. Planning duration is populated wherever status is converted/rejected
9. ground_truth fields are non-null for all rows

Fails the run with a clear error message if any check fails.

---

## 9. Test Suite (`tests/test_data_quality.py`)

10 spot checks using `pytest`:

1. `test_asset_row_count` — assets between 480 and 520
2. `test_criticality_distribution` — T1 between 3–7%, T2 between 12–18%
3. `test_notification_row_count` — total notifications between 11,000 and 13,000
4. `test_open_backlog_count` — open notifications between 1,800 and 2,200
5. `test_no_orphan_asset_fk` — all notification asset_ids in asset table
6. `test_no_orphan_wo_fk` — all WO notification_ids in notification table
7. `test_planning_time_distribution` — median between 18–26 min, p95 between 60–90 min
8. `test_raw_text_non_empty` — no empty raw_text values
9. `test_ground_truth_populated` — no nulls in ground_truth_severity or ground_truth_category
10. `test_backlog_age_tail` — at least 100 open notifications older than 30 days

---

## 10. Performance

All generators use vectorised numpy/pandas operations. No Python loops over rows. Target: **< 60 seconds** on a MacBook Pro M-series.

The notification raw_text instantiation (template + vocabulary substitution) is the only potentially slow step — vectorised using `numpy.vectorize` over a dictionary of templates.

---

## 11. Key Realism Numbers (Workshop Story)

The dataset must tell this story:

- **Weekly inflow:** ~1,900 notifications/week (historical average)
- **Weekly planner capacity:** ~1,260 notifications/week (6 planners × ~35/day × 6 working days)
- **Resulting backlog growth:** ~640/week
- **Open backlog at run date:** ~2,000
- **Oldest open notification:** 60–90 days
- **T1 criticals in open backlog:** 10–20 (should have been processed within 24h)
- **Unplanned downtime cost (rolling 12mo):** $25–35M
- **Avoidable downtime (if timely processing):** $10–14M

These numbers are validated in `SUMMARY.md` after generation.

---

## 12. Implementation Sequence

```
Phase 1: Scaffold
  - pyproject.toml / requirements.txt
  - generators/__init__.py
  - generators/common.py (vocabularies, RNG helpers)
  - generate_data.py (CLI entry point, orchestration)

Phase 2: Independent entities (can be parallelised)
  - generators/assets.py
  - generators/operations_calendar.py
  - generators/parts.py
  - generators/crews.py
  - generators/permits.py
  - generators/planners.py

Phase 3: Dependent entities
  - generators/notifications.py
  - generators/work_orders.py
  - generators/failures.py

Phase 4: Output & validation
  - Schema .md files
  - output/SUMMARY.md generation
  - FK validation pass

Phase 5: Tests
  - tests/test_data_quality.py

Phase 6: Final run and README
  - Verify seed 42 run completes < 60s
  - README.md with install/run instructions
```
