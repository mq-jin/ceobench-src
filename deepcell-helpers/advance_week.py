#!/usr/bin/env python3
"""Advance the NovaMind week, submitting forecasts read from the model.

Usage (from the agent workspace):

    python3 advance_week.py <week_being_completed> '<rationale>'

No forecast numbers are accepted on the command line. This wrapper queries
novamind.deepcell for EndingCash at +1/+4/+12/+26 weeks — point from the
base scenario, band from the `low`/`high` scenarios — and submits exactly
those to `./novamind-operation next-week`. To change the forecast, change
the model: update the drivers (and scenario overrides), then run this.

After a successful advance it also appends a calibration row to
forecast_log.csv automatically: the week's realized cumulative ledger cash,
compared against the +1w point submitted at the PREVIOUS advance. The
calibration record exists whether or not you remember it.

The reasoning-record discipline (a wk<N>_* claim + argument edge before
advancing) lives in the instructions, not here.
"""
import csv
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roll_week import TOTAL_WEEKS, deepcell_value, novamind_query

HORIZONS = (1, 4, 12, 26)
LOG = Path("forecast_log.csv")
LOG_HEADER = ["week", "realized_cash", "prev_point_forecast", "pct_error",
              "next_point", "next_low", "next_high"]


def fail(msg: str):
    print(f"NOT advanced.\n{msg}", file=sys.stderr)
    sys.exit(1)


def log_calibration(week: int, next_triple):
    """Append realized-vs-previous-forecast for week N + this advance's +1w
    forecast. All numbers come from the sim ledger or the model."""
    _, rows = novamind_query(
        f"SELECT COALESCE(SUM(amount), 0) AS cash FROM ledger "
        f"WHERE day <= {week * 7}"
    )
    r0 = rows[0]
    realized = float(r0["cash"] if isinstance(r0, dict) else r0[0])

    prev_point, pct = "", ""
    if LOG.exists():
        last = list(csv.DictReader(LOG.open()))
        if last and last[-1].get("next_point"):
            prev_point = float(last[-1]["next_point"])
            pct = round(100 * (prev_point - realized) / max(abs(realized), 1), 2)

    new = not LOG.exists()
    with LOG.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(LOG_HEADER)
        w.writerow([week, round(realized, 2), prev_point, pct, *next_triple])
    if pct != "":
        print(f"calibration: week {week} realized {realized:,.2f} vs "
              f"forecast {prev_point:,.2f} ({pct:+}%) — logged.")
    else:
        print(f"calibration: week {week} realized {realized:,.2f} logged "
              f"(no prior forecast to compare).")


def main():
    if len(sys.argv) != 3:
        fail(f"usage: advance_week.py <week_being_completed> '<rationale>' "
             f"(got {len(sys.argv) - 1} args — forecast numbers are read "
             f"from the model, not the command line)")
    week = int(sys.argv[1])
    rationale = sys.argv[2]
    if not rationale.strip():
        fail("rationale must be non-empty")

    nums, detail = [], []
    for h in HORIZONS:
        target = min(week + h, TOTAL_WEEKS)
        point = deepcell_value("EndingCash", f"W{target}")
        if point is None:
            fail(f"no computed EndingCash for W{target} — every cash-bridge "
                 f"driver needs a value in all weeks; fill the future drivers "
                 f"and re-run.")
        low = deepcell_value("EndingCash", f"W{target}", "low")
        high = deepcell_value("EndingCash", f"W{target}", "high")
        low = low if low is not None else point
        high = high if high is not None else point
        lo, hi = min(low, high, point), max(low, high, point)
        nums += [round(point), round(lo), round(hi)]
        detail.append(f"  +{h}w (W{target}): point={point:,.0f} "
                      f"low={lo:,.0f} high={hi:,.0f}")

    print("submitting model-derived forecasts:")
    print("\n".join(detail))
    proc = subprocess.run(
        ["./novamind-operation", "next-week", rationale]
        + [str(n) for n in nums],
    )
    if proc.returncode == 0:
        try:
            log_calibration(week, nums[0:3])
        except Exception as e:  # never let logging mask a successful advance
            print(f"WARNING: advance succeeded but calibration logging "
                  f"failed: {e}", file=sys.stderr)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
