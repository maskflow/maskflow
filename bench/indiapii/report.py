"""Prints the PERSON_NAME (Indian) / INDIAN_ADDRESS precision/recall table
against every packs/maskflow-pack-india/tests/fixtures/india_l*_samples.py
fixture module built so far. Re-run after each of the work order's L1-L4
layers to produce that layer's written accuracy report -- see CLAUDE.md and
metrics.py's docstring.

Reported cumulatively (every layer's fixtures scored together), not
per-layer in isolation: each layer's patterns/recognizers register
alongside the previous ones against the same PIIType.PERSON_NAME/
INDIAN_ADDRESS, so a single detect() call always reflects every layer
registered so far -- there's no way to run detect() with only a subset of
that pack's recognizers active.

Usage: uv run python bench/indiapii/report.py
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parents[1] / "packs" / "maskflow-pack-india" / "tests"))

from maskflow_core.entities import PIIType  # noqa: E402
from metrics import LayerReport, evaluate  # noqa: E402

# Every layer's fixtures built so far, in order -- add "india_l4_samples"
# here once/if L4 ships.
LAYER_MODULES = [
    "fixtures.india_l1_samples",
    "fixtures.india_l2_samples",
    "fixtures.india_l3_samples",
]
LAYER_LABEL = "L1+L2+L3 (gazetteer + structural + NLP agreement, cumulative)"


def main() -> None:
    person_pos: list = []
    person_neg: list = []
    person_hard_neg: list = []
    addr_pos: list = []
    addr_neg: list = []
    addr_hard_neg: list = []

    for module_name in LAYER_MODULES:
        mod = importlib.import_module(module_name)
        person_pos += mod.PERSON_NAME_POSITIVE_SAMPLES
        person_neg += mod.PERSON_NAME_NEGATIVE_SAMPLES
        person_hard_neg += mod.PERSON_NAME_HARD_NEGATIVE_SAMPLES
        addr_pos += mod.INDIAN_ADDRESS_POSITIVE_SAMPLES
        addr_neg += mod.INDIAN_ADDRESS_NEGATIVE_SAMPLES
        addr_hard_neg += mod.INDIAN_ADDRESS_HARD_NEGATIVE_SAMPLES

    person_name_results = evaluate(
        person_pos, person_neg, person_hard_neg, target_types=(PIIType.PERSON_NAME,)
    )
    address_results = evaluate(
        addr_pos, addr_neg, addr_hard_neg, target_types=(PIIType.INDIAN_ADDRESS,)
    )
    combined = {**person_name_results, **address_results}
    print(LayerReport(layer=LAYER_LABEL, results=combined).render())


if __name__ == "__main__":
    main()
