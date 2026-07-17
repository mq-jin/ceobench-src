#!/usr/bin/env python3
"""Advance the NovaMind week, submitting forecasts read from the model.

Usage (from the agent workspace):

    python3 advance_week.py <week_being_completed> '<rationale>'

No forecast numbers are accepted on the command line. This wrapper queries
novamind.deepcell for EndingCash at +1/+4/+12/+26 weeks — point from the
base scenario, band from the `low`/`high` scenarios — and submits exactly
those to `./novamind-operation next-week`. To change the forecast, change
the model: update the drivers (and scenario overrides), then run this.

The reasoning-record discipline (a wk<N>_* claim + argument edge before
advancing) lives in the instructions, not here.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roll_week import TOTAL_WEEKS, deepcell_value

HORIZONS = (1, 4, 12, 26)


def fail(msg: str):
    print(f"NOT advanced.\n{msg}", file=sys.stderr)
    sys.exit(1)


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
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
