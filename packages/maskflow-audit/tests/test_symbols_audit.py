"""Symbol resolution -- the piece that decides real-world recall.

If a client's name cannot be resolved back to its constructor, the call is
invisible and the audit silently under-reports. These are therefore the
tests that matter most in the package.
"""

from __future__ import annotations

import ast

from maskflow_audit.discovery.symbols import (
    attribute_chain,
    build_symbol_table,
    dotted,
    scope_chain,
)


def _create_call(source: str) -> tuple[ast.Call, ast.Module]:
    tree = ast.parse(source)
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"create", "add", "upsert", "invoke", "generation"}
    ]
    return calls[0], tree


def _resolve(source: str, scope: str) -> str | None:
    call, tree = _create_call(source)
    return build_symbol_table(ast.parse(source)).resolve(call.func, scope)


def test_scope_chain_walks_outwards() -> None:
    assert scope_chain("Svc.go") == ("Svc.go", "Svc", "")
    assert scope_chain("") == ("",)


def test_attribute_chain_flattens() -> None:
    node = ast.parse("a.b.c").body[0].value  # type: ignore[attr-defined]
    assert attribute_chain(node) == ("a", ("b", "c"))
    assert dotted(node) == "a.b.c"


def test_a_call_on_a_call_has_no_resolvable_base() -> None:
    node = ast.parse("get_client().chat").body[0].value  # type: ignore[attr-defined]
    assert attribute_chain(node) is None


def test_plain_import_and_direct_construction() -> None:
    assert (
        _resolve("import openai\nc = openai.OpenAI()\nc.chat.completions.create()\n", "")
        == "openai.OpenAI.chat.completions.create"
    )


def test_from_import_with_alias() -> None:
    assert (
        _resolve(
            "from openai import OpenAI as Client\nc = Client()\nc.chat.completions.create()\n", ""
        )
        == "openai.OpenAI.chat.completions.create"
    )


def test_module_alias() -> None:
    assert (
        _resolve("import openai as oai\nc = oai.OpenAI()\nc.chat.completions.create()\n", "")
        == "openai.OpenAI.chat.completions.create"
    )


def test_self_attribute_is_visible_from_a_sibling_method() -> None:
    # The common shape: built in __init__, used in a request handler.
    source = (
        "import openai\n"
        "class Svc:\n"
        "    def __init__(self):\n"
        "        self.oa = openai.OpenAI()\n"
        "    def go(self, t):\n"
        "        return self.oa.chat.completions.create(messages=t)\n"
    )
    assert _resolve(source, "Svc.go") == "openai.OpenAI.chat.completions.create"


def test_a_plain_alias_keeps_pointing_at_the_client() -> None:
    source = "import openai\nc = openai.OpenAI()\nalias = c\nalias.chat.completions.create()\n"
    assert _resolve(source, "") == "openai.OpenAI.chat.completions.create"


def test_factory_chain_resolves_to_the_yielded_client() -> None:
    # chroma.get_or_create_collection() -> Collection, and it is
    # Collection.add that egresses. Without the factory map the chain
    # breaks here and the real sink is never found.
    source = (
        "import chromadb\n"
        "client = chromadb.PersistentClient(path='x')\n"
        "collection = client.get_or_create_collection('kyc')\n"
        "collection.add(documents=['a'])\n"
    )
    table = build_symbol_table(
        ast.parse(source),
        factories={"chromadb.PersistentClient.get_or_create_collection": "chromadb.Collection"},
    )
    call, _ = _create_call(source)
    assert table.resolve(call.func, "") == "chromadb.Collection.add"


def test_unresolvable_name_returns_none_rather_than_guessing() -> None:
    assert _resolve("c = make_client()\nc.chat.completions.create()\n", "") is None


def test_relative_import_is_not_treated_as_a_third_party_path() -> None:
    table = build_symbol_table(ast.parse("from . import OpenAI\n"))
    assert "OpenAI" not in table.imports


def test_constructor_string_kwargs_are_recorded() -> None:
    table = build_symbol_table(
        ast.parse("import openai\nc = openai.OpenAI(base_url='http://gw/v1', timeout=30)\n")
    )
    assert table.client_kwargs[("", "c")] == {"base_url": "http://gw/v1"}


def test_a_dynamic_base_url_is_recorded_as_absent_not_guessed() -> None:
    table = build_symbol_table(
        ast.parse("import openai\nimport os\nc = openai.OpenAI(base_url=os.environ['U'])\n")
    )
    assert "base_url" not in table.client_kwargs[("", "c")]


class TestMaskednessPropagation:
    """A name holding mask() output must stay recognisable downstream."""

    @staticmethod
    def _masked(source: str, name: str, scope: str = "f") -> bool:
        table = build_symbol_table(ast.parse(source))
        return table.is_masked_name(ast.Name(id=name, ctx=ast.Load()), scope)

    def test_tuple_unpacked_mask_call(self) -> None:
        assert self._masked("from maskflow import mask\ndef f(t):\n    m, _ = mask(t)\n", "m")

    def test_masked_text_attribute(self) -> None:
        assert self._masked(
            "from maskflow import mask\ndef f(t):\n    r = mask(t)\n    s = r.masked_text\n", "s"
        )

    def test_through_a_format_call(self) -> None:
        # The fixture-03 shape: a prompt template rendered with masked text.
        assert self._masked(
            "from maskflow import mask\n"
            "def f(t, tpl):\n"
            "    m, _ = mask(t)\n"
            "    rendered = tpl.format(x=m)\n",
            "rendered",
        )

    def test_through_an_fstring(self) -> None:
        assert self._masked(
            "from maskflow import mask\ndef f(t):\n    m, _ = mask(t)\n    p = f'prefix {m}'\n",
            "p",
        )

    def test_through_concatenation(self) -> None:
        assert self._masked(
            "from maskflow import mask\ndef f(t):\n    m, _ = mask(t)\n    p = 'a' + m\n", "p"
        )

    def test_unmasked_text_is_not_marked_masked(self) -> None:
        assert not self._masked("def f(t):\n    p = f'prefix {t}'\n", "p")
