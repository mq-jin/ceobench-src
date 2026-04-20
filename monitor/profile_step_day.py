"""Profile consecutive step_day() calls at scale with real LLM timing.

Loads a session's world.nmdb, reconstructs the Simulator, instruments
every Bedrock/OpenAI call with wall-time logging, then runs N step_days.
Prints per-day phase breakdown plus per-LLM-call wall times grouped by
call site.

Usage:
    uv run python monitor/profile_step_day.py <session_nmdb_path> --runs 7
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))


def _load_dotenv(path: Path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


_load_dotenv(_PROJECT_ROOT / ".env")
_load_dotenv(Path.cwd() / ".env")

from numpy.random import Generator, PCG64  # noqa: E402

from saas_bench.config import BenchmarkConfig  # noqa: E402
from saas_bench.db_protection import load_session_db  # noqa: E402
from saas_bench.simulation import Simulator  # noqa: E402
from saas_bench.customer_llm import CustomerSimulator  # noqa: E402


# -----------------------------------------------------------------------------
# LLM call tracing: wrap bedrock_client.messages.create and
# customer_simulator.client.responses.create to log every call's wall time.
# -----------------------------------------------------------------------------

_LLM_CALLS: list[dict] = []
_LLM_CALLS_LOCK = threading.Lock()
_CURRENT_DAY_HOLDER = {"day": -1}
_CURRENT_PHASE_HOLDER = {"phase": "?"}


def _record_call(provider: str, purpose_hint: str, elapsed: float,
                 input_tokens: int, output_tokens: int, ok: bool, err: str = ""):
    with _LLM_CALLS_LOCK:
        _LLM_CALLS.append({
            "day": _CURRENT_DAY_HOLDER["day"],
            "phase": _CURRENT_PHASE_HOLDER["phase"],
            "provider": provider,
            "purpose": purpose_hint,
            "elapsed_s": elapsed,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "ok": ok,
            "err": err[:200],
        })


def _wrap_bedrock(bedrock_client):
    """Wrap the AnthropicBedrock client's messages.create to time every call."""
    original_create = bedrock_client.messages.create

    def traced_create(*args, **kwargs):
        t0 = time.monotonic()
        try:
            resp = original_create(*args, **kwargs)
            elapsed = time.monotonic() - t0
            try:
                in_tok = resp.usage.input_tokens
                out_tok = resp.usage.output_tokens
            except Exception:
                in_tok, out_tok = 0, 0
            _record_call("bedrock", _CURRENT_PHASE_HOLDER["phase"], elapsed,
                         in_tok, out_tok, True)
            return resp
        except Exception as e:
            elapsed = time.monotonic() - t0
            _record_call("bedrock", _CURRENT_PHASE_HOLDER["phase"], elapsed,
                         0, 0, False, repr(e))
            raise

    bedrock_client.messages.create = traced_create
    return bedrock_client


def _wrap_openai_responses(openai_client):
    if openai_client is None or not hasattr(openai_client, "responses"):
        return openai_client
    original_create = openai_client.responses.create

    def traced_create(*args, **kwargs):
        t0 = time.monotonic()
        try:
            resp = original_create(*args, **kwargs)
            elapsed = time.monotonic() - t0
            try:
                in_tok = resp.usage.input_tokens
                out_tok = resp.usage.output_tokens
            except Exception:
                in_tok, out_tok = 0, 0
            _record_call("openai", _CURRENT_PHASE_HOLDER["phase"], elapsed,
                         in_tok, out_tok, True)
            return resp
        except Exception as e:
            elapsed = time.monotonic() - t0
            _record_call("openai", _CURRENT_PHASE_HOLDER["phase"], elapsed,
                         0, 0, False, repr(e))
            raise

    openai_client.responses.create = traced_create
    return openai_client


# -----------------------------------------------------------------------------
# Phase tracing: wrap specific simulation methods so every LLM call records
# which logical phase it belongs to.
# -----------------------------------------------------------------------------

def _wrap_phase(sim: Simulator, method_name: str, phase_label: str):
    original = getattr(sim, method_name)

    def wrapper(*args, **kwargs):
        prev = _CURRENT_PHASE_HOLDER["phase"]
        _CURRENT_PHASE_HOLDER["phase"] = phase_label
        t0 = time.monotonic()
        try:
            return original(*args, **kwargs)
        finally:
            _CURRENT_PHASE_HOLDER["phase"] = prev
            PHASE_TIMES[phase_label].append(time.monotonic() - t0)

    setattr(sim, method_name, wrapper)


PHASE_TIMES: dict[str, list[float]] = defaultdict(list)


