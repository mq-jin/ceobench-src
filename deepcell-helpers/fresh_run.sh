#!/usr/bin/env bash
# Prepare a pristine CEO-Bench + DeepCell run. Guarantees no state leaks in
# from previous games:
#   1. restores the shared helper scripts + instructions to their committed
#      versions (a prior run's agent may have edited them — it happened);
#   2. deletes old runs' Claude Code auto-memory dirs (never auto-loaded by a
#      new run, which gets its own project path — pure hygiene);
#   3. creates a brand-new deepcell workspace (old workspaces keep their
#      claims/actuals/version history; a new slug makes them unreachable)
#      and seeds the default NovaMind model into it.
#
# Usage:  deepcell-helpers/fresh_run.sh [workspace-slug]
#         WEEKS=72 (default) can be overridden via env.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SLUG="${1:-ceo-bench-$(date +%Y%m%d-%H%M%S)}"
WEEKS="${WEEKS:-72}"

# deepcell API must be reachable before we bother with anything else.
if ! deepcell workspace list >/dev/null 2>&1; then
    echo "ERROR: deepcell CLI can't reach the Jingwei API — start the stack first." >&2
    exit 1
fi

echo "==> restoring committed helpers + instructions"
# NOTE: fresh_run.sh deliberately not in this list — bash reads scripts
# incrementally, and checking out the file being executed corrupts the run.
git -C "$REPO" checkout -- \
    deepcell-helpers/gen_model.py \
    deepcell-helpers/roll_week.py \
    deepcell-helpers/advance_week.py \
    deepcell-instructions.md

echo "==> clearing old runs' Claude Code auto-memory"
rm -rf "$HOME"/.claude/projects/*ceobench-src-claude-code-runs*/memory 2>/dev/null || true

echo "==> creating fresh workspace '$SLUG' + seeding model ($WEEKS weeks)"
deepcell workspace create "$SLUG" --slug "$SLUG" \
    --description "CEO-Bench run prepared $(date -u +%FT%TZ)"
DEEPCELL_WORKSPACE="$SLUG" python3 "$REPO/deepcell-helpers/gen_model.py" --weeks "$WEEKS"

cat <<EOF

Ready. Launch a run with:

  cd $REPO
  export OPENROUTER_API_KEY=<your key>       # never echo it
  export NMDB_KEY=<published SQLCipher key from KEYS.md>
  export DEEPCELL_WORKSPACE=$SLUG
  export CEOBENCH_EXTRA_INSTRUCTIONS=\$PWD/deepcell-instructions.md
  uv run python -m saas_bench.agents.claude_code.run_test \\
      --days 500 --seed 42 --workspace claude_code_runs
EOF
