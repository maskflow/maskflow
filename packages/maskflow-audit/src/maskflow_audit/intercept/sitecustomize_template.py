"""Template for the `sitecustomize.py` written into the child's sys.path.

Kept as a template string rather than a shipped `sitecustomize.py`, because
a module with that name inside an installed package would be imported by
every Python process that happened to have the package's directory on its
path -- including the audit's own.
"""

from __future__ import annotations

SITECUSTOMIZE = '''\
"""Written by `maskflow audit --prove`. Safe to delete.

Installs MaskFlow's egress interception for this process only: it does
nothing unless MASKFLOW_AUDIT_DUMP is set in the environment.
"""

try:
    from maskflow_audit.intercept.hook import install

    install()
except Exception:  # pragma: no cover -- never break the child's startup
    pass

# Chain to any sitecustomize the environment already had, so this does not
# silently disable somebody's own startup hook.
try:
    import os
    import sys

    _previous = os.environ.get("MASKFLOW_AUDIT_PREV_SITECUSTOMIZE")
    if _previous and _previous not in sys.path:
        sys.path.append(_previous)
except Exception:  # pragma: no cover
    pass
'''
