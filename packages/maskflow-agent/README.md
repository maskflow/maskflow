# maskflow-agent

**Use AI coding agents on production data without Indian PII reaching the model.**

Hooks for Claude Code, and for GitHub Copilot, Cursor, Codex, Antigravity,
Gemini CLI, OpenCode, Cline and Devin Desktop, that mask personal data (Aadhaar, PAN, UPI IDs, mobile
numbers, bank accounts, names, ...) in every tool result before the model
sees it. Real values are restored only inside allowlisted database/kubectl
commands, at run time, in a separate process. The agent can still run
`UPDATE kyc ... WHERE pan='<PAN_3>'` against the right row without ever
seeing the PAN.

```bash
pip install maskflow-agent
maskflow-agent install        # adds hooks to .claude/settings.json
maskflow-agent doctor         # proves it end to end with synthetic canaries
```

Or as a Claude Code plugin, with no pip and no settings edits:

```
/plugin marketplace add maskflow/maskflow
/plugin install maskflow-agent@maskflow
```

- Tool output masked: Bash, Read, Grep, WebFetch, MCP, ...
- One placeholder per value for the whole session. A value identified once is
  masked everywhere after that.
- Fails closed: if the guard can't run, the tool doesn't either.
- Never grants permissions you didn't already have.
- The transcript on disk, the permission prompt and logs only ever see
  placeholders.
- MIT, no telemetry, everything runs locally.

Other agents (all **experimental** until verified in a live session):

```bash
maskflow-agent install --agent copilot      # Copilot CLI, cloud agent, VS Code agent mode
maskflow-agent install --agent cursor       # Cursor desktop + CLI
maskflow-agent install --agent codex        # OpenAI Codex CLI
maskflow-agent install --agent antigravity  # Google Antigravity CLI + IDE
maskflow-agent install --agent gemini       # Gemini CLI
maskflow-agent install --agent opencode     # OpenCode (local plugin file)
maskflow-agent install --agent cline        # Cline CLI/SDK (local plugin file)
maskflow-agent install --agent devin        # Devin Desktop / Windsurf
```

Agents whose hooks can't replace a tool's result run in *wrap mode*. Shell
commands run inside a masking wrapper, and built-in search and PII-holding
file reads are refused with a hint to use the shell. Coverage per agent is
in the docs below.

Claude Code needs 2.1.295+. Every agent runs on macOS or Linux. Full documentation, threat
model and limits:
[docs/agent.md](https://github.com/maskflow/maskflow/blob/main/docs/agent.md).
