"""PyInstaller entry point for the standalone `maskflow` binary.

A thin module (not a console-script shim) so the spec has a concrete file
to analyse. Imports the packs explicitly -- in a frozen build the
`"maskflow.recognizers"` entry points are not always discoverable, but the
direct import side effect always registers the recognizers.
"""

from __future__ import annotations

import multiprocessing

import maskflow_pack_india  # noqa: F401
import maskflow_pack_intl  # noqa: F401
from maskflow_cli.app import main

if __name__ == "__main__":
    # MUST be first: when `scan --workers >1` spawns a pool, PyInstaller
    # re-launches this same binary as the worker with multiprocessing's own
    # argv (`-B -S -c ...`). freeze_support() intercepts that, runs the
    # worker, and exits -- without it Typer sees `-B` and aborts.
    multiprocessing.freeze_support()
    main()
