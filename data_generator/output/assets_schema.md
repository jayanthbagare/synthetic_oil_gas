# assets_schema.md

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
