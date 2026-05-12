# Crestmount Refinery — Synthetic Data Generator

Generates the canonical dataset for the Crestmount Refinery agent-building workshop.
A single `--seed` argument controls all randomness: same seed → byte-identical CSVs.

---

## Prerequisites

Python 3.11+ required.

```bash
cd data_generator
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # installs numpy, pandas, faker, pytest
```

---

## Generate the canonical workshop dataset

```bash
python generate_data.py --seed 42 --output-dir ./output
```

Expected output:

```
Crestmount Refinery data generator — seed=42, run_date=<today>
  Generating assets …
  Generating operations calendar …
  Generating spare parts …
  Generating crews …
  Generating permits …
  Generating planners …
  Generating notifications …
  Generating work orders …
  Generating failure events …
  Validating foreign keys …
[VALIDATION] All foreign key checks passed.
  Writing SUMMARY.md …

Done in ~2–3s

Output: output/SUMMARY.md

On the current snapshot date …
```

The final paragraph is what the workshop facilitator reads to confirm the dataset tells the right story.

---

## Options

| Flag | Default | Description |
|---|---|---|
| `--seed` | `42` | Master RNG seed. Controls all randomness. |
| `--output-dir` | `./output` | Directory where CSVs and schema files land. |

---

## Output files

All files are written to `--output-dir`. CSVs are excluded from the git repository
(see `.gitignore`). Schema files (`*_schema.md`) **are** committed.

| File | Rows | Description |
|---|---|---|
| `assets.csv` | ~500 | Plant assets with class, location, criticality, MTBF |
| `operations_calendar.csv` | 730 | Daily plant state for 24 months |
| `spare_parts.csv` | ~5,000 | Spare parts catalogue with lead times and stock |
| `crews.csv` | ~30 | Maintenance crews with skills and shift |
| `permits.csv` | 10 | Permit types with prerequisites and lead times |
| `planners.csv` | 6 | Planner roster with throughput stats |
| `notifications.csv` | ~12,000 | Maintenance notifications (historical + open backlog) |
| `work_orders.csv` | ~8,500 | Work orders (historical closed + in-flight) |
| `failure_events.csv` | ~1,200 | Failure events with downtime and cost |
| `SUMMARY.md` | — | Key metrics for facilitator sanity-check |

---

## Regenerating

Any change to generator code or vocabulary may shift the output. To re-generate:

```bash
python generate_data.py --seed 42 --output-dir ./output
```

To validate the generated files against quality targets:

```bash
pytest tests/test_data_quality.py -v
```

All 14 tests should pass.

---

## Architecture

```
data_generator/
├── PLAN.md                    # design decisions and generation order
├── generate_data.py           # CLI entry point and orchestration pipeline
├── generators/
│   ├── common.py              # RNG helpers, vocabularies, shared lookups
│   ├── assets.py              # independent — no upstream deps
│   ├── operations_calendar.py # independent
│   ├── parts.py               # independent
│   ├── crews.py               # independent
│   ├── permits.py             # independent (fixed set)
│   ├── planners.py            # independent (fixed roster)
│   ├── notifications.py       # depends on assets, planners, calendar
│   ├── work_orders.py         # depends on notifications, assets, planners, parts, permits
│   └── failures.py            # derived from work_orders + notifications
├── tests/
│   └── test_data_quality.py   # 14 spot-checks
└── output/                    # generated files land here (CSVs gitignored)
    ├── .gitkeep
    └── *_schema.md            # column descriptions (committed)
```

**Generation order:**
assets → calendar → parts → crews → permits → planners
→ notifications → work_orders → failures (derived)

**Reproducibility:** A `numpy.random.default_rng(seed)` master RNG spawns child
RNGs via `SeedSequence` for each generator. Same seed → byte-identical output.

---

## Key design choices

- **Ground-truth first.** `ground_truth_severity` and `ground_truth_category` are
  generated first; observed fields and `raw_text` are derived with controlled noise
  (15% severity mismatch, 10% false positives, 5% duplicates).
- **Bottleneck is structural.** Planner capacity ≈ 1,260 notifications/week; the open
  backlog has 1,800–2,000 items with T1 criticals visibly aging.
- **No ML dependencies.** Pure numpy + pandas + faker. Run completes in < 5 seconds.
- **FK validation.** The run fails hard if any foreign key dangles.
