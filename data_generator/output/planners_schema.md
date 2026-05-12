# planners_schema.md

| Column | Type | Description |
|---|---|---|
| planner_id | string | Primary key. Format: PLN-X |
| planner_name | string | Anonymised name (Planner-A through Planner-F) |
| experience_years | int | Years of maintenance planning experience |
| specialization | string | rotating_equipment \| static_equipment \| instrumentation \| electrical \| generalist |
| avg_notifications_per_day | int | Historical average notifications processed per day |
| shift | string | day \| night |

**Capacity note:** combined team processes ~252 notifications/day × 5 working days = **1,260/week**.
Weekly inflow is ~1,900. The deficit (~640/week) is the structural backlog growth visible in notifications.csv.
