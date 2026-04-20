"""Test candidate rewrites for the slow open_issues dashboard query."""
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
from saas_bench.db_protection import load_session_db

NMDB = Path("bash_agent_runs/profile_af67e8ef_copy/agent_workspace/sessions/adf7b9a7b8c6/world.nmdb")

print(f"Loading {NMDB.name} ({NMDB.stat().st_size / 1e6:.1f} MB)...")
t0 = time.monotonic()
conn = load_session_db(NMDB)
print(f"  load: {time.monotonic() - t0:.1f}s\n")


def t(label, sql, params=()):
    t0 = time.monotonic()
    r = conn.execute(sql, params).fetchall()
    el = time.monotonic() - t0
    print(f"  [{el:6.2f}s] {label}  -> {r[0] if r else '(none)'}")
    return el


# Show the query plan for the slow query
print("=== EXPLAIN QUERY PLAN: original ===")
plan = conn.execute("""
    EXPLAIN QUERY PLAN
    SELECT COUNT(*) FROM customer_state cs
    JOIN subscriptions s ON cs.customer_id = s.customer_id
    WHERE s.status = 'subscribed' AND s.end_day IS NULL
      AND cs.open_issue_days > 0
""").fetchall()
for row in plan:
    print(f"  {dict(row)}")
print()

# Does customer_state have a PK / implicit rowid-based index on customer_id?
print("=== customer_state schema ===")
for row in conn.execute("SELECT sql FROM sqlite_master WHERE tbl_name='customer_state' AND type='table'").fetchall():
    print(f"  {row[0]}")
print()

# Baseline: repeat the original query
print("=== Candidate rewrites ===\n")
t("ORIGINAL (as written today)", """
    SELECT COUNT(*) FROM customer_state cs
    JOIN subscriptions s ON cs.customer_id = s.customer_id
    WHERE s.status = 'subscribed' AND s.end_day IS NULL
      AND cs.open_issue_days > 0
""")

# Rewrite 1: drive from customer_state (uses partial index idx_cs_open_issues)
t("R1: drive from customer_state, EXISTS", """
    SELECT COUNT(*) FROM customer_state cs
    WHERE cs.open_issue_days > 0
      AND EXISTS (
        SELECT 1 FROM subscriptions s
        WHERE s.customer_id = cs.customer_id
          AND s.status = 'subscribed' AND s.end_day IS NULL
      )
""")

# Rewrite 2: INDEXED BY to force planner
t("R2: explicit INDEXED BY idx_cs_open_issues", """
    SELECT COUNT(*) FROM customer_state cs INDEXED BY idx_cs_open_issues
    JOIN subscriptions s ON cs.customer_id = s.customer_id
    WHERE s.status = 'subscribed' AND s.end_day IS NULL
      AND cs.open_issue_days > 0
""")

# Rewrite 3: drive from subscriptions (partial index idx_subs_active_customer)
t("R3: drive from subscriptions (active), EXISTS", """
    SELECT COUNT(*) FROM subscriptions s
    WHERE s.status = 'subscribed' AND s.end_day IS NULL
      AND EXISTS (
        SELECT 1 FROM customer_state cs
        WHERE cs.customer_id = s.customer_id
          AND cs.open_issue_days > 0
      )
""")

# Rewrite 4: ANALYZE then retry original
print()
print("[running ANALYZE]")
t0 = time.monotonic()
conn.execute("ANALYZE")
print(f"  ANALYZE took {time.monotonic() - t0:.2f}s")
print()

t("R4: ORIGINAL after ANALYZE", """
    SELECT COUNT(*) FROM customer_state cs
    JOIN subscriptions s ON cs.customer_id = s.customer_id
    WHERE s.status = 'subscribed' AND s.end_day IS NULL
      AND cs.open_issue_days > 0
""")

print("\n=== EXPLAIN QUERY PLAN: after ANALYZE ===")
plan = conn.execute("""
    EXPLAIN QUERY PLAN
    SELECT COUNT(*) FROM customer_state cs
    JOIN subscriptions s ON cs.customer_id = s.customer_id
    WHERE s.status = 'subscribed' AND s.end_day IS NULL
      AND cs.open_issue_days > 0
""").fetchall()
for row in plan:
    print(f"  {dict(row)}")
