"""Triage agent — prioritises open notifications.

Scores each open notification on a weighted blend of:
  * asset criticality (T1 highest)
  * observed severity (1 = worst)
  * age in backlog (older = riskier)
  * source (predictive_model / sensor rank higher)

Emits a normalised priority score (0–100) and a recommended SLA bucket. The
agent re-derives a *predicted* severity from the raw text + asset context so
that mis-assessed severities (the 15% noise injected at generation time) can
be caught — this is what the evaluator measures.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from .base import Agent

# Keyword → severity bump (1 = most severe). Used to predict true severity
# from raw text, independent of the (noisy) observed_severity.
_SEVERITY_KEYWORDS: list[tuple[str, list[str]]] = [
    (1, ["fire", "explosion", "leak", "spill", "trip", "ground fault",
         "emergency", "shutdown", "burst"]),
    (2, ["high temp", "high vibe", "vibration alarm", "high pressure",
         "bearing", "seal leak", "seal weep", "overheating", "hot ", "rust",
         "corrosion", "wall thickness"]),
    (3, ["drift", "oscillat", "hunting", "fouling", "dp rising", "low flow"]),
    (4, ["calibration", "stuck", "spurious", "reading", "indicator"]),
    (5, ["false", "duplicate", "re-notification", "follow-up", "still open"]),
]

_SOURCE_RANK = {
    "predictive_model": 1.0,
    "sensor": 0.9,
    "inspection_round": 0.7,
    "operator": 0.5,
}


@dataclass
class TriageResult:
    notification_id: str
    priority_score: float       # 0–100, higher = more urgent
    predicted_severity: int     # 1–5, agent's own read
    sla_bucket: str             # immediate | 24h | 72h | 7d | routine
    rationale: str


class TriageAgent(Agent):
    name = "triage-agent"

    def __init__(self, db, cfg: dict | None = None) -> None:
        super().__init__(db, cfg)
        tcfg = self.cfg.get("triage", {})
        self.w_criticality = float(tcfg.get("weight_criticality", 0.40))
        self.w_severity = float(tcfg.get("weight_severity", 0.30))
        self.w_age = float(tcfg.get("weight_age", 0.15))
        self.w_source = float(tcfg.get("weight_source", 0.15))
        self.t1_sla = float(tcfg.get("t1_target_sla_hours", 24))
        self.t2_sla = float(tcfg.get("t2_target_sla_hours", 72))

    # ------------------------------------------------------------------ #
    def predict_severity(self, raw_text: str, observed: int, criticality: int) -> int:
        """Predict the true severity from raw text + asset criticality.

        Falls back to ``observed`` when no keywords match. T1/T2 assets get
        bumped one notch more severe because their failures are costlier.
        """
        text = (raw_text or "").lower()
        pred = observed
        for sev, kws in _SEVERITY_KEYWORDS:
            if any(kw in text for kw in kws):
                pred = sev
                break
        if criticality <= 2 and pred > 1:
            pred = max(1, pred - 1)
        return int(pred)

    def _age_days(self, raised_at: str, run_date: str) -> float:
        try:
            raised = pd.to_datetime(raised_at)
            run = pd.to_datetime(run_date)
            return max(0.0, (run - raised).total_seconds() / 86400.0)
        except Exception:
            return 0.0

    def _sla_bucket(self, score: float, criticality: int) -> str:
        if score >= 80 or criticality == 1:
            return "immediate"
        if score >= 60 or criticality == 2:
            return "24h"
        if score >= 40:
            return "72h"
        if score >= 20:
            return "7d"
        return "routine"

    # ------------------------------------------------------------------ #
    def triage_one(self, notification: dict[str, Any], asset: dict[str, Any] | None,
                   run_date: str) -> TriageResult:
        observed = int(notification.get("observed_severity", 3))
        criticality = int(asset["criticality_tier"]) if asset else 5
        raw_text = str(notification.get("raw_text", ""))
        source = str(notification.get("source", "operator"))
        age_days = self._age_days(str(notification.get("raised_at", "")), run_date)

        pred_sev = self.predict_severity(raw_text, observed, criticality)

        # Normalised sub-scores (each 0–1)
        s_crit = (5 - criticality) / 4.0                       # T1→1.0, T5→0.0
        s_sev = (5 - pred_sev) / 4.0                            # sev1→1.0, sev5→0.0
        s_age = min(1.0, age_days / 30.0)                      # saturates at 30d
        s_src = _SOURCE_RANK.get(source, 0.5)

        score = 100.0 * (
            self.w_criticality * s_crit
            + self.w_severity * s_sev
            + self.w_age * s_age
            + self.w_source * s_src
        )

        bucket = self._sla_bucket(score, criticality)
        rationale = (
            f"criticality T{criticality} ({s_crit:.2f}), "
            f"predicted severity {pred_sev} ({s_sev:.2f}), "
            f"age {age_days:.1f}d ({s_age:.2f}), source {source} ({s_src:.2f})"
        )
        return TriageResult(
            notification_id=notification["notification_id"],
            priority_score=round(score, 1),
            predicted_severity=pred_sev,
            sla_bucket=bucket,
            rationale=rationale,
        )

    def run(self, run_date: str) -> list[TriageResult]:
        """Triage all open notifications. Returns results sorted by priority desc."""
        notifs = self.db.query(
            "SELECT * FROM notifications WHERE status IN ('open','in_review') "
            "ORDER BY raised_at"
        )
        if not notifs:
            return []
        # Bulk-load assets for FK resolution
        asset_map = {a["asset_id"]: a for a in self.db.query("SELECT * FROM assets")}
        results = [
            self.triage_one(n, asset_map.get(n["asset_id"]), run_date)
            for n in notifs
        ]
        results.sort(key=lambda r: r.priority_score, reverse=True)
        return results
