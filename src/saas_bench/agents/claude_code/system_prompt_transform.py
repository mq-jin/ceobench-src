"""Build the Claude Code CLAUDE.md from the bash_agent system prompt.

The public repo ships the bash_agent system prompt (``system_prompt.md``) and
the shared ``simulator_instructions.md``. Claude Code drives the simulator with
its native tools rather than the bash agent's bespoke 6-tool loop, so this
module substitutes the simulator instructions into the prompt and swaps the
bash-agent "## Tools" section for native-tool guidance.
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


def build_claude_code_system_prompt(bash_prompt: str, sim_text: str) -> str:
    body = bash_prompt.replace("{simulator_instructions}", sim_text)
    body = body.replace(
        "# SaaS Bench — Bash Agent", "# SaaS Bench — Claude Code Agent"
    )
    # Replace the bash-agent tool table ("## Tools" up to the next "## "
    # heading) with the Claude Code native-tools note.
    body = re.sub(
        r"## Tools\n.*?(?=\n## )",
        _CLAUDE_CODE_TOOLS_SECTION,
        body,
        count=1,
        flags=re.DOTALL,
    )
    return body
