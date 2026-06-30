"""Crestmount Refinery agent framework.

Agent shapes that operate at the planner bottleneck:
  * TriageAgent         — scores & prioritises open notifications.
  * ContextGatherer     — enriches a notification with asset/sensor/parts context.
  * PlannerAssistant    — recommends a planning action per notification.
  * Evaluator           — scores agent outputs against ground-truth columns.

All agents read from a :class:`infra.db.RefineryDB` so they exercise the same
relational data an agent deployed against the live system would see.
"""
from .base import Agent, NotificationContext  # noqa: F401
from .triage import TriageAgent, TriageResult  # noqa: F401
from .context_gatherer import ContextGatherer, EnrichedContext  # noqa: F401
from .planner_assistant import PlannerAssistant, PlannerRecommendation  # noqa: F401
from .eval import Evaluator, EvalReport  # noqa: F401
