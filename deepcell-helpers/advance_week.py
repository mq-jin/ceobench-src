#!/usr/bin/env python3
"""Advance the NovaMind week — GATED on a recorded decision in the reasoning graph.

Usage (from the agent workspace):

    python3 advance_week.py <week_being_completed> "<rationale>" <12 numbers>

The 12 numbers are point low95 high95 at +7, +28, +84, +182 days (same order
`./novamind-operation next-week` expects).

The gate: novamind.deepcell's <Reasoning> must contain at least one Claim with
id `wk<N>_*` for this week (your decision + why), and from week 2 on at least
one Argument edge from a `wk<N>_*` node (supports / refutes / supersedes /
depends_on a prior claim or assumption). If the gate fails, nothing is sent to
the simulator — add the claim first:

    deepcell reasoning add-claim novamind.deepcell --id wk<N>_<slug> \
        --kind thesis --label "..." --body "what you decided and why"
    deepcell reasoning add-argument novamind.deepcell --from-id wk<N>_<slug> \
        --to-id <prior_node> --rel supports

On success this wrapper execs `./novamind-operation next-week` for you.
"""
import json
import os
import re
import subprocess
import sys

MODEL = os.environ.get("DEEPCELL_MODEL_FILE", "novamind.deepcell")


def fail(msg: str):
    print(f"BLOCKED — week NOT advanced.\n{msg}", file=sys.stderr)
    sys.exit(1)


def main():
    if len(sys.argv) < 15:
        fail(f"usage: advance_week.py <week> \"<rationale>\" <12 numbers> "
             f"(got {len(sys.argv) - 1} args)")
    week = int(sys.argv[1])
    rationale = sys.argv[2]
    raw_nums = sys.argv[3:15]

    # --- validate the 12 forecasts -------------------------------------
    try:
        nums = [float(x.replace(",", "")) for x in raw_nums]
    except ValueError as e:
        fail(f"forecast numbers must be numeric: {e}")
    for i in range(0, 12, 3):
        point, lo, hi = nums[i], nums[i + 1], nums[i + 2]
        if not (lo <= point <= hi):
            fail(f"horizon {i // 3 + 1}: expected low <= point <= high, got "
                 f"point={point} low={lo} high={hi} — fix the ordering "
                 f"(each triple is point low95 high95).")

    # --- the reasoning gate ---------------------------------------------
    xml = subprocess.run(
        ["deepcell", "cat", MODEL], capture_output=True, text=True,
    ).stdout
    claims = re.findall(rf'<Claim\s+id="(wk{week}_[^"]*)"', xml)
    if not claims:
        fail(
            f"no decision recorded for week {week}. Add at least one Claim "
            f"with id prefix 'wk{week}_' to {MODEL} first:\n"
            f"  deepcell reasoning add-claim {MODEL} --id wk{week}_<slug> "
            f"--kind thesis --label \"...\" --body \"decision + why\"\n"
            f"then re-run this command."
        )
    if week >= 2:
        edges = re.findall(rf'<Argument[^>]*\bfrom="wk{week}_[^"]*"', xml)
        if not edges:
            fail(
                f"week {week} claim(s) {claims} exist but are not linked to "
                f"prior reasoning. Add an Argument edge first:\n"
                f"  deepcell reasoning add-argument {MODEL} "
                f"--from-id {claims[0]} --to-id <prior_node_id> "
                f"--rel supports|refutes|supersedes|depends_on\n"
                f"then re-run this command."
            )

    print(f"reasoning gate OK (week {week}: {', '.join(claims)}) — advancing.")
    proc = subprocess.run(
        ["./novamind-operation", "next-week", rationale] + raw_nums,
    )
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
