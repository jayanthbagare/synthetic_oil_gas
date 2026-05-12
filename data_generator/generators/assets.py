"""Generate the assets table (~500 plant assets)."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .common import (
    ASSET_CLASSES,
    ASSET_CLASS_WEIGHTS,
    ASSET_NAME_SUFFIXES,
    ASSET_NAME_TEMPLATES,
    CRITICALITY_COST_MULTIPLIER,
    CRITICALITY_MTBF_MULTIPLIER,
    LOCATION_UNITS,
    MTBF_RANGES,
    REPLACEMENT_COST_RANGES,
)

N_ASSETS = 500

CRITICALITY_DIST = [0.05, 0.15, 0.25, 0.30, 0.25]  # T1–T5


def generate_assets(rng: np.random.Generator, run_date: date) -> pd.DataFrame:
    n = N_ASSETS

    # Asset classes — weighted sample
    weights = [ASSET_CLASS_WEIGHTS[c] for c in ASSET_CLASSES]
    total_w = sum(weights)
    probs = [w / total_w for w in weights]
    asset_classes = rng.choice(ASSET_CLASSES, size=n, p=probs)

    # Location units — uniform
    location_units = rng.choice(LOCATION_UNITS, size=n)

    # Criticality tiers
    criticality_tiers = rng.choice([1, 2, 3, 4, 5], size=n, p=CRITICALITY_DIST).astype(int)

    # Install dates: 5–35 years ago
    install_offset_days = rng.integers(5 * 365, 35 * 365, size=n)
    install_dates = [run_date - timedelta(days=int(d)) for d in install_offset_days]

    # Last major overhaul: ~30% of assets; between install_date and run_date
    has_overhaul = rng.random(n) < 0.30
    overhaul_dates: list[str | None] = []
    for i in range(n):
        if has_overhaul[i]:
            install_ts = install_dates[i]
            gap = (run_date - install_ts).days
            if gap > 365:
                offset = rng.integers(180, gap)
                overhaul_dates.append(str(install_ts + timedelta(days=int(offset))))
            else:
                overhaul_dates.append(None)
        else:
            overhaul_dates.append(None)

    # MTBF — base from class range, modified by criticality
    mtbf_days: list[int] = []
    for ac, tier in zip(asset_classes, criticality_tiers):
        lo, hi = MTBF_RANGES[ac]
        base = rng.integers(lo, hi + 1)
        adj = int(base * CRITICALITY_MTBF_MULTIPLIER[tier])
        mtbf_days.append(max(30, adj))

    # Replacement cost — base from class range, modified by criticality
    replacement_costs: list[int] = []
    for ac, tier in zip(asset_classes, criticality_tiers):
        lo, hi = REPLACEMENT_COST_RANGES[ac]
        base = rng.integers(lo, hi + 1)
        adj = int(base * CRITICALITY_COST_MULTIPLIER[tier])
        replacement_costs.append(adj)

    # Asset names — template + unit prefix + suffix for uniqueness
    asset_names: list[str] = []
    name_counters: dict[tuple, int] = {}
    for ac, loc in zip(asset_classes, location_units):
        templates = ASSET_NAME_TEMPLATES[ac]
        idx = rng.integers(0, len(templates))
        base_name = templates[idx]
        key = (ac, loc, base_name)
        count = name_counters.get(key, 0)
        suffix = ASSET_NAME_SUFFIXES[count % len(ASSET_NAME_SUFFIXES)]
        asset_names.append(f"{base_name} {suffix}")
        name_counters[key] = count + 1

    asset_ids = [f"AST-{i+1:05d}" for i in range(n)]

    df = pd.DataFrame({
        "asset_id":                asset_ids,
        "asset_class":             asset_classes,
        "asset_name":              asset_names,
        "location_unit":           location_units,
        "criticality_tier":        criticality_tiers,
        "install_date":            [str(d) for d in install_dates],
        "last_major_overhaul_date": overhaul_dates,
        "mtbf_days":               mtbf_days,
        "replacement_cost_usd":    replacement_costs,
    })

    _write_schema(df)
    return df


def _write_schema(df: pd.DataFrame) -> None:
    from pathlib import Path
    schema = """# assets_schema.md

| Column | Type | Description |
|---|---|---|
| asset_id | string | Primary key. Format: AST-NNNNN |
| asset_class | string | Equipment type (centrifugal_pump, heat_exchanger, …) |
| asset_name | string | Descriptive name, unique within location_unit |
| location_unit | string | Process unit where the asset is installed |
| criticality_tier | int | 1 (highest) to 5 (lowest) |
| install_date | date | Date the asset was installed |
| last_major_overhaul_date | date | Date of last major overhaul, or null |
| mtbf_days | int | Mean time between failures (days) |
| replacement_cost_usd | int | Estimated replacement cost in USD |
"""
    # Write next to the output dir
    out = Path(__file__).parent.parent / "output" / "assets_schema.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(schema)
