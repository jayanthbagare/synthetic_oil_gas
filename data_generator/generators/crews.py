"""Generate the maintenance crews (~30 crews)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common import CREW_SKILL_PROFILES, SKILL_CODES

N_CREWS = 30
SHIFTS = ["day", "night", "rotation"]


def generate_crews(rng: np.random.Generator) -> pd.DataFrame:
    crew_ids: list[str] = []
    crew_names: list[str] = []
    skill_codes_col: list[str] = []
    sizes: list[int] = []
    shifts: list[str] = []
    avail_hours: list[float] = []

    shift_dist = ["day"] * 10 + ["night"] * 10 + ["rotation"] * 10

    for i in range(N_CREWS):
        crew_ids.append(f"CRW-{i+1:03d}")
        crew_names.append(f"Crew-{i+1:02d}")

        profile = CREW_SKILL_PROFILES[i % len(CREW_SKILL_PROFILES)]
        # Occasionally add an extra skill
        if rng.random() < 0.3:
            extra = SKILL_CODES[rng.integers(0, len(SKILL_CODES))]
            profile = list(dict.fromkeys(profile + [extra]))  # deduplicate, preserve order
        skill_codes_col.append(";".join(profile))

        size = int(rng.integers(3, 9))  # 3–8 inclusive
        sizes.append(size)

        shift = shift_dist[i]
        shifts.append(shift)

        # Available hours/week: size × 40 × 0.85 availability factor
        avail_hours.append(round(size * 40 * 0.85, 1))

    df = pd.DataFrame({
        "crew_id":                crew_ids,
        "crew_name":              crew_names,
        "skill_codes":            skill_codes_col,
        "size":                   sizes,
        "shift":                  shifts,
        "available_hours_per_week": avail_hours,
    })

    _write_schema()
    return df


def _write_schema() -> None:
    from pathlib import Path
    schema = """# crews_schema.md

| Column | Type | Description |
|---|---|---|
| crew_id | string | Primary key. Format: CRW-NNN |
| crew_name | string | Human-readable crew name |
| skill_codes | string | Semicolon-separated skill codes |
| size | int | Number of people in the crew |
| shift | string | day \\| night \\| rotation |
| available_hours_per_week | float | Effective available work hours per week (size × 40 × 0.85) |
"""
    out = Path(__file__).parent.parent / "output" / "crews_schema.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(schema)
