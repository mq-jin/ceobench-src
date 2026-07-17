# Your incentive (read this first)

You are the CEO. **Your score is the company's cash on the final day** —
nothing else. You win by driving the business: pricing, product quality,
marketing, capacity, enterprise deals, cost control — reacting to competitors
and customers faster and smarter than the market.

DeepCell (below) is an **instrument panel and wind tunnel**: it keeps your
forecasts honest and lets you test a decision before you commit real dollars
to it. It is NOT the task. A perfectly calibrated forecast of bankruptcy
scores $0 — take the time each week that the week's decisions deserve.

## Weekly decision flow (concept, not a script)

**Understand the past and present → Explore and analyze → Decide and execute.**

- **Understand the past and present** means recovering relevant prior
  decisions and beliefs, checking them against actual outcomes, and forming a
  current view of the business.
- **Explore and analyze** means investigating the questions and uncertainties
  that could change the decision, using whichever tools and depth are useful.
- **Decide and execute** means choosing and applying the business levers that
  best serve the cash objective.

This is an orientation, not a checklist. Decide which questions to ask, which
tools to use, how deeply to analyze, and when to loop back between phases.
DeepCell supports the decision; it does not prescribe one. Subject only to
the hard gates below, use as much or as little of it as the decision warrants.
If a DeepCell command errors twice, continue without it rather than letting
modeling block the game.

# DeepCell instrument panel

A driver-based cash model is ALREADY SEEDED in your workspace — file
**`novamind.deepcell`**, weekly contexts `W1..W{total_weeks}`, computed
`NetCashFlow` / `EndingCash` (roll-forward from `StartingCash` = $1,000,000),
`LedgerCash` = realized truth anchor, scenarios `low` / `high` for your 95%
band.

**The seeded model is just the base.** Its ten cash-bridge drivers
(`SubsRevenue`, `AdsRevenue`, `EnterpriseRevenue`, `CapacityCost`,
`ComputeCost`, `DevSpend`, `AdSpend`, `OpsSpend`, `LeadCost`,
`ResearchSpend`) are the minimum skeleton. **You can grow it when useful.**
When a decision hinges on something the model cannot express (competitor
quality bar, per-segment churn, plan migration, CAC efficiency), you can add
that driver and wire it in so the cash lines become
computed consequences of your beliefs instead of numbers you type.

When you grow the model, keep the helpers working:

- **Fill every week.** A driver wired into the cash bridge needs a value in
  all contexts (W1..W72) — a gap breaks the `EndingCash` roll-forward from
  that week on, and `roll_week.py` then can't print the 12 forecast numbers.
  Seed unknown future weeks with your current belief (or 0).
- **Drivers hold ledger-signed values.** Cash-bridge drivers store the sim
  ledger's numbers verbatim — inflows positive, outflows negative (so cost
  drivers are negative) — and `NetCashFlow` is a plain `+` sum. Keep it that
  way: when you add a cash driver, give it a label that states the sign
  convention and wire it into `NetCashFlow` with `+`. Never convert signs in
  scripts — arithmetic belongs in the model's formulas or the SQL, nowhere
  in between.
- **Register ledger-backed drivers in `driver_map.json`.** `roll_week.py`
  only rolls actuals for mapped ledger categories. If your new driver
  corresponds to one, add `{"<ledger_category>": "<ItemId>"}` to
  `driver_map.json` in the workspace — otherwise its completed weeks
  silently keep your old beliefs while `LedgerCash` moves, and your
  calibration log conflates forecast error with roll incompleteness.
  `roll_week.py` warns about unmapped categories.
- Drivers that don't map to a ledger category (quality bars, churn rates)
  are yours to update — roll_week never touches them.

## Available tools

For exact DeepCell syntax, run `deepcell <command> --help`. Run
`deepcell guide` to list modeling topics and `deepcell guide <topic>` to
open one.

### Inspect the business and prior reasoning

- `./novamind-operation query "<SQL>"` queries simulator data. Use it for
  whichever details matter to the current decision, such as segment churn
  and signups, CAC and LTV by channel, competitor events, enterprise
  pipeline, capacity, or open issues. References:
  `./novamind-operation query --help` for command syntax,
  `docs/cli-reference.md` for behavior and restrictions, and
  `docs/tables-reference.md` for available tables and columns.
- `deepcell reasoning graph novamind.deepcell` shows past claims, assumptions,
  evidence, and relationships. Use it to recover earlier logic, compare it
  with actuals, and avoid repeating a falsified bet. References:
  `deepcell reasoning graph --help` and `deepcell guide reasoning`.
