# spare_parts_schema.md

| Column | Type | Description |
|---|---|---|
| part_id | string | Primary key. Format: PRT-NNNNNN |
| part_name | string | Descriptive name including spec suffix |
| part_category | string | bearing \| seal \| gasket \| valve_trim \| motor \| instrument \| lubricant \| coupling \| electrical \| fitting |
| compatible_asset_classes | string | Semicolon-separated list of compatible asset_class values |
| supplier_id | string | Supplier identifier (SUP-NNN) |
| lead_time_days_mean | float | Mean procurement lead time in days |
| lead_time_days_stdev | float | Standard deviation of lead time |
| unit_cost_usd | float | Unit cost in USD |
| in_stock_qty | int | Current warehouse quantity |
| reorder_point | int | Reorder trigger quantity |
