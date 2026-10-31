"""`--handoff`: a task file for the user's own coding agent.

No key, no network, no model. This is the path most people should take: the
user already has Claude Code or Cursor open, with their repository's context
loaded and their own review habits. What they lack is a precise, gated
statement of the work -- which is exactly what the audit has.

The file is written to be pasted whole into an agent. It names the flow,
the evidence, the three fixes that fit MaskFlow, and -- critically -- the
same four gates `--fix` enforces, so a human-driven fix is held to the
identical standard.

No canary value, no column value, and no source line appears in it. Column
*names* do, because they are the actionable part.
"""

from __future__ import annotations

from pathlib import Path

from ..report.summary import AuditSummary, FlowRow

HANDOFF_FILENAME = "maskflow-audit-tasks.md"

_GATES = """\
A fix for any task below is finished only when **all four** of these hold.
Check them yourself; do not take the model's word for it.

1. **The project's tests pass** — unchanged. Never edit a test to make a
   gate green. If a test genuinely encodes the leak, say so and stop.
2. **Zero canaries escape on that flow** — re-run
   `maskflow audit --prove` and confirm the flow reports
   `canary_status: contained`, not `escaped` and not `not_exercised`.
3. **The round trip still works** — whatever the application showed a
   human before, it still shows. `unmask()` must be applied to the
   response wherever real values are expected, with the mapping from the
   matching `mask()` call. A masked prompt with an un-unmasked response is
   a broken feature, not a fix.
4. **No new network destination, permission, or secret** — the diff adds
   no URL, no `base_url`, no credential, no `subprocess`. The only new
   import should be MaskFlow's.
"""

_FIXES = """\
Pick whichever fits the codebase; they are listed cheapest-first.

- **Route through the gateway.** No code change beyond one `base_url`, and
  it covers every call that client makes:
  ```python
  client = OpenAI(base_url="http://maskflow-gateway:8000/v1", api_key=...)
  ```
  Best when the service makes many calls. Note the audit can only *see*
  this is a guard if the host is recognisable or the module carries a
  MaskFlow marker — otherwise it reports `unknown`, correctly.
- **Install the framework integration**, if this flow goes through
  LangChain / LlamaIndex / LiteLLM / MCP: `maskflow-langchain`,
  `maskflow-llamaindex`, `maskflow-litellm`, `maskflow-mcp`.
- **Wrap the call site** with `mask()` / `unmask()`:
  ```python
  from maskflow import mask, unmask

  masked, mapping = mask(prompt)
  answer = client.chat.completions.create(
      model=..., messages=[{"role": "user", "content": masked}]
  )
  return unmask(answer.choices[0].message.content, mapping)
  ```
  Keep the mapping alive across the whole round trip. Add no dependency
  other than MaskFlow's own, and match the surrounding style.
"""


def _task(flow: FlowRow, index: int) -> str:
    sources = (
        ", ".join(f"`{s.kind}:{s.detail}`" if s.detail else f"`{s.kind}`" for s in flow.sources)
        or "_not traced_"
    )

    if flow.canary_escapes:
        entities = sorted({e.entity_type for e in flow.canary_escapes})
        host = flow.canary_escapes[0].host
        stack = flow.canary_escapes[0].app_stack
        evidence = (
            f"**Proven.** A synthetic {', '.join(entities)} canary was observed "
            f"reaching `{host}` from this call site. Call path at send time:\n\n"
            + "\n".join(f"    {frame}" for frame in stack)
        )
    else:
        evidence = (
            f"**Predicted, not proven** (confidence: {flow.confidence}). Static "
            "analysis found no guard on this path; no canary run has confirmed it. "
            "Re-run with `--prove` for evidence before spending much time here."
        )

    return f"""\
## Task {index}: {flow.file}:{flow.line} — {flow.sink_id}

| | |
|---|---|
| Flow | `{flow.flow_id}` |
| Status | `{flow.masking_status}` |
| Destination | `{flow.provider}`{f" (`{flow.host}`)" if flow.host else ""} |
| Call | `{flow.call_path}` |
| Function | `{flow.function or "<module>"}` |
| Payload argument(s) | {", ".join(f"`{a}`" for a in flow.payload_args) or "_unknown_"} |
| Data reaching it | {sources} |

{evidence}

Why the audit flagged it: {flow.masking_reason}
"""


def build_handoff(summary: AuditSummary) -> str:
    """The full task document."""
    leaks = [f for f in summary.flows if f.canary_status == "escaped"]
    unguarded = [
        f
        for f in summary.flows
        if f.masking_status in {"unmasked", "unknown"} and f.canary_status != "escaped"
    ]
    # Confirmed leaks first, then predictions -- the same order the report
    # uses, for the same reason.
    ordered = leaks + unguarded

    if not ordered:
        return (
            "# MaskFlow audit — nothing to fix\n\n"
            f"{summary.headline}. No unmasked or unknown LLM egress path was found.\n\n"
            "**That means nothing known was found, not that nothing exists.** See the "
            "limits section of the audit report before treating this as a clean bill "
            "of health.\n"
        )

    tasks = "\n".join(_task(flow, i) for i, flow in enumerate(ordered, start=1))
    proven = len(leaks)
    return f"""\
# MaskFlow audit — {len(ordered)} path(s) to fix

Generated by `maskflow audit --handoff` on {summary.scope.generated_at.isoformat()}.
{summary.headline}; {proven} of these {"is" if proven == 1 else "are"} a **confirmed**
leak (a canary was observed reaching a provider), the rest are predicted from
static analysis.

Give this file to your coding agent. It contains no personal data, no canary
value, and no line of your source — only file paths, call paths, and the names
of the columns and fields involved.

## The gates

{_GATES}
## How to fix a flow

{_FIXES}
---

{tasks}"""


def write_handoff(path: Path, summary: AuditSummary) -> int:
    """Write the task file. Returns the number of tasks in it."""
    content = build_handoff(summary)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return content.count("\n## Task ")