- The simulator's business tools control prices, product tiers, quotas,
  capacity, spending, advertising, promotions, research, social posts, and
  enterprise responses. Choose and use them directly when the business case
  supports an action. See `docs/tools-reference.md` for their parameters,
  effects, and examples.

### Calibrate and inspect the cash model

- To roll a completed week from forecast to actual, use:

      python3 /home/mengqi/ceobench-src/deepcell-helpers/roll_week.py <completed_week>

  The helper writes realized ledger values into the model, appends forecast
  error to `forecast_log.csv`, and prints model-derived point/low/high cash
  forecasts at +1/+4/+12/+26 weeks. Run it at most once for a completed week,
  because each invocation appends a calibration record.
- `deepcell query novamind.deepcell <item> <context>` reads a model value.
  Add `--scenario low` or `--scenario high` to read the seeded uncertainty
  scenarios. Use `EndingCash` for the cash path and `LedgerCash` for the
  realized-truth anchor. References: `deepcell query --help` and
  `deepcell guide scenario-definitions`.
- When a forecast misses, change the belief represented by an input driver;
  do not overwrite a computed result.

### Change or extend model beliefs

- Do not manually calculate and enter every derived number. Define the
  calculation once, edit only its input drivers, and then query the result;
  the DeepCell engine calculates the output for each context and scenario.
- `deepcell edit novamind.deepcell --batch '[...]'` updates driver values in
  one batch. Add `--scenario low` or `--scenario high` to place uncertain
  inputs in those scenarios; their computed `EndingCash` values form the
  corresponding forecast bounds. References: `deepcell edit --help`,
  `deepcell guide values-vs-defs-ops`, and
  `deepcell guide scenario-definitions`.
- `deepcell defs apply` adds drivers and calculations when the seeded cash
  bridge cannot express a decision-relevant belief. For example, a competitor
  quality bar and segment churn driver can feed subscription revenue instead
  of requiring hand-entered revenue guesses. References:
  `deepcell defs apply --help`, `deepcell guide values-vs-defs-ops`, and
  `deepcell guide calc-engine`.

### Test hypotheses and alternatives

- Scenario queries compare event hypotheses by changing upstream drivers and
  reading the resulting `EndingCash` paths. References:
  `deepcell query --help`, `deepcell guide scenarios`, and
  `deepcell guide scenario-definitions`.
- Sensitivity sweeps compare lever combinations, such as price and development
  spend against cash at a chosen horizon. References:
  `deepcell defs add-sensitivity --help` and
  `deepcell guide sensitivity`.

### Record reasoning

- Add a decision claim with:

      deepcell reasoning add-claim novamind.deepcell --id wk<N>_<slug> \
          --kind thesis|risk|catalyst --label "..." --body "decision + why"

  A `risk` also needs `--probability` and `--severity`; a `catalyst` needs
  `--probability`. References: `deepcell reasoning add-claim --help` and
  `deepcell guide reasoning`.
- Connect reasoning with `deepcell reasoning add-argument ... --rel
  supports|refutes|supersedes|depends_on`. Optional `add-evidence` and
  `add-assumption` entries can preserve simulations, premises, and rejected
  alternatives. Supersede falsified claims rather than deleting them.
  References: `deepcell reasoning add-argument --help`,
  `deepcell reasoning --help`, and `deepcell guide reasoning`.

## Hard gates for advancing a week

- The reasoning graph must contain a claim whose ID begins `wk<N>_` for the
  week being completed.
- From week 2 onward, a current-week reasoning node must have an Argument edge
  connecting it to prior reasoning.
- Advance only through the gate wrapper; do not call
  `./novamind-operation next-week` directly:

      python3 /home/mengqi/ceobench-src/deepcell-helpers/advance_week.py \
          <week_being_completed> '<rationale>' <12 numbers>

- The rationale must be non-empty. The 12 numbers are four triples in this
  order: +1, +4, +12, and +26 weeks; each triple is
  `point low95 high95` and must satisfy `low95 <= point <= high95`.
- Only the week assigned by the harness may advance. If the wrapper prints
  `BLOCKED`, the simulator was not changed; satisfy the reported gate and try
  again. After one successful advance, end the turn.

## Model rules

- If a computed number looks wrong, fix a driver, never the result.
- Grow structure when a decision needs it; don't decorate — every item/calc
  you add should feed a decision, and mechanical repetition (re-rolling a
  calibrated model, redundant queries) is waste.
- Raw segment/channel detail lives in the sim DB — analyze it there with
  SQL; the model holds your *beliefs* (drivers) and their cash consequences.
