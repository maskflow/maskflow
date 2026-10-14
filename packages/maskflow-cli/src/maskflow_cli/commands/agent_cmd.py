"""`maskflow agent ...` -- passthrough to the `maskflow-agent` console script
(Claude Code PII guard: install / uninstall / doctor).

`maskflow-agent` is an **optional** dependency (`pip install
'maskflow-cli[agent]'`), imported lazily like `maskflow bench`. The hooks
themselves never go through this command: `maskflow-agent install` writes
`python -m maskflow_agent hook ...` so each tool call skips this CLI's
pack/typer import cost.
"""

from __future__ import annotations

import typer

_MISSING = (
    "`maskflow agent` needs the agent extra -- install it with: pip install 'maskflow-cli[agent]'"
)


def agent(ctx: typer.Context) -> None:
    """Claude Code PII guard: `maskflow agent install | uninstall | doctor`."""
    try:
        from maskflow_agent.cli import main as agent_main
    except ImportError:
        typer.echo(_MISSING, err=True)
        raise typer.Exit(code=1) from None
    raise typer.Exit(code=agent_main(list(ctx.args) or ["--help"]))
