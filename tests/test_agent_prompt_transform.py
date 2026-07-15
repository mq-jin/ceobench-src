from saas_bench.agents.claude_code.system_prompt_transform import (
    build_claude_code_system_prompt,
    build_codex_system_prompt,
)


_BASH_PROMPT = """# SaaS Bench — Bash Agent

## Tools

| Tool | Purpose |
|---|---|
| `bash` | Run commands |

## Objective

{simulator_instructions}
"""


def test_claude_code_prompt_uses_claude_native_tools():
    prompt = build_claude_code_system_prompt(_BASH_PROMPT, "Play the sim.")

    assert "# SaaS Bench — Claude Code Agent" in prompt
    assert "You are running as Claude Code" in prompt
    assert "Bash, Read, Write" in prompt
    assert "Play the sim." in prompt
    assert "| `bash` | Run commands |" not in prompt


def test_codex_prompt_uses_codex_native_tools():
    prompt = build_codex_system_prompt(_BASH_PROMPT, "Play the sim.")

    assert "# SaaS Bench — Codex CLI Agent" in prompt
    assert "You are running as Codex CLI" in prompt
    assert "Claude Code" not in prompt
    assert "Play the sim." in prompt
    assert "| `bash` | Run commands |" not in prompt
