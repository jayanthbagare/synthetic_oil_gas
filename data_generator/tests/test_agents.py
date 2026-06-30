"""Tests for the agent framework (agents/).

Requires the DB to be built first:
    python generate_data.py --seed 42 --build-db
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from infra.db import RefineryDB
from agents import TriageAgent, ContextGatherer, PlannerAssistant, Evaluator

DB_PATH = Path(__file__).parent.parent / "output" / "crestmount.db"
RUN_DATE = str(date.today())


@pytest.fixture(scope="module")
def db() -> RefineryDB:
    if not DB_PATH.exists():
        pytest.skip("crestmount.db not found — run generate_data.py --build-db")
    return RefineryDB(DB_PATH)


# ---------------------------------------------------------------------------
# Triage agent
# ---------------------------------------------------------------------------

class TestTriageAgent:
    def test_predict_severity_escalates_leak(self, db: RefineryDB) -> None:
        agent = TriageAgent(db)
        # "leak" is a severity-1 keyword
        sev = agent.predict_severity("big leak from the seal", observed=3, criticality=1)
        assert sev == 1

    def test_predict_severity_bumps_critical_assets(self, db: RefineryDB) -> None:
        agent = TriageAgent(db)
        # bearing keyword = severity 2; on a T1 asset it bumps to 1
        sev_t1 = agent.predict_severity("bearing wear noted", observed=3, criticality=1)
        sev_t5 = agent.predict_severity("bearing wear noted", observed=3, criticality=5)
        assert sev_t1 < sev_t5

    def test_triage_one_returns_score_in_range(self, db: RefineryDB) -> None:
        agent = TriageAgent(db)
        notif = db.query("SELECT * FROM notifications WHERE status='open' LIMIT 1")[0]
        asset = db.query("SELECT * FROM assets WHERE asset_id=?", (notif["asset_id"],))[0]
        result = agent.triage_one(notif, asset, RUN_DATE)
        assert 0 <= result.priority_score <= 100
        assert 1 <= result.predicted_severity <= 5
        assert result.sla_bucket in {"immediate", "24h", "72h", "7d", "routine"}

    def test_run_sorts_by_priority_desc(self, db: RefineryDB) -> None:
        agent = TriageAgent(db)
        results = agent.run(RUN_DATE)
        assert len(results) > 0
        scores = [r.priority_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_run_t1_gets_immediate_or_24h(self, db: RefineryDB) -> None:
        """T1-critical open notifications should be flagged urgent."""
        agent = TriageAgent(db)
        results = agent.run(RUN_DATE)
        asset_map = {a["asset_id"]: a for a in db.query("SELECT * FROM assets")}
        t1_results = [r for r in results
                      if asset_map.get(
                          db.query("SELECT asset_id FROM notifications WHERE notification_id=?",
                                   (r.notification_id,))[0]["asset_id"],
                          {}).get("criticality_tier") == 1]
        for r in t1_results:
            assert r.sla_bucket in {"immediate", "24h"}, \
                f"T1 notification {r.notification_id} got {r.sla_bucket}"


# ---------------------------------------------------------------------------
# Context gatherer
# ---------------------------------------------------------------------------

class TestContextGatherer:
    def test_enriches_with_asset(self, db: RefineryDB) -> None:
        agent = ContextGatherer(db)
        notif = db.query("SELECT * FROM notifications WHERE status='open' LIMIT 1")[0]
        ctx = agent.run(notif, RUN_DATE)
        assert ctx.notification["notification_id"] == notif["notification_id"]
        assert ctx.asset is not None
        assert ctx.asset["asset_id"] == notif["asset_id"]

    def test_pulls_asset_history(self, db: RefineryDB) -> None:
        agent = ContextGatherer(db)
        # Pick an asset with multiple notifications for a richer history
        row = db.query("""
            SELECT n.* FROM notifications n
            WHERE n.status='open' AND n.asset_id IN (
                SELECT asset_id FROM notifications GROUP BY asset_id HAVING COUNT(*) > 1
            ) LIMIT 1
        """)[0]
        ctx = agent.run(row, RUN_DATE)
        assert isinstance(ctx.asset_history, list)

    def test_to_prompt_dict_drops_empty(self, db: RefineryDB) -> None:
        agent = ContextGatherer(db)
        notif = db.query("SELECT * FROM notifications WHERE status='open' LIMIT 1")[0]
        ctx = agent.run(notif, RUN_DATE)
        d = ctx.to_prompt_dict()
        assert "notification" in d
        # Empty lists should not appear
        for k, v in d.items():
            if isinstance(v, list):
                assert len(v) > 0, f"Empty list leaked into prompt dict: {k}"


# ---------------------------------------------------------------------------
# Planner assistant
# ---------------------------------------------------------------------------

class TestPlannerAssistant:
    def test_rejects_false_positive_signal(self, db: RefineryDB) -> None:
        agent = PlannerAssistant(db)
        # Craft a notification whose raw_text contains a false-positive signal
        notif = db.query("SELECT * FROM notifications WHERE status='open' LIMIT 1")[0]
        notif = dict(notif)
        notif["raw_text"] = "checked field, unit running normally — false alarm"
        ctx = ContextGatherer(db).run(notif, RUN_DATE)
        rec = agent.run(ctx)
        assert rec.action == "reject_false_positive"

    def test_rejects_duplicate_signal(self, db: RefineryDB) -> None:
        agent = PlannerAssistant(db)
        notif = db.query("SELECT * FROM notifications WHERE status='open' LIMIT 1")[0]
        notif = dict(notif)
        notif["raw_text"] = "follow-up to earlier notification, still not resolved"
        ctx = ContextGatherer(db).run(notif, RUN_DATE)
        rec = agent.run(ctx)
        assert rec.action == "reject_duplicate"

    def test_convert_to_wo_suggests_crew_and_parts(self, db: RefineryDB) -> None:
        agent = PlannerAssistant(db)
        notif = db.query("SELECT * FROM notifications WHERE status='open' LIMIT 1")[0]
        notif = dict(notif)
        notif["raw_text"] = "seal leak on pump — needs repair"
        notif["observed_severity"] = 2
        ctx = ContextGatherer(db).run(notif, RUN_DATE)
        rec = agent.run(ctx)
        assert rec.action in {"convert_to_wo", "escalate"}
        if rec.action == "convert_to_wo":
            assert rec.suggested_priority is not None
            assert rec.suggested_crew_id is not None

    def test_action_is_valid(self, db: RefineryDB) -> None:
        agent = PlannerAssistant(db)
        notif = db.query("SELECT * FROM notifications WHERE status='open' LIMIT 1")[0]
        ctx = ContextGatherer(db).run(notif, RUN_DATE)
        rec = agent.run(ctx)
        assert rec.action in {
            "convert_to_wo", "reject_false_positive",
            "reject_duplicate", "defer", "escalate",
        }
        assert 0 <= rec.confidence <= 1
        assert isinstance(rec.rationale, str) and rec.rationale


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class TestEvaluator:
    def test_evaluate_returns_report(self, db: RefineryDB) -> None:
        evaluator = Evaluator(db)
        report = evaluator.evaluate(RUN_DATE)
        assert report.n_evaluated > 0
        assert report.severity_mae >= 0
        assert 0 <= report.severity_acc_within_1 <= 1
        assert report.throughput_per_sec > 0
        assert isinstance(report.action_distribution, dict)
        assert len(report.action_distribution) > 0

    def test_eval_report_markdown(self, db: RefineryDB) -> None:
        evaluator = Evaluator(db)
        report = evaluator.evaluate(RUN_DATE)
        md = report.to_markdown()
        assert "Agent Evaluation Report" in md
        assert "Severity prediction" in md
        assert "False-positive detection" in md
