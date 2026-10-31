"""Backward tracing: does a finding name a cause, not just a line?"""

from __future__ import annotations

from maskflow_audit.api import run_audit
from maskflow_audit.discovery.flows import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    SOURCE_DB_COLUMN,
    SOURCE_FILE_READ,
    SOURCE_LITERAL,
    SOURCE_PARAMETER,
    SOURCE_REQUEST_FIELD,
    SOURCE_UNKNOWN,
)

_HEAD = "from openai import OpenAI\nclient = OpenAI()\n"


def _sources(tree, body: str) -> set[tuple[str, str]]:
    summary = run_audit(tree(_HEAD + body))
    assert len(summary.flows) == 1
    return {(s.kind, s.detail) for s in summary.flows[0].sources}


def _flow(tree, body: str):
    summary = run_audit(tree(_HEAD + body))
    return summary.flows[0]


def test_db_column_through_a_subscript(tree) -> None:
    sources = _sources(
        tree,
        "def f(cur):\n"
        "    row = cur.fetchone()\n"
        "    client.chat.completions.create(messages=row['aadhaar'])\n",
    )
    assert (SOURCE_DB_COLUMN, "aadhaar") in sources


def test_db_columns_through_an_fstring(tree) -> None:
    sources = _sources(
        tree,
        "def f(cur):\n"
        "    row = cur.fetchone()\n"
        "    p = f\"{row['pan']} and {row['mobile']}\"\n"
        "    client.chat.completions.create(messages=p)\n",
    )
    assert (SOURCE_DB_COLUMN, "pan") in sources
    assert (SOURCE_DB_COLUMN, "mobile") in sources


def test_loop_variable_inherits_the_iterables_provenance(tree) -> None:
    sources = _sources(
        tree,
        "def f(cur):\n"
        "    for row in cur.fetchall():\n"
        "        client.chat.completions.create(messages=row['pan'])\n",
    )
    assert (SOURCE_DB_COLUMN, "pan") in sources


def test_request_field(tree) -> None:
    sources = _sources(
        tree,
        "def f(request):\n"
        "    body = request.json\n"
        "    client.chat.completions.create(messages=body['grievance'])\n",
    )
    assert (SOURCE_REQUEST_FIELD, "grievance") in sources


def test_file_read(tree) -> None:
    sources = _sources(
        tree,
        "def f(path):\n"
        "    text = path.read_text()\n"
        "    client.chat.completions.create(messages=text)\n",
    )
    assert any(kind == SOURCE_FILE_READ for kind, _ in sources)


def test_a_parameter_is_a_named_but_weaker_source(tree) -> None:
    flow = _flow(tree, "def f(prompt):\n    client.chat.completions.create(messages=prompt)\n")
    assert (SOURCE_PARAMETER, "prompt") in {(s.kind, s.detail) for s in flow.sources}
    assert flow.confidence == CONFIDENCE_MEDIUM


def test_a_string_literals_contents_are_never_recorded(tree) -> None:
    """Rule 1 reaches into the trace: a literal is kind-only, detail empty.

    A hard-coded value in the audited codebase must not ride into the
    report, so `literal` deliberately carries no text.
    """
    sources = _sources(
        tree, "def f():\n    client.chat.completions.create(messages='sekrit-value-123')\n"
    )
    assert (SOURCE_LITERAL, "") in sources
    assert not any("sekrit" in detail for _, detail in sources)


def test_mask_is_transparent_to_provenance(tree) -> None:
    """Masking changes the value, not where it came from.

    "the aadhaar column is masked before it is sent" is a far more useful
    report line than "something called mask()", so the trace follows
    through mask() rather than stopping at it.
    """
    sources = _sources(
        tree,
        "from maskflow import mask\n"
        "def f(cur):\n"
        "    row = cur.fetchone()\n"
        "    m, _ = mask(row['aadhaar'])\n"
        "    client.chat.completions.create(messages=m)\n",
    )
    assert (SOURCE_DB_COLUMN, "aadhaar") in sources


def test_confidence_is_high_only_with_a_named_origin(tree) -> None:
    named = _flow(
        tree,
        "def f(cur):\n"
        "    row = cur.fetchone()\n"
        "    client.chat.completions.create(messages=row['aadhaar'])\n",
    )
    assert named.confidence == CONFIDENCE_HIGH

    anonymous = _flow(tree, "def f():\n    client.chat.completions.create(messages=blah())\n")
    assert anonymous.confidence == CONFIDENCE_LOW


def test_a_cyclic_assignment_terminates(tree) -> None:
    """`a = b` / `b = a` must not recurse forever."""
    flow = _flow(
        tree, "def f():\n    a = b\n    b = a\n    client.chat.completions.create(messages=a)\n"
    )
    assert any(kind == SOURCE_UNKNOWN for kind in (s.kind for s in flow.sources))


def test_a_deep_but_real_chain_is_still_traced(tree) -> None:
    """Regression guard for the depth bound.

    A limit of 6 silently downgraded fixture 04's columns to `unknown`
    while fixture 01 found them, for the same SQL -- the mask() hop costs
    two levels. The bound is an effort limit; cycles are stopped elsewhere.
    """
    sources = _sources(
        tree,
        "from maskflow import mask\n"
        "def f(cur):\n"
        "    row = cur.fetchone()\n"
        "    p = f\"x {row['aadhaar']}\"\n"
        "    m, _ = mask(p)\n"
        "    msgs = [{'role': 'user', 'content': m}]\n"
        "    client.chat.completions.create(messages=msgs)\n",
    )
    assert (SOURCE_DB_COLUMN, "aadhaar") in sources
