#!/bin/bash
# Start a fresh Claude Opus 4.7 run (500 days, seed 42) via Anthropic direct API.
# Uses thinking effort = max (highest level).
# Prompt caching is enabled via cache_control breakpoints (system + last tool + last message).

set -euo pipefail
cd "$(dirname "$0")"

LOG="/tmp/bossbench_opus_fresh.log"

echo "Starting fresh Claude Opus 4.7 run..." | tee "$LOG"
nohup setsid uv run python -m saas_bench.agents.bash_agent.run_test \
  --model claude-opus-4-7 \
  --provider anthropic \
  --reasoning-effort max \
  --seed 42 \
  --days 500 \
  --workspace bash_agent_runs \
  >> "$LOG" 2>&1 &

PID=$!
echo "PID: $PID"
echo "Log: $LOG"

sleep 5
if kill -0 $PID 2>/dev/null; then
    echo "Process alive (PID $PID)"
    # Wait briefly for the run directory to be created, then attach monitor.
    for i in 1 2 3 4 5 6 7 8 9 10; do
        RUN_DIR=$(ls -td bash_agent_runs/run_*/ 2>/dev/null | head -1)
        if [ -n "$RUN_DIR" ] && [ -f "$RUN_DIR/checkpoint.json" ]; then
            break
        fi
        sleep 2
    done
    if [ -n "$RUN_DIR" ]; then
        echo "Run dir: $RUN_DIR"
        bash start_monitor.sh "$RUN_DIR" 2>/dev/null || echo "Monitor failed to start (non-fatal)"
    fi
else
    echo "ERROR: Process died immediately"
    tail -40 "$LOG"
fi
