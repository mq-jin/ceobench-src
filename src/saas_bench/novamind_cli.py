"""NovaMind CLI — Command-line interface for the NovaMind SaaS simulator.

Two entry points:
    novamind-operation  — Simulation control (next-week)
    novamind            — Script management (register/list/remove daily scripts)
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


def _get_workspace() -> Path:
    """Get the agent workspace directory from environment."""
    ws = os.environ.get('NOVAMIND_WORKSPACE', '')
    if not ws:
        return Path.cwd()
    return Path(ws)


# =========================================================================
# novamind-operation CLI
# =========================================================================

def _cmd_next_week(args):
    """Advance the simulator by one week (7 days) — REQUIRES cash predictions.

    Usage:
        novamind-operation next-week <cash_1wk> <cash_4wk> <cash_12wk>

    Arguments (all required, all numeric, in dollars):
        cash_1wk   Predicted cash 1 week from today (+7 days).
        cash_4wk   Predicted cash 4 weeks from today (+28 days).
        cash_12wk  Predicted cash 12 weeks from today (+84 days).

    All three predictions are recorded at submission time and scored on
    percent error `(predicted - actual) / actual` once actual cash is known.
    You are evaluated on prediction accuracy at each horizon in addition
    to realized cash.

    Calls the API server to step the simulation forward by one week.
    Prints the dashboard to stdout, which includes key metrics,
    this week's results, and inbox notifications.

    **What happens each day (in order):**
    1. Daily calculations run (if registered)
    2. New customers spawned based on marketing + reputation
    3. Customers at billing day re-evaluate plans (may switch/cancel)
    4. Usage simulated, compute costs incurred
    5. Service metrics calculated (latency, errors, outages)
    6. Revenue collected from billing customers
    7. Fixed costs deducted (capacity, operations, development, advertising)
    8. Social posts generated based on satisfaction
    9. Enterprise negotiations processed (customer replies, timeouts)
    10. VC negotiations processed (counter-offers delivered)
    11. Each predefined VC independently rolls for daily approach
    12. Deal expiry processed (accepted-but-unsettled deals + stale threads)
    13. Reputation updated
    14. Dashboard built and returned

    **Dashboard includes:** CASH, MRR, SUBSCRIBERS, yesterday's metrics
    (revenue, costs, new/cancelled subs, usage, overload, outages), INBOX
    (new notifications), and current config summary.

    **NOTE:** The next_week call may take several minutes at large subscriber
    counts. This is normal — just wait for the response.

    Exit code 0 on success, 1 on failure (including missing predictions).
    """
    from .novamind_api._client import next_week
    predictions = {
        "cash_1wk": float(args.cash_1wk),
        "cash_4wk": float(args.cash_4wk),
        "cash_12wk": float(args.cash_12wk),
    }
    try:
        result = next_week(predictions=predictions)
        dashboard = result.get('dashboard', '')
        print(dashboard)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def operation_main():
    """Entry point for novamind-operation CLI.

    Commands:
        next-week   Advance the simulation by one week (7 days).
                    REQUIRES 3 cash predictions as positional args.

    Examples:
        ./novamind-operation next-week 1050000 1200000 1800000
    """
    parser = argparse.ArgumentParser(
        prog='novamind-operation',
        description='NovaMind simulator operation commands',
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    # next-week (requires predictions)
    sub_next = subparsers.add_parser(
        'next-week',
        help='Advance by 7 days. Requires 3 cash predictions (+7d, +28d, +84d).',
    )
    sub_next.add_argument('cash_1wk', type=float,
                          help='Predicted cash 1 week from today (+7 days)')
    sub_next.add_argument('cash_4wk', type=float,
                          help='Predicted cash 4 weeks from today (+28 days)')
    sub_next.add_argument('cash_12wk', type=float,
                          help='Predicted cash 12 weeks from today (+84 days)')
    sub_next.set_defaults(func=_cmd_next_week)

    args = parser.parse_args()
    args.func(args)


# =========================================================================
# novamind CLI (daily script management)
# =========================================================================

def _daily_scripts_dir() -> Path:
    """Get the daily scripts directory."""
    ws = _get_workspace()
    d = ws / 'daily_scripts'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cmd_register_daily_script(args):
    """Register a Python script to run automatically at the start of each day.

    The script content is snapshotted at registration time. Subsequent edits
    to the source file will NOT affect the registered version. To update,
    re-register the script.

    If a script with the same filename already exists, it is overwritten.
    Scripts are executed in alphabetical order at the start of each day,
    with novamind_api pre-imported.

    Args:
        script_path: Path to the Python script to register.

    Example:
        novamind register-daily-script my_strategy.py
    """
    src = Path(args.script_path)
    if not src.exists():
        print(f"Error: File not found: {src}", file=sys.stderr)
        sys.exit(1)

    content = src.read_text()

    # Also copy to daily_scripts/ for agent reference
    dst = _daily_scripts_dir() / src.name
    shutil.copy2(src, dst)

    # Register snapshot with the API server
    from .novamind_api._client import _post
    try:
        result = _post('/daily-scripts', {'name': src.name, 'content': content})
        print(json.dumps({"success": True, "registered": src.name, "path": str(dst)}))
    except Exception as e:
        print(f"Error registering with API server: {e}", file=sys.stderr)
        # Still registered locally via file copy, print success
        print(json.dumps({"success": True, "registered": src.name, "path": str(dst),
                          "warning": "Snapshot not saved to server"}))


def _cmd_list_daily_scripts(args):
    """List all registered daily scripts.

    Shows script names and sizes. Scripts run at the start of each day
    in alphabetical order.

    Example:
        novamind list-daily-scripts
    """
    from .novamind_api._client import _get
    try:
        result = _get('/daily-scripts')
        print(json.dumps(result.get('data', result)))
    except Exception:
        # Fallback to local file listing
        scripts_dir = _daily_scripts_dir()
        scripts = sorted(scripts_dir.glob('*.py'))
        result = []
        for s in scripts:
            result.append({"name": s.name, "size": s.stat().st_size})
        print(json.dumps({"scripts": result}))


def _cmd_remove_daily_script(args):
    """Remove a registered daily script.

    Args:
        script_name: Filename of the script to remove.

    Example:
        novamind remove-daily-script my_strategy.py
    """
    # Remove from API server snapshot store
    from .novamind_api._client import _delete
    try:
        _delete('/daily-scripts', {'name': args.script_name})
    except Exception:
        pass  # Best effort

    # Also remove local file
    target = _daily_scripts_dir() / args.script_name
    if target.exists():
        target.unlink()

    print(json.dumps({"success": True, "removed": args.script_name}))


def novamind_main():
    """Entry point for novamind CLI.

    Commands:
        register-daily-script   Register a script to run daily
        list-daily-scripts      List all registered daily scripts
        remove-daily-script     Remove a registered daily script

    Examples:
        novamind register-daily-script strategy.py
        novamind list-daily-scripts
        novamind remove-daily-script strategy.py
    """
    parser = argparse.ArgumentParser(
        prog='novamind',
        description='NovaMind daily script management',
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    # register-daily-script
    sub_reg = subparsers.add_parser('register-daily-script', help='Register a daily script')
    sub_reg.add_argument('script_path', help='Path to the Python script')
    sub_reg.set_defaults(func=_cmd_register_daily_script)

    # list-daily-scripts
    sub_list = subparsers.add_parser('list-daily-scripts', help='List registered daily scripts')
    sub_list.set_defaults(func=_cmd_list_daily_scripts)

    # remove-daily-script
    sub_rm = subparsers.add_parser('remove-daily-script', help='Remove a daily script')
    sub_rm.add_argument('script_name', help='Filename of the script to remove')
    sub_rm.set_defaults(func=_cmd_remove_daily_script)

    args = parser.parse_args()
    args.func(args)


# =========================================================================
# CLI documentation generator
# =========================================================================

def get_cli_docs() -> str:
    """Generate CLI documentation from docstrings.

    Renders documentation for all CLI commands programmatically
    from their docstrings.

    Returns:
        Markdown-formatted CLI reference.
    """
    lines = [
        "# CEOBench CLI Reference",
        "",
        "## novamind-operation",
        "",
        f"{operation_main.__doc__}",
        "",
        "### Commands",
        "",
    ]

    # operation commands
    op_commands = [
        ("next-week", _cmd_next_week),
    ]
    for name, func in op_commands:
        doc = func.__doc__ or "No documentation."
        lines.append(f"#### `./novamind-operation {name}`")
        lines.append("")
        lines.append(doc.strip())
        lines.append("")

    lines.extend([
        "## novamind",
        "",
        f"{novamind_main.__doc__}",
        "",
        "### Commands",
        "",
    ])

    # novamind commands
    nm_commands = [
        ("register-daily-script", _cmd_register_daily_script),
        ("list-daily-scripts", _cmd_list_daily_scripts),
        ("remove-daily-script", _cmd_remove_daily_script),
    ]
    for name, func in nm_commands:
        doc = func.__doc__ or "No documentation."
        lines.append(f"#### `novamind {name}`")
        lines.append("")
        lines.append(doc.strip())
        lines.append("")

    return "\n".join(lines)
