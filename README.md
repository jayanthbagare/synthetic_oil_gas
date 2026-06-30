# Crestmount Refinery — Agent Workshop

> A hands-on workshop on building agents that move throughput at a real constraint.

---

## The scene

You are a small team of engineers and product managers working with **Crestmount Refinery**, a fictional mid-sized refinery in West Texas that processes ~100,000 barrels per day at design capacity.

The plant's maintenance organisation is in trouble. Notifications about asset problems — from operators on the floor, from sensors, from inspection rounds — arrive faster than the planning team can process them. The backlog is growing. Critical work is ageing in the queue. Unplanned downtime events are running at 1.5× target. The plant manager has asked you the team to propose an intervention before the next turnaround.

See this as a system problem. The constraint is not the crews. It is not the spare parts. It is not the schedule. **The constraint is the planner** — a small team of six performing cognitively-intensive judgment work that paces the entire pipeline.

Today, you build the intervention.

```
~1,900 notifications / week
                          inflow
                            │
                            ▼
        ┌─────────────────────────┐
        │   Operators             │
        │   Sensors               │
        │   Inspection rounds     │
        │   Predictive models     │
        └────────────┬────────────┘
                     │
                     ▼
        ┌─────────────────────────┐
        │        QUEUE            │     backlog: ~2,000 open
        │  (open notifications)   │     growing: ~600 / week
        │                         │     oldest:  60–90 days
        └────────────┬────────────┘
                     │
                     ▼
        ╔═════════════════════════╗
        ║       PLANNER           ║     ★ THE CONSTRAINT
        ║       (6 people)        ║
        ║                         ║     capacity: ~1,260 / week
        ║   triage · classify ·   ║     avg time: ~30 min / item
        ║   scope · parts · crew  ║
        ║   · permits · schedule  ║
        ╚════════════╤════════════╝
                     │
                     ▼
        ┌─────────────────────────┐
        │       Scheduler         │
        │  (fit into ops window)  │
        └────────────┬────────────┘
                     │
                     ▼
        ┌─────────────────────────┐
        │         Crew            │
        │  (execute with parts    │
        │   and permits)          │
        └────────────┬────────────┘
                     │
                     ▼
        ┌─────────────────────────┐
        │        Closure          │
        │  (record + feed back    │
        │   to asset history)     │
        └─────────────────────────┘

       ────►  throughput is limited at the planner  ◄────
```

---

## Your task

Build an agent — or a small system of agents — that demonstrably improves throughput at the planner station.

You will defend your work using the throughput equation taught in yesterday's session:

> **Δ(T − OE) − ΔI/payback > 0** ?

In plain terms: the additional value your agent unlocks at the constraint must meaningfully exceed the cost of running it, plus the amortised cost of building it. Numbers are required. Hand-waving is not.

---

## What's in this data pack

All files are CSVs in the `data_generator/output` directory. Schemas are in `data_generator/output/*_schema.md`.
A queryable SQLite database (`crestmount.db`) and a Streamlit dashboard are also provided — see `data_generator/README.md`.

### Core entities

| File | What it is | Why you care |
|---|---|---|
| `assets.csv` | ~500 plant assets with class, location, criticality, MTBF, replacement cost | The agent will reason about asset-specific failure patterns |
| `operations_calendar.csv` | 730 days of plant state (running / derate / turnaround / shutdown) and maintenance window hours | Scheduling agents need this; even classifiers benefit from knowing when work *can* happen |
| `spare_parts.csv` | ~5,000 part SKUs with categories, suppliers, lead times, inventory | Planning a work order means knowing what parts are needed and whether they're available |
| `crews.csv` | ~30 maintenance crews with skills, sizes, shifts | Required-skills matching is part of planning |
| `permits.csv` | ~10 permit types with prerequisites and lead times | Many WOs need permits; this is the "subordinate" work that wraps the constraint |
| `planners.csv` | The 6 planners with specialisation and throughput stats | Useful for routing logic |
| `notifications.csv` | **~12,000 notifications** (10,000 historical + 2,000 current open backlog) | **This is your main input.** Free-text descriptions, observed severity, source, ground-truth columns for evaluation |
| `work_orders.csv` | ~8,500 work orders, mostly closed | Use as training-by-example for what a "good" WO looks like, and to measure historical throughput |
| `failure_events.csv` | ~1,200 actual failures with root causes and downtime cost | Use to calibrate avoided-downtime calculations |

