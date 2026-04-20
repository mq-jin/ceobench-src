"""Profile a single step_day() call on a resumed session to find slow spots."""
import cProfile
import pstats
import time
import json
import sys
from pathlib import Path
from numpy.random import Generator, PCG64

from saas_bench.db_protection import load_session_db
from saas_bench.config import BenchmarkConfig
from saas_bench.simulation import Simulator
from saas_bench.customer_llm import CustomerSimulator

BASE = Path("bash_agent_runs/run_e5f93da7_debug/agent_workspace")
SESSION_ID = "02377aa9e79b"

sdir = BASE / "sessions" / SESSION_ID
meta = json.loads((sdir / "session.json").read_text())
seed = meta["seed"]
total_days = meta["total_days"]
current_day = meta["current_day"]
initial_cash = meta["initial_cash"]
print(f"Resuming session {SESSION_ID} at day {current_day} (seed {seed}, total_days {total_days})")

t0 = time.time()
conn = load_session_db(sdir / "world.nmdb")
print(f"  load_session_db: {time.time()-t0:.2f}s")

t0 = time.time()
conn.execute("ANALYZE")
print(f"  ANALYZE: {time.time()-t0:.2f}s")

try:
    conn.execute("ALTER TABLE agent_social_media_posts ADD COLUMN reasoning_by_group TEXT NOT NULL DEFAULT '{}'")
except Exception:
    pass

rng = Generator(PCG64(seed))
config = BenchmarkConfig(seed=seed, total_days=total_days, initial_cash=initial_cash)

customer_sim = CustomerSimulator(client=None, conn=conn, config=config)
simulator = Simulator(conn, config, rng, customer_simulator=customer_sim)
simulator.initialize(resume=True)
simulator.current_day = current_day

t0 = time.time()
ok = simulator.restore_rng_states()
print(f"  restore_rng_states: ok={ok}, {time.time()-t0:.2f}s")

print(f"\nProfiling step_day() for day {current_day + 1}...")
pr = cProfile.Profile()
t0 = time.time()
pr.enable()
result = simulator.step_day()
pr.disable()
elapsed = time.time() - t0
print(f"step_day elapsed: {elapsed:.2f}s")
print(f"  new day: {simulator.current_day}")
print(f"  cash: ${result.cash:,.0f}")

pr.dump_stats("/tmp/step_day_profile.prof")
stats = pstats.Stats(pr)
stats.sort_stats("cumulative")
print("\n=== Top 30 by cumulative time ===")
stats.print_stats(30)

stats.sort_stats("tottime")
print("\n=== Top 30 by total time (self) ===")
stats.print_stats(30)
