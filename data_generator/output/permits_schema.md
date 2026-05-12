# permits_schema.md

| Column | Type | Description |
|---|---|---|
| permit_code | string | Primary key. Format: PMT-XX |
| permit_name | string | Full permit name |
| typical_lead_time_hours | int | Hours needed to obtain permit before work starts |
| prerequisites | string | Semicolon-separated permit_codes that must be obtained first, or empty |
