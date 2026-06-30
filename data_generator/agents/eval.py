"""Evaluation harness — scores agent outputs against ground-truth columns.

Runs the triage + planner-assistant pipeline over a held-out slice of the
notifications and reports:
  * severity prediction — MAE and accuracy-within-1 vs ground_truth_severity
  * triage ranking      — precision@K / recall@K for surfacing the most
                          critical notifications (ground_truth_severity ≤ 2)
  * false-positive F1   — detecting ground_truth_category == 'false_positive'
  * duplicate F1        — detecting ground_truth_category == 'duplicate'
  * throughput          — notifications processed / second

The evaluator is intentionally model-agnostic: it consumes the agents'
public ``run()`` outputs, so an LLM-backed planner can be dropped in without
changing the harness.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from infra.db import RefineryDB
from .triage import TriageAgent, TriageResult
from .context_gatherer import ContextGatherer
from .planner_assistant import PlannerAssistant, PlannerRecommendation


@dataclass
class EvalReport:
    n_evaluated: int = 0
    severity_mae: float = 0.0
    severity_acc_within_1: float = 0.0
    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    fp_precision: float = 0.0
    fp_recall: float = 0.0
    fp_f1: float = 0.0
    dup_precision: float = 0.0
    dup_recall: float = 0.0
    dup_f1: float = 0.0
    action_distribution: dict[str, int] = field(default_factory=dict)
    throughput_per_sec: float = 0.0
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_markdown(self) -> str:
        lines = [
            "# Agent Evaluation Report",
            "",
            f"- Notifications evaluated: **{self.n_evaluated}**",
            f"- Throughput: **{self.throughput_per_sec:.1f} notifications/sec**",
            "",
            "## Severity prediction (triage)",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| MAE vs ground_truth_severity | {self.severity_mae:.3f} |",
            f"| Accuracy within ±1 | {self.severity_acc_within_1:.1%} |",
            f"| Precision@K (critical surfacing) | {self.precision_at_k:.1%} |",
            f"| Recall@K (critical surfacing) | {self.recall_at_k:.1%} |",
            "",
            "## False-positive detection (planner-assistant)",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Precision | {self.fp_precision:.1%} |",
            f"| Recall | {self.fp_recall:.1%} |",
            f"| F1 | {self.fp_f1:.1%} |",
            "",
            "## Duplicate detection (planner-assistant)",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Precision | {self.dup_precision:.1%} |",
            f"| Recall | {self.dup_recall:.1%} |",
            f"| F1 | {self.dup_f1:.1%} |",
            "",
            "## Action distribution",
            "",
            "| Action | Count |",
            "|---|---|",
        ]
        for a, c in sorted(self.action_distribution.items(), key=lambda x: -x[1]):
            lines.append(f"| {a} | {c} |")
        return "\n".join(lines)


class Evaluator:
    """Runs the full agent pipeline and scores it."""

    def __init__(self, db: RefineryDB, cfg: dict | None = None) -> None:
        self.db = db
        self.cfg = cfg or {}
        self.held_out_fraction = float(self.cfg.get("eval", {}).get("held_out_fraction", 0.20))

    # ------------------------------------------------------------------ #
    def _holdout(self, open_notifs: list[dict]) -> list[dict]:
        """Take the held-out fraction of open notifications (newest first)."""
        if not open_notifs:
            return []
        n = max(1, int(len(open_notifs) * self.held_out_fraction))
        # Sort by raised_at ascending then take the last n (most recent = holdout)
        ordered = sorted(open_notifs, key=lambda r: r.get("raised_at", ""))
        return ordered[-n:]

    @staticmethod
    def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        return prec, rec, f1

    # ------------------------------------------------------------------ #
    def evaluate(self, run_date: str, k: int | None = None) -> EvalReport:
        report = EvalReport()
        open_notifs = self.db.query(
            "SELECT * FROM notifications WHERE status IN ('open','in_review')"
        )
        holdout = self._holdout(open_notifs)
        report.n_evaluated = len(holdout)
        if not holdout:
            return report

        if k is None:
            k = max(1, len(holdout) // 5)

        triage = TriageAgent(self.db, self.cfg)
        gatherer = ContextGatherer(self.db, self.cfg)
        planner = PlannerAssistant(self.db, self.cfg)

        # Bulk triage for ranking metrics (uses all open, ranked)
        all_triage: list[TriageResult] = triage.run(run_date)
        holdout_ids = {n["notification_id"] for n in holdout}
        holdout_triage = [t for t in all_triage if t.notification_id in holdout_ids]

        # ---- severity prediction ----
        gt_map = {n["notification_id"]: n for n in holdout}
        abs_errors: list[int] = []
        within1 = 0
        for t in holdout_triage:
            gt = int(gt_map[t.notification_id].get("ground_truth_severity", 0))
            if gt <= 0:
                continue
            err = abs(t.predicted_severity - gt)
            abs_errors.append(err)
            if err <= 1:
                within1 += 1
        if abs_errors:
            report.severity_mae = sum(abs_errors) / len(abs_errors)
            report.severity_acc_within_1 = within1 / len(abs_errors)

        # ---- ranking precision@K / recall@K ----
        # "Critical" = ground_truth_severity <= 2.
        ranked = sorted(holdout_triage, key=lambda r: r.priority_score, reverse=True)
        top_k = ranked[:k]
        actual_critical = {nid for nid, n in gt_map.items()
                           if int(n.get("ground_truth_severity", 5) or 5) <= 2}
        if actual_critical:
            tp = sum(1 for t in top_k if t.notification_id in actual_critical)
            report.precision_at_k = tp / len(top_k) if top_k else 0.0
            report.recall_at_k = tp / len(actual_critical)

        # ---- planner-assistant FP / duplicate detection ----
        fp_tp = fp_fp = fp_fn = 0
        dup_tp = dup_fp = dup_fn = 0
        t0 = time.perf_counter()
        for n in holdout:
            ctx = gatherer.run(n, run_date)
            rec: PlannerRecommendation = planner.run(ctx)
            report.action_distribution[rec.action] = (
                report.action_distribution.get(rec.action, 0) + 1)
            gt_cat = str(n.get("ground_truth_category", "")).strip()

            # false-positive detection
            is_gt_fp = gt_cat == "false_positive"
            is_pred_fp = rec.action == "reject_false_positive"
            if is_pred_fp and is_gt_fp:
                fp_tp += 1
            elif is_pred_fp and not is_gt_fp:
                fp_fp += 1
            elif (not is_pred_fp) and is_gt_fp:
                fp_fn += 1

            # duplicate detection
            is_gt_dup = gt_cat == "duplicate"
            is_pred_dup = rec.action == "reject_duplicate"
            if is_pred_dup and is_gt_dup:
                dup_tp += 1
            elif is_pred_dup and not is_gt_dup:
                dup_fp += 1
            elif (not is_pred_dup) and is_gt_dup:
                dup_fn += 1

        elapsed = time.perf_counter() - t0
        report.throughput_per_sec = len(holdout) / elapsed if elapsed else 0.0
        report.fp_precision, report.fp_recall, report.fp_f1 = self._prf(fp_tp, fp_fp, fp_fn)
        report.dup_precision, report.dup_recall, report.dup_f1 = self._prf(dup_tp, dup_fp, dup_fn)
        return report
