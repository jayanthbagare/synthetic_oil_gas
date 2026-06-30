"""Generate the weather dataset — West Texas climatology (Phase 2).

Weather drives equipment stress (heat waves stress cooling/transformers,
hard freezes crack piping/instruments) and crew safety (storms restrict
work-at-height permits). 730 days ending on run_date.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

CONDITIONS: list[str] = ["clear", "partly_cloudy", "cloudy", "rain", "storm", "dust", "fog"]


def generate_weather(
    rng: np.random.Generator,
    run_date: date,
    cfg: dict | None = None,
) -> pd.DataFrame:
    """Return a 730-day daily weather DataFrame."""
    cfg = cfg or {}
    n_days: int = int(cfg.get("days", 730))
    base_temp: float = float(cfg.get("base_temp_c", 19.0))
    amplitude: float = float(cfg.get("temp_amplitude_c", 13.0))
    summer_storm_rate: float = float(cfg.get("summer_storm_rate", 0.08))
    winter_freeze_rate: float = float(cfg.get("winter_freeze_rate", 0.05))

    start = run_date - timedelta(days=n_days - 1)
    dates = pd.date_range(start=start, periods=n_days, freq="D")

    # Day-of-year seasonal cycle (peak ~Jul 21, trough ~Jan 21)
    doy = np.array([d.timetuple().tm_yday for d in dates])
    seasonal = base_temp + amplitude * np.cos(2 * np.pi * (doy - 201) / 365.0)
    daily_noise = rng.normal(0, 3.0, size=n_days)
    temp_avg = seasonal + daily_noise
    temp_high = temp_avg + rng.uniform(4, 9, size=n_days)
    temp_low = temp_avg - rng.uniform(4, 9, size=n_days)

    # Wind — West Texas is windy; baseline ~18 km/h with gusts
    wind = np.maximum(0, rng.normal(18, 7, size=n_days))

    # Precipitation — mostly dry; rain/storm days get a spike
    precip = np.zeros(n_days)
    months = np.array([d.month for d in dates])
    is_summer = (months >= 6) & (months <= 8)
    is_winter = (months == 12) | (months <= 2)

    has_storm = np.zeros(n_days, dtype=int)
    has_freeze = np.zeros(n_days, dtype=int)

    # Summer storms
    storm_days = is_summer & (rng.random(n_days) < summer_storm_rate)
    precip[storm_days] = rng.uniform(5, 40, size=int(storm_days.sum()))
    wind[storm_days] += rng.uniform(10, 25, size=int(storm_days.sum()))
    has_storm[storm_days] = 1

    # Winter hard freezes
    freeze_days = is_winter & (rng.random(n_days) < winter_freeze_rate)
    temp_avg[freeze_days] -= rng.uniform(5, 10, size=int(freeze_days.sum()))
    temp_low[freeze_days] = np.minimum(temp_low[freeze_days], -3.0)
    has_freeze[freeze_days] = 1

    # Light rain on a few non-storm days
    light_rain = (~storm_days) & (rng.random(n_days) < 0.04)
    precip[light_rain] = rng.uniform(0.5, 5, size=int(light_rain.sum()))

    # Condition labels
    condition = np.array(["clear"] * n_days, dtype=object)
    condition[storm_days] = "storm"
    condition[freeze_days] = "cloudy"
    condition[light_rain] = "rain"
    cloudy_mask = (~storm_days) & (~light_rain) & (rng.random(n_days) < 0.3)
    condition[cloudy_mask] = rng.choice(["partly_cloudy", "cloudy", "dust", "fog"],
                                        size=int(cloudy_mask.sum()))
    # Dust more likely in dry spring
    dust_mask = (months >= 3) & (months <= 5) & (rng.random(n_days) < 0.05)
    condition[dust_mask] = "dust"

    df = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "temp_high_c": np.round(temp_high, 1),
        "temp_low_c": np.round(temp_low, 1),
        "temp_avg_c": np.round(temp_avg, 1),
        "wind_speed_kmh": np.round(wind, 1),
        "precipitation_mm": np.round(precip, 1),
        "condition": condition,
        "has_storm": has_storm,
        "has_freeze": has_freeze,
    })

    _write_schema()
    return df


def _write_schema() -> None:
    out = Path(__file__).resolve().parent.parent / "output"
    out.mkdir(parents=True, exist_ok=True)
    (out / "weather_schema.md").write_text("""# weather_schema.md

Daily weather for the Crestmount Refinery (West Texas), 730 days.

| Column | Type | Description |
|---|---|---|
| date | date | Calendar date (PK) |
| temp_high_c | float | Daily high temperature (°C) |
| temp_low_c | float | Daily low temperature (°C) |
| temp_avg_c | float | Daily average temperature (°C) |
| wind_speed_kmh | float | Average wind speed (km/h) |
| precipitation_mm | float | Daily precipitation (mm) |
| condition | string | clear \\| partly_cloudy \\| cloudy \\| rain \\| storm \\| dust \\| fog |
| has_storm | int | 1 if a storm occurred (restricts working-at-height) |
| has_freeze | int | 1 if a hard freeze occurred (risks piping/instruments) |

## Usage

Join to `operations_calendar` and `notifications` on date to study how
weather drives failure rates and permit restrictions.
""")
