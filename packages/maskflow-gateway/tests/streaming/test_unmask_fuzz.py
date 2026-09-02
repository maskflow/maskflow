"""The streaming-unmask correctness gate (work order part 2).

For any chunking of a masked text -- including splits mid-placeholder and
mid-UTF-8 -- the concatenated streamed output must equal the non-streaming
``maskflow_core.unmask`` result.
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from maskflow_core import Mapping, MappingEntry, PIIType, Strategy, unmask
from maskflow_gateway.streaming import ByteStreamingUnmasker, StreamingUnmasker

_ENTITY_NAMES = ["EMAIL", "PHONE", "PERSON_NAME", "AADHAAR", "PAN", "INDIAN_ADDRESS"]
for _name in _ENTITY_NAMES:
    PIIType.register(_name)

# Originals: everything the round-trip rule calls sacred -- unicode, emoji,
# RTL, zero-width, ZWJ sequences, and placeholder-lookalikes as literal
# content. Built from variable-length pieces because a ZWJ emoji is several
# code points and can't live in a single-char text alphabet.
_ORIGINAL_PIECE = st.one_of(
    st.text(st.characters(codec="utf-8", min_codepoint=0x20), min_size=1, max_size=4),
    st.sampled_from(["😀", "🏳️‍🌈", "​", "‍", "क", "م", "א", "क़", "\U0001f1ee\U0001f1f3"]),
    st.sampled_from(["<EMAIL_9>", "<PHONE_42>", "<PAN_1_dead>", "<X_1>"]),
)
_ORIGINALS = st.lists(_ORIGINAL_PIECE, min_size=1, max_size=8).map("".join)

_TOKENS = st.builds(
    lambda name, n, nonce: f"<{name}_{n}>" if nonce is None else f"<{name}_{n}_{nonce}>",
    st.sampled_from(_ENTITY_NAMES),
    st.integers(min_value=1, max_value=99),
    st.one_of(st.none(), st.text("0123456789abcdef", min_size=4, max_size=4)),
)

# Filler between tokens: no '<' or '>' so it can never contain a placeholder,
# and encodable (real HTTP bytes never carry unpaired surrogates).
_FILLER = st.text(st.characters(codec="utf-8", exclude_characters="<>"), max_size=12)


@st.composite
def _masked_document(draw: st.DrawFn) -> tuple[str, Mapping]:
    tokens = draw(st.lists(_TOKENS, min_size=1, max_size=6, unique=True))
    originals = draw(st.lists(_ORIGINALS, min_size=len(tokens), max_size=len(tokens)))
    pairs = dict(zip(tokens, originals, strict=True))
    # Property 3: no placeholder may be an infix of any original.
    for tok in pairs:
        for original in pairs.values():
            assume(tok not in original)

    mapping = Mapping(
        {
            tok: MappingEntry(
                token=tok,
                entity_type=PIIType.register(tok[1:].split("_")[0]),
                strategy=Strategy.REPLACE,
                reversible=True,
                original=original,
            )
            for tok, original in pairs.items()
        }
    )

    # Interleave tokens with filler into the masked text.
    parts: list[str] = [draw(_FILLER)]
    for tok in draw(st.lists(st.sampled_from(tokens), min_size=1, max_size=10)):
        parts.append(tok)
        parts.append(draw(_FILLER))
    return "".join(parts), mapping


def _stream_bytes(text: str, mapping: Mapping, split_points: list[int]) -> str:
    data = text.encode("utf-8")
    cuts = sorted(p for p in split_points if 0 < p < len(data))
    bounds = [0, *cuts, len(data)]
    u = ByteStreamingUnmasker(mapping)
    out = [u.feed(data[a:b]) for a, b in zip(bounds[:-1], bounds[1:], strict=True)]
    out.append(u.flush())
    return "".join(out)


@settings(max_examples=400, deadline=None)
@given(doc=_masked_document(), splits=st.lists(st.integers(min_value=1, max_value=400)))
def test_arbitrary_byte_chunking_equals_nonstreaming(
    doc: tuple[str, Mapping], splits: list[int]
) -> None:
    text, mapping = doc
    assert _stream_bytes(text, mapping, splits) == unmask(text, mapping)


@settings(max_examples=150, deadline=None)
@given(doc=_masked_document())
def test_every_single_byte_split_point(doc: tuple[str, Mapping]) -> None:
    text, mapping = doc
    oracle = unmask(text, mapping)
    data = text.encode("utf-8")
    for cut in range(1, len(data)):
        assert _stream_bytes(text, mapping, [cut]) == oracle, f"split at byte {cut}"


@settings(max_examples=150, deadline=None)
@given(doc=_masked_document())
def test_byte_by_byte_equals_all_at_once(doc: tuple[str, Mapping]) -> None:
    text, mapping = doc
    data = text.encode("utf-8")
    every = _stream_bytes(text, mapping, list(range(1, len(data))))
    whole = _stream_bytes(text, mapping, [])
    assert every == whole == unmask(text, mapping)


def test_split_mid_multibyte_codepoint() -> None:
    PIIType.register("PERSON_NAME")
    mapping = Mapping(
        {
            "<PERSON_NAME_1>": MappingEntry(
                token="<PERSON_NAME_1>",
                entity_type=PIIType.register("PERSON_NAME"),
                strategy=Strategy.REPLACE,
                reversible=True,
                original="अनcustomer😀",
            )
        }
    )
    text = "नमस्ते <PERSON_NAME_1> जी"
    oracle = unmask(text, mapping)
    data = text.encode("utf-8")
    for cut in range(1, len(data)):
        assert _stream_bytes(text, mapping, [cut]) == oracle, cut


def test_placeholder_split_across_every_char_boundary() -> None:
    PIIType.register("EMAIL")
    mapping = Mapping(
        {
            "<EMAIL_1>": MappingEntry(
                token="<EMAIL_1>",
                entity_type=PIIType.register("EMAIL"),
                strategy=Strategy.REPLACE,
                reversible=True,
                original="alice@example.com",
            )
        }
    )
    text = "reach me: <EMAIL_1> ok?"
    oracle = unmask(text, mapping)
    for cut in range(1, len(text)):
        u = StreamingUnmasker(mapping)
        assert u.feed(text[:cut]) + u.feed(text[cut:]) + u.flush() == oracle


def test_unknown_placeholder_from_model_is_left_literal() -> None:
    PIIType.register("EMAIL")
    mapping = Mapping(
        {
            "<EMAIL_1>": MappingEntry(
                token="<EMAIL_1>",
                entity_type=PIIType.register("EMAIL"),
                strategy=Strategy.REPLACE,
                reversible=True,
                original="alice@example.com",
            )
        }
    )
    u = StreamingUnmasker(mapping)
    out = u.feed("see <EMAIL_1> and <EMAIL_2>") + u.flush()
    assert out == "see alice@example.com and <EMAIL_2>"


def test_non_incremental_fallback_when_token_is_infix_of_original() -> None:
    PIIType.register("EMAIL")
    PIIType.register("PHONE")
    mapping = Mapping(
        {
            "<PHONE_1>": MappingEntry(
                token="<PHONE_1>",
                entity_type=PIIType.register("PHONE"),
                strategy=Strategy.REPLACE,
                reversible=True,
                original="wrap <EMAIL_1> here",
            ),
            "<EMAIL_1>": MappingEntry(
                token="<EMAIL_1>",
                entity_type=PIIType.register("EMAIL"),
                strategy=Strategy.REPLACE,
                reversible=True,
                original="alice@example.com",
            ),
        }
    )
    u = StreamingUnmasker(mapping)
    assert u._safe_incremental is False
    text = "x <PHONE_1> y"
    assert u.feed(text[:4]) + u.feed(text[4:]) + u.flush() == unmask(text, mapping)
