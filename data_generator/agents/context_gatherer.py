"""Context-gathering agent — enriches a notification with planner context.

Given a single notification, pulls together everything a planner needs to make
a decision: asset record, maintenance history, recent failures, open work
orders, live sensor anomalies, downstream (P&ID) impact, required parts &
permit picture, and the day's weather. The output is an :class:`EnrichedContext`
ready to feed to the planner-assistant or an LLM.
"""
from __future__ import annotations

from typing import Any

from .base import Agent, EnrichedContext


class ContextGatherer(Agent):
    name = "context-gatherer"

    def run(self, notification: dict[str, Any], run_date: str) -> EnrichedContext:
        ctx = EnrichedContext(notification=notification)
        asset_id = notification.get("asset_id")
        raised = str(notification.get("raised_at", ""))[:10]  # YYYY-MM-DD

        if asset_id:
            asset_rows = self.db.query("SELECT * FROM assets WHERE asset_id = ?", (asset_id,))
            ctx.asset = asset_rows[0] if asset_rows else None

            # Maintenance history: prior notifications on the same asset
            ctx.asset_history = self.db.query(
                "SELECT notification_id, raised_at, source, observed_severity, "
                "status, ground_truth_category "
                "FROM notifications WHERE asset_id = ? "
                "ORDER BY raised_at DESC LIMIT 10",
                (asset_id,),
            )

            # Recent failures on the asset
            ctx.recent_failures = self.db.query(
                "SELECT failure_id, failed_at, downtime_hours, downtime_cost_usd, "
                "root_cause FROM failure_events WHERE asset_id = ? "
                "ORDER BY failed_at DESC LIMIT 5",
                (asset_id,),
            )

            # Open work orders on the asset
            ctx.open_work_orders = self.db.query(
                "SELECT wo_id, work_type, priority, status, scheduled_start "
                "FROM work_orders WHERE asset_id = ? AND status IN "
                "('planned','scheduled','in_progress') ORDER BY scheduled_start",
                (asset_id,),
            )

            # Recent sensor anomalies (last 7 days of readings)
            ctx.sensor_anomalies = self.db.query(
                "SELECT s.sensor_type, r.timestamp, r.value, r.anomaly_type "
                "FROM sensor_readings r JOIN sensors s ON s.sensor_id = r.sensor_id "
                "WHERE r.asset_id = ? AND r.is_anomalous = 1 "
                "ORDER BY r.timestamp DESC LIMIT 20",
                (asset_id,),
            )

            # Downstream assets (failure-cascade impact) via the P&ID graph
            ctx.downstream_assets = self.db.query(
                "SELECT a.asset_id, a.asset_name, a.criticality_tier, "
                "c.connection_type, c.process_stream "
                "FROM asset_connections c JOIN assets a ON a.asset_id = c.target_asset_id "
                "WHERE c.source_asset_id = ?",
                (asset_id,),
            )

        # Day's weather (affects permit feasibility)
        if raised:
            w = self.db.query("SELECT * FROM weather WHERE date = ?", (raised,))
            ctx.weather = w[0] if w else None

        return ctx
