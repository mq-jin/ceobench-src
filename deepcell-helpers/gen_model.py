#!/usr/bin/env python3
"""Generate the default NovaMind cash model and upload it to the deepcell workspace.

Usage: python3 gen_model.py [--weeks 72] [--file novamind.deepcell]

Design (deliberately status-free to avoid actual/projected calc-resolution
mismatches): every driver holds ONE value per week — the current belief for
future weeks, the realized value for completed weeks (roll_week.py overwrites
them). Driver values are LEDGER-SIGNED (inflows positive, outflows negative,
exactly as the sim DB reports them); all arithmetic lives in the model's
formulas, none in the helper scripts. NetCashFlow and EndingCash are CalcDefs over the drivers; LedgerCash is
the sim-ledger truth anchor written by roll_week.py. Scenarios `low`/`high`
carry 95%-band driver overrides.
"""
import argparse
import os
import subprocess
import sys
import tempfile

# Drivers hold LEDGER-SIGNED cash flows exactly as the sim DB reports them:
# inflows positive, outflows negative. No sign conversion happens anywhere
# outside the model — NetCashFlow is a plain sum of these.
#
# SubsRevenue is NOT a typed number: it is computed NewSubs * AvgSubPrice in
# every week. This seeds the modeling pattern — revenue is a consequence of
# belief drivers, and the only way to change a revenue forecast is to change
# the beliefs behind it. Grow the same way (deeper drivers feeding these).
BELIEF_DRIVERS = [
    ("NewSubs", "New subscribers in week (belief; overwrite with actuals)",
     90, "numeric"),
    ("AvgSubPrice", "Avg revenue per new subscriber, USD (belief; overwrite "
     "with actuals = subs revenue / signups)", 95, "monetary"),
]
DRIVERS = [
    ("SubsRevenue", "Subscription Revenue = NewSubs * AvgSubPrice (computed "
     "- edit the belief drivers, never this)", 100),
    ("AdsRevenue", "In-App Ads Revenue (ledger-signed: inflow +)", 110),
    ("EnterpriseRevenue", "Enterprise Revenue excl. subs-billed (ledger-signed: inflow +)", 120),
    ("CapacityCost", "Capacity Cost (ledger-signed: outflow -)", 200),
    ("ComputeCost", "Compute Cost (ledger-signed: outflow -)", 210),
    ("DevSpend", "Development Spend (ledger-signed: outflow -)", 220),
    ("AdSpend", "Advertising Spend (ledger-signed: outflow -)", 230),
    ("OpsSpend", "Operations Spend (ledger-signed: outflow -)", 235),
    ("LeadCost", "Lead Acquisition Cost (ledger-signed: outflow -)", 237),
    ("ResearchSpend", "Research Spend (ledger-signed: outflow -)", 240),
]


