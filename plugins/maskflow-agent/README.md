# maskflow-agent — Claude Code plugin

The [maskflow-agent](../../packages/maskflow-agent) PII guard, packaged as a
Claude Code plugin: no `pip install` and no edits to your `settings.json`.

```
/plugin marketplace add maskflow/maskflow
/plugin install maskflow-agent@maskflow
```

From a shell, `claude plugin marketplace add maskflow/maskflow --sparse
.claude-plugin plugins` checks out only what the plugin needs.

Start a new session. If [uv](https://docs.astral.sh/uv/) is installed, the
first session builds the plugin's own environment (the pinned
`maskflow-agent` plus the spaCy English model, in the plugin's data
directory). That takes about a minute, once. Without uv, run
`pip install maskflow-agent`; the plugin then uses the `maskflow-agent` on
your PATH. Until one of these exists, every tool call is **denied**. The
guard never lets a tool run unmasked.

Use either the plugin or `maskflow-agent install`, not both: each one
installs the same hooks, so with both the hooks run twice. `maskflow-agent
doctor` flags this.

What it does, the threat model and the limits are in
[docs/agent.md](../../docs/agent.md) and on
[maskflow.in/agents](https://maskflow.in/agents).
