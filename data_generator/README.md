# Crestmount Refinery — Synthetic Data Generator

Generates the canonical dataset for the Crestmount Refinery agent-building workshop,
plus an agent framework, evaluation harness, and dashboard.

A single `--seed` argument controls all randomness: same seed → byte-identical CSVs.

---

## Prerequisites

Python 3.11+ required.

```bash
cd data_generator
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"            # numpy, pandas, faker, pyyaml, pytest
pip install -e ".[dashboard]"      # streamlit, plotly (optional, for the dashboard)
```

---

## Generate the canonical workshop dataset

```bash
python generate_data.py --seed 42 --output-dir ./output --build-db
```

Expected output (structured JSON logs):

```
{"msg": "Crestmount Refinery data generator starting", "seed": 42, ...}
{"msg": "Generating assets", ...}
  ...
{"msg": "Generation complete", "elapsed_s": 4.6}
[VALIDATION] All foreign key checks passed.
  SQLite DB: output/crestmount.db

Done in 4.6s
```

The `--build-db` flag also builds a queryable SQLite database (`output/crestmount.db`)
from the generated CSVs.

---

## Options

| Flag | Default | Description |
|---|---|---|
| `--seed` | `42` (from config) | Master RNG seed. Controls all randomness. |
| `--output-dir` | `./output` | Directory where CSVs and schema files land. |
| `--config` | `config/default.yaml` | YAML config file (merged over defaults). |
| `--build-db` | off | Build a SQLite DB from the generated CSVs. |
| `--no-sensors` | off | Skip the (large) sensor telemetry dataset. |

All flags override values in `config/default.yaml`.

---

## Output files

All files are written to `--output-dir`. CSVs are excluded from the git repository
(see `.gitignore`). Schema files (`*_schema.md`) **are** committed.

### Core entities (Phase 1)

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

### Domain datasets (Phase 2)

| File | Rows | Description |
|---|---|---|
| `sensors.csv` | ~940 | Sensor catalog (vibration, temperature, pressure, flow) |
| `sensor_readings.csv` | ~680,000 | Hourly telemetry with pre-failure anomaly ramps |
| `asset_connections.csv` | ~1,500 | P&ID graph — directed asset-to-asset process connections |
| `weather.csv` | 730 | West Texas daily weather (storms, freezes, dust) |
| `production.csv` | 730 | Daily barrel production and product yields |
| `SUMMARY.md` | — | Key metrics for facilitator sanity-check |
| `crestmount.db` | — | SQLite DB with all tables + FK constraints + indexes |

---

## Configuration

All tunable parameters live in [`config/default.yaml`](config/default.yaml): entity
volumes, noise rates, sensor/weather/production/agent settings, and infrastructure
paths. A custom config can be supplied with `--config path/to/custom.yaml`; it is
deep-merged over the defaults.

```python
from infra.config import load_config
cfg = load_config()
print(cfg.get("sensors.history_days"))   # dotted-key access
cfg.override(seed=99)                     # programmatic override
```

---

## The agent framework

Five agent shapes operate at the planner bottleneck. All read from the SQLite DB
so they exercise the same relational data a deployed agent would see.

```bash
# Run the full agent pipeline + evaluation harness
python run_agents.py --db ./output/crestmount.db --run-date 2026-06-30
```

This writes `output/agent_eval_report.md` with severity-prediction MAE,
precision/recall for critical-surfacing, and false-positive / duplicate F1 scores.

| Agent | What it does |
|---|---|
| `TriageAgent` | Scores & prioritises open notifications; predicts true severity from raw text |
| `ContextGatherer` | Enriches a notification with asset history, failures, sensor anomalies, downstream impact, parts, weather |
| `PlannerAssistant` | Recommends an action: convert_to_wo / reject_false_positive / reject_duplicate / defer / escalate |
| `Evaluator` | Scores agent outputs against the ground-truth columns |

```python
from infra.db import RefineryDB
from agents import TriageAgent, ContextGatherer, PlannerAssistant

db = RefineryDB("output/crestmount.db")
triage = TriageAgent(db)
for result in triage.run("2026-06-30")[:5]:
    print(result.notification_id, result.priority_score, result.sla_bucket)
```

An optional `llm_decide` hook on `PlannerAssistant` lets you swap in an LLM for the
final verdict without touching the surrounding plumbing:

```python
def my_llm(ctx: EnrichedContext) -> str:
    # call your model here, return one of the action strings
    ...

planner = PlannerAssistant(db, llm_decide=my_llm)
```

