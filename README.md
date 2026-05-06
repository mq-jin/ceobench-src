<p align="center">
  <img src="assets/mascot.png" alt="CEO-Bench mascot" width="220"/>
</p>

# 🤖 CEO-Bench: Can Agents Play the Long Game?

Source repository for **CEO-Bench** — a long-horizon agent benchmark in which an
LLM agent operates a fictional B2B/B2C AI SaaS company for 500 simulated days.

This repo contains the simulator engine, the bash-agent baseline harness, and the
build pipeline that produces the public, tamper-resistant distribution
(`zlab-princeton/run-ceobench`) that any coding agent can download and play.

---

## 📊 Overview

<p align="center">
  <img src="assets/teaser.png" alt="CEO-Bench teaser" width="100%"/>
</p>

CEO-Bench evaluates general long-horizon agent capabilities by simulating a
startup over 500 days in a realistic and challenging environment. The agent
operates through a programmable interface with access to business databases,
company management tools, and social media. Outcomes are driven by a partially
observable, noisy, and evolving market with delayed and coupled consequences.

## 📝 What CEO-Bench tests

Language model agents are becoming proficient executors at isolated, short-horizon
tasks such as software engineering and customer service. Yet real-world challenges
require a combination of sophisticated skills that remain largely untested in
agents:

1. **Navigating long horizons amid uncertainty**
2. **Acquiring information in noisy environments**
3. **Adapting to a changing world**
4. **Orchestrating multiple moving parts toward a coherent goal**

CEO-Bench evaluates these capabilities together by simulating a representative
real-world task: operating a startup for 500 days. Given diverse and realistic
company-management tools, business databases, and social media, an agent needs to
design pricing strategies, allocate operation budgets, analyze business data,
respond to unexpected competitor moves, and more. Most state-of-the-art models
struggle to succeed in this environment, and only one model (**GPT-5.5**)
finishes the simulation above its $1M starting balance.

---

## 🚀 Running CEO-Bench

### 🔑 Step 0 — Environment variables

The simulator uses a small Claude model (**Haiku 4.5** by default) to generate
customer-facing social-media content during the simulation. Pick **one**
provider and export the matching credentials:

```bash
# Option A — Amazon Bedrock (default)
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-2"

# Option B — Anthropic direct API
export ANTHROPIC_API_KEY="sk-ant-..."

# Option C — OpenAI (Responses API)
export OPENAI_API_KEY="sk-..."
```

Then in `src/saas_bench/config.py`, set the matching provider/model:

```python
social_post_llm_model:    str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
social_post_llm_provider: str = "bedrock"   # "bedrock" | "anthropic" | "openai"
```

If you switch to `anthropic`, set `social_post_llm_model` to
`"claude-haiku-4-5-20251001"` (drop the Bedrock prefix/suffix).