### Domain datasets

| File | What it is | Why you care |
|---|---|---|
| `sensors.csv` | ~940 sensors (vibration, temperature, pressure, flow) on rotating/static equipment | Live condition data — the input your predictive-maintenance agent reads |
| `sensor_readings.csv` | ~680,000 hourly readings with **pre-failure anomaly ramps** | The learnable signal: anomalies escalate in the 24h before each failure event |
| `asset_connections.csv` | ~1,500 directed edges in the P&ID process-flow graph | Failure-cascade analysis — a failing feed pump degrades everything downstream |
| `weather.csv` | 730 days of West Texas weather (storms, freezes, dust) | Drives equipment stress (heat→transformers, freeze→piping) and permit feasibility (storms→no work at height) |
| `production.csv` | 730 days of barrel output and product yields (gasoline, diesel, jet fuel, …) | Converts maintenance decisions into business impact: lost barrels × refining margin = revenue at risk |

### Two columns you can use only for evaluation

`notifications.csv` contains two columns marked **evaluation-only**:

- `ground_truth_severity` — the actual severity, often different from `observed_severity`
- `ground_truth_category` — the actual root-cause category, often different from what the operator named in `raw_text`

**Do not feed these to your agent.** Use them to score your agent's classifications and root-cause hypotheses. If you train on them, your numbers will lie and your final presentation will not survive questioning.

---

## The current state (your baseline)

Run this once when you start the workshop to confirm the baseline. It should reproduce these numbers (within ~5%):

| Metric | Value |
|---|---|
| Open notifications in backlog | ~2,000 |
| Oldest open notification | 60–90 days |
| Open tier-1 critical notifications | 10–20 |
| Average planning time per notification | ~30 min |
| Planner team weekly capacity | ~1,260 notifications |
| Weekly notification inflow | ~1,900 |
| Resulting weekly backlog growth | ~600 notifications |
| Unplanned downtime cost (rolling 12mo) | ~$25–35M |
| Estimated downtime that could have been avoided with timely processing | ~$10–14M |

**The bottleneck is visible.** Capacity is 1,260/week, inflow is 1,900/week. The system loses ~600 notifications per week to ageing in the queue. Some of those ageing notifications are exactly the criticals that, left unaddressed, become the unplanned downtime events that cost real money.

This is the gap your agent should close.

---

## Suggested agent shapes

You may build any of these, combine them, or invent something new. They are ordered by approximate complexity, not by quality.

### 1. Triage agent (simplest)

Reads `notification.raw_text` + a little asset context. Outputs a structured triage: predicted severity (1–5), predicted category, suggested fast-lane / standard-lane / reject. Routes high-confidence rejects (false positives, duplicates) without planner time.

**Why this works at the constraint:** the planner currently spends 5–10 minutes per notification just deciding whether it's real. Removing that fraction is a clean, measurable throughput win.

**Subsystems used:** Instructions (criticality rubric, category definitions), Tools (asset lookup), Feedback (compare to ground_truth columns post-hoc).

### 2. Context-gathering agent

For each notification, pulls the relevant context — asset history, recent failures on similar assets, supplier lead times for likely parts, plant state on the planned execution date — into a 30-second-readable brief. The planner reads the brief and decides; the agent doesn't make the call.

**Why this works:** the planner's biggest time sink is *gathering*, not *deciding*. A brief that takes the planner from cold-start to informed in 30 seconds compresses each notification from 30 min to ~10 min.

