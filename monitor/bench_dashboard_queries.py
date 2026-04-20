"""Time each SQL query in build_weekly_dashboard on the snapshot to pinpoint which is slow."""
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")

from saas_bench.db_protection import load_session_db

NMDB = Path("bash_agent_runs/profile_af67e8ef_copy/agent_workspace/sessions/adf7b9a7b8c6/world.nmdb")

print(f"Loading {NMDB.name} ({NMDB.stat().st_size / 1e6:.1f} MB)")
t0 = time.monotonic()
conn = load_session_db(NMDB)
print(f"  load: {time.monotonic() - t0:.1f}s\n")

DAY = 250

def time_query(label, sql, params=()):
    t0 = time.monotonic()
    rows = conn.execute(sql, params).fetchall()
    el = time.monotonic() - t0
    print(f"  [{el:6.2f}s]  {label}  ({len(rows)} rows)")
    return el

print("=== Queries inside build_weekly_dashboard ===\n")

# get_config + get_cash + get_active_subscriber_count (these come from helpers, we time the
# equivalents directly)
time_query(
    "get_active_subscriber_count",
    "SELECT COUNT(*) FROM subscriptions WHERE status='subscribed' AND end_day IS NULL",
)

# open_issues
time_query(
    "open_issues (JOIN customer_state + subscriptions)",
    """
    SELECT COUNT(*) FROM customer_state cs
    JOIN subscriptions s ON cs.customer_id = s.customer_id
    WHERE s.status = 'subscribed' AND s.end_day IS NULL
      AND cs.open_issue_days > 0
    """,
)

# ind_subs fallback
time_query(
    "ind_subs fallback",
    """
    SELECT COUNT(*) FROM subscriptions s
    JOIN customers c ON s.customer_id = c.customer_id
    WHERE s.status = 'subscribed' AND s.end_day IS NULL
      AND c.customer_type = 'small'
    """,
)

# ent_seats fallback
time_query(
    "ent_seats fallback",
    """
    SELECT COALESCE(SUM(CAST(c.seat_count AS INTEGER)), 0) FROM subscriptions s
    JOIN customers c ON s.customer_id = c.customer_id
    WHERE s.status = 'subscribed' AND s.end_day IS NULL
      AND c.customer_type = 'large'
    """,
)

# q_shared_bonus
time_query(
    "q_shared_bonus",
    "SELECT value FROM global_state WHERE key = 'q_shared_bonus'",
)

# q_group_bonuses
time_query(
    "q_group_bonus_* LIKE scan",
    "SELECT key, value FROM global_state WHERE key LIKE 'q_group_bonus_%'",
)

# discovered groups (function call)
time_query(
    "get_discovered_groups-like query (proxy)",
    "SELECT DISTINCT group_id FROM customers WHERE group_id IS NOT NULL",
)

# agent posts query (day > 7 branch)
time_query(
    "agent_posts GROUP BY with LEFT JOIN",
    """
    SELECT asp.agent_post_id, asp.content, asp.views, asp.comment_post_ids,
           COUNT(smp.post_id) AS comment_count
    FROM agent_social_media_posts asp
    LEFT JOIN social_media_posts smp ON smp.reply_to_agent_post_id = asp.agent_post_id
    WHERE asp.day > ? AND asp.day <= ?
    GROUP BY asp.agent_post_id
    """,
    (DAY - 7, DAY),
)

print("\n=== Queries inside get_thread_inbox_items ===\n")

week_start = max(1, DAY - 6)
time_query(
    "new_threads",
    """
    SELECT COUNT(*) as cnt,
           COALESCE(SUM(CAST(c.seat_count AS INTEGER)), 0) as total_seats
    FROM enterprise_turns et
    JOIN customers c ON et.customer_id = c.customer_id
    WHERE et.turn_number = 0 AND et.day >= ? AND et.day <= ?
    """,
    (week_start, DAY),
)

time_query(
    "new_replies",
    """
    SELECT COUNT(*) as cnt
    FROM enterprise_turns et
    WHERE et.day >= ? AND et.day <= ? AND et.turn_number > 0 AND et.sender = 'customer'
    """,
    (week_start, DAY),
)

time_query(
    "awaiting (correlated subquery over enterprise_turns)",
    """
    SELECT COUNT(*) as cnt
    FROM enterprise_turns et
    WHERE et.message_id = (
        SELECT MAX(et2.message_id) FROM enterprise_turns et2
        WHERE et2.thread_id = et.thread_id
    )
    AND et.closed = 0
    AND et._internal_status IS NULL
    AND et.sender = 'customer'
    """,
)

# Also check table sizes
print("\n=== Table row counts ===")
for t in ["subscriptions", "customers", "customer_state", "issues", "enterprise_turns",
          "social_media_posts", "agent_social_media_posts", "daily_usage", "global_state"]:
    try:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:30s} {cnt:>12,d}")
    except Exception as e:
        print(f"  {t:30s} error: {e}")

print("\n=== Check for indices ===")
for t in ["subscriptions", "customers", "customer_state", "enterprise_turns",
          "social_media_posts", "agent_social_media_posts"]:
    idx = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=?", (t,)
    ).fetchall()
    print(f"  {t}:")
    for r in idx:
        print(f"    {r[0]}: {r[1]}")