---

## Dashboard

A Streamlit dashboard visualises the bottleneck, backlog ageing, failure costs,
sensor anomalies, and the agent evaluation report.

```bash
streamlit run dashboard/app.py -- --db ./output/crestmount.db
# → http://localhost:8501
```

---

## Docker

Run the full stack (generator + agents + dashboard) containerised:

```bash
# from the repo root
docker compose up          # builds data, runs agents, launches dashboard on :8501
```

Or build just the generator image:

```bash
cd data_generator
docker build -t crestmount-generator .
docker run --rm -v "$PWD/output:/app/output" crestmount-generator
```

---

## Testing

```bash
pytest tests/ -v          # 55 tests
```

| Test file | Coverage |
|---|---|
| `tests/test_data_quality.py` | 14 spot-checks on the core entities |
| `tests/test_phase2_datasets.py` | 19 checks on weather, production, connectivity, sensors |
| `tests/test_db.py` | 7 checks on the SQLite layer + referential integrity |
| `tests/test_agents.py` | 15 checks on the triage / context / planner / evaluator agents |

Tests read from `output/` and skip gracefully if data hasn't been generated.

---

## Architecture

```
data_generator/
├── config/
│   └── default.yaml           # all tunable parameters
├── generate_data.py           # CLI entry point and orchestration pipeline
├── run_agents.py              # agent pipeline + evaluation CLI
├── infra/                     # Phase 1 — foundation
│   ├── config.py              #   YAML config loader
│   ├── logging_setup.py       #   structured JSON logging
│   └── db.py                  #   SQLite layer (RefineryDB)
├── generators/                # data generators (deterministic, seeded)
│   ├── common.py              #   RNG helpers, vocabularies, shared lookups
│   ├── assets.py              #   independent — no upstream deps
│   ├── operations_calendar.py #   independent
│   ├── parts.py               #   independent
│   ├── crews.py               #   independent
│   ├── permits.py             #   independent (fixed set)
│   ├── planners.py            #   independent (fixed roster)
│   ├── weather.py             #   independent (Phase 2)
│   ├── production.py          #   depends on calendar (Phase 2)
│   ├── asset_connectivity.py  #   depends on assets (Phase 2)
│   ├── notifications.py       #   depends on assets, planners, calendar
│   ├── work_orders.py         #   depends on notifications, assets, planners, parts, permits
│   ├── failures.py            #   derived from work_orders + notifications
│   └── sensors.py             #   depends on assets + failures (Phase 2)
├── agents/                    # Phase 3 — agent framework
│   ├── base.py                #   Agent ABC + EnrichedContext
│   ├── triage.py              #   TriageAgent
│   ├── context_gatherer.py    #   ContextGatherer
│   ├── planner_assistant.py   #   PlannerAssistant
│   └── eval.py                #   Evaluator + EvalReport
├── dashboard/
│   └── app.py                 # Phase 4 — Streamlit dashboard
├── tests/                     # 55 pytest checks
└── output/                    # generated files land here (CSVs gitignored)
    ├── .gitkeep
    ├── *_schema.md            # column descriptions (committed)
    └── crestmount.db          # SQLite DB (gitignored)
```

**Generation order:**
assets → calendar → parts → crews → permits → planners → weather → production →
connectivity → notifications → work_orders → failures → sensors (telemetry)

**Reproducibility:** A `numpy.random.default_rng(seed)` master RNG spawns child
RNGs via `SeedSequence` for each generator. Same seed → byte-identical output.

---

## Key design choices

- **Ground-truth first.** `ground_truth_severity` and `ground_truth_category` are
  generated first; observed fields and `raw_text` are derived with controlled noise
  (15% severity mismatch, 10% false positives, 5% duplicates).
- **Bottleneck is structural.** Planner capacity ≈ 1,260 notifications/week; the open
  backlog has 1,800–2,000 items with T1 criticals visibly aging.
- **Pre-failure sensor signal.** Sensor anomalies ramp up in the 24h before each
  failure event, giving predictive-maintenance agents a learnable signal.
- **Relational integrity.** The SQLite DB enforces foreign keys and is verified with
  `PRAGMA foreign_key_check` after every build.
- **No ML dependencies for generation.** Pure numpy + pandas + pyyaml. Run completes
  in < 5 seconds (excluding sensor telemetry, which is ~1s more).
- **FK validation.** The run fails hard if any foreign key dangles.

See `PLAN.md` for the original design document.
