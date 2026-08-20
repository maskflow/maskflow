"""Mapping/MappingEntry container behavior -- the dict-like surface unmask()
and MappingStore rely on, plus JSON (de)serialization round-tripping.
"""

from maskflow_core.entities import PIIType
from maskflow_core.mapping import Mapping, MappingEntry
from maskflow_core.strategies import Strategy


def _entry(token: str = "<TEST_1>", original: str = "secret-value") -> MappingEntry:
    pii_type = PIIType.register("TEST_MAPPING_TYPE")
    return MappingEntry(
        token=token,
        entity_type=pii_type,
        strategy=Strategy.REPLACE,
        reversible=True,
        original=original,
    )


def test_mapping_supports_dict_like_access() -> None:
    entry = _entry()
    mapping = Mapping({entry.token: entry})

    assert mapping[entry.token] is entry
    assert entry.token in mapping
    assert "<NOT_PRESENT>" not in mapping
    assert list(mapping) == [entry.token]
    assert len(mapping) == 1
    assert list(mapping.keys()) == [entry.token]
    assert list(mapping.values()) == [entry]
    assert mapping.get(entry.token) is entry
    assert mapping.get("<MISSING>") is None
    assert mapping.get("<MISSING>", entry) is entry


def test_mapping_setitem_adds_an_entry() -> None:
    mapping = Mapping()
    entry = _entry()
    mapping[entry.token] = entry
    assert mapping[entry.token] is entry


def test_mapping_equality() -> None:
    entry = _entry()
    a = Mapping({entry.token: entry})
    b = Mapping({entry.token: entry})
    assert a == b
    assert a != Mapping()
    assert a.__eq__("not a mapping") is NotImplemented


def test_mapping_json_round_trip_preserves_entries() -> None:
    entry = _entry(original="245-11-2222")
    mapping = Mapping({entry.token: entry})

    restored = Mapping.from_json(mapping.to_json())

    assert restored[entry.token].token == entry.token
    assert restored[entry.token].entity_type == entry.entity_type
    assert restored[entry.token].strategy == entry.strategy
    assert restored[entry.token].reversible == entry.reversible
    assert restored[entry.token].original == entry.original
