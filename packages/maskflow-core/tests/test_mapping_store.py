"""MappingStore implementations: InMemoryMappingStore (TTL), EncryptedFileMappingStore
(AES-GCM at rest), and RedisMappingStore (interface-only stub this round).
"""

import sys
import time
from pathlib import Path

import pytest
from maskflow_core.entities import PIIType
from maskflow_core.mapping import Mapping, MappingEntry
from maskflow_core.mapping_store import (
    EncryptedFileMappingStore,
    InMemoryMappingStore,
    RedisMappingStore,
)
from maskflow_core.strategies import Strategy


def _sample_mapping() -> Mapping:
    pii_type = PIIType.register("TEST_STORE_TYPE")
    entry = MappingEntry(
        token="<TEST_STORE_TYPE_1>",
        entity_type=pii_type,
        strategy=Strategy.REPLACE,
        reversible=True,
        original="245-11-2222",
    )
    return Mapping({entry.token: entry})


def test_in_memory_store_round_trips_a_saved_mapping() -> None:
    store = InMemoryMappingStore()
    mapping = _sample_mapping()

    store.save("session-1", mapping)
    loaded = store.load("session-1")

    assert loaded is not None
    assert loaded["<TEST_STORE_TYPE_1>"].original == "245-11-2222"


def test_in_memory_store_load_returns_none_for_unknown_session() -> None:
    store = InMemoryMappingStore()
    assert store.load("never-saved") is None


def test_in_memory_store_delete_removes_the_entry() -> None:
    store = InMemoryMappingStore()
    store.save("session-1", _sample_mapping())
    store.delete("session-1")
    assert store.load("session-1") is None


def test_in_memory_store_delete_is_a_no_op_for_an_unknown_session() -> None:
    InMemoryMappingStore().delete("never-saved")  # must not raise


def test_in_memory_store_expires_entries_past_their_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    store = InMemoryMappingStore(ttl_seconds=10)
    store.save("session-1", _sample_mapping())

    clock["now"] = 5.0
    assert store.load("session-1") is not None

    clock["now"] = 10.0
    assert store.load("session-1") is None


def test_encrypted_file_store_round_trips_a_saved_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MASKFLOW_MAPPING_KEY", "00" * 32)
    store = EncryptedFileMappingStore(tmp_path)
    mapping = _sample_mapping()

    store.save("session-1", mapping)
    loaded = store.load("session-1")

    assert loaded is not None
    assert loaded["<TEST_STORE_TYPE_1>"].original == "245-11-2222"


def test_encrypted_file_store_writes_ciphertext_not_plaintext(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MASKFLOW_MAPPING_KEY", "00" * 32)
    store = EncryptedFileMappingStore(tmp_path)
    store.save("session-1", _sample_mapping())

    raw_bytes = next(tmp_path.iterdir()).read_bytes()
    assert b"245-11-2222" not in raw_bytes


def test_encrypted_file_store_load_returns_none_for_unknown_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MASKFLOW_MAPPING_KEY", "00" * 32)
    store = EncryptedFileMappingStore(tmp_path)
    assert store.load("never-saved") is None


def test_encrypted_file_store_delete_removes_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MASKFLOW_MAPPING_KEY", "00" * 32)
    store = EncryptedFileMappingStore(tmp_path)
    store.save("session-1", _sample_mapping())
    store.delete("session-1")
    assert store.load("session-1") is None
    store.delete("session-1")  # deleting again must not raise


def test_encrypted_file_store_rejects_a_path_like_session_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MASKFLOW_MAPPING_KEY", "00" * 32)
    store = EncryptedFileMappingStore(tmp_path)
    with pytest.raises(ValueError, match="Invalid session_id"):
        store.save("../escape", _sample_mapping())


def test_encrypted_file_store_requires_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MASKFLOW_MAPPING_KEY", raising=False)
    with pytest.raises(ValueError, match="MASKFLOW_MAPPING_KEY"):
        EncryptedFileMappingStore(tmp_path)


def test_encrypted_file_store_accepts_an_explicit_key(tmp_path: Path) -> None:
    store = EncryptedFileMappingStore(tmp_path, key=b"\x00" * 32)
    store.save("session-1", _sample_mapping())
    assert store.load("session-1") is not None


def test_encrypted_file_store_raises_a_clear_error_without_cryptography_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives.ciphers.aead", None)
    with pytest.raises(ImportError, match=r"maskflow-core\[store\]"):
        EncryptedFileMappingStore(tmp_path, key=b"\x00" * 32)


def test_redis_store_is_not_implemented_yet() -> None:
    store = RedisMappingStore(host="example.internal", port=6380, db=1)
    mapping = _sample_mapping()

    with pytest.raises(NotImplementedError):
        store.save("session-1", mapping)
    with pytest.raises(NotImplementedError):
        store.load("session-1")
    with pytest.raises(NotImplementedError):
        store.delete("session-1")
