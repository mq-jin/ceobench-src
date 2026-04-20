#!/bin/bash
# Start a fresh Grok 4.20-0309-reasoning run (500 days, seed 42) via xAI

set -euo pipefail
cd "$(dirname "$0")"

LOG="/tmp/bossbench_grok_fresh.log"

echo "Starting fresh Grok 4.20-0309-reasoning run..." | tee "$LOG"
nohup setsid uv run python -m saas_bench.agents.bash_agent.run_test \
  --model grok-4.20-0309-reasoning \
  --provider xai \
  --seed 42 \
  --days 500 \
  --workspace bash_agent_runs \
  >> "$LOG" 2>&1 &

PID=$!
echo "PID: $PID"
echo "Log: $LOG"

sleep 3
if kill -0 $PID 2>/dev/null; then
    echo "Process alive (PID $PID)"
    RUN_DIR=$(ls -td bash_agent_runs/run_*/ 2>/dev/null | head -1)
    if [ -n "$RUN_DIR" ]; then
        echo "Run dir: $RUN_DIR"
        bash start_monitor.sh "$RUN_DIR" 2>/dev/null || echo "Monitor failed to start (non-fatal)"
    fi
else
    echo "ERROR: Process died immediately"
    tail -30 "$LOG"
fi
