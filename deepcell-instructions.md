# DeepCell decision-support layer (REQUIRED workflow)

A driver-based cash model for NovaMind is ALREADY SEEDED in your deepcell
workspace (`DEEPCELL_WORKSPACE=ceo-bench` is set; the `deepcell` CLI is on
PATH — `deepcell guide <topic>` for docs). File: **`novamind.deepcell`**.

- Weekly contexts `W1..W{total_weeks}`.
- Driver items (your forecast beliefs, one value per week): `SubsRevenue`,
  `AdsRevenue`, `EnterpriseRevenue`, `CapacityCost`, `ComputeCost`, `DevSpend`,
  `AdSpend`, `OpsSpend`, `LeadCost`, `ResearchSpend`. All start at 0.
- CalcDefs (never edit these cells): `NetCashFlow`, `EndingCash` (roll-forward
  from `StartingCash` = $1,000,000).
- `LedgerCash`: realized cumulative cash, written by the roll script — the
  truth anchor for calibration.
- Scenarios `low` / `high`: your 95% band, expressed as driver overrides.

**Helper script (host):**

    python3 /home/mengqi/ceobench-src/deepcell-helpers/roll_week.py <completed_week>

Run from your working directory. It pulls that week's realized flows from the
sim ledger into the model (drivers for completed weeks become actuals), logs
your forecast-vs-actual error to `forecast_log.csv`, and prints the model's
current **12 forecast numbers** (point/low/high at +1, +4, +12, +26 weeks).
Re-running it for the same week is safe and re-prints fresh numbers.

## Prime directive

Advance the simulation exactly ONCE per prompt, then END YOUR TURN — the
harness prompts you again for each new week with a fresh dashboard. Never
play multiple weeks in one turn (the advance gate hard-refuses any week
other than the current one). The model supports decisions — never let
modeling block the game. If the script or a deepcell command errors twice,
continue the week without it.

## Weekly loop (every prompt)

1. **Roll actuals in:** `python3 .../roll_week.py <week that just finished>`
   (skip in the very first prompt — nothing has finished yet; go to step 2).
2. Study the sim (`./novamind-operation status` / `query "<SQL>"`) and decide
   this week's levers.
3. **Update FUTURE weeks' drivers** to your honest expectations under those
   levers: `deepcell edit novamind.deepcell <Item> <Wn> <value>` (or `--batch
   '[{"itemRef":...,"contextRef":...,"newValue":...}, ...]'`). For the 95%
   band, write pessimistic / optimistic values for the noisiest drivers with
   `--scenario low` / `--scenario high` — widen the spread at longer horizons.
   Update at least the next 4 weeks and the +12/+26-week landmarks every turn.
4. **Read your forecasts off the model:** re-run `roll_week.py <same week>`
   (or `deepcell query novamind.deepcell EndingCash W<n> [--scenario low|high]`).
   The printed "12 numbers" line is your `next-week` payload. Points must be
   your honest mean — never shade them for safety; uncertainty lives in the
   low/high band only. Check `forecast_log.csv` for drift in your calibration.
5. **Record the decision** in the reasoning graph (1–3 nodes, no essays) —
   REQUIRED: the advance step below is gated on it and will refuse otherwise.
   - `deepcell reasoning add-claim novamind.deepcell --id wk<N>_<slug>
     --kind thesis|risk|catalyst --label "..." --body "what you decided and
     why" --item-refs <Driver1,Driver2>` (`risk` needs `--probability` +
     `--severity`; `catalyst` needs `--probability`). The id MUST start with
     `wk<N>_` for the week being completed; anchor it to the driver items the
     decision moves.
   - From week 2 on, link it to prior reasoning (also gate-enforced):
     `deepcell reasoning add-argument novamind.deepcell --from-id <new>
     --to-id <prior> --rel supports|refutes|supersedes|depends_on`
   - When actuals falsify an earlier claim, don't delete it — add the
     corrected claim with `--rel supersedes` (the graph is your audit trail).
6. **Advance — ONLY via the gate wrapper** (never call
   `./novamind-operation next-week` directly; the wrapper verifies your week's
   reasoning entry and forecast triple ordering, then advances for you):

       python3 /home/mengqi/ceobench-src/deepcell-helpers/advance_week.py \
           <week_being_completed> '<rationale>' <12 numbers>

   Use single quotes around the rationale (dollar amounts inside double
   quotes get mangled by the shell). If it prints BLOCKED, do what it says
   and re-run — the simulator was not touched.
7. **Stop.** Once the advance succeeds, end your turn immediately — do NOT
   start the next week; you'll be prompted for it.

## Rules

- Values only: don't add items/contexts/calcs or restructure the model unless
  something is truly missing — edit driver values.
- `EndingCash` / `NetCashFlow` are computed; if a number looks wrong, fix the
  driver, never the result.
- Segment/channel detail (per-group CAC, churn, WTP) lives in the sim DB —
  analyze it there with SQL; only the cash-bridge drivers go into the model.
