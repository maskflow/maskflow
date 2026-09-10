"""Pure comparison logic -- no framework imports, no network."""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field

from .adapters import MaskRun


@dataclass
class ParityTally:
    name: str
    docs: int = 0
    detection_matches: int = 0  # (type, value) set == core's
    roundtrip_exact: int = 0
    streaming_exact: int = 0
    extra_types: Counter[str] = field(default_factory=Counter)  # wrapper masked, core didn't
    missed_types: Counter[str] = field(default_factory=Counter)  # core masked, wrapper didn't
    roundtrip_fail_docs: list[str] = field(default_factory=list)
    streaming_fail_docs: list[str] = field(default_factory=list)

    def rate(self, attr: str) -> float | None:
        return getattr(self, attr) / self.docs if self.docs else None


def compare(tally: ParityTally, doc_id: str, text: str, run: MaskRun, core: MaskRun) -> None:
    tally.docs += 1

    if run.pairs == core.pairs:
        tally.detection_matches += 1
    else:
        for et, _v in run.pairs - core.pairs:
            tally.extra_types[et] += 1
        for et, _v in core.pairs - run.pairs:
            tally.missed_types[et] += 1

    if run.roundtrip == text:
        tally.roundtrip_exact += 1
    elif len(tally.roundtrip_fail_docs) < 10:
        tally.roundtrip_fail_docs.append(doc_id)

    if _streaming_roundtrips(run):
        tally.streaming_exact += 1
    elif len(tally.streaming_fail_docs) < 10:
        tally.streaming_fail_docs.append(doc_id)


def _streaming_roundtrips(run: MaskRun) -> bool:
    """Feed `run.masked_text` -- as if it were the model echoing placeholders
    -- through the shared StreamingUnmasker at several chunk splittings;
    every reassembly must equal the non-streaming unmask."""
    from maskflow.streaming import StreamingUnmasker, unmask_whole

    if not run.token_map:
        return True

    expected = unmask_whole(run.masked_text, run.token_map)
    rng = random.Random(len(run.masked_text) or 1)
    splittings = [
        [1] * len(run.masked_text),  # one byte at a time -- worst case for the trie
        _random_splits(run.masked_text, rng),
        _random_splits(run.masked_text, rng),
    ]
    for sizes in splittings:
        um = StreamingUnmasker(run.token_map)
        out: list[str] = []
        i = 0
        for n in sizes:
            out.append(um.feed(run.masked_text[i : i + n]))
            i += n
        out.append(um.feed(run.masked_text[i:]))
        out.append(um.flush())
        if "".join(out) != expected:
            return False
    return True


def _random_splits(s: str, rng: random.Random) -> list[int]:
    sizes: list[int] = []
    remaining = len(s)
    while remaining > 0:
        n = rng.randint(1, min(7, remaining))
        sizes.append(n)
        remaining -= n
    return sizes
