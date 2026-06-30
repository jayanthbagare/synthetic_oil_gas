"""Base agent primitives shared across all agent shapes."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from infra.db import RefineryDB


@dataclass
class NotificationContext:
    """A single notification plus the run-date used for age calculations."""

    notification: dict[str, Any]
    run_date: str  # ISO date string


@dataclass
class EnrichedContext:
    """A notification enriched with all the context a planner needs."""

    notification: dict[str, Any]
    asset: dict[str, Any] | None = None
    asset_history: list[dict[str, Any]] = field(default_factory=list)
    recent_failures: list[dict[str, Any]] = field(default_factory=list)
    open_work_orders: list[dict[str, Any]] = field(default_factory=list)
    sensor_anomalies: list[dict[str, Any]] = field(default_factory=list)
    downstream_assets: list[dict[str, Any]] = field(default_factory=list)
    required_parts: list[dict[str, Any]] = field(default_factory=list)
    available_crews: list[dict[str, Any]] = field(default_factory=list)
    required_permits: list[dict[str, Any]] = field(default_factory=list)
    weather: dict[str, Any] | None = None

    def to_prompt_dict(self) -> dict[str, Any]:
        """Return a compact, LLM-friendly representation (drops empty lists)."""
        out: dict[str, Any] = {"notification": self.notification}
        for k in ("asset", "weather"):
            v = getattr(self, k)
            if v:
                out[k] = v
        for k in ("asset_history", "recent_failures", "open_work_orders",
                  "sensor_anomalies", "downstream_assets", "required_parts",
                  "available_crews", "required_permits"):
            v = getattr(self, k)
            if v:
                out[k] = v
        return out


class Agent(ABC):
    """Abstract base class for all refinery agents.

    Agents are stateless w.r.t. individual notifications but hold a reference
    to the shared :class:`RefineryDB` so they can query relational context.
    """

    name: str = "base-agent"

    def __init__(self, db: RefineryDB, cfg: dict | None = None) -> None:
        self.db = db
        self.cfg = cfg or {}

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Process inputs and return a result. Implemented by subclasses."""
        raise NotImplementedError
