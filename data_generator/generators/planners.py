"""Generate the planners table (fixed set of 6)."""
from __future__ import annotations

import pandas as pd

# Fixed roster — matches PLAN.md targets
# avg_notifications_per_day tuned so that:
#   sum × 5 days/week = ~1,260 notifications/week
#   vs inflow ~1,900/week → visible bottleneck
_PLANNER_DATA = [
    ("PLN-A", "Planner-A", 22, "rotating_equipment",  36, "day"),
    ("PLN-B", "Planner-B", 15, "static_equipment",    40, "day"),
    ("PLN-C", "Planner-C",  8, "instrumentation",     44, "day"),
    ("PLN-D", "Planner-D",  5, "electrical",          48, "night"),
    ("PLN-E", "Planner-E", 12, "generalist",          42, "day"),
    ("PLN-F", "Planner-F",  3, "generalist",          42, "night"),
]
# Total: 252 notifications/day × 5 = 1,260/week


def generate_planners() -> pd.DataFrame:
    rows = []
    for planner_id, name, exp, spec, avg, shift in _PLANNER_DATA:
        rows.append({
            "planner_id":               planner_id,
            "planner_name":             name,
            "experience_years":         exp,
            "specialization":           spec,
            "avg_notifications_per_day": avg,
            "shift":                    shift,
        })
    df = pd.DataFrame(rows)
    _write_schema()
    return df


def _write_schema() -> None:
    from pathlib import Path
    schema = """# planners_schema.md

| Column | Type | Description |
|---|---|---|
| planner_id | string | Primary key. Format: PLN-X |
| planner_name | string | Anonymised name (Planner-A through Planner-F) |
| experience_years | int | Years of maintenance planning experience |
| specialization | string | rotating_equipment \\| static_equipment \\| instrumentation \\| electrical \\| generalist |
| avg_notifications_per_day | int | Historical average notifications processed per day |
| shift | string | day \\| night |

**Capacity note:** combined team processes ~252 notifications/day × 5 working days = **1,260/week**.
Weekly inflow is ~1,900. The deficit (~640/week) is the structural backlog growth visible in notifications.csv.
"""
    out = Path(__file__).parent.parent / "output" / "planners_schema.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(schema)