**Subsystems used:** Tools (multi-source retrieval), State (the brief itself), Instructions (what to include, what to omit).

### 3. Planner-assistant agent (full pipeline)

End-to-end: takes a notification, classifies it, identifies probable root cause, suggests required parts (with availability check), required crew skills, required permits, drafts the work-order text with reasoning trail. Routes to the planner for review and release. The planner edits the draft; the agent learns from the edits.

**Why this works:** the highest-leverage shape if you can pull it off. The planner moves from author to editor. Time per notification drops to 5–10 min.

**Subsystems used:** all five.

### 4. Schedule-fit optimiser

Given a stream of drafted work orders and the `operations_calendar`, optimises *when* each WO should execute to maximise throughput-weighted criticality completion under operations constraints. This is more "operations research with LLM in the loop" than "agent" — and that distinction is itself a useful lesson.

**Why this works:** the constraint is the planner, but scheduling decisions feed back into the planner's queue. A good scheduler reduces re-work and re-planning. But this is downstream of the bottleneck — be honest in your throughput math.

### 5. Anomaly correlator

Identifies clusters of notifications that may all be symptoms of one underlying issue (cascade failures, related instrument drift, a single root cause expressing in multiple ways). Consolidates them into a single work order with multiple sub-tasks.

**Why this works:** the duplicate-detection win is real but small (~5% of the backlog). The cascade-detection win is much larger and shows up in avoided-downtime calculations.

---

## How you'll be evaluated

You'll present for **10 minutes** to a panel of senior architects. The evaluation is **not** about model sophistication or code quality. It is about whether you can defend the throughput math.

You will be asked to make three claims and defend each with evidence from the data:

### Claim 1 — Where the constraint is

State the constraint. Show one piece of data from the pack that confirms it (a backlog-age chart, a planner-capacity-vs-inflow comparison, an aging-criticals breakdown).

### Claim 2 — What your agent does (and does not do)

State what your agent does at the constraint. State explicitly what stays human. Show, on a sample of 5–10 notifications, what the agent produces. Identify failure modes you discovered.

### Claim 3 — The math

Defend the throughput equation with numbers and visible assumptions:

