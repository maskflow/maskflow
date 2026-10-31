"""Masking classification, including the cases where `unknown` is right.

The two ways to be wrong are not symmetric: calling a guarded path
unmasked wastes an afternoon, calling an unguarded path masked is the
failure this tool exists to prevent. Several tests below therefore assert
`unknown` on purpose.
"""

from __future__ import annotations

from maskflow_audit.api import run_audit
from maskflow_audit.discovery.flows import (
    MASKED_VIA_GATEWAY,
    MASKED_VIA_INTEGRATION,
    MASKED_VIA_MASK_CALL,
    UNKNOWN,
    UNMASKED,
)

_OPENAI = "from openai import OpenAI\nclient = OpenAI({ctor})\n"


def _status(tree, source: str) -> str:
    summary = run_audit(tree(source))
    assert len(summary.flows) == 1, [f.sink_id for f in summary.flows]
    return summary.flows[0].masking_status


def test_bare_client_is_unmasked(tree) -> None:
    assert (
        _status(
            tree,
            _OPENAI.format(ctor="") + "def f(t):\n    client.chat.completions.create(messages=t)\n",
        )
        == UNMASKED
    )


def test_mask_call_on_the_payload(tree) -> None:
    assert (
        _status(
            tree,
            "from maskflow import mask\n" + _OPENAI.format(ctor="") + "def f(t):\n"
            "    m, _ = mask(t)\n"
            "    client.chat.completions.create(messages=[{'role': 'user', 'content': m}])\n",
        )
        == MASKED_VIA_MASK_CALL
    )


def test_mask_and_call_wrapper(tree) -> None:
    assert (
        _status(
            tree,
            "from maskflow import mask_and_call\n" + _OPENAI.format(ctor="") + "def f(t):\n"
            "    return mask_and_call(\n"
            "        t, lambda p: client.chat.completions.create(messages=p)\n"
            "    )\n",
        )
        == MASKED_VIA_MASK_CALL
    )


def test_gateway_recognised_by_host_name(tree) -> None:
    assert (
        _status(
            tree,
            _OPENAI.format(ctor="base_url='http://maskflow-gateway:8000/v1'")
            + "def f(t):\n    client.chat.completions.create(messages=t)\n",
        )
        == MASKED_VIA_GATEWAY
    )


def test_gateway_recognised_by_a_module_marker(tree) -> None:
    assert (
        _status(
            tree,
            _OPENAI.format(
                ctor="base_url='http://localhost:8000/v1', "
                "default_headers={'X-Maskflow-Session': 's'}"
            )
            + "def f(t):\n    client.chat.completions.create(messages=t)\n",
        )
        == MASKED_VIA_GATEWAY
    )


def test_an_unidentifiable_custom_base_url_is_unknown_not_masked(tree) -> None:
    """The honest answer, and the one that matters most.

    MaskFlow's gateway has no reserved hostname -- it is deliberately
    path-compatible with OpenAI's API -- so a bare localhost base_url is
    indistinguishable from any other proxy by reading source. Assuming a
    guard here would be the single most dangerous false negative the tool
    could produce.
    """
    assert (
        _status(
            tree,
            _OPENAI.format(ctor="base_url='http://localhost:8000/v1'")
            + "def f(t):\n    client.chat.completions.create(messages=t)\n",
        )
        == UNKNOWN
    )


def test_an_unknown_third_party_proxy_is_also_unknown(tree) -> None:
    assert (
        _status(
            tree,
            _OPENAI.format(ctor="base_url='https://some-llm-proxy.example.com/v1'")
            + "def f(t):\n    client.chat.completions.create(messages=t)\n",
        )
        == UNKNOWN
    )


def test_integration_import_guards_its_own_framework(tree) -> None:
    assert (
        _status(
            tree,
            "import maskflow_litellm\nimport litellm\n"
            "def f(t):\n    litellm.completion(model='gpt-4', messages=t)\n",
        )
        == MASKED_VIA_INTEGRATION
    )


def test_integration_import_does_not_guard_an_unrelated_sink(tree) -> None:
    """Importing maskflow_langchain must not excuse a bare openai call.

    An integration guards the framework it wraps and nothing else; a
    blanket "this module imports something from MaskFlow, so it is fine"
    rule would be precisely the kind of false reassurance that makes an
    audit worthless.
    """
    assert (
        _status(
            tree,
            "import maskflow_langchain\n"
            + _OPENAI.format(ctor="")
            + "def f(t):\n    client.chat.completions.create(messages=t)\n",
        )
        == UNMASKED
    )


def test_a_sink_with_no_declared_payload_argument_is_unknown(tree) -> None:
    # An MCP tool egresses whatever it returns; there is no single argument
    # to inspect, so masking cannot be judged from the call site.
    assert (
        _status(
            tree,
            "from fastmcp import FastMCP\n"
            "mcp = FastMCP('x')\n"
            "def f():\n    mcp.add_tool(lambda: 'x')\n",
        )
        == UNKNOWN
    )


def test_raw_http_to_a_known_provider_host_is_a_flow(tree) -> None:
    assert (
        _status(
            tree,
            "import requests\n"
            "def f(t):\n"
            "    requests.post('https://api.openai.com/v1/chat/completions', json=t)\n",
        )
        == UNMASKED
    )


def test_raw_http_to_an_unknown_host_is_not_reported_at_all(tree) -> None:
    """Otherwise the report is every requests.post in the repository."""
    summary = run_audit(
        tree("import requests\ndef f(t):\n    requests.post('https://internal/x', json=t)\n")
    )
    assert summary.flows == ()


def test_the_reason_is_always_populated(tree) -> None:
    # The report shows this string to a human; an empty one is a bug.
    source = _OPENAI.format(ctor="") + (
        "def f(t):\n    client.chat.completions.create(messages=t)\n"
    )
    summary = run_audit(tree(source))
    assert summary.flows[0].masking_reason
    assert summary.flows[0].explanation
