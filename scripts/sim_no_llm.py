"""Run simulation without LLM — just step_day repeatedly.

Outputs competitor events, drift accumulators, and effective q_min over time.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from saas_bench.config import CUSTOMER_GROUPS, BenchmarkConfig
from saas_bench.simulation import Simulator
from saas_bench.database import (
    init_database, get_global_drift, get_all_group_parameters,
)
from numpy.random import default_rng
from pathlib import Path
import json
import tempfile

TOTAL_DAYS = 730
SEED = 42


def main():
    # Create temp DB
    db_path = Path(tempfile.mktemp(suffix=".db"))
    conn = init_database(db_path)

    config = BenchmarkConfig()
    config.total_days = TOTAL_DAYS
    rng = default_rng(SEED)

    sim = Simulator(conn, config, rng)
    sim.initialize()

    # Default pricing is already set by initialize()

    print(f"{'Day':>5} | {'Global q_bias':>13} | {'Competitor Event':>50} | {'S1 eff_qmin':>12} | {'E1 eff_qmin':>12} | {'S3 eff_qmin':>12}")
    print("-" * 115)

    competitor_events = []
    daily_data = []

    for day in range(1, TOTAL_DAYS + 1):
        try:
            sim.step_day()
        except Exception as e:
            print(f"Day {day}: ERROR: {e}")
            break

        # Read drift state
        global_q = get_global_drift(conn)
        all_gp = get_all_group_parameters(conn)

        # Check for new competitor events
        events = conn.execute(
            "SELECT start_day, boost_amount, description FROM competitor_events WHERE start_day = ?",
            (day,)
        ).fetchall()

        event_str = ""
        for ev in events:
            event_str = f"boost={ev['boost_amount']:.4f} ({ev['description'][:40]})"
            competitor_events.append({
                "day": day,
                "boost": round(ev['boost_amount'], 6),
                "description": ev['description'],
            })

        # Compute effective q_min for sample groups
        base_s1 = CUSTOMER_GROUPS['S1'].q_min_mean
        base_e1 = CUSTOMER_GROUPS['E1'].q_min_mean
        base_s3 = CUSTOMER_GROUPS['S3'].q_min_mean

        s1_gd = all_gp.get('S1', {}).get('drift_q_bias_total', 0.0)
        e1_gd = all_gp.get('E1', {}).get('drift_q_bias_total', 0.0)
        s3_gd = all_gp.get('S3', {}).get('drift_q_bias_total', 0.0)

        s1_eff = base_s1 + global_q + s1_gd
        e1_eff = base_e1 + global_q + e1_gd
        s3_eff = base_s3 + global_q + s3_gd

        daily_data.append({
            "day": day,
            "global_q_bias": round(global_q, 6),
            "s1_eff_qmin": round(s1_eff, 4),
            "e1_eff_qmin": round(e1_eff, 4),
            "s3_eff_qmin": round(s3_eff, 4),
        })

        # Print every 30 days or on events
        if day % 30 == 0 or events or day == 1 or day == TOTAL_DAYS:
            print(f"{day:5d} | {global_q:13.6f} | {event_str:>50s} | {s1_eff:12.4f} | {e1_eff:12.4f} | {s3_eff:12.4f}")

    print("\n" + "=" * 115)
    print(f"\nTotal competitor events: {len(competitor_events)}")
    print(f"Final global q_bias: {global_q:.6f}")
    print(f"\nCompetitor events timeline:")
    for ev in competitor_events:
        print(f"  Day {ev['day']:4d}: boost={ev['boost']:.6f} — {ev['description']}")

    # Save full data
    output = {
        "competitor_events": competitor_events,
        "final_global_q_bias": round(global_q, 6),
        "total_days": TOTAL_DAYS,
        "daily_data": daily_data,
    }
    with open("/tmp/sim_no_llm_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nFull results saved to /tmp/sim_no_llm_results.json")

    # Cleanup
    conn.close()
    db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
