"""Generate the production / output dataset (Phase 2).

Daily barrel production and product yields, tied to the operations calendar's
production rate. Gives the workshop a direct line from maintenance decisions
to business impact (barrels not produced = revenue lost).
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def generate_production(
    rng: np.random.Generator,
    calendar_df: pd.DataFrame,
    run_date: date,
    cfg: dict | None = None,
) -> pd.DataFrame:
    """Return a daily production/yield DataFrame aligned to the calendar."""
    cfg = cfg or {}
    design_bpd: float = float(cfg.get("design_capacity_bpd", 100_000))
    yields: dict[str, float] = cfg.get("product_yields", {
        "gasoline": 0.46, "diesel": 0.28, "jet_fuel": 0.10,
        "lpg": 0.05, "fuel_oil": 0.06, "other": 0.05,
    })

    cal = calendar_df.copy()
    cal["date"] = pd.to_datetime(cal["date"])
    n = len(cal)

    rate_pct = cal["production_rate_pct"].to_numpy(dtype=float)
    state = cal["plant_state"].to_numpy(dtype=str)
    # Small day-to-day processing noise on top of the calendar rate
    noise = rng.normal(0, 1.5, size=n)
    effective_rate = np.clip(rate_pct + noise, 0, 100)
    # Hard-zero production on turnaround / shutdown days (calendar rate is 0,
    # but processing noise could otherwise leak a few barrels through).
    off_days = np.isin(state, ["turnaround", "shutdown"])
    effective_rate[off_days] = 0.0
    barrels = design_bpd * effective_rate / 100.0
    barrels = np.maximum(barrels, 0.0)

    # On-spec quality: dips during derate/startup/turnaround
    on_spec = np.full(n, 99.0)
    on_spec[state == "derate"] = 96.0
    on_spec[state == "startup"] = 92.0
    on_spec[state == "turnaround"] = 0.0
    on_spec[state == "shutdown"] = 0.0
    on_spec += rng.normal(0, 0.8, size=n)
    on_spec = np.clip(on_spec, 0, 100)

    # Allocate yields — normalize per day so they sum to barrels produced
    yield_keys = ["gasoline", "diesel", "jet_fuel", "lpg", "fuel_oil", "other"]
    base_y = np.array([yields.get(k, 0.0) for k in yield_keys])
    base_y = base_y / base_y.sum()  # normalize
    # Slight day-to-day yield variation
    jitter = rng.normal(1.0, 0.01, size=(n, len(yield_keys)))
    ymat = base_y * jitter
    ymat = ymat / ymat.sum(axis=1, keepdims=True)
    split = ymat * barrels[:, None]

    notes = [""] * n
    for i, st in enumerate(state):
        if st == "turnaround":
            notes[i] = "turnaround — no production"
        elif st == "shutdown":
            notes[i] = "shutdown — no production"
        elif st == "derate":
            notes[i] = "derated operation"
        elif st == "startup":
            notes[i] = "startup ramp"

    df = pd.DataFrame({
        "date": cal["date"].dt.strftime("%Y-%m-%d"),
        "barrels_produced": np.round(barrels, 0),
        "gasoline_bbl": np.round(split[:, 0], 0),
        "diesel_bbl": np.round(split[:, 1], 0),
        "jet_fuel_bbl": np.round(split[:, 2], 0),
        "lpg_bbl": np.round(split[:, 3], 0),
        "fuel_oil_bbl": np.round(split[:, 4], 0),
        "other_bbl": np.round(split[:, 5], 0),
        "on_spec_pct": np.round(on_spec, 1),
        "notes": notes,
    })

    _write_schema()
    return df


def _write_schema() -> None:
    out = Path(__file__).resolve().parent.parent / "output"
    out.mkdir(parents=True, exist_ok=True)
    (out / "production_schema.md").write_text("""# production_schema.md

Daily plant production and product yields.

| Column | Type | Description |
|---|---|---|
| date | date | Calendar date (PK) |
| barrels_produced | float | Total crude throughput (bbl) |
| gasoline_bbl | float | Gasoline yield (bbl) |
| diesel_bbl | float | Diesel yield (bbl) |
| jet_fuel_bbl | float | Jet fuel yield (bbl) |
| lpg_bbl | float | LPG yield (bbl) |
| fuel_oil_bbl | float | Fuel oil yield (bbl) |
| other_bbl | float | Other products yield (bbl) |
| on_spec_pct | float | Percentage of output meeting product spec |
| notes | string | Operational note (turnaround, derate, …) |

## Usage

Multiply lost barrels by a refining margin (e.g. $12/bbl) to convert
downtime into revenue impact — the business case for maintenance throughput.
""")
