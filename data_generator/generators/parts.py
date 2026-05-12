"""Generate the spare parts catalogue (~5,000 SKUs)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common import (
    PART_CATEGORIES,
    PART_CATEGORY_COMPATIBLE_CLASSES,
    PART_CATEGORY_COST,
    PART_CATEGORY_LEAD_TIME,
    PART_NAME_ROOTS,
)

N_PARTS = 5_000
N_SUPPLIERS = 80


def generate_parts(rng: np.random.Generator) -> pd.DataFrame:
    # Spread parts roughly evenly across categories
    category_counts = _distribute(N_PARTS, len(PART_CATEGORIES), rng)
    categories: list[str] = []
    for cat, cnt in zip(PART_CATEGORIES, category_counts):
        categories.extend([cat] * cnt)
    categories_arr = np.array(categories)
    rng.shuffle(categories_arr)

    n = len(categories_arr)

    # Part names: root + size/spec suffix for variety
    spec_suffixes = [
        "6206", "6208", "6310", "7210", "32210",   # bearing numbers
        "1.5\"", "2\"", "3\"", "4\"", "6\"",       # sizes
        "150#", "300#", "600#",                     # pressure classes
        "SS316", "CS A105", "Duplex",               # materials
        "ATEX", "ExD", "NEC Div1",                  # electrical ratings
        "ISO VG 46", "ISO VG 68", "ISO VG 100",    # lube grades
    ]
    part_names: list[str] = []
    for cat in categories_arr:
        roots = PART_NAME_ROOTS[cat]
        root = roots[rng.integers(0, len(roots))]
        suffix = spec_suffixes[rng.integers(0, len(spec_suffixes))]
        part_names.append(f"{root} {suffix}")

    # Supplier IDs
    supplier_ids = [f"SUP-{rng.integers(1, N_SUPPLIERS + 1):03d}" for _ in range(n)]

    # Lead times
    lt_means = np.empty(n)
    lt_stdevs = np.empty(n)
    for i, cat in enumerate(categories_arr):
        mu, sd = PART_CATEGORY_LEAD_TIME[cat]
        lt_means[i] = round(mu + rng.normal(0, 1), 1)
        lt_stdevs[i] = round(sd, 1)
    lt_means = np.clip(lt_means, 1, 120)

    # Unit costs
    unit_costs = np.empty(n)
    for i, cat in enumerate(categories_arr):
        lo, hi = PART_CATEGORY_COST[cat]
        unit_costs[i] = round(float(rng.uniform(lo, hi)), 2)

    # Stock levels
    in_stock_qty = rng.poisson(lam=20, size=n).astype(int)
    reorder_points = np.maximum(1, (lt_means * 0.5).astype(int))

    # Compatible asset classes (semicolon-joined)
    compatible: list[str] = []
    for cat in categories_arr:
        classes = PART_CATEGORY_COMPATIBLE_CLASSES[cat]
        compatible.append(";".join(classes))

    part_ids = [f"PRT-{i+1:06d}" for i in range(n)]

    df = pd.DataFrame({
        "part_id":                  part_ids,
        "part_name":                part_names,
        "part_category":            categories_arr,
        "compatible_asset_classes": compatible,
        "supplier_id":              supplier_ids,
        "lead_time_days_mean":      lt_means,
        "lead_time_days_stdev":     lt_stdevs,
        "unit_cost_usd":            unit_costs,
        "in_stock_qty":             in_stock_qty,
        "reorder_point":            reorder_points,
    })

    _write_schema()
    return df


def _distribute(total: int, buckets: int, rng: np.random.Generator) -> list[int]:
    """Distribute total into buckets with small random variation."""
    base = total // buckets
    counts = [base] * buckets
    remainder = total - base * buckets
    for i in rng.choice(buckets, size=remainder, replace=False):
        counts[i] += 1
    return counts


def _write_schema() -> None:
    from pathlib import Path
    schema = """# spare_parts_schema.md

| Column | Type | Description |
|---|---|---|
| part_id | string | Primary key. Format: PRT-NNNNNN |
| part_name | string | Descriptive name including spec suffix |
| part_category | string | bearing \\| seal \\| gasket \\| valve_trim \\| motor \\| instrument \\| lubricant \\| coupling \\| electrical \\| fitting |
| compatible_asset_classes | string | Semicolon-separated list of compatible asset_class values |
| supplier_id | string | Supplier identifier (SUP-NNN) |
| lead_time_days_mean | float | Mean procurement lead time in days |
| lead_time_days_stdev | float | Standard deviation of lead time |
| unit_cost_usd | float | Unit cost in USD |
| in_stock_qty | int | Current warehouse quantity |
| reorder_point | int | Reorder trigger quantity |
"""
    out = Path(__file__).parent.parent / "output" / "spare_parts_schema.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(schema)
