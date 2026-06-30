# sensors_schema.md

| Column | Type | Description |
|---|---|---|
| sensor_id | string | Primary key. Format: SEN-NNNNNN |
| asset_id | string | FK → assets.asset_id |
| sensor_type | string | vibration \| temperature \| pressure \| flow |
| measurement | string | Measured quantity name |
| unit | string | Engineering unit |
| baseline_value | float | Normal operating value for this asset |
| alarm_high | float | High-alarm threshold |
| alarm_low | float | Low-alarm threshold |
