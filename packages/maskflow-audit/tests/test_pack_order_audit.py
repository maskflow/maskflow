"""maskflow-audit imports both packs, so it inherits the ordering hazard.

Both packs register PERSON_NAME and a PERSON NER recognizer, and the LAST
registration wins. pack-india extends pack-intl's, so pack-intl must be
imported first -- the reverse order silently drops pack-india's
span_filter and its Devanagari context keywords.

This is easy to get wrong from a distance: importing
`maskflow_pack_india.checksums` for a checksum helper is enough to
register pack-india first, and then any later `import maskflow_pack_intl`
anywhere in the process re-registers PERSON last and wins (a second
`import maskflow_pack_india` is a no-op, so it cannot win it back). That
is exactly how this package's own conftest broke
maskflow-cli's test_cli_pack_registration.py.
"""

from __future__ import annotations

import inspect

import maskflow_audit
from maskflow_core.context import CONTEXT_KEYWORDS
from maskflow_core.entities import PIIType
from maskflow_core.registry import NER_RECOGNIZERS
from maskflow_pack_india import _plausible_person_entity


def test_pack_india_wins_person_registration() -> None:
    assert NER_RECOGNIZERS["PERSON"].span_filter is _plausible_person_entity
    assert "नाम" in CONTEXT_KEYWORDS[PIIType.register("PERSON_NAME")]


def test_the_package_imports_pack_intl_before_pack_india() -> None:
    source = inspect.getsource(maskflow_audit)
    assert source.index("import maskflow_pack_intl") < source.index("import maskflow_pack_india"), (
        "pack-intl must be imported before pack-india; see this module's docstring"
    )
