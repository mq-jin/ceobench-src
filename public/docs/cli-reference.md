# NovaMind CLI Reference

## `novamind-operation`

The primary CLI for interacting with the NovaMind SaaS simulator.

### Session Management

#### `novamind-operation new-session`
Create a new simulation session.

```bash
novamind-operation new-session [--days 365] [--seed 42] [--cash 1000000]
```

**Options:**
- `--days`: Total simulation days (default: 365)
- `--seed`: Random seed for reproducibility (default: 42)
- `--cash`: Initial cash balance (default: 1,000,000)

**Returns:** JSON with `session_id`, `seed`, `total_days`, `initial_cash`, `workspace` path.

#### `novamind-operation list-sessions`
List all existing sessions.

```bash
novamind-operation list-sessions
```

#### `novamind-operation status [--session ID]`
Get the current status of a session.

```bash
novamind-operation status
novamind-operation status --session abc123def456
```

#### `novamind-operation stop [--session ID]`
Stop the simulation server for a session.

```bash
novamind-operation stop
```

---

### Simulation Control

#### `novamind-operation next-week <cash_1wk> <cash_4wk> <cash_12wk> [--session ID]`
Advance the simulation by one week (7 days). **Requires 3 cash predictions** as positional arguments — all three are mandatory, numeric (dollars).

```bash
novamind-operation next-week 1050000 1200000 1800000
```

**Arguments:**
- `cash_1wk`: Predicted cash 1 week from today (+7 days)
- `cash_4wk`: Predicted cash 4 weeks from today (+28 days)
- `cash_12wk`: Predicted cash 12 weeks from today (+84 days)

Predictions are stored in the `predictions` table at submission time and scored on percent error `(predicted - actual) / actual` when the actual cash at each horizon is known. The agent is evaluated on prediction accuracy at each horizon in addition to realized cash.

**Output:** The weekly dashboard showing cash, subscribers, MRR, this week's metrics, current config, product quality, and inbox notifications.

---

### Code Execution

#### `novamind-operation python <script.py> [--session ID]`
Execute a Python script in the simulation environment with `novamind_api` available.

```bash
novamind-operation python my_strategy.py
```

The script runs with `novamind_api` importable. Example script:
```python
import novamind_api as nm

# Set prices
nm.pricing.set_prices(A=25, B=69, C=179)

# Check current day
print(f"Day: {nm.vars.current_day}")

# Query data
result = nm.query("SELECT COUNT(*) as n FROM subscriptions WHERE status='active'")
print(f"Active subscribers: {result['rows'][0]['n']}")
```

#### `novamind-operation python-c "<code>" [--session ID]`
Execute inline Python code.

```bash
novamind-operation python-c "import novamind_api as nm; nm.pricing.set_prices(A=29.99)"
```

---

### Database Queries

#### `novamind-operation query "<SQL>" [--session ID]`
Execute a read-only SQL query against the simulation database.

```bash
novamind-operation query "SELECT * FROM subscriptions WHERE status='active' LIMIT 10"
novamind-operation query "SELECT group_id, COUNT(*) as n FROM subscriptions WHERE status='active' GROUP BY group_id"
```

**Restrictions:**
- Read-only (SELECT only) — no INSERT/UPDATE/DELETE
- Schema introspection blocked (no PRAGMA, sqlite_master)
- Some internal tables and columns are hidden
- Results capped at 5,000 rows

See `docs/tables-reference.md` for available tables and columns.

---

### History

#### `novamind-operation history [--tail N] [--session ID]`
View the action history for a session.

```bash
novamind-operation history
novamind-operation history --tail 100
```

Shows recent tool calls, queries, next-day advancements, and Python executions.

---

### Session ID

All commands accept `--session <id>` to target a specific session. If omitted, the most recently created session is used.

```bash
# These are equivalent (both use latest session):
novamind-operation next-day
novamind-operation next-day --session <latest-id>

# Target a specific session:
novamind-operation next-day --session abc123def456
```
