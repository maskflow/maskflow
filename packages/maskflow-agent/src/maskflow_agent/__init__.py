"""MaskFlow guard for AI coding agents.

Claude Code hooks mask PII in every tool result before the model sees it and
restore real values only inside allowlisted commands, at run time, in a
wrapper process -- so the model, the transcript on disk and the permission
prompt only ever see placeholders.

Import-light on purpose: every hook invocation starts a fresh Python
process, so this package's top level and the hook client (`hooks.py`,
`protocol.py`, `config.py`, `paths.py`) use the standard library only. The
masking engine is imported by the per-session daemon (`daemon.py`) alone.
"""

__version__ = "0.1.3"