You will also need `NMDB_KEY` set if you want to decrypt the simulation ledger
after a run (see [🔓 Decrypting the database](#-decrypting-the-database)).

---

### 🎯 Step 1A — Evaluate any coding agent (default config)

Most users should start here. The public, tamper-resistant distribution lives in a
separate repo:

➡️ **[zlab-princeton/run-ceobench](https://github.com/zlab-princeton/run-ceobench)**

It ships a single zipapp (`novamind-operation`), a generated `docs/` tree, and a
`requirements.txt`. The agent only ever sees the CLI and the encrypted `.nmdb`
ledger — engine sources are compiled to `.pyc` and never exposed.

Drop your coding agent (Claude Code, Cursor, GPT, Codex, …) into the
`run-ceobench` directory and prompt it with exactly:

```
Read instructions
```

The agent will discover `README.md` and `docs/`, learn the CLI, and start playing.
The score at the end is the agent's total cash on day 500.

🔓 The session ledger (`world.nmdb`) is encrypted so an agent cannot read it
directly. To analyze a finished run — including computing cash-on-hand on each
day — see [docs/decrypting-database.md](docs/decrypting-database.md).

---

### ⚙️ Step 1B — Customize the configuration

All tunable simulator constants live in **`src/saas_bench/config.py`** — pricing,
customer groups, ad-channel productivity, R&D speed, competitor difficulty, etc.
After editing, rebuild the public bundle so the agent sees the new world:

```bash
uv sync                                  # one-time install
uv run python scripts/build_public.py    # rebuild public/ artifact
```

Then deploy the regenerated `public/` directory the same way as Step 1A and run
your coding agent against it.

**Tuning competitor difficulty** is the most common knob. Every competitor event
draws `u ~ U(competitor_feedback_u_min, competitor_feedback_u_max)`; the applied
boost is `max(sampled_boost, u × unreleased_dev_bank)`. When the feedback term
wins, the competitor "consumes" `u × bank` from the player's unreleased
research stockpile.

| Difficulty | `competitor_feedback_u_min` | `competitor_feedback_u_max` | Behavior |
|------------|-----------------------------|-----------------------------|----------|
| Very easy  | 0.0                         | 0.1                         | Competitor barely catches up; bank stockpiling dominates |
| Easy       | 0.1                         | 0.3                         | Mild catch-up pressure |
| **Default**| **0.2**                     | **0.5**                     | Balanced — bank still useful but not invincible |
| Hard       | 0.3                         | 0.7                         | Stockpiling is risky; release cadence matters |
| Very hard  | 0.5                         | 0.9                         | Competitor eats most unreleased work |

Other competitor knobs in the same `# === COMPETITOR EVENT SYSTEM ===` block of
`config.py`: event frequency, lognormal boost distribution, magnitude scaling,
post engagement, severity tiers, competitor names + post perspectives, and
per-segment `q_bias` reactivity.

---

### 🤖 Step 1C — Replicate the bash-agent baseline

The bash-agent harness is the canonical baseline used to produce the numbers in
the paper. It gives the LLM a sandboxed bash shell and the public CLI, and runs
the day-by-day loop with checkpointing and full logging.

```bash
# Single run (Bedrock Sonnet 4.6, max reasoning effort)
uv run python -m saas_bench.agents.bash_agent.run_test \
    --model us.anthropic.claude-sonnet-4-6 \
    --provider bedrock \
    --reasoning-effort max \
    --seed 42 \
    --days 500 \
    --workspace bash_agent_runs
```

Convenience launchers wrap this with `nohup setsid` for long unattended runs:

```bash
bash scripts/start_fresh_sonnet_bash.sh      # Bedrock Sonnet 4.6, max effort
bash scripts/start_fresh_gpt_bash.sh         # OpenAI GPT-5.5, xhigh effort
bash scripts/resume_run.sh bash_agent_runs/run_<id>   # resume from checkpoint
```

Each run lands at `bash_agent_runs/run_<id>/` with `world.nmdb`, `messages.jsonl`,
`logs/`, `agent_workspace/` (a fresh git repo with weekly commits), `config.json`,
and `checkpoint.json`. Provider credentials needed at runtime depend on the
chosen model — see `agents/bash_agent/agent.py` for the full provider list
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `AWS_*`, `GOOGLE_API_KEY`, `XAI_API_KEY`,
`TOGETHER_API_KEY`, `MODAL_TOKEN_*`).

---

## 🔓 Decrypting the database

Session ledgers are stored as encrypted `.nmdb` files (HMAC-SHA256 stream cipher,
PBKDF2-derived key) so the agent can never read them directly. To decrypt a
finished run and compute per-day cash, revenue, customer counts, etc., see:

➡️ **[docs/decrypting-database.md](docs/decrypting-database.md)**

---

## 📁 Repo layout

```
ceobench-src/
├── README.md                          ← this file
├── assets/                            ← mascot, teaser, paper figures
├── docs/
│   └── decrypting-database.md         ← decrypt + cash-per-day guide
├── pyproject.toml, uv.lock, .python-version
├── public/                            ← built public artifact (submodule)
├── public_sources/                    ← human-written inputs to the public build
│   ├── README.md, requirements.txt
│   └── examples/{autoplay_loop,basic_strategy}.py
├── scripts/
│   ├── build_public.py                ← canonical public-repo builder
│   ├── start_fresh_sonnet_bash.sh     ← bash-agent launcher (Bedrock Sonnet)
│   ├── start_fresh_gpt_bash.sh        ← bash-agent launcher (OpenAI GPT)
│   └── resume_run.sh                  ← resume bash agent from checkpoint
└── src/saas_bench/                    ← simulator + bash agent
    ├── simulation.py, environment.py, shocks.py, event_logger.py
    ├── config.py                      ← all tunable constants
    ├── customer_llm.py, personas.py, enterprise.py
    ├── database.py, db_protection.py
    ├── api_server.py, server_entry.py, tools.py
    ├── novamind_api/, novamind_cli.py, _public_cli.py
    └── agents/bash_agent/             ← canonical baseline harness
```

---

## 📜 Citation

```bibtex
@article{ceobench2026,
  title  = {CEO-Bench: Can Agents Play the Long Game?},
  author = {<authors>},
  year   = {2026},
}
```
