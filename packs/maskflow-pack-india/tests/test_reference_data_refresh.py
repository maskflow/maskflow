"""Tests for scripts/refresh_india_reference_data.py's pure diff functions
(no network -- see the script's own docstring for why fetch/parse is kept
separate from diffing) and for basic hygiene of the bundled reference data
those diffs feed into.
"""

import importlib.util
import sys
from pathlib import Path

from maskflow_pack_india.data.ifsc_bank_codes import IFSC_BANK_CODES
from maskflow_pack_india.data.indian_places import INDIAN_CITIES

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "refresh_india_reference_data.py"

_spec = importlib.util.spec_from_file_location("refresh_india_reference_data", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
refresh = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = refresh
_spec.loader.exec_module(refresh)


class TestIfscDiff:
    def test_in_scope_addition_is_surfaced(self) -> None:
        current = frozenset({"HDFC"})
        fetched = {"HDFC": {"type": "Private"}, "IPPB": {"type": "PB"}}
        added, unseen = refresh.ifsc_diff(current, fetched)
        assert added == ["IPPB"]
        assert unseen == []

    def test_out_of_scope_type_is_never_surfaced(self) -> None:
        current: frozenset[str] = frozenset()
        fetched = {"AACX": {"type": "O-UCB"}, "ACAX": {"type": "SCB"}}
        added, _ = refresh.ifsc_diff(current, fetched)
        assert added == []

    def test_psb_allowlist_overrides_missing_type(self) -> None:
        current: frozenset[str] = frozenset()
        fetched = {"RBIN": {"type": "PSB"}}
        added, _ = refresh.ifsc_diff(current, fetched)
        assert added == ["RBIN"]

    def test_bundled_code_absent_from_fetch_is_flagged_not_removed(self) -> None:
        current = frozenset({"XXXX"})
        fetched: dict[str, dict] = {}
        added, unseen = refresh.ifsc_diff(current, fetched)
        assert added == []
        assert unseen == ["XXXX"]


class TestCitiesDiff:
    def test_population_threshold_is_applied(self) -> None:
        current: frozenset[str] = frozenset()
        rows = [
            {"name_of_city": "BigCity", "population_total": "100000"},
            {"name_of_city": "SmallTown", "population_total": "99999"},
        ]
        added = refresh.cities_diff(current, rows)
        assert added == ["BigCity"]

    def test_already_bundled_city_is_not_surfaced(self) -> None:
        current = frozenset({"Mumbai"})
        rows = [{"name_of_city": "Mumbai", "population_total": "12000000"}]
        assert refresh.cities_diff(current, rows) == []

    def test_malformed_population_is_skipped_not_crashed(self) -> None:
        current: frozenset[str] = frozenset()
        rows = [{"name_of_city": "Nowhere", "population_total": "N/A"}]
        assert refresh.cities_diff(current, rows) == []


class TestBundledDataHygiene:
    def test_indian_cities_has_no_case_insensitive_duplicates(self) -> None:
        lowered = [c.lower() for c in INDIAN_CITIES]
        assert len(lowered) == len(set(lowered))

    def test_indian_cities_clears_top_500_target(self) -> None:
        assert len(INDIAN_CITIES) >= 500

    def test_ifsc_bank_codes_has_no_lowercase_or_malformed_entries(self) -> None:
        assert all(len(code) == 4 and code.isupper() for code in IFSC_BANK_CODES)
