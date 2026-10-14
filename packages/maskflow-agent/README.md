# maskflow-agent

**Use Claude Code on production data without Indian PII reaching the model.**

Claude Code hooks that mask personal data (Aadhaar, PAN, UPI IDs, mobile
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

Requires Claude Code 2.1.295+ on macOS or Linux. Full documentation, threat
model and limits:
[docs/agent.md](https://github.com/maskflow/maskflow/blob/main/docs/agent.md).
