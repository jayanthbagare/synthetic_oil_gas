# work_orders_schema.md

| Column | Type | Description |
|---|---|---|
| wo_id | string | Primary key. Format: WO-NNNNNNN |
| asset_id | string | FK → assets.asset_id |
| notification_id | string | FK → notifications.notification_id (nullable for PM/regulatory WOs) |
| planner_id | string | FK → planners.planner_id |
| created_at | timestamp | When the WO was created |
| scheduled_start | timestamp | Planned start date |
| actual_start | timestamp | Actual start (nullable if not yet started) |
| actual_end | timestamp | Actual completion (nullable) |
| status | string | planned \| scheduled \| in_progress \| completed \| cancelled |
| priority | int | 1 (highest) to 5 (lowest) |
| estimated_hours | float | Planner's estimated work hours |
| actual_hours | float | Actual hours taken (nullable) |
| work_type | string | corrective \| preventive \| predictive \| regulatory |
| required_crew_skills | string | Semicolon-separated skill codes |
| required_parts_json | string | JSON list of {part_id, qty} objects |
| required_permits | string | Semicolon-separated permit_codes |
| description | string | One-line WO description |
| closure_notes | string | Free-text from crew at job completion (nullable) |
| avoided_downtime_hours | float | Estimated avoided downtime for PM/predictive WOs (nullable) |
