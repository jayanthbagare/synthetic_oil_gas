# sensor_readings_schema.md

| Column | Type | Description |
|---|---|---|
| reading_id | string | Primary key. Format: RDG-NNNNNNNNN |
| sensor_id | string | FK → sensors.sensor_id |
| asset_id | string | FK → assets.asset_id (denormalised for fast queries) |
| timestamp | datetime | Reading timestamp (hourly) |
| value | float | Measured value |
| is_anomalous | int | 1 if the reading is flagged anomalous, else 0 |
| anomaly_type | string | pre_failure \| spurious \| (empty) |

## Anomaly signal

`pre_failure` readings ramp up in the 24h preceding each entry in
`failure_events`, giving predictive-maintenance agents a learnable signal.
`spurious` anomalies are random noise with rate `sensors.anomaly_rate`.