- **ΔT (annual)** — additional value the constraint unlocks. Break it down: avoided downtime (use `failure_events.csv` and your agent's effect on which notifications get processed in time), recovered discounts, faster restoration. Cite the data.
- **ΔOE (annual)** — agent operating cost. Include: model API costs (estimate from your prompt sizes and notification volume), monitoring/eval/retraining (~10% of build cost annually), human supervision time (be honest — a planner reviewing each agent output still takes minutes).
- **ΔI (one-time)** — build cost. For this workshop, estimate what it would cost to productionise what you built today: engineering hours × loaded rate, plus integration, plus security review.
- **Payback period** — months. Defend the number.

**A team that says "ΔT = $10M" without showing how is failing the exercise.** A team that says "ΔT is between $4M and $7M, here's the lower-bound calculation, here are the assumptions we'd have to validate in pilot" is doing the exercise correctly.

### Bonus credit

- **Honest negatives.** If your agent makes some notifications *worse* (over-confident rejections, missed criticals), surface them. Show how you'd mitigate.
- **Where it doesn't apply.** Name the bottlenecks in this plant that your agent does **not** address. The throughput equation cuts both ways: an agent that improves the wrong station can degrade overall throughput.
- **Voltage.** If you can argue from the data that some notifications carry higher business intent (e.g., near a tier-1 asset before a turnaround) and your agent routes accordingly, you've internalised yesterday's framework.

---

## Constraints and rules

- **Time:** 3 hours of build, 30 min to prepare your presentation, 10 min to present.
- **Tech:** any model, any framework. Anthropic, OpenAI, open-source — use what serves the team. Cost will count in ΔOE — favour the model that wins on dollars per outcome, not on token count.
- **Data:** you may not pull external data sources. Everything you need is in this pack.
- **Code:** working code is encouraged but not required. A clear architecture diagram + traces of agent behaviour on 5–10 notifications + the throughput math is enough.
- **Honesty:** the panel will ask hard questions. The team that says "we don't know" honestly does better than the team that bluffs.

---

## Starter agent framework & dashboard

The repo ships with a **reference agent implementation** and an **evaluation harness** so you can skip the plumbing and focus on improving the decisions. They are not the answer — they are a baseline to beat.

```bash
# Generate data + build the queryable SQLite DB
python data_generator/generate_data.py --seed 42 --output-dir ./output --build-db

# Run the reference agent pipeline + evaluation
python data_generator/run_agents.py --db ./output/crestmount.db --run-date 2026-06-30

# Launch the bottleneck dashboard
streamlit run data_generator/dashboard/app.py -- --db ./output/crestmount.db
```

What's included (see `data_generator/README.md` for full details):

- **`TriageAgent`** — scores & prioritises open notifications; predicts true severity from raw text (catches the 15% noisy `observed_severity`).
- **`ContextGatherer`** — enriches a notification with asset history, recent failures, live sensor anomalies, downstream (P&ID) impact, required parts, and weather.
- **`PlannerAssistant`** — recommends an action (`convert_to_wo` / `reject_false_positive` / `reject_duplicate` / `defer` / `escalate`) with a rationale and suggested crew/parts. Exposes an `llm_decide` hook so you can swap in your model without touching the plumbing.
- **`Evaluator`** — scores agent outputs against the ground-truth columns: severity MAE, precision@K for critical surfacing, and false-positive / duplicate F1.
- **`RefineryDB`** — a SQLite layer over all 14 tables with foreign keys and indexes, so your agent queries relational data instead of juggling DataFrames.

**Baseline numbers** (rule-based, seed 42): severity MAE ≈ 1.0 (69% within ±1), false-positive F1 ≈ 0.46, duplicate F1 ≈ 0.82. Your job is to beat these — especially the false-positive precision, where an over-confident rejection of a real failure is costly.

---

## Starting points (technical)

A minimal harness in Python is ~80 lines. Key choices to make in the first 30 minutes:

- **Which model.** A cheap fast model on every notification, or a slower better one on the hard 10%? Both are defensible. Justify in your presentation.
- **How much context per call.** Stuff everything into one prompt, or build a retrieval step that gathers per-notification context first? Affects ΔOE significantly.
- **How to evaluate yourself.** Reserve 100 notifications you don't show your agent during development. After building, run on those 100 and compare to `ground_truth_*` columns. That's your real performance number.
- **Where humans stay.** Define this **before** you build. "All tier-1 decisions stay human." "Rejections always go to planner first." Whatever your rule is, write it down.

The five-subsystem harness you saw yesterday — Instructions, Tools, State, Environment, Feedback — applies here. You will not have time to build a production harness; you will have time to gesture at one. Be explicit about what you have and what you'd build with another week.

---

## What "winning" looks like

The team that demonstrates the cleanest throughput-equation argument wins, not the team with the most sophisticated architecture. A working triage agent with a tight ROI defence beats an elegant multi-agent system that can't show numbers.

Three points to leave the panel with:

1. **Where the constraint is**, with one piece of data from the pack that confirms it.
2. **What your agent does** at the constraint — and what stays human.
3. **The math**: ΔT, ΔOE, ΔI with the assumptions visible.

We are looking for systems thinking and intellectual honesty, not engineering bravado.

---

## A final note

Crestmount Refinery is fictional, but the shape of this problem is real. Variants of it appear in every customer engagement you will run: a knowledge-intensive triage step starves the downstream pipeline; throwing automation at the wrong station makes it worse; the agent that succeeds is the one placed where the constraint actually lives.

The discipline you practise today — *find the constraint, then build at it* — is the discipline you'll bring back to your accounts on Monday.

Good luck.
