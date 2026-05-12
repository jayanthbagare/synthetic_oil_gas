"""Generate the operations calendar (730 days ending on run_date)."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd


N_DAYS = 730


def generate_operations_calendar(rng: np.random.Generator, run_date: date) -> pd.DataFrame:
    start_date = run_date - timedelta(days=N_DAYS - 1)
    all_dates = [start_date + timedelta(days=i) for i in range(N_DAYS)]

    states = ["running"] * N_DAYS
    prod_rates = [0.0] * N_DAYS
    maint_windows = [0.0] * N_DAYS
    notes_col = [""] * N_DAYS

    def _day_index(d: date) -> int:
        return (d - start_date).days

    # -- One full turnaround (14 days), placed 8–18 months ago -----------
    ta_offset_months = rng.integers(8, 19)
    ta_start_day = N_DAYS - int(ta_offset_months * 30.5) - 14
    ta_start_day = max(3, min(ta_start_day, N_DAYS - 30))  # bounds safety

    # Shutdown (2 days before turnaround)
    for d in range(ta_start_day - 2, ta_start_day):
        if 0 <= d < N_DAYS:
            states[d] = "shutdown"

    # Turnaround (14 days)
    for d in range(ta_start_day, ta_start_day + 14):
        if 0 <= d < N_DAYS:
            states[d] = "turnaround"
            notes_col[d] = f"scheduled turnaround day {d - ta_start_day + 1} of 14"

    # Startup (3 days after turnaround)
    for d in range(ta_start_day + 14, ta_start_day + 17):
        if 0 <= d < N_DAYS:
            states[d] = "startup"

    # -- Two derate periods (~7 days each) --------------------------------
    for _ in range(2):
        de_start = int(rng.integers(30, N_DAYS - 60))
        # Don't overlap turnaround window
        if abs(de_start - ta_start_day) < 25:
            de_start = (de_start + 60) % (N_DAYS - 10)
        for d in range(de_start, min(de_start + 7, N_DAYS)):
            if states[d] == "running":
                states[d] = "derate"

    # -- Sporadic single-day derates (~5 scattered) -----------------------
    for _ in range(5):
        d = int(rng.integers(0, N_DAYS))
        if states[d] == "running":
            states[d] = "derate"

    # -- Fill production rates and maintenance windows --------------------
    for i, state in enumerate(states):
        if state == "running":
            prod_rates[i] = round(float(rng.uniform(85, 100)), 1)
            maint_windows[i] = round(float(rng.uniform(2, 5)), 1)
        elif state == "derate":
            prod_rates[i] = round(float(rng.uniform(50, 80)), 1)
            maint_windows[i] = round(float(rng.uniform(6, 10)), 1)
        elif state == "turnaround":
            prod_rates[i] = 0.0
            maint_windows[i] = round(float(rng.uniform(20, 24)), 1)
        elif state == "shutdown":
            prod_rates[i] = 0.0
            maint_windows[i] = 0.0
        elif state == "startup":
            prod_rates[i] = round(float(rng.uniform(20, 60)), 1)
            maint_windows[i] = round(float(rng.uniform(1, 4)), 1)

    df = pd.DataFrame({
        "date":                    [str(d) for d in all_dates],
        "plant_state":             states,
        "production_rate_pct":     prod_rates,
        "maintenance_window_hours": maint_windows,
        "notes":                   notes_col,
    })

    _write_schema()
    return df


def _write_schema() -> None:
    from pathlib import Path
    schema = """# operations_calendar_schema.md

| Column | Type | Description |
|---|---|---|
| date | date | Calendar date |
| plant_state | string | running \\| derate \\| turnaround \\| startup \\| shutdown |
| production_rate_pct | float | Plant production rate as % of design capacity (0–100) |
| maintenance_window_hours | float | Hours of maintenance work the plant can absorb that day |
| notes | string | Optional note (e.g., "scheduled turnaround day 3 of 14") |
"""
    out = Path(__file__).parent.parent / "output" / "operations_calendar_schema.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(schema)
