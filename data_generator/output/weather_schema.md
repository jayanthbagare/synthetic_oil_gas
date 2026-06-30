# weather_schema.md

Daily weather for the Crestmount Refinery (West Texas), 730 days.

| Column | Type | Description |
|---|---|---|
| date | date | Calendar date (PK) |
| temp_high_c | float | Daily high temperature (°C) |
| temp_low_c | float | Daily low temperature (°C) |
| temp_avg_c | float | Daily average temperature (°C) |
| wind_speed_kmh | float | Average wind speed (km/h) |
| precipitation_mm | float | Daily precipitation (mm) |
| condition | string | clear \| partly_cloudy \| cloudy \| rain \| storm \| dust \| fog |
| has_storm | int | 1 if a storm occurred (restricts working-at-height) |
| has_freeze | int | 1 if a hard freeze occurred (risks piping/instruments) |

## Usage

Join to `operations_calendar` and `notifications` on date to study how
weather drives failure rates and permit restrictions.
