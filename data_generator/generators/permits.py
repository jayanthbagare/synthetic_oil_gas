"""Generate the permit types table (fixed set of 10)."""
from __future__ import annotations

import pandas as pd

from .common import PERMITS


def generate_permits() -> pd.DataFrame:
    df = pd.DataFrame(PERMITS)
    _write_schema()
    return df


def _write_schema() -> None:
    from pathlib import Path
    schema = """# permits_schema.md

| Column | Type | Description |
|---|---|---|
| permit_code | string | Primary key. Format: PMT-XX |
| permit_name | string | Full permit name |
| typical_lead_time_hours | int | Hours needed to obtain permit before work starts |
| prerequisites | string | Semicolon-separated permit_codes that must be obtained first, or empty |
"""
    out = Path(__file__).parent.parent / "output" / "permits_schema.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(schema)
