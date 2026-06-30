"""Generate the asset connectivity (P&ID) graph (Phase 2).

Models how equipment is connected in process flows so that failure-cascade
analysis is possible: a failure on a feed pump can propagate downstream to
the column it feeds. Produces a directed edge list:
``source_asset → target_asset`` with a connection type and process stream.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# Plausible intra-unit process chains by asset class order
PROCESS_ORDER: list[str] = [
    "centrifugal_pump", "reciprocating_pump", "fired_heater",
    "heat_exchanger", "compressor", "column", "vessel",
    "control_valve", "isolation_valve", "piping", "instrument",
    "cooling_tower", "electrical_motor", "transformer", "flare",
]

CONNECTION_TYPES: list[str] = ["feed", "return", "utility", "parallel", "standby"]

PROCESS_STREAMS: list[str] = [
    "crude", "naphtha", "kerosene", "diesel", "gas_oil", "residue",
    "steam", "cooling_water", "fuel_gas", "flare_gas", "power",
]


def generate_asset_connections(
    rng: np.random.Generator,
    assets_df: pd.DataFrame,
    cfg: dict | None = None,
) -> pd.DataFrame:
    """Return an edge-list DataFrame of asset-to-asset process connections."""
    cfg = cfg or {}
    avg_edges: int = int(cfg.get("avg_edges_per_asset", 3))
    feed_edges_per_unit: int = int(cfg.get("feed_edges_per_unit", 2))

    # Rank each asset class by process order for plausible flow direction
    order_index = {cls: i for i, cls in enumerate(PROCESS_ORDER)}
    assets = assets_df.copy()
    assets["_order"] = assets["asset_class"].map(lambda c: order_index.get(c, 99))

    edges: list[dict] = []
    eid = 1

    # ---- intra-unit edges ----------------------------------------------
    for unit, group in assets.groupby("location_unit"):
        # Build a pool of asset_ids grouped by class within this unit
        by_class: dict[str, list[str]] = {}
        for cls, sub in group.groupby("asset_class"):
            by_class[cls] = sub["asset_id"].tolist()

        # Connect along process order: each asset gets ~avg_edges outgoing
        # to assets later (or utility/parallel) in the same unit.
        unit_assets = group.sort_values("_order")["asset_id"].tolist()
        for src in unit_assets:
            n_edges = max(1, int(rng.poisson(avg_edges)))
            # Prefer downstream targets (higher process order), allow parallel
            candidates = [a for a in unit_assets if a != src]
            if not candidates:
                continue
            chosen = rng.choice(candidates, size=min(n_edges, len(candidates)), replace=False)
            for tgt in chosen:
                ctype = rng.choice(CONNECTION_TYPES, p=[0.5, 0.15, 0.15, 0.12, 0.08])
                stream = rng.choice(PROCESS_STREAMS)
                edges.append({
                    "edge_id": f"EDG-{eid:06d}",
                    "source_asset_id": src,
                    "target_asset_id": str(tgt),
                    "connection_type": str(ctype),
                    "process_stream": str(stream),
                })
                eid += 1

        # ---- inter-unit feed edges --------------------------------------
        other_units = [u for u in assets["location_unit"].unique() if u != unit]
        for _ in range(feed_edges_per_unit):
            if not other_units:
                break
            src_pool = unit_assets
            tgt_unit = rng.choice(other_units)
            tgt_pool = assets[assets["location_unit"] == tgt_unit]["asset_id"].tolist()
            if not src_pool or not tgt_pool:
                continue
            edges.append({
                "edge_id": f"EDG-{eid:06d}",
                "source_asset_id": str(rng.choice(src_pool)),
                "target_asset_id": str(rng.choice(tgt_pool)),
                "connection_type": "feed",
                "process_stream": str(rng.choice(PROCESS_STREAMS)),
            })
            eid += 1

    df = pd.DataFrame(edges, columns=[
        "edge_id", "source_asset_id", "target_asset_id",
        "connection_type", "process_stream"])

    # Deduplicate identical (src,tgt,type) edges
    if not df.empty:
        df = df.drop_duplicates(subset=["source_asset_id", "target_asset_id", "connection_type"])
        df = df.reset_index(drop=True)

    _write_schema()
    return df


def _write_schema() -> None:
    out = Path(__file__).resolve().parent.parent / "output"
    out.mkdir(parents=True, exist_ok=True)
    (out / "asset_connections_schema.md").write_text("""# asset_connections_schema.md

Directed edge list representing the P&ID process-flow graph.

| Column | Type | Description |
|---|---|---|
| edge_id | string | Primary key. Format: EDG-NNNNNN |
| source_asset_id | string | FK → assets.asset_id (upstream) |
| target_asset_id | string | FK → assets.asset_id (downstream) |
| connection_type | string | feed \\| return \\| utility \\| parallel \\| standby |
| process_stream | string | Process medium flowing through the connection |

## Usage

Use for failure-cascade analysis: a failure on `source_asset_id` can degrade
or halt `target_asset_id`. Query the graph with recursive CTEs to find all
assets downstream of a failing asset.
""")
