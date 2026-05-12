# crews_schema.md

| Column | Type | Description |
|---|---|---|
| crew_id | string | Primary key. Format: CRW-NNN |
| crew_name | string | Human-readable crew name |
| skill_codes | string | Semicolon-separated skill codes |
| size | int | Number of people in the crew |
| shift | string | day \| night \| rotation |
| available_hours_per_week | float | Effective available work hours per week (size × 40 × 0.85) |
