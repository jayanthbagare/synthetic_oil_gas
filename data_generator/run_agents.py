"""CLI to run the agent pipeline over generated data and emit an eval report.

Usage:
    python run_agents.py --db ./output/crestmount.db --run-date 2026-06-30

Builds nothing — it assumes generate_data.py has already produced the CSVs
and the SQLite DB (run with --build-db to (re)build the DB from CSVs first).
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from infra.db import RefineryDB, build_database
from infra.config import load_config
from infra.logging_setup import configure_logging, get_logger
from agents import TriageAgent, ContextGatherer, PlannerAssistant, Evaluator


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the Crestmount agent pipeline")
    ap.add_argument("--db", type=Path, default=Path("./output/crestmount.db"))
    ap.add_argument("--output-dir", type=Path, default=Path("./output"),
                    help="CSV dir (used with --build-db)")
    ap.add_argument("--build-db", action="store_true",
                    help="(Re)build the SQLite DB from CSVs before running")
    ap.add_argument("--run-date", type=str, default=None,
                    help="Run date ISO string (default: today)")
    ap.add_argument("--report-out", type=Path, default=Path("./output/agent_eval_report.md"))
    args = ap.parse_args()

    cfg = load_config()
    configure_logging(cfg.get("logging.level", "INFO"), cfg.get("logging.format", "structured"))
    log = get_logger("agents")

    run_date = args.run_date or str(date.today())

    if args.build_db:
        log.info("Building SQLite DB from CSVs", extra={"phase": "db", "entity": "all"})
        build_database(args.output_dir, args.db)

    db = RefineryDB(args.db)
    log.info("Opened DB", extra={"rows": db.table_rowcounts(), "entity": "all"})

    log.info("Running triage agent", extra={"phase": "triage"})
    triage = TriageAgent(db, cfg.raw)
    results = triage.run(run_date)
    log.info("Triage complete", extra={"phase": "triage", "rows": len(results)})
    if results:
        top5 = results[:5]
        print("\nTop 5 prioritised notifications:")
        for r in top5:
            print(f"  {r.notification_id}  score={r.priority_score:5.1f}  "
                  f"sev={r.predicted_severity}  sla={r.sla_bucket}")

    log.info("Running evaluation harness", extra={"phase": "eval"})
    evaluator = Evaluator(db, cfg.raw)
    report = evaluator.evaluate(run_date)
    md = report.to_markdown()
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(md + "\n")
    print(f"\n{md}")
    print(f"\nReport written to {args.report_out}")

    db.close()


if __name__ == "__main__":
    main()
