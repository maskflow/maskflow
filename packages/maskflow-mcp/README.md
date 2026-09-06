<!-- mcp-name: io.github.maskflow/mcp -->

# maskflow-mcp

A [Model Context Protocol](https://modelcontextprotocol.io) proxy that
wraps any MCP server and keeps PII out of your agent's tool traffic. It
masks PII in outbound `tools/call` arguments before they reach the backend
tool, and restores the originals in the results, with placeholders that
stay consistent for the whole agent run.

Agents routinely pass user PII (names, emails, PAN, Aadhaar, phone numbers)
straight into third-party MCP servers as tool arguments. This proxy is a
drop-in shim that stops the real values at the boundary. It runs MaskFlow's
detection engine, so the Indian identifiers (Aadhaar, PAN, GSTIN, UPI,
IFSC, ABHA, Indian names / addresses) are covered alongside the generic PII.

MIT, no gates, no telemetry.

## Install

```bash
pip install maskflow-mcp
# or, no install:
uvx maskflow-mcp stdio --backend "npx -y @modelcontextprotocol/server-github"
```

Pulls `fastmcp` (the 2.x line, which does not bundle LLM vendor SDKs). The
first detection run downloads a small spaCy model; pass `--patterns-only`
to skip it.

## Use it

### stdio (Claude Desktop, most agents)

Point the agent at `maskflow-mcp` and give it the real server as `--backend`:

```jsonc
// claude_desktop_config.json
{
  "mcpServers": {
    "github": {
      "command": "maskflow-mcp",
      "args": ["stdio", "--backend", "npx -y @modelcontextprotocol/server-github",
               "--pass-env", "GITHUB_TOKEN"]
    }
  }
}
```

Or wrap a server already defined in a config file:

```bash
maskflow-mcp stdio --config ./claude_desktop_config.json --backend-name github
```

### HTTP

```bash
maskflow-mcp http --backend https://example.com/mcp --host 127.0.0.1 --port 9000
```

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--backend` | – | Backend command line, or a URL |
| `--config` / `--backend-name` | – | Read the backend from a Claude-Desktop-style JSON file |
| `--pass-env VAR` | – | Forward an env var to a stdio backend (repeatable) |
| `--min-confidence` | `0.5` | Detection threshold |
| `--patterns-only` | off | Skip the spaCy NER pass (faster; drops bare-name / address detection) |
| `--mask-tool-results` | off | Also mask PII the tool *introduced* in its result, not just unmask placeholders it echoed |
| `--session-ttl` | `3600` | Lifetime of a per-connection session |

## What is masked

`tools/call` arguments are walked (string and numeric *values* only, keys
never) and masked through the connection's session. The result's text and
structured content is unmasked, restoring placeholders the tool echoed. By
default raw PII that the tool *adds* to a result passes through untouched;
`--mask-tool-results` masks that too, so the agent never sees it.

`tools/list`, `prompts/*`, and `resources/*` pass through unchanged
(resource content masking is not on by default).

## PII safety

The token-to-value map lives in memory per connection and is never logged.
Only masked values cross the wire to the backend. See `docs/mcp.md` in the
MaskFlow repo for the design.
