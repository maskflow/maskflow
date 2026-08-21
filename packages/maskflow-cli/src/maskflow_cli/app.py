"""Root CLI: `maskflow ...` (console script entry point, see pyproject.toml)."""

from __future__ import annotations

import typer

from .commands.config_cmd import app as config_app

app = typer.Typer(help="MaskFlow: reversible PII masking for LLM calls.", no_args_is_help=True)
app.add_typer(config_app, name="config")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
