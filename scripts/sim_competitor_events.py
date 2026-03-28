"""Run simulation without LLM to extract competitor events."""
import sqlite3
import sys
from pathlib import Path
from numpy.random import Generator, PCG64

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from saas_bench.config import BenchmarkConfig
from saas_bench.database import init_database
from saas_bench.simulation import Simulator

# Setup
config = BenchmarkConfig(total_days=730, seed=42)
db_path = Path('/tmp/sim_competitor_test.db')
db_path.unlink(missing_ok=True)

conn = init_database(db_path)
rng = Generator(PCG64(config.seed))

sim = Simulator(conn, config, rng)
sim.initialize()

# Step through all days with default config (no agent actions)
for day in range(1, config.total_days + 1):
    sim.step_day()

# Extract competitor events
events = conn.execute("""
    SELECT start_day, boost_amount, description
    FROM competitor_events
    ORDER BY start_day
""").fetchall()

print(f"Total competitor events: {len(events)}")
print(f"{'Day':>5} {'Boost':>10} Description")
print("-" * 80)
total_boost = 0
for e in events:
    day, boost, desc = e['start_day'], e['boost_amount'], e['description']
    total_boost += boost
    print(f"{day:>5} {boost:>10.4f} {desc}")

print("-" * 80)
print(f"{'TOTAL':>5} {total_boost:>10.4f}")

# Cleanup
conn.close()
db_path.unlink(missing_ok=True)
