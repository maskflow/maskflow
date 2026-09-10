"""Realism noise applied to template PROSE ONLY -- never to a PII value's
own characters (see this package's __init__.py for why). Callers pass each
literal text chunk through apply_noise() before appending it; entity values
are always inserted verbatim afterward, so noise can never shift or corrupt
a recorded span's offsets.

Deliberately lighter than bench/indiapii/generator/realism.py: the intl
corpus's job is a clean, defensible baseline on generic PII, not a
stress-test of code-mixed / OCR'd input (that discipline lives in the
India moat).
"""

from __future__ import annotations

import random

_CASING_TARGETS = ("Name", "Email", "Phone", "Address", "Date of Birth", "Card", "Account")


def _typo(text: str, rng: random.Random, prob: float) -> str:
    chars = list(text)
    out: list[str] = []
    i = 0
    while i < len(chars):
        ch = chars[i]
        if ch.isalpha() and rng.random() < prob:
            roll = rng.random()
            if roll < 0.34 and i + 1 < len(chars) and chars[i + 1].isalpha():
                out.append(chars[i + 1])
                out.append(ch)
                i += 2
                continue
            if roll < 0.67:
                out.append(ch)
                out.append(ch)
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _casing_wobble(text: str, rng: random.Random, prob: float) -> str:
    for target in _CASING_TARGETS:
        if target in text and rng.random() < prob:
            text = text.replace(target, target.lower(), 1)
    return text


def apply_noise(
    text: str,
    rng: random.Random,
    *,
    typo: bool = False,
    casing: bool = False,
) -> str:
    """Apply the requested knobs, each independently probabilistic, in a
    fixed order so results stay reproducible for a given rng state."""
    if typo:
        text = _typo(text, rng, prob=0.012)
    if casing:
        text = _casing_wobble(text, rng, prob=0.4)
    return text