def _active_subscriber_count(conn) -> int:
    try:
        row = conn.execute("""
            SELECT COUNT(*) FROM subscriptions
            WHERE status='subscribed' AND end_day IS NULL
        """).fetchone()
        return row[0] if row else 0
    except Exception:
        return -1


def _active_issue_count(conn, current_day: int) -> int:
    try:
        row = conn.execute("""
            SELECT COUNT(*) FROM issues
            WHERE open_day <= ? AND (resolved_day IS NULL OR resolved_day > ?) AND status != 'resolved'
        """, (current_day, current_day)).fetchone()
        return row[0] if row else 0
    except Exception:
        return -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nmdb", type=Path)
    ap.add_argument("--session-dir", type=Path, default=None,
                    help="session dir to read meta from (defaults to nmdb parent)")
    ap.add_argument("--runs", type=int, default=7, help="number of step_days to run")
    ap.add_argument("--out-json", type=Path, default=None,
                    help="dump full per-call data to this JSON file")
    args = ap.parse_args()

    session_dir = args.session_dir or args.nmdb.parent
    session_meta = json.loads((session_dir / "session.json").read_text())
    seed = session_meta["seed"]
    total_days = session_meta["total_days"]
    current_day = session_meta["current_day"]
    initial_cash = session_meta["initial_cash"]

    print(f"Session: {session_meta['session_id']}")
    print(f"  seed={seed}, total_days={total_days}, current_day={current_day}")
    print(f"  nmdb: {args.nmdb} ({args.nmdb.stat().st_size / 1e6:.1f} MB)")

    aws_key = os.environ.get("AWS_ACCESS_KEY_ID")
    print(f"  AWS_ACCESS_KEY_ID: {'set (' + aws_key[:6] + '...)' if aws_key else 'NOT SET'}")
    print(f"  AWS_REGION: {os.environ.get('AWS_REGION', '<unset>')}")

    t0 = time.monotonic()
    conn = load_session_db(args.nmdb)
    print(f"  decrypt+load: {time.monotonic()-t0:.2f}s")

    # Ensure reasoning_by_group column exists (added after this checkpoint)
    try:
        conn.execute("ALTER TABLE agent_social_media_posts "
                     "ADD COLUMN reasoning_by_group TEXT NOT NULL DEFAULT '{}'")
    except Exception:
        pass

    print(f"  active subscribers: {_active_subscriber_count(conn):,}")
    print(f"  active issues:      {_active_issue_count(conn, current_day):,}")

    rng = Generator(PCG64(seed))
    config = BenchmarkConfig(seed=seed, total_days=total_days, initial_cash=initial_cash)

    # Instantiate customer sim with an OpenAI client (so the openai fallback path
    # can be exercised if the config is flipped). Bedrock is the primary path.
    try:
        from openai import OpenAI
        openai_client = OpenAI()
    except Exception:
        openai_client = None

    customer_sim = CustomerSimulator(client=openai_client, conn=conn, config=config)

    # Trigger lazy bedrock init + wrap its messages.create BEFORE step_day runs.
    _wrap_bedrock(customer_sim.bedrock_client)
    _wrap_openai_responses(customer_sim.client)

    simulator = Simulator(conn, config, rng, customer_simulator=customer_sim)
    simulator.initialize(resume=True)
    simulator.current_day = current_day
    try:
        simulator.restore_rng_states()
    except Exception as e:
        print(f"  (rng restore skipped: {e})")

    # Wrap logical phase boundaries so every LLM call is tagged.
    _wrap_phase(simulator, "_generate_competitor_event_posts", "competitor_event_posts")
    _wrap_phase(simulator, "_submit_social_posts_async",        "social_posts_submit")
    _wrap_phase(simulator, "_collect_social_posts_async",       "social_posts_collect")
    _wrap_phase(simulator, "_process_agent_social_posts",       "agent_social_posts")
    _wrap_phase(simulator, "_process_issues",                   "process_issues")
    _wrap_phase(simulator, "_update_customer_satisfaction",     "update_satisfaction")
    _wrap_phase(simulator, "_process_enterprise_negotiations",  "enterprise_negs")
    _wrap_phase(simulator, "_generate_new_customers",           "generate_customers")
    _wrap_phase(simulator, "_process_billing",                  "process_billing")
    _wrap_phase(simulator, "_process_billing_decisions",        "billing_decisions")

    print(f"\n=== Running {args.runs} consecutive step_days "
          f"(day {current_day+1} .. {current_day+args.runs}) ===")

    per_day: list[dict] = []

    for i in range(args.runs):
        _CURRENT_DAY_HOLDER["day"] = simulator.current_day + 1
        start = time.monotonic()
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            simulator.step_day()
        elapsed = time.monotonic() - start
        stderr_text = captured.getvalue()

        # LLM calls this day only
        with _LLM_CALLS_LOCK:
            day_calls = [c for c in _LLM_CALLS if c["day"] == simulator.current_day]
        day_llm_sum = sum(c["elapsed_s"] for c in day_calls)
        day_llm_n = len(day_calls)
        day_llm_max = max((c["elapsed_s"] for c in day_calls), default=0.0)

        per_day.append({
            "day": simulator.current_day,
            "elapsed_s": elapsed,
            "llm_n": day_llm_n,
            "llm_sum_s": day_llm_sum,
            "llm_max_s": day_llm_max,
            "stderr": stderr_text,
        })

        print(f"  day {simulator.current_day}: total {elapsed:6.2f}s | "
              f"{day_llm_n:3d} LLM calls sum={day_llm_sum:6.1f}s max={day_llm_max:6.1f}s")

    # -------------------------------------------------------------------------
    # Report
    # -------------------------------------------------------------------------
    total_wall = sum(d["elapsed_s"] for d in per_day)
    total_llm_wall = sum(d["llm_sum_s"] for d in per_day)
    total_llm_n = sum(d["llm_n"] for d in per_day)

    print("\n=== Week summary ===")
    print(f"  step_days run:       {len(per_day)}")
    print(f"  total wall time:     {total_wall:.1f}s  ({total_wall/len(per_day):.1f}s/day)")
    print(f"  total LLM calls:     {total_llm_n}")
    print(f"  total LLM wall-sum:  {total_llm_wall:.1f}s  "
          f"({total_llm_wall/max(total_llm_n,1):.2f}s/call avg)")
    print(f"  LLM fraction of wall (incl. parallelism): "
          f"{(total_llm_wall/total_wall*100) if total_wall else 0:.0f}%")

    print("\n=== Per-phase totals (inclusive, summed across days) ===")
    phase_rows = sorted(PHASE_TIMES.items(), key=lambda kv: -sum(kv[1]))
    for phase, times in phase_rows:
        s = sum(times)
        print(f"  {phase:28s} {s:8.2f}s total   "
              f"{s/len(per_day):6.2f}s/day  (n_calls={len(times)})")

    print("\n=== Per-phase LLM call breakdown ===")
    phase_call_stats: dict[str, dict] = defaultdict(lambda: {"n": 0, "sum": 0.0, "max": 0.0, "tail_p99": 0.0})
    phase_samples: dict[str, list[float]] = defaultdict(list)
    for c in _LLM_CALLS:
        p = c["phase"]
        phase_call_stats[p]["n"] += 1
        phase_call_stats[p]["sum"] += c["elapsed_s"]
        phase_call_stats[p]["max"] = max(phase_call_stats[p]["max"], c["elapsed_s"])
        phase_samples[p].append(c["elapsed_s"])
    for p, samples in phase_samples.items():
        samples.sort()
        if samples:
            idx = max(0, int(len(samples) * 0.99) - 1)
            phase_call_stats[p]["tail_p99"] = samples[idx]
            mid = len(samples) // 2
            phase_call_stats[p]["p50"] = samples[mid]

    print(f"  {'phase':28s} {'n':>4s} {'sum_s':>8s} {'avg_s':>6s} {'p50':>6s} {'p99':>6s} {'max':>6s}")
    for p, stats in sorted(phase_call_stats.items(), key=lambda kv: -kv[1]["sum"]):
        avg = stats["sum"] / max(stats["n"], 1)
        p50 = stats.get("p50", 0.0)
        print(f"  {p:28s} {stats['n']:>4d} {stats['sum']:>8.1f} {avg:>6.2f} "
              f"{p50:>6.2f} {stats['tail_p99']:>6.2f} {stats['max']:>6.2f}")

    print("\n=== Per-day [step_day] stderr ===")
    for d in per_day:
        print(f"\n  day {d['day']}: total {d['elapsed_s']:.2f}s")
        for line in d["stderr"].splitlines():
            if line.startswith("[step_day]") or line.startswith("[entsim]") or line.startswith("[step_week]"):
                print(f"    {line}")

    if args.out_json:
        args.out_json.write_text(json.dumps({
            "per_day": [{k: v for k, v in d.items() if k != "stderr"} for d in per_day],
            "llm_calls": _LLM_CALLS,
            "phase_times": {k: list(v) for k, v in PHASE_TIMES.items()},
        }, indent=2))
        print(f"\n  wrote detailed JSON -> {args.out_json}")


if __name__ == "__main__":
    main()
