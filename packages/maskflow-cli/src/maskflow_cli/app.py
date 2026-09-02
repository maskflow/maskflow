"""Root CLI: `maskflow ...` (console script entry point, see pyproject.toml)."""

from __future__ import annotations

import maskflow_pack_india  # noqa: F401 -- import side effect registers pack-india's entity types
import maskflow_pack_intl  # noqa: F401 -- import side effect registers pack-intl's entity types
import typer

from .commands.config_cmd import app as config_app
from .commands.doctor_cmd import doctor
from .commands.explain_cmd import explain
from .scan.cmd import scan

app = typer.Typer(help="MaskFlow: reversible PII masking for LLM calls.", no_args_is_help=True)
app.add_typer(config_app, name="config")
app.command("doctor")(doctor)
app.command("explain")(explain)
app.command("scan")(scan)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
