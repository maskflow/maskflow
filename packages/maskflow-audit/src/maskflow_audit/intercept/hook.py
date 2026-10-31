"""The in-child interception hook, loaded via `sitecustomize`.

The audit runs the project's own command -- its test suite, or a
user-defined flows script -- in a **subprocess**, because that is the only
way to intercept a suite that spawns its own interpreter, sets its own env,
or would otherwise be polluted by running inside the audit's process. The
patches must therefore be installed in the child, before any application
code imports its HTTP client, which is exactly what `sitecustomize` is for:
Python imports it automatically at startup if it is on `sys.path`.

**No payload ever reaches disk.** The child runs escape detection itself and
writes only metadata -- host, method, library, the stack, and which canary
types escaped in which form. The request body, which during a seeded run
contains canaries and may contain whatever else the application handles, is
searched in memory and discarded. A design that dumped payloads for the
parent to scan would leave real personal data in a temp file, which is
precisely what this tool exists to prevent.

Canary values reach the child through `MASKFLOW_AUDIT_CANARY_<TYPE>`
environment variables (see `seeding.adapters.EnvSeeder`), so they live only
in the child's ephemeral environment.
"""

from __future__ import annotations

import atexit
import json
import os
from typing import Any
from urllib.parse import urlsplit

#: Env var naming the file the child writes its findings to.
DUMP_PATH_VAR = "MASKFLOW_AUDIT_DUMP"

#: Prefix the seeder uses for canary values.
CANARY_PREFIX = "MASKFLOW_AUDIT_CANARY_"

#: The live interception context, held at module scope for the life of the
#: process. This is load-bearing, not tidiness: a `@contextmanager` object
#: left as a local is garbage-collected when install() returns, and
#: collecting a generator throws GeneratorExit at its `yield`, which runs
#: the ExitStack's __exit__ and silently UNDOES every patch. The symptom is
#: an audit that reports zero captures while the application's requests go
#: to the real provider -- the one failure this module must never have.
_ACTIVE: list[object] = []


def canaries_from_env() -> dict[str, tuple[str, int]]:
    """value -> (entity_type, identity), read from the environment."""
    out: dict[str, tuple[str, int]] = {}
    for key, value in os.environ.items():
        if key.startswith(CANARY_PREFIX) and value:
            out[value] = (key[len(CANARY_PREFIX) :], 0)
    return out


def install() -> bool:
    """Patch the transports for the life of this process.

    Returns False when there is nothing to do (no dump path configured),
    so a stray `sitecustomize` left on a path is harmless.
    """
    dump_path = os.environ.get(DUMP_PATH_VAR)
    if not dump_path:
        return False

    from ..escape.detect import find_escapes
    from .capture import CaptureStore
    from .transport import intercept

    canaries = canaries_from_env()
    store = CaptureStore()

    # Entered and never exited: the patches must outlive this function for
    # the whole run. The reference goes into _ACTIVE so the generator is not
    # collected -- see that constant.
    context = intercept(store)
    context.__enter__()
    _ACTIVE.append(context)

    def _dump() -> None:
        records: list[dict[str, Any]] = []
        for capture in store.captures:
            escapes = find_escapes(capture.payload, canaries)
            records.append(
                {
                    "host": capture.host,
                    "method": capture.method,
                    "library": capture.library,
                    # The URL path only. Not the query string (it can
                    # carry an API key) and not the host again.
                    "path": urlsplit(capture.url).path,
                    "stack": [
                        {"file": f.file, "line": f.line, "function": f.function}
                        for f in capture.stack
                    ],
                    "escapes": [
                        {"entity_type": e.entity_type, "form": e.form, "identity": e.identity}
                        for e in escapes
                    ],
                }
            )
        try:
            with open(dump_path, "w", encoding="utf-8") as handle:
                json.dump({"captures": records}, handle)
        except OSError:
            # The audit reports "the run produced no capture file" rather
            # than crashing somebody's test suite on the way out.
            pass

    atexit.register(_dump)
    return True
