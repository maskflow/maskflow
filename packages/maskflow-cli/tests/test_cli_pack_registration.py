"""The CLI imports both recognizer packs itself; pack-india must register
after pack-intl so its PERSON_NAME context keywords and spaCy mapping win
(see maskflow_cli/app.py and scan/worker.py)."""

import maskflow_cli.app  # noqa: F401 -- import side effect registers both packs
from maskflow_cli.scan import worker
from maskflow_core.context import CONTEXT_KEYWORDS
from maskflow_core.entities import PIIType
from maskflow_core.registry import NER_RECOGNIZERS
from maskflow_pack_india import _plausible_person_entity


def test_cli_registers_pack_india_last() -> None:
    assert NER_RECOGNIZERS["PERSON"].span_filter is _plausible_person_entity
    assert "नाम" in CONTEXT_KEYWORDS[PIIType.register("PERSON_NAME")]


def test_scan_worker_imports_pack_intl_before_pack_india() -> None:
    import inspect

    source = inspect.getsource(worker)
    for block in source.split("import maskflow_pack_intl")[1:]:
        assert "import maskflow_pack_india" in block.split("\n\n\n")[0]
    assert source.index("import maskflow_pack_intl") < source.index("import maskflow_pack_india")
