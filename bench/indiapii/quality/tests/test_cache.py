from __future__ import annotations

from pathlib import Path

from bench.indiapii.quality.cache import DiskCache


def test_miss_returns_none(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    assert cache.get("nope") is None


def test_set_then_get_round_trips(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    cache.set("key-1", {"response": "hello"})
    assert cache.get("key-1") == {"response": "hello"}


def test_distinct_keys_do_not_collide(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    cache.set("a", {"v": 1})
    cache.set("b", {"v": 2})
    assert cache.get("a") == {"v": 1}
    assert cache.get("b") == {"v": 2}


def test_persists_across_new_instance_same_dir(tmp_path: Path) -> None:
    DiskCache(tmp_path).set("key", {"v": 42})
    reopened = DiskCache(tmp_path)
    assert reopened.get("key") == {"v": 42}
