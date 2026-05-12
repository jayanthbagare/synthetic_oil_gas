# operations_calendar_schema.md

| Column | Type | Description |
|---|---|---|
| date | date | Calendar date |
| plant_state | string | running \| derate \| turnaround \| startup \| shutdown |
| production_rate_pct | float | Plant production rate as % of design capacity (0–100) |
| maintenance_window_hours | float | Hours of maintenance work the plant can absorb that day |
| notes | string | Optional note (e.g., "scheduled turnaround day 3 of 14") |
