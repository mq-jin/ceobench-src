#!/usr/bin/env python3
"""Roll a completed NovaMind week from forecast to actual.

Usage (run from the agent workspace, where ./novamind-operation lives):

    python3 roll_week.py <completed_week_number>

What it does:
  1. Pulls week N's realized flows from the sim ledger (per-category sums via
     `./novamind-operation query`) and the cumulative ledger cash.
  2. Overwrites week N's driver values in novamind.deepcell with the actuals
     (base scenario) and writes LedgerCash (cumulative realized cash).
     SubsRevenue is computed (NewSubs * AvgSubPrice), so it is never written:
     instead the script reports the realized subscription total and warns if
     the model's computed value has drifted from it — update NewSubs /
     AvgSubPrice actuals (signups from the weekly report or subscriptions
     table; price = revenue / signups, in SQL) to reconcile.
  3. Prints the recomputed EndingCash path and reference forecasts
     (point/low95/high95 at +1, +4, +12, +26 weeks). Calibration is logged
     automatically by advance_week.py at each advance — not here.

The model's future-week drivers are NOT touched — revising beliefs for
upcoming weeks stays a judgment call (deepcell edit ... --scenario low/high
for the band).

Grown models: a workspace-local driver_map.json extends the built-in
ledger-category -> driver map ({"<category>": "<ItemId>"}); ledger categories
mapped by neither are warned about, not silently dropped. Ledger sums are
written to drivers VERBATIM (signed) — all arithmetic stays in the model.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

MODEL = os.environ.get("DEEPCELL_MODEL_FILE", "novamind.deepcell")
TOTAL_WEEKS = int(os.environ.get("CEOBENCH_TOTAL_WEEKS", "72"))

# ledger category -> model item. Values are written LEDGER-SIGNED, verbatim
# (inflows positive, outflows negative) — the model's NetCashFlow formula is
# a plain sum, and no arithmetic happens in this script.
CATEGORY_TO_ITEM = {
    # subscription_payment is handled specially: SubsRevenue is computed
    # (NewSubs * AvgSubPrice), so the ledger total is reconciled, not written.
    "ad_revenue": "AdsRevenue",
    "capacity": "CapacityCost",
    "compute": "ComputeCost",
    "development": "DevSpend",
    "advertising": "AdSpend",
    "operations": "OpsSpend",
    "lead_acquisition_cost": "LeadCost",
    "market_research": "ResearchSpend",
    "group_research": "ResearchSpend",
    "research_project": "ResearchSpend",
    # initial_funding is capital, not a weekly flow — excluded (StartingCash).
}

# Capital events, not weekly flows — never warned about as unmapped.
IGNORED_CATEGORIES = {"initial_funding"}


def load_driver_map() -> dict:
    """Merge workspace-local driver_map.json over the built-in category map.

    When you grow the model with a new driver that corresponds to a ledger
    category, register it here so this script rolls its actuals too:

        driver_map.json:  {"<ledger_category>": "<ItemId>"}

    The ledger sum is written to the item verbatim (signed) — wire the item
    into NetCashFlow with a plain +.
    """
    mapping = dict(CATEGORY_TO_ITEM)
    path = Path("driver_map.json")
    if path.exists():
        try:
            extra = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            sys.exit(f"driver_map.json is not valid JSON: {e}")
        for cat, item in extra.items():
            if not isinstance(item, str):
                sys.exit(f"driver_map.json: value for '{cat}' must be an item "
                         f"id string (got {item!r}) — ledger sums are written "
                         f"signed, so no flow type is needed")
            mapping[cat] = item
    return mapping


def novamind_query(sql: str):
    out = subprocess.run(
        ["./novamind-operation", "query", sql],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    return data.get("columns", []), data.get("rows", [])


def deepcell_value(item: str, ctx: str, scenario: str | None = None):
    cmd = ["deepcell", "-f", "json", "query", MODEL, item, ctx]
    if scenario:
        cmd += ["--scenario", scenario]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        return None
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError:
        return None
    # payload shape: {"success": true, "query_type": "value",
    #                 "result": {"value": <number|null>, ...}}
    value = (data.get("result") or {}).get("value")
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    week = int(sys.argv[1])
    if week < 1:
        print("Nothing to roll before week 1 — decide your levers, update the "
              "drivers, and read forecasts with `deepcell query` instead.")
        return
    # Ledger day convention: day 0 holds only the initial funding entry; week
    # N's flows land on days (N-1)*7+1 .. N*7 inclusive (the sim advances to
    # day N*7 and bills it), so the window is half-open on the LEFT.
    d0, d1 = (week - 1) * 7, week * 7

    # 1. realized flows for the completed week
    category_map = load_driver_map()
    _, rows = novamind_query(
        f"SELECT category, SUM(amount) AS total FROM ledger "
        f"WHERE day > {d0} AND day <= {d1} GROUP BY category"
    )
    by_item = {item: 0.0 for item in category_map.values()}
    by_item["EnterpriseRevenue"] = 0.0  # billed through subscription_payment
    def cell(row, idx, key):
        return row[key] if isinstance(row, dict) else row[idx]

    unmapped, subs_total = [], 0.0
    for r in rows:
        cat, total = cell(r, 0, "category"), float(cell(r, 1, "total") or 0)
        if cat == "subscription_payment":
            subs_total += total
        elif cat in category_map:
            by_item[category_map[cat]] += total
        elif cat not in IGNORED_CATEGORIES:
            unmapped.append((cat, total))
    if unmapped:
        print("WARNING: ledger categories with no driver mapping — their flows "
              "are in LedgerCash but NOT in any driver (extend driver_map.json "
              "to roll them):", file=sys.stderr)
        for cat, total in unmapped:
            print(f"  {cat:<24} {total:>12,.2f}", file=sys.stderr)

    _, cash_rows = novamind_query(
        f"SELECT COALESCE(SUM(amount), 0) AS cash FROM ledger WHERE day <= {d1}"
    )
    ledger_cash = float(cell(cash_rows[0], 0, "cash"))

    # 2. pre-roll forecast vs realized, printed for reference (the durable
    #    calibration log is written by advance_week.py at each advance)
    forecast = deepcell_value("EndingCash", f"W{week}")
    pct = (
        round(100 * (forecast - ledger_cash) / max(abs(ledger_cash), 1), 2)
        if forecast is not None else None
    )

    # SubsRevenue is computed (NewSubs * AvgSubPrice) — reconcile, don't write
    model_subs = deepcell_value("SubsRevenue", f"W{week}") or 0.0
    model_ent = deepcell_value("EnterpriseRevenue", f"W{week}") or 0.0
    subs_drift = subs_total - (model_subs + model_ent)
    if abs(subs_drift) > max(0.01 * abs(subs_total), 1):
        print(f"WARNING: realized subscription_payment {subs_total:,.2f} vs "
              f"model SubsRevenue+EnterpriseRevenue "
              f"{model_subs + model_ent:,.2f} (drift {subs_drift:,.2f}).\n"
              f"  SubsRevenue is computed — reconcile by writing W{week} "
              f"ACTUALS into its inputs: NewSubs (signups from the weekly "
              f"report or subscriptions table) and AvgSubPrice (= subs "
              f"revenue / signups, computed in SQL).", file=sys.stderr)

    # 3. write actuals into the model
    batch = [
        {"itemRef": item, "contextRef": f"W{week}", "newValue": str(round(val, 2))}
        for item, val in sorted(by_item.items())
    ]
    batch.append({"itemRef": "LedgerCash", "contextRef": f"W{week}",
                  "newValue": str(round(ledger_cash, 2))})
    subprocess.run(
        ["deepcell", "edit", MODEL, "--batch", json.dumps(batch)],
        check=True, capture_output=True, text=True,
    )

    # 4. report + the 12 numbers for next-week
    print(f"Week {week} rolled to actual. Realized flows:")
    for item, val in sorted(by_item.items()):
        print(f"  {item:<18} {val:>12,.2f}")
    print(f"  {'subscription_pmt':<18} {subs_total:>12,.2f}  (reconcile via "
          f"NewSubs/AvgSubPrice — SubsRevenue is computed)")
    print(f"  {'LedgerCash':<18} {ledger_cash:>12,.2f}")
    if forecast is not None:
        print(f"Model forecast for W{week} was {forecast:,.2f} "
              f"(error {pct}% vs ledger)")

    horizons = [1, 4, 12, 26]
    detail = []
    for h in horizons:
        target = min(week + h, TOTAL_WEEKS)
        point = deepcell_value("EndingCash", f"W{target}")
        low = deepcell_value("EndingCash", f"W{target}", "low")
        high = deepcell_value("EndingCash", f"W{target}", "high")
        low = low if low is not None else point
        high = high if high is not None else point
        if point is None:
            print(f"WARNING: no EndingCash for W{target}; fill drivers first")
            return
        lo, hi = min(low, high, point), max(low, high, point)
        detail.append(f"  +{h}w (W{target}): point={point:,.0f} low={lo:,.0f} high={hi:,.0f}")
    print("\nReference forecasts (advance_week.py re-reads the model at "
          "submit time — update future drivers first, then advance):")
    print("\n".join(detail))


if __name__ == "__main__":
    main()