def build_xml(weeks: int) -> str:
    L = []
    L.append("<FinancialDocument>")
    L.append("  <StatusDefinitions>")
    L.append('    <Status statusId="actual" />')
    L.append('    <Status statusId="projected" />')
    L.append("  </StatusDefinitions>")
    L.append("  <ScenarioDefinitions>")
    L.append("    <Scenarios>")
    L.append('      <Scenario scenarioId="base" label="Base Case" />')
    L.append('      <Scenario scenarioId="low" label="Bear Case (95% CI lower)" />')
    L.append('      <Scenario scenarioId="high" label="Bull Case (95% CI upper)" />')
    L.append("    </Scenarios>")
    L.append("  </ScenarioDefinitions>")
    L.append("  <ContextDefinitions>")
    for w in range(1, weeks + 1):
        d0, d1 = (w - 1) * 7, w * 7
        L.append(
            f'    <Context contextId="W{w}" order="{w}" '
            f'label="Week {w} (Days {d0}-{d1})" kind="period" level="0" />'
        )
    L.append("  </ContextDefinitions>")
    L.append("  <ItemDefinitions>")
    items = (
        [("StartingCash", "Starting Cash (constant)", 50, "monetary")]
        + BELIEF_DRIVERS
        + [(iid, label, order, "monetary") for iid, label, order in DRIVERS]
        + [
            ("NetCashFlow", "Net Cash Flow", 300, "monetary"),
            ("EndingCash", "Ending Cash", 400, "monetary"),
            ("LedgerCash", "Ledger Cash (realized, cumulative)", 410, "monetary"),
        ]
    )
    for iid, label, order, dtype in items:
        L.append(f'    <Item itemId="{iid}" order="{order}" level="0">')
        L.append(f'      <Label lang="en">{label}</Label>')
        L.append(f"      <DataType>{dtype}</DataType>")
        if dtype == "monetary":
            L.append("      <Currency>USD</Currency>")
        L.append("      <Scale>1</Scale>")
        L.append("    </Item>")
    L.append("  </ItemDefinitions>")
    L.append("  <CalculationDefinitions>")
    # All drivers are ledger-signed, so net cash flow is a straight sum.
    ncf = " + ".join(f"{d[0]}[CURRENT]" for d in DRIVERS)
    # NOTE: the element is <Calculation> with @contextRefs (CSV) — see
    # `deepcell guide calc-specificity`. A calc with no statusRef matches any
    # cell, which is what this status-free model wants.
    L.append('    <Calculation id="calc_ncf" itemRef="NetCashFlow">')
    L.append(f"      <Formula>{ncf}</Formula>")
    L.append("    </Calculation>")
    L.append('    <Calculation id="calc_subsrev" itemRef="SubsRevenue">')
    L.append("      <Formula>NewSubs[CURRENT] * AvgSubPrice[CURRENT]</Formula>")
    L.append("    </Calculation>")
    L.append('    <Calculation id="calc_endcash_w1" itemRef="EndingCash" contextRefs="W1">')
    L.append("      <Formula>StartingCash[CURRENT] + NetCashFlow[CURRENT]</Formula>")
    L.append("    </Calculation>")
    rest = ",".join(f"W{w}" for w in range(2, weeks + 1))
    L.append(f'    <Calculation id="calc_endcash_roll" itemRef="EndingCash" contextRefs="{rest}">')
    L.append("      <Formula>EndingCash[PREVIOUS] + NetCashFlow[CURRENT]</Formula>")
    L.append("    </Calculation>")
    L.append("  </CalculationDefinitions>")
    L.append("  <Values>")
    L.append(
        '    <Value itemRef="StartingCash" contextRef="W1" '
        'valueEditable="true">1000000</Value>'
    )
    seeded = [iid for iid, _, _, _ in BELIEF_DRIVERS] + [
        iid for iid, _, _ in DRIVERS if iid != "SubsRevenue"  # computed
    ]
    for iid in seeded:
        for w in range(1, weeks + 1):
            L.append(
                f'    <Value itemRef="{iid}" contextRef="W{w}" '
                f'valueEditable="true">0</Value>'
            )
    L.append("  </Values>")
    L.append("</FinancialDocument>")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks", type=int, default=72)
    ap.add_argument("--file", default="novamind.deepcell")
    ap.add_argument("--dry-run", action="store_true", help="print XML, don't upload")
    args = ap.parse_args()

    xml = build_xml(args.weeks)
    if args.dry_run:
        print(xml)
        return

    with tempfile.NamedTemporaryFile("w", suffix=".deepcell", delete=False) as f:
        f.write(xml)
        tmp = f.name
    try:
        subprocess.run(
            ["deepcell", "write", args.file, "--file", tmp,
             "-m", f"seed default NovaMind model ({args.weeks} weeks)"],
            check=True,
        )
    finally:
        os.unlink(tmp)
    print(f"seeded {args.file} ({args.weeks} weeks) in workspace "
          f"{os.environ.get('DEEPCELL_WORKSPACE', '<active>')}", file=sys.stderr)


if __name__ == "__main__":
    main()
