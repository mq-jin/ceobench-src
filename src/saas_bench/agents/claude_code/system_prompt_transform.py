"""Build native CLI-agent instructions from the bash_agent system prompt.

The public repo ships the bash_agent system prompt (``system_prompt.md``) and
the shared ``simulator_instructions.md``. Claude Code and Codex drive the
simulator with native tools rather than the bash agent's bespoke 6-tool loop,
so this module substitutes the simulator instructions into the prompt and
swaps the bash-agent "## Tools" section for agent-specific native-tool
guidance.
"""
from __future__ import annotations

import re

_CLAUDE_CODE_TOOLS_SECTION = """## Tools

You are running as Claude Code — use your native tools (Bash, Read, Write,
Edit, Grep, Glob). Everywhere the instructions below mention `bash`,
`read_file`, `write_file`, `edit_file`, `search_files`, or `glob_files`, use
the corresponding native tool. Your working directory is the agent workspace;
run all simulator commands from here (e.g. `./novamind-operation status`).
"""

_CODEX_TOOLS_SECTION = """## Tools

You are running as Codex CLI. Use your native shell and file-editing tools.
Everywhere the instructions below mention `bash`, `read_file`, `write_file`,
`edit_file`, `search_files`, or `glob_files`, perform the corresponding
operation with your available native tools. Your working directory is the
agent workspace; run all simulator commands from here (for example,
`./novamind-operation status`).
"""


def _build_native_system_prompt(
    bash_prompt: str,
    sim_text: str,
    *,
    agent_title: str,
    tools_section: str,
) -> str:
    body = bash_prompt.replace("{simulator_instructions}", sim_text)
    body = body.replace("# SaaS Bench — Bash Agent", agent_title)
    return re.sub(
        r"## Tools\n.*?(?=\n## )",
        tools_section,
        body,
        count=1,
        flags=re.DOTALL,
    )


def build_claude_code_system_prompt(bash_prompt: str, sim_text: str) -> str:
    return _build_native_system_prompt(
        bash_prompt,
        sim_text,
        agent_title="# SaaS Bench — Claude Code Agent",
        tools_section=_CLAUDE_CODE_TOOLS_SECTION,
    )


def build_codex_system_prompt(bash_prompt: str, sim_text: str) -> str:
    """Build Codex CLI's AGENTS.md content."""
    return _build_native_system_prompt(
        bash_prompt,
        sim_text,
        agent_title="# SaaS Bench — Codex CLI Agent",
        tools_section=_CODEX_TOOLS_SECTION,
    )
