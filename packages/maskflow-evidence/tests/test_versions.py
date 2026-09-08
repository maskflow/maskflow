from __future__ import annotations

import re

from maskflow_evidence import engine_version, pack_version, pack_versions

_VER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


def test_engine_version_is_a_version_string() -> None:
    v = engine_version()
    assert _VER.match(v)
    assert v != "unknown"  # maskflow-core is always installed in the test env


def test_pack_versions_includes_india_and_intl() -> None:
    packs = pack_versions()
    assert "maskflow-pack-india" in packs
    assert "maskflow-pack-intl" in packs
    assert all(_VER.match(v) for v in packs.values())


def test_pack_version_prefers_india() -> None:
    assert pack_version() == pack_versions()["maskflow-pack-india"]
