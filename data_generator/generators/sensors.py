"""Generate the sensor/telemetry dataset (Phase 2).

Produces two tables:
  * ``sensors``           — catalog of instrumented sensors attached to assets.
  * ``sensor_readings``   — hourly time-series with injected anomalies that
                            correlate with known failure events, giving the
                            anomaly-correlator agent something real to find.

Anomalies are seeded in the 24h preceding each failure_event timestamp so that
predictive-maintenance agents have a learnable signal, plus a background
``anomaly_rate`` of spurious anomalies.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SENSOR_TYPES: list[dict[str, Any]] = [
    {"sensor_type": "vibration",  "measurement": "vibration_rms", "unit": "mm/s",
     "baseline": 2.2, "alarm_low": 0.0,  "alarm_high": 7.1},
    {"sensor_type": "temperature", "measurement": "bearing_temp", "unit": "degC",
     "baseline": 68.0, "alarm_low": 10.0, "alarm_high": 95.0},
    {"sensor_type": "pressure",   "measurement": "discharge_pressure", "unit": "psi",
     "baseline": 45.0, "alarm_low": 20.0, "alarm_high": 80.0},
    {"sensor_type": "flow",       "measurement": "outlet_flow", "unit": "m3/h",
     "baseline": 95.0, "alarm_low": 40.0, "alarm_high": 130.0},
]

# Asset classes that are typically instrumented
INSTRUMENTED_CLASSES: list[str] = [
    "centrifugal_pump", "reciprocating_pump", "compressor",
    "electrical_motor", "heat_exchanger", "fired_heater",
]


def generate_sensors(
    rng: np.random.Generator,
    assets_df: pd.DataFrame,
    failures_df: pd.DataFrame,
    run_date: date,
    cfg: dict | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (sensors_df, sensor_readings_df)."""
    cfg = cfg or {}
    history_days: int = int(cfg.get("history_days", 30))
    anomaly_rate: float = float(cfg.get("anomaly_rate", 0.02))
    sensors_per_asset: int = int(cfg.get("sensors_per_asset", 4))
    instrumented = set(cfg.get("instrumented_asset_classes", INSTRUMENTED_CLASSES))

    # ---- sensor catalog --------------------------------------------------
    eligible = assets_df[assets_df["asset_class"].isin(instrumented)].reset_index(drop=True)
    n_assets = len(eligible)
    if n_assets == 0:
        empty_sensors = pd.DataFrame(columns=[
            "sensor_id", "asset_id", "sensor_type", "measurement", "unit",
            "baseline_value", "alarm_high", "alarm_low"])
        empty_readings = pd.DataFrame(columns=[
            "reading_id", "sensor_id", "asset_id", "timestamp", "value",
            "is_anomalous", "anomaly_type"])
        _write_schema()
        return empty_sensors, empty_readings

    sensor_rows: list[dict] = []
    sid = 1
    asset_sensor_map: dict[str, list[dict]] = {}
    for _, arow in eligible.iterrows():
        chosen = SENSOR_TYPES[:sensors_per_asset]
        for st in chosen:
            # Jitter baseline per-asset so values aren't identical
            base = float(st["baseline"]) * float(rng.normal(1.0, 0.08))
            high = float(st["alarm_high"])
            low = float(st["alarm_low"])
            sensor = {
                "sensor_id": f"SEN-{sid:06d}",
                "asset_id": arow["asset_id"],
                "sensor_type": st["sensor_type"],
                "measurement": st["measurement"],
                "unit": st["unit"],
                "baseline_value": round(base, 2),
                "alarm_high": round(high, 2),
                "alarm_low": round(low, 2),
            }
            sensor_rows.append(sensor)
            asset_sensor_map.setdefault(arow["asset_id"], []).append(sensor)
            sid += 1

    sensors_df = pd.DataFrame(sensor_rows)

    # ---- readings time-series -------------------------------------------
    window_start = datetime.combine(run_date, datetime.min.time()) - timedelta(days=history_days)
    # hourly timestamps ending at run_date 23:00
    hours = history_days * 24
    ts_index = pd.date_range(end=datetime.combine(run_date, datetime.min.time()),
                             periods=hours, freq="h")

    # Map failures to pre-failure anomaly windows
    failure_windows: dict[str, list[datetime]] = {}
    if not failures_df.empty:
        for _, frow in failures_df.iterrows():
            try:
                ft = pd.Timestamp(frow["failed_at"]).to_pydatetime()
            except Exception:
                continue
            if ft < window_start:
                continue
            failure_windows.setdefault(frow["asset_id"], []).append(ft)

    reading_id = 1
    reading_chunks: list[pd.DataFrame] = []
    for asset_id, sensors in asset_sensor_map.items():
        pre_fail_times = failure_windows.get(asset_id, [])
        for s in sensors:
            base = s["baseline_value"]
            spread = max(0.05, base * 0.05)  # normal noise ~5% of baseline
            values = rng.normal(base, spread, size=len(ts_index))
            anomalous = np.zeros(len(ts_index), dtype=int)
            anomaly_type = np.array([""] * len(ts_index), dtype=object)

            # Inject pre-failure anomalies: ramp in the 24h before each failure
            for ft in pre_fail_times:
                lead = int((ft - ts_index[0]).total_seconds() // 3600)
                start = max(0, lead - 24)
                end = min(len(ts_index), lead)
                if end <= start:
                    continue
                # Escalating deviation toward the failure time
                ramp = np.linspace(0.2, 1.2, end - start)
                if s["sensor_type"] in ("vibration", "temperature", "pressure"):
                    values[start:end] += ramp * spread * 6
                else:  # flow drops before failure
                    values[start:end] -= ramp * spread * 5
                anomalous[start:end] = 1
                anomaly_type[start:end] = "pre_failure"

            # Background spurious anomalies
            bg = rng.random(len(ts_index)) < anomaly_rate
            bg &= anomalous == 0
            anomalous[bg] = 1
            anomaly_type[bg] = "spurious"

            # Clamp non-physical negatives
            values = np.maximum(values, 0.0)

            chunk = pd.DataFrame({
                "reading_id": [f"RDG-{reading_id + i:09d}" for i in range(len(ts_index))],
                "sensor_id": s["sensor_id"],
                "asset_id": asset_id,
                "timestamp": ts_index.strftime("%Y-%m-%d %H:%M:%S"),
                "value": np.round(values, 3),
                "is_anomalous": anomalous,
                "anomaly_type": anomaly_type,
            })
            reading_id += len(ts_index)
            reading_chunks.append(chunk)

    if reading_chunks:
        readings_df = pd.concat(reading_chunks, ignore_index=True)
    else:
        readings_df = pd.DataFrame(columns=[
            "reading_id", "sensor_id", "asset_id", "timestamp", "value",
            "is_anomalous", "anomaly_type"])

    _write_schema()
    return sensors_df, readings_df


def _write_schema() -> None:
    out = Path(__file__).resolve().parent.parent / "output"
    out.mkdir(parents=True, exist_ok=True)
    (out / "sensors_schema.md").write_text("""# sensors_schema.md

| Column | Type | Description |
|---|---|---|
| sensor_id | string | Primary key. Format: SEN-NNNNNN |
| asset_id | string | FK → assets.asset_id |
| sensor_type | string | vibration \\| temperature \\| pressure \\| flow |
| measurement | string | Measured quantity name |
| unit | string | Engineering unit |
| baseline_value | float | Normal operating value for this asset |
| alarm_high | float | High-alarm threshold |
| alarm_low | float | Low-alarm threshold |
""")
    (out / "sensor_readings_schema.md").write_text("""# sensor_readings_schema.md

| Column | Type | Description |
|---|---|---|
| reading_id | string | Primary key. Format: RDG-NNNNNNNNN |
| sensor_id | string | FK → sensors.sensor_id |
| asset_id | string | FK → assets.asset_id (denormalised for fast queries) |
| timestamp | datetime | Reading timestamp (hourly) |
| value | float | Measured value |
| is_anomalous | int | 1 if the reading is flagged anomalous, else 0 |
| anomaly_type | string | pre_failure \\| spurious \\| (empty) |

## Anomaly signal

`pre_failure` readings ramp up in the 24h preceding each entry in
`failure_events`, giving predictive-maintenance agents a learnable signal.
`spurious` anomalies are random noise with rate `sensors.anomaly_rate`.
""")
