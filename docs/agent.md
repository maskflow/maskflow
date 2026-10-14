# maskflow-agent: PII guard for Claude Code

Use Claude Code on production data without Indian PII reaching the model.

A typical debugging session in a fintech, lending or health codebase looks
like: *"why is KYC failing for this user?"* → the agent runs `psql -c
"select * from kyc where ..."` → the rows hold an Aadhaar number, PAN,
mobile and bank account → all of it goes into the model's context.

`maskflow-agent` puts MaskFlow between Claude Code's tools and the model:

- **Every tool result is masked before the model sees it.** Shell output,
  file reads, searches, web fetches and MCP results. Aadhaar, PAN, UPI IDs,
  mobiles, bank accounts, names, ... become `<AADHAAR_1>`, `<PAN_3>`,
  `<INDIAN_MOBILE_2>`. The same value always gets the same placeholder in a
  session.
- **The agent can still act on a specific record.** In allowlisted
  database/kubectl commands the placeholders are swapped for the real values
  *when the command runs*, in a separate process. So
  `sqlite3 kyc.db "UPDATE kyc SET status='ok' WHERE pan='<PAN_3>'"` updates
  the right row, and the model never sees the PAN.
- **The transcript on disk, the permission prompt and Claude Code's logs only
  ever see placeholders.**

## Setup

```bash
pip install maskflow-agent          # or: pip install 'maskflow-cli[agent]'
python -m spacy download en_core_web_sm   # names/addresses; IDs work without it

cd your-project
maskflow-agent install              # writes .claude/settings.json (commit it to share)
maskflow-agent doctor               # proves it end to end with synthetic canaries
```

`install --scope local` writes `.claude/settings.local.json` (just you);
`--scope user` writes `~/.claude/settings.json` (every project).
`maskflow-agent uninstall` removes exactly the guard's hooks and nothing else.

Requirements: Claude Code **2.1.295+** (needed to block a tool when the guard
can't run), macOS or Linux (Windows isn't supported in 0.1).

## How it works

| Hook | What it does |
|---|---|
| `SessionStart` | Starts one masking daemon per session. It keeps the value ↔ placeholder mapping **in memory only**. Tells the model what placeholders are. |
| `PreToolUse` (every tool) | Makes sure the daemon is alive, and restarts it if not. Runs with `onFailure: block`, so **a tool never runs while its output can't be masked.** Wraps allowlisted commands that use placeholders. Refuses file edits that contain placeholders. |
| `PostToolUse` (every tool) | Replaces the tool result with its masked version, keeping the result's structure. |
| `UserPromptSubmit` | Warns when *you* type personal data. Prompts can't be masked, only warned about or blocked. |
| `SessionEnd` | Writes a counts-only summary to `~/.maskflow/agent/sessions/` and stops the daemon. |

A value identified once is masked everywhere after that, whatever its
context. A mobile seen under a `mobile` CSV header is also masked in a bare
`grep` hit or a headerless `sqlite3` row later.

### Placeholders → real values: when it does and doesn't happen

Placeholders are restored **only** when every command in the Bash command
line starts with an allowlisted program:
`psql mysql mariadb sqlite3 duckdb mongosh mongo redis-cli clickhouse-client cqlsh` and
`kubectl exec`.

Restoration does not happen:

- for anything else (`curl …/<PAN_3>` sends the literal text `<PAN_3>`).
- when the command line has a part that can't be read with certainty:
  `$(…)`, backticks, process substitution or unbalanced quotes.
- in `Write` / `Edit` / `MultiEdit` / `NotebookEdit`. These are refused
  outright, because writing a placeholder over real data would corrupt it.
  The agent is told to edit around them or ask you.

The hook rewrites the command to `python -m maskflow_agent exec --session …
--ticket … -- '<command with placeholders>'`. The ticket is single-use,
bound to that exact command text, and issued only by the hook. Without it,
the daemon refuses to restore anything. That covers both the model calling
the wrapper itself and anything talking to the daemon's socket directly.

**Permissions.** The guard never grants more than you already allowed. A
wrapped command is auto-approved only if *your* allow rules in
`settings.json` cover the original command. A matching deny rule still
denies, and a matching ask rule still asks. Otherwise Claude Code's normal
flow (prompt or auto mode) judges the wrapped command. Hooks can't see the
`--allowedTools` CLI flag, so put allow rules for wrapped commands in a
settings file.

### Configuration

`.claude/maskflow-agent.json` (or `~/.maskflow/agent/config.json`):

```json
{
  "unmask_allow_extra": ["my-db-cli"],
  "prompt_mode": "warn"
}
```

`unmask_allow` replaces the default allowlist instead of extending it.
`prompt_mode` is `warn` (default), `block` or `off`.

## Measured

- Real `claude -p` sessions on a synthetic KYC table: the agent read a CSV,
  updated the right row with `WHERE pan='<PAN_4>'`, and read it back.
  **0** of 20 synthetic identifiers appeared in the session transcript.
- Overhead: about **65 ms per hook** (p50, Apple M-series). That is mostly
  Python start-up plus one local socket round trip, so about 130 ms per tool
  call. A 200-row CSV result takes about 350 ms to mask.

## Limits

- **Threat model: accidental exposure, not a malicious agent.** An agent
  with shell access running as you can always reach the data some other way
  (for example `psql` with base64-encoded output, which isn't recognised as
  PII). Use read-only database roles and Claude Code permissions for that.
  The guard keeps routine debugging from shipping customer data to a model.
- **Detection is MaskFlow's.** A value seen only once, with no context and
  no checksum (a bare 10-digit number in a headerless row), can be missed.
  See the published IndiaPII benchmarks for per-entity accuracy.
- **Telemetry.** If you export Claude Code OpenTelemetry tool spans, they
  record the *original* tool output before hooks run. Commands wrapped for
  restoration are masked before Claude Code sees them; other tool output
  isn't.
- **A post-tool hook that crashes outright** (not an error inside it, which
  withholds the output) can't stop Claude Code from using the original
  output. The hook is a small standard-library client with a catch-all for
  that reason. `maskflow-agent doctor` tests this path.
- **`--resume` starts a new mapping.** Placeholders from before the resume
  can't be restored. New values never reuse their names: the restarted
  daemon reserves every placeholder already in the transcript.
- **Cursor is not supported yet.** Its hooks can only replace MCP tool
  output.
