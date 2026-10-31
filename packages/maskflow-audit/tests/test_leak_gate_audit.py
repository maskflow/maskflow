"""The leak gate: no value from an audited tree may reach the report.

The audit reads somebody else's source, and that source can contain real
personal data sitting in a hard-coded constant, a test fixture, or a
docstring. So this package inherits non-negotiable rule 1 with an extra
edge: the input is untrusted text, and the output is a document a DPO is
expected to retain and share.

The gate seeds a tree with synthetic identifier values in every awkward
place -- a literal argument, a dict, a default parameter, a docstring, a
comment -- audits it, and asserts none of them appears in any rendered
format, under the same normalisations maskflow-cli's scan fuzz gate uses
(casefold, separator stripping, and the four unicode normal forms).
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest
from maskflow_audit.api import run_audit
from maskflow_audit.report import FORMATS, render


def _normalisations(value: str) -> set[str]:
    """Every form the value could survive in. Mirrors scan's fuzz gate."""
    forms = {value, value.casefold(), value.replace(" ", ""), value.replace("-", "")}
    for form in tuple(forms):
        for scheme in ("NFC", "NFKC", "NFD", "NFKD"):
            forms.add(unicodedata.normalize(scheme, form))
    return forms


@pytest.fixture
def seeded_tree(tmp_path: Path, canaries: dict[str, str]) -> tuple[Path, list[str]]:
    """A tree whose source is littered with synthetic identifier values."""
    aadhaar = canaries["AADHAAR"]
    pan = canaries["PAN"]
    mobile = canaries["INDIAN_MOBILE"]
    spaced = f"{aadhaar[0:4]} {aadhaar[4:8]} {aadhaar[8:12]}"

    (tmp_path / "app.py").write_text(
        f'''"""Module docstring mentioning {pan} on purpose."""

from openai import OpenAI
from maskflow import mask

client = OpenAI()

# A comment carrying {mobile}, which must not reach the report either.
DEFAULT_UID = "{aadhaar}"
LOOKUP = {{"pan": "{pan}", "uid": "{spaced}"}}


def summarize(cur, uid: str = "{aadhaar}"):
    """Docstring with {mobile}."""
    row = cur.fetchone()
    prompt = f"{{row['aadhaar']}} {{uid}} {pan}"
    return client.chat.completions.create(messages=[{{"role": "user", "content": prompt}}])


def already_masked(text):
    masked, _ = mask(text)
    return client.chat.completions.create(messages=masked)


def to_vector(text):
    return client.embeddings.create(model="text-embedding-3-small", input="{spaced}")
''',
        encoding="utf-8",
    )
    # A file that cannot be parsed, so the skip path is exercised too --
    # a SyntaxError's own message quotes the offending line.
    (tmp_path / "broken.py").write_text(f'x = "{aadhaar}" (\n', encoding="utf-8")

    return tmp_path, [aadhaar, pan, mobile, spaced]


@pytest.mark.leak
@pytest.mark.parametrize("fmt", FORMATS)
def test_no_seeded_value_survives_into_any_format(
    seeded_tree: tuple[Path, list[str]], fmt: str
) -> None:
    root, seeded = seeded_tree
    rendered = render(run_audit(root), fmt)
    haystacks = {rendered, rendered.casefold(), unicodedata.normalize("NFKC", rendered)}

    leaked = [
        value
        for value in seeded
        if any(form in hay for form in _normalisations(value) for hay in haystacks)
    ]
    assert not leaked, f"{len(leaked)} seeded value(s) leaked into {fmt}: {leaked}"


@pytest.mark.leak
def test_the_gate_is_not_vacuous(seeded_tree: tuple[Path, list[str]]) -> None:
    """The audit must actually have found things, or the assertion above
    proves nothing. Same guard as scan's test_report_is_non_trivial."""
    root, seeded = seeded_tree
    summary = run_audit(root)
    assert len(summary.flows) >= 3, [f.sink_id for f in summary.flows]
    assert summary.coverage.unmasked >= 1
    assert summary.coverage.masked >= 1
    assert summary.skipped_files, "the unparseable file should have been skipped"
    assert seeded


@pytest.mark.leak
def test_no_source_line_is_embedded_anywhere(seeded_tree: tuple[Path, list[str]]) -> None:
    """Beyond identifiers: no line of the audited source may be quoted.

    The report names identifiers -- paths, functions, columns, arguments --
    and never content, so a whole source line appearing in it would mean a
    renderer gained a way to quote the tree.
    """
    root, _ = seeded_tree
    rendered = render(run_audit(root), "json")
    for line in (root / "app.py").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if len(stripped) < 20:
            continue
        assert stripped not in rendered, f"a source line was embedded in the report: {stripped!r}"


@pytest.mark.leak
def test_an_exception_from_the_registry_carries_no_source(tmp_path: Path) -> None:
    """RegistryError lists ids and field names, never file contents."""
    from maskflow_audit.sinks.loader import RegistryError, load_registry

    bad = tmp_path / "registry.yaml"
    bad.write_text("version: 1\nsinks:\n  - id: a\n    category: nope\n    provider: p\n", "utf-8")
    with pytest.raises(RegistryError) as excinfo:
        load_registry(bad)
    assert "nope" in str(excinfo.value)  # the bad value is a field, fine to name
    assert "version: 1" not in str(excinfo.value)  # but not the file's text
