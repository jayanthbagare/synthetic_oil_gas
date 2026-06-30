# production_schema.md

Daily plant production and product yields.

| Column | Type | Description |
|---|---|---|
| date | date | Calendar date (PK) |
| barrels_produced | float | Total crude throughput (bbl) |
| gasoline_bbl | float | Gasoline yield (bbl) |
| diesel_bbl | float | Diesel yield (bbl) |
| jet_fuel_bbl | float | Jet fuel yield (bbl) |
| lpg_bbl | float | LPG yield (bbl) |
| fuel_oil_bbl | float | Fuel oil yield (bbl) |
| other_bbl | float | Other products yield (bbl) |
| on_spec_pct | float | Percentage of output meeting product spec |
| notes | string | Operational note (turnaround, derate, …) |

## Usage

Multiply lost barrels by a refining margin (e.g. $12/bbl) to convert
downtime into revenue impact — the business case for maintenance throughput.
