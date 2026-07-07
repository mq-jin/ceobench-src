import sys

from saas_bench import _public_cli
from saas_bench.agents.bash_agent.agent import BashAgent
from saas_bench.agents.bash_agent.run_test import extract_dashboard_status


def test_bash_agent_detects_current_week_dashboard_header():
    agent = BashAgent([], client=object(), system_prompt="test")

    output = """before
=== Week 72 Dashboard (Day 504) ===

Cash: $7,220,368
Individual Subscribers: 0
after
"""

    assert agent.check_day_advanced(output)
    assert agent.day_advanced
    assert agent.new_dashboard.startswith("=== Week 72 Dashboard (Day 504) ===")


def test_extract_dashboard_status_from_current_header():
    status = extract_dashboard_status(
        """=== Week 72 Dashboard (Day 504) ===

Cash: $7,220,368
Individual Subscribers: 12,345
"""
    )

    assert status == {
        "day": 504,
        "cash": 7220368.0,
        "subscribers": 12345,
    }


def test_public_cli_uses_locked_api_port_when_env_port_is_unset(monkeypatch, tmp_path):
    zipapp = tmp_path / "novamind-operation"
    zipapp.write_text("")
    (tmp_path / ".novamind_api_port").write_text("54321")

    monkeypatch.setattr(sys, "argv", [str(zipapp)])
    monkeypatch.delenv("NOVAMIND_API_PORT", raising=False)

    assert _public_cli._resolve_session() == "__env__"
    assert _public_cli._ensure_server_running("__env__") == 54321
