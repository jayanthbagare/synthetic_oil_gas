# asset_connections_schema.md

Directed edge list representing the P&ID process-flow graph.

| Column | Type | Description |
|---|---|---|
| edge_id | string | Primary key. Format: EDG-NNNNNN |
| source_asset_id | string | FK → assets.asset_id (upstream) |
| target_asset_id | string | FK → assets.asset_id (downstream) |
| connection_type | string | feed \| return \| utility \| parallel \| standby |
| process_stream | string | Process medium flowing through the connection |

## Usage

Use for failure-cascade analysis: a failure on `source_asset_id` can degrade
or halt `target_asset_id`. Query the graph with recursive CTEs to find all
assets downstream of a failing asset.
