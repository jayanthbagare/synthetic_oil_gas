"""Planner-assistant agent — recommends a planning action per notification.

Consumes an :class:`EnrichedContext` (from the context-gatherer) and emits a
:class:`PlannerRecommendation` with one of:

  * convert_to_wo          — plan the work and open a work order
  * reject_false_positive  — likely a false alarm; close without action
  * reject_duplicate       — already covered by an open notification/WO
  * defer                  — low priority; defer to next planning cycle
  * escalate               — high-impact / needs specialist or manager input

The decision logic is rule-based and fully transparent (each recommendation
carries a rationale). An optional ``llm_decide`` hook lets you swap in an
LLM call for the final verdict without touching the surrounding plumbing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .base import Agent, EnrichedContext


@dataclass
class PlannerRecommendation:
    notification_id: str
    action: str               # convert_to_wo | reject_false_positive | reject_duplicate | defer | escalate
    confidence: float         # 0–1
    rationale: str
    suggested_priority: int | None = None
    suggested_crew_id: str | None = None
    suggested_parts: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


# Text signals that a notification is likely a false positive
_FP_SIGNALS = ["false", "spurious", "calibration", "checked field", "running normally",
               "reading restored", "instrument connection", "no defect", "bad tag",
               "investigated"]
# Text signals that a notification is a duplicate
_DUP_SIGNALS = ["follow-up", "same ", "re-notification", "still not resolved",
                "again by", "still showing", "raising again", "previous ticket"]


class PlannerAssistant(Agent):
    name = "planner-assistant"

    def __init__(self, db, cfg: dict | None = None,
                 llm_decide: Callable[[EnrichedContext], str] | None = None) -> None:
        super().__init__(db, cfg)
        self._llm_decide = llm_decide

    # ------------------------------------------------------------------ #
    def _decide_rule(self, ctx: EnrichedContext) -> tuple[str, float, str]:
        n = ctx.notification
        raw = str(n.get("raw_text", "")).lower()
        observed = int(n.get("observed_severity", 3))
        criticality = int(ctx.asset["criticality_tier"]) if ctx.asset else 5

        # Duplicate: text signals OR an open WO already exists for this asset+symptom
        if any(s in raw for s in _DUP_SIGNALS) or any(
            _same_asset_open_wo(n, wo) for wo in ctx.open_work_orders
        ):
            return "reject_duplicate", 0.8, "duplicate signal in text or open WO on asset"

        # False positive: text signals OR recent sensor data contradicts the alarm
        sensor_contradicts = (
            not ctx.sensor_anomalies
            and n.get("source") in ("sensor", "predictive_model")
        )
        if any(s in raw for s in _FP_SIGNALS) or sensor_contradicts:
            return "reject_false_positive", 0.75, "false-positive signal or sensor data contradicts alarm"

        # Escalate: T1/T2 critical asset with high severity or downstream cascade
        downstream_t1 = any(d.get("criticality_tier") == 1 for d in ctx.downstream_assets)
        if (criticality <= 2 and observed <= 2) or downstream_t1:
            risks = []
            if downstream_t1:
                risks.append("cascades to T1 downstream asset")
            return "escalate", 0.7, "high-impact asset or downstream cascade risk"

        # Defer: low severity on low-criticality asset, no recent failures
        if criticality >= 4 and observed >= 4 and not ctx.recent_failures:
            return "defer", 0.6, "low criticality/severity, no recent failure history"

        # Default: convert to work order
        return "convert_to_wo", 0.8, "genuine maintenance need; plan work"

    # ------------------------------------------------------------------ #
    def _suggest_priority(self, ctx: EnrichedContext) -> int:
        criticality = int(ctx.asset["criticality_tier"]) if ctx.asset else 5
        observed = int(ctx.notification.get("observed_severity", 3))
        # priority 1 (highest) .. 4 (lowest)
        if criticality <= 1 or observed <= 1:
            return 1
        if criticality <= 2 or observed <= 2:
            return 2
        if criticality <= 3:
            return 3
        return 4

    def _suggest_crew(self, ctx: EnrichedContext) -> str | None:
        if not ctx.asset:
            return None
        cls = ctx.asset.get("asset_class", "")
        # Pick a crew whose skill profile plausibly matches the asset class
        from generators.common import required_skills_for
        wanted = set(required_skills_for(cls))
        crews = self.db.query("SELECT crew_id, skill_codes FROM crews")
        for c in crews:
            profile = set(str(c.get("skill_codes", "")).split(";"))
            if wanted & profile:
                return c["crew_id"]
        return crews[0]["crew_id"] if crews else None

    def _suggest_parts(self, ctx: EnrichedContext) -> list[str]:
        if not ctx.asset:
            return []
        from generators.common import PART_CATEGORY_COMPATIBLE_CLASSES
        cls = ctx.asset.get("asset_class", "")
        cats = [cat for cat, classes in PART_CATEGORY_COMPATIBLE_CLASSES.items() if cls in classes]
        if not cats:
            return []
        # Pick up to 2 parts from the first compatible category that are in stock
        cat = cats[0]
        rows = self.db.query(
            "SELECT part_id FROM spare_parts WHERE part_category = ? AND in_stock_qty > reorder_point "
            "LIMIT 2",
            (cat,),
        )
        return [r["part_id"] for r in rows]

    def _risks(self, ctx: EnrichedContext) -> list[str]:
        risks: list[str] = []
        if ctx.weather and ctx.weather.get("has_storm"):
            risks.append("storm today — restricts working-at-height permits")
        if ctx.weather and ctx.weather.get("has_freeze"):
            risks.append("hard freeze — instrument/line freeze risk")
        if any(d.get("criticality_tier", 5) <= 2 for d in ctx.downstream_assets):
            risks.append("failure cascades to critical downstream asset")
        if ctx.sensor_anomalies and len(ctx.sensor_anomalies) >= 5:
            risks.append("cluster of sensor anomalies — confirm before planning")
        if not risks:
            risks.append("none identified")
        return risks

    # ------------------------------------------------------------------ #
    def run(self, ctx: EnrichedContext) -> PlannerRecommendation:
        if self._llm_decide is not None:
            action = self._llm_decide(ctx)
            confidence = 0.9
            rationale = "LLM-decided action"
        else:
            action, confidence, rationale = self._decide_rule(ctx)

        nid = ctx.notification["notification_id"]
        rec = PlannerRecommendation(
            notification_id=nid,
            action=action,
            confidence=confidence,
            rationale=rationale,
            risks=self._risks(ctx),
        )
        if action in ("convert_to_wo", "escalate"):
            rec.suggested_priority = self._suggest_priority(ctx)
            rec.suggested_crew_id = self._suggest_crew(ctx)
            rec.suggested_parts = self._suggest_parts(ctx)
        return rec


def _same_asset_open_wo(notification: dict[str, Any], wo: dict[str, Any]) -> bool:
    """Heuristic: an open WO on the same asset suggests a duplicate notification."""
    return wo.get("asset_id") == notification.get("asset_id")
