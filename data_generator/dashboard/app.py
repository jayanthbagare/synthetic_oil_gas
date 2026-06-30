"""Streamlit dashboard for the Crestmount Refinery agent workshop.

Visualises the planner bottleneck, backlog ageing, failure costs, sensor
anomalies, and (optionally) the agent evaluation report.

Run:
    streamlit run dashboard/app.py -- --db ./output/crestmount.db

Requires the SQLite DB produced by ``generate_data.py --build-db`` (or
``run_agents.py --build-db``).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Allow importing the infra package when running from data_generator/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from infra.db import RefineryDB  # noqa: E402


@st.cache_resource
def get_db(db_path: str) -> RefineryDB:
    return RefineryDB(db_path)


def _parse_db_arg() -> str:
    # Streamlit passes --db via argv; fall back to default.
    default = "./output/crestmount.db"
    if "--db" in sys.argv:
        i = sys.argv.index("--db")
        return sys.argv[i + 1] if i + 1 < len(sys.argv) else default
    return default


def main() -> None:
    st.set_page_config(page_title="Crestmount Refinery", page_icon="🛢️", layout="wide")
    st.title("🛢️ Crestmount Refinery — Planner Bottleneck Dashboard")

    db_path = _parse_db_arg()
    if not Path(db_path).exists():
        st.error(f"Database not found at `{db_path}`. Run `python generate_data.py --build-db` first.")
        st.stop()

    db = get_db(db_path)

    # ---- KPI row ----
    counts = db.table_rowcounts()
    open_n = db.query(
        "SELECT COUNT(*) AS c FROM notifications WHERE status IN ('open','in_review')")[0]["c"]
    t1_open = db.query("""
        SELECT COUNT(*) AS c FROM notifications n
        JOIN assets a ON a.asset_id = n.asset_id
        WHERE n.status IN ('open','in_review') AND a.criticality_tier = 1
    """)[0]["c"]
    rolling_cost = db.query("""
        SELECT COALESCE(SUM(downtime_cost_usd),0) AS c FROM failure_events
        WHERE failed_at >= date('now','-12 months')
    """)[0]["c"]
    weekly_cap = db.query(
        "SELECT COALESCE(SUM(avg_notifications_per_day)*5,0) AS c FROM planners")[0]["c"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Open backlog", f"{open_n:,}")
    c2.metric("T1 criticals open", f"{t1_open:,}")
    c3.metric("Rolling 12-mo downtime cost", f"${rolling_cost/1e6:,.1f}M")
    c4.metric("Planner capacity / week", f"{int(weekly_cap):,}")

    st.divider()

    # ---- Backlog ageing ----
    st.subheader("Backlog age distribution")
    ageing = db.query_df("""
        SELECT n.notification_id, n.raised_at, n.observed_severity,
               a.criticality_tier,
               CAST(julianday('now') - julianday(n.raised_at) AS INT) AS age_days
        FROM notifications n JOIN assets a ON a.asset_id = n.asset_id
        WHERE n.status IN ('open','in_review')
    """)
    if not ageing.empty:
        col1, col2 = st.columns(2)
        with col1:
            bins = [0, 7, 30, 60, 90, 10_000]
            labels = ["0–7d", "8–30d", "31–60d", "61–90d", ">90d"]
            ageing["bucket"] = pd.cut(ageing["age_days"], bins=bins, labels=labels, right=True)
            counts_age = ageing["bucket"].value_counts().reindex(labels, fill_value=0)
            st.bar_chart(counts_age)
        with col2:
            sev_counts = ageing["observed_severity"].value_counts().sort_index()
            st.bar_chart(sev_counts)
            st.caption("Open backlog by observed severity (1 = worst)")
    else:
        st.info("No open notifications.")

    st.divider()

    # ---- Failure cost by tier ----
    st.subheader("Failure downtime cost by criticality tier")
    fc = db.query_df("""
        SELECT a.criticality_tier, COUNT(*) AS failures,
               SUM(f.downtime_cost_usd) AS total_cost
        FROM failure_events f JOIN assets a ON a.asset_id = f.asset_id
        GROUP BY a.criticality_tier ORDER BY a.criticality_tier
    """)
    if not fc.empty:
        st.dataframe(fc, use_container_width=True, hide_index=True)
        st.bar_chart(fc.set_index("criticality_tier")["total_cost"])

    st.divider()

    # ---- Sensor anomalies ----
    st.subheader("Recent sensor anomalies (top assets)")
    anom = db.query_df("""
        SELECT r.asset_id, a.asset_name, COUNT(*) AS anomaly_count,
               MAX(r.timestamp) AS latest_anomaly
        FROM sensor_readings r JOIN assets a ON a.asset_id = r.asset_id
        WHERE r.is_anomalous = 1
        GROUP BY r.asset_id ORDER BY anomaly_count DESC LIMIT 15
    """)
    if not anom.empty:
        st.dataframe(anom, use_container_width=True, hide_index=True)
        st.bar_chart(anom.set_index("asset_name")["anomaly_count"])
    else:
        st.info("No sensor anomalies.")

    st.divider()

    # ---- Production vs calendar ----
    st.subheader("Production vs. plant state (last 90 days)")
    prod = db.query_df("""
        SELECT p.date, p.barrels_produced, c.plant_state
        FROM production p JOIN operations_calendar c ON c.date = p.date
        ORDER BY p.date DESC LIMIT 90
    """).sort_values("date")
    if not prod.empty:
        st.line_chart(prod.set_index("date")["barrels_produced"])
        st.dataframe(prod.tail(10), use_container_width=True, hide_index=True)

    st.divider()

    # ---- Agent eval report (if present) ----
    report_path = Path("./output/agent_eval_report.md")
    if report_path.exists():
        st.subheader("Agent evaluation report")
        st.markdown(report_path.read_text())
    else:
        st.caption("Run `python run_agents.py --build-db` to generate the agent evaluation report.")

    db.close()


if __name__ == "__main__":
    main()
