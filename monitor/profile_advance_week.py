"""Profile the full advance_week() path on a snapshot (matches prod exactly).

This replays ONE full next-week on the session snapshot with:
  - shock_manager
  - event_logger
  - dashboard building
  - day_callback that calls save_session_db (the 46s bottleneck)
  - step_week inside (7× step_day with _suppress_customer_posts logic)

Every phase wall time is logged. LLM calls are traced.

Usage:
    uv run python monitor/profile_advance_week.py \\
        --session-dir <snapshot_session_dir> \\
        --weeks 1 \\
        --with-save
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

from saas_bench.config import BenchmarkConfig, SCENARIO_PACKS, ScenarioPack  # noqa: E402
from saas_bench.db_protection import load_session_db, save_session_db  # noqa: E402
from saas_bench.simulation import Simulator  # noqa: E402
from saas_bench.customer_llm import CustomerSimulator  # noqa: E402
from saas_bench.tools import AgentTools  # noqa: E402
from saas_bench.api_server import NovaMindAPIServer  # noqa: E402
from saas_bench.shocks import ShockManager  # noqa: E402
from saas_bench.event_logger import EventLogger  # noqa: E402


_CURRENT_PHASE = {"phase": "?"}
_LLM_CALLS: list[dict] = []
_LOCK = threading.Lock()
PHASE_TIMES: dict[str, list[float]] = defaultdict(list)


def _record(provider, elapsed, in_tok, out_tok, ok, err=""):
    with _LOCK:
        _LLM_CALLS.append({
            "phase": _CURRENT_PHASE["phase"],
            "provider": provider,
            "elapsed_s": elapsed,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "ok": ok,
            "err": err[:200],
        })


def _wrap_bedrock(client):
    orig = client.messages.create

    def traced(*a, **kw):
        t0 = time.monotonic()
        try:
            resp = orig(*a, **kw)
            el = time.monotonic() - t0
            try:
                in_tok = resp.usage.input_tokens
                out_tok = resp.usage.output_tokens
            except Exception:
                in_tok, out_tok = 0, 0
            _record("bedrock", el, in_tok, out_tok, True)
            return resp
        except Exception as e:
            _record("bedrock", time.monotonic() - t0, 0, 0, False, repr(e))
            raise

    client.messages.create = traced


def _wrap_openai(client):
    if client is None or not hasattr(client, "responses"):
        return
    orig = client.responses.create

    def traced(*a, **kw):
        t0 = time.monotonic()
        try:
            resp = orig(*a, **kw)
            el = time.monotonic() - t0
            try:
                in_tok = resp.usage.input_tokens
                out_tok = resp.usage.output_tokens
            except Exception:
                in_tok, out_tok = 0, 0
            _record("openai", el, in_tok, out_tok, True)
            return resp
        except Exception as e:
            _record("openai", time.monotonic() - t0, 0, 0, False, repr(e))
            raise

    client.responses.create = traced


def _wrap_phase(obj, method_name: str, phase_label: str):
    if not hasattr(obj, method_name):
        return
    original = getattr(obj, method_name)

    def wrapper(*a, **kw):
        prev = _CURRENT_PHASE["phase"]
        _CURRENT_PHASE["phase"] = phase_label
        t0 = time.monotonic()
        try:
            return original(*a, **kw)
        finally:
            _CURRENT_PHASE["phase"] = prev
            PHASE_TIMES[phase_label].append(time.monotonic() - t0)

    setattr(obj, method_name, wrapper)


def _wrap_module_fn(module, fn_name: str, phase_label: str):
    """Wrap a module-level function (e.g., save_session_db) for timing."""
    if not hasattr(module, fn_name):
        return
    original = getattr(module, fn_name)

    def wrapper(*a, **kw):
        t0 = time.monotonic()
        try:
            return original(*a, **kw)
        finally:
            PHASE_TIMES[phase_label].append(time.monotonic() - t0)

    setattr(module, fn_name, wrapper)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-dir", type=Path, required=True,
                    help="Session directory containing session.json + world.nmdb")
    ap.add_argument("--weeks", type=int, default=1)
    ap.add_argument("--no-save", action="store_true",
                    help="Skip save_session_db in day_callback (to isolate sim cost)")
    ap.add_argument("--out-json", type=Path, default=None)
    args = ap.parse_args()

    session_dir = args.session_dir
    meta_path = session_dir / "session.json"
    nmdb_path = session_dir / "world.nmdb"

    meta = json.loads(meta_path.read_text())
    seed = meta["seed"]
    total_days = meta["total_days"]
    current_day = meta.get("current_day", 0)
    initial_cash = meta["initial_cash"]
    session_id = meta["session_id"]

    print(f"Session: {session_id}")
    print(f"  seed={seed}, total_days={total_days}, current_day={current_day}")
    print(f"  nmdb: {nmdb_path} ({nmdb_path.stat().st_size / 1e6:.1f} MB)")

    # --- Instrument save_session_db BEFORE it's imported by anyone else ---
    import saas_bench.db_protection as dbp
    _wrap_module_fn(dbp, "save_session_db", "save_session_db")
    # Re-export the wrapper so api_server / server_entry pick it up
    import saas_bench.api_server as apis  # noqa
    import saas_bench.server_entry as se  # noqa

    # --- Load DB ---
    t0 = time.monotonic()
    conn = load_session_db(nmdb_path)
    print(f"  decrypt+load: {time.monotonic() - t0:.2f}s")

    # migration
    try:
        conn.execute("ALTER TABLE agent_social_media_posts "
                     "ADD COLUMN reasoning_by_group TEXT NOT NULL DEFAULT '{}'")
    except Exception:
        pass

    # --- Reconstruct world ---
    rng = Generator(PCG64(seed))
    config = BenchmarkConfig(seed=seed, total_days=total_days, initial_cash=initial_cash)

    try:
        from openai import OpenAI
        openai_client = OpenAI()
    except Exception:
        openai_client = None

    customer_sim = CustomerSimulator(client=openai_client, conn=conn, config=config)
    _wrap_bedrock(customer_sim.bedrock_client)
    _wrap_openai(customer_sim.client)

    simulator = Simulator(conn, config, rng, customer_simulator=customer_sim)
    simulator.initialize(resume=True)
    simulator.current_day = current_day
    try:
        simulator.restore_rng_states()
    except Exception as e:
        print(f"  (rng restore skipped: {e})")

    workspace = session_dir / "agent_workspace"
    workspace.mkdir(exist_ok=True)
    tools = AgentTools(conn, current_day, workspace, rng=rng, config=config, seed=seed)

    scenario_name = meta.get("scenario", "default")
    scenario_pack = SCENARIO_PACKS.get(scenario_name, ScenarioPack(
        name='Default', description='Balanced scenario'))
    shock_manager = ShockManager(conn, rng, scenario_pack)

    logs_dir = session_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    event_logger = EventLogger(
        run_id=session_id, output_dir=logs_dir,
        seed=seed, scenario="default",
        config={"seed": seed, "total_days": total_days},
    )
    simulator.set_event_logger(event_logger)
    tools.set_event_logger(event_logger)

    # --- Phase wrapping on simulator ---
    for method, label in [
        ("_generate_competitor_event_posts", "competitor_event_posts"),
        ("_submit_social_posts_async",        "social_posts_submit"),
        ("_collect_social_posts_async",       "social_posts_collect"),
        ("_process_agent_social_posts",       "agent_social_posts"),
        ("_process_issues",                   "process_issues"),
        ("_update_customer_satisfaction",     "update_satisfaction"),
        ("_process_enterprise_negotiations",  "enterprise_negs"),
        ("_generate_new_customers",           "generate_customers"),
        ("_process_billing",                  "process_billing"),
        ("_process_billing_decisions",        "billing_decisions"),
        ("step_day",                          "step_day_inclusive"),
        ("step_week",                         "step_week_inclusive"),
    ]:
        _wrap_phase(simulator, method, label)

    # --- day_callback: mirror server_entry._day_callback ---
    skip_save = args.no_save
    save_path = session_dir / "world_profile_save.nmdb"

    def day_callback(day, dashboard):
        meta["current_day"] = day
        # skip meta rewrite; negligible
        if not skip_save:
            t0 = time.monotonic()
            save_session_db(conn, save_path)
            PHASE_TIMES["day_callback_save"].append(time.monotonic() - t0)

    # Wrap shock_manager.check_and_generate_shocks
    _wrap_phase(shock_manager, "check_and_generate_shocks", "shock_check_per_day")

    # Wrap build_weekly_dashboard and get_thread_inbox_items (inside api_server.advance_week)
    import saas_bench.api_server as apis_mod
    if hasattr(apis_mod, "build_weekly_dashboard"):
        orig_dashboard = apis_mod.build_weekly_dashboard
        def wrapped_dashboard(*a, **kw):
            t0 = time.monotonic()
            try:
                return orig_dashboard(*a, **kw)
            finally:
                PHASE_TIMES["build_weekly_dashboard"].append(time.monotonic() - t0)
        apis_mod.build_weekly_dashboard = wrapped_dashboard

    # get_thread_inbox_items is imported inside advance_week()
    import saas_bench.environment as env_mod
    if hasattr(env_mod, "get_thread_inbox_items"):
        orig_inbox = env_mod.get_thread_inbox_items
        def wrapped_inbox(*a, **kw):
            t0 = time.monotonic()
            try:
                return orig_inbox(*a, **kw)
            finally:
                PHASE_TIMES["get_thread_inbox_items"].append(time.monotonic() - t0)
        env_mod.get_thread_inbox_items = wrapped_inbox

    # Also wrap shock_manager.get_inbox_items
    _wrap_phase(shock_manager, "get_inbox_items", "shock_get_inbox_items")

    # --- Build API server (we'll just call advance_week directly) ---
    api_server = NovaMindAPIServer(
        tools=tools, simulator=simulator, conn=conn,
        day_callback=day_callback,
        shock_manager=shock_manager,
        event_logger=event_logger,
    )

    # Wrap advance_week for outer timing
    _wrap_phase(api_server, "advance_week", "advance_week_total")

    # --- Run N weeks ---
    print(f"\n=== Running {args.weeks} advance_week() (from day {current_day}) ===")
    per_week = []
    for w in range(args.weeks):
        t0 = time.monotonic()
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            result = api_server.advance_week()
        elapsed = time.monotonic() - t0
        per_week.append({
            "week_index": w,
            "elapsed_s": elapsed,
            "success": result.get("success"),
            "new_day": result.get("day"),
            "stderr": captured.getvalue(),
        })
        print(f"  week {w+1}: elapsed={elapsed:.2f}s, success={result.get('success')}, "
              f"new_day={result.get('day')}")

    # --- Report ---
    total_wall = sum(w["elapsed_s"] for w in per_week)
    total_llm = sum(c["elapsed_s"] for c in _LLM_CALLS)
    n_llm = len(_LLM_CALLS)

    print("\n=== Overall ===")
    print(f"  weeks run:           {len(per_week)}")
    print(f"  total wall:          {total_wall:.1f}s  ({total_wall/max(len(per_week),1):.1f}s/week)")
    print(f"  total LLM calls:     {n_llm}")
    print(f"  total LLM wall-sum:  {total_llm:.1f}s")

    print("\n=== Per-phase wall time (inclusive, summed across all weeks) ===")
    rows = sorted(PHASE_TIMES.items(), key=lambda kv: -sum(kv[1]))
    for phase, times in rows:
        s = sum(times)
        n = len(times)
        print(f"  {phase:32s} {s:8.2f}s total   n={n:4d}   avg={s/max(n,1):.3f}s")

    print("\n=== Per-week stderr ===")
    for w in per_week:
        print(f"\n  week {w['week_index']+1}: elapsed={w['elapsed_s']:.2f}s new_day={w['new_day']}")
        for line in w["stderr"].splitlines():
            low = line.lower()
            if any(k in low for k in ("step_day", "step_week", "entsim", "bedrock", "retry")):
                print(f"    {line}")

    if args.out_json:
        args.out_json.write_text(json.dumps({
            "per_week": [{k: v for k, v in w.items() if k != "stderr"} for w in per_week],
            "phase_times": {k: list(v) for k, v in PHASE_TIMES.items()},
            "llm_calls": _LLM_CALLS,
        }, indent=2))
        print(f"\n  wrote JSON -> {args.out_json}")

    # Cleanup
    if save_path.exists():
        save_path.unlink()


if __name__ == "__main__":
    main()
