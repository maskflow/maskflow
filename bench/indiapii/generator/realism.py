"""Realism noise knobs applied to template PROSE ONLY -- never to an
identifier value's own characters (see this package's __init__.py
docstring for why). Callers pass each literal text chunk through
apply_noise() before appending it to the document; entity values are always
inserted verbatim afterward, so noise can never shift or corrupt a
recorded span's offsets.
"""

from __future__ import annotations

import random

_OCR_CONFUSIONS: dict[str, str] = {
    "0": "O",
    "O": "0",
    "1": "l",
    "l": "1",
    "5": "S",
    "S": "5",
}

_WHATSAPP_ABBREVIATIONS: dict[str, str] = {
    "please": "pls",
    "thanks": "thnx",
    "thank you": "TY",
    "you": "u",
    "are": "r",
    "your": "ur",
    "before": "b4",
    "today": "2day",
    "tomorrow": "kal",
    "okay": "ok",
    "regarding": "re",
    "as soon as possible": "asap",
    "for": "4",
    "and": "n",
}

_HINGLISH_SPLICES: tuple[str, ...] = (
    "kripya jaldi karein",
    "zara check kar lijiye",
    "bahut zaroori hai",
    "thoda time lagega",
    "sir yeh mera issue hai",
    "please help karo",
)

_DEVANAGARI_SPLICES: tuple[str, ...] = (
    "कृपया जल्दी करें",
    "धन्यवाद",
    "जी हाँ",
    "नमस्ते",
)


def _ocr_noise(text: str, rng: random.Random, prob: float) -> str:
    out = []
    for ch in text:
        if ch in _OCR_CONFUSIONS and rng.random() < prob:
            out.append(_OCR_CONFUSIONS[ch])
        elif ch == " " and rng.random() < prob * 0.3:
            continue  # dropped space
        else:
            out.append(ch)
    return "".join(out)


def _typo(text: str, rng: random.Random, prob: float) -> str:
    chars = list(text)
    i = 0
    out = []
    while i < len(chars):
        ch = chars[i]
        if ch.isalpha() and rng.random() < prob:
            choice = rng.random()
            if choice < 0.34 and i + 1 < len(chars) and chars[i + 1].isalpha():
                out.append(chars[i + 1])
                out.append(ch)
                i += 2
                continue
            elif choice < 0.67:
                out.append(ch)
                out.append(ch)  # duplicated char
            # else: dropped char entirely
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _whatsapp_abbreviate(text: str, rng: random.Random, prob: float) -> str:
    for phrase, short in _WHATSAPP_ABBREVIATIONS.items():
        if phrase in text.lower() and rng.random() < prob:
            idx = text.lower().find(phrase)
            text = text[:idx] + short + text[idx + len(phrase) :]
    return text


def apply_noise(
    text: str,
    rng: random.Random,
    *,
    ocr: bool = False,
    typo: bool = False,
    whatsapp: bool = False,
    hinglish_splice: bool = False,
    devanagari_splice: bool = False,
) -> str:
    """Apply the requested knobs, each independently probabilistic, in a
    fixed order so results stay reproducible for a given rng state."""
    if whatsapp:
        text = _whatsapp_abbreviate(text, rng, prob=0.5)
    if typo:
        text = _typo(text, rng, prob=0.015)
    if ocr:
        text = _ocr_noise(text, rng, prob=0.02)
    if hinglish_splice and rng.random() < 0.25:
        text = _splice(text, rng.choice(_HINGLISH_SPLICES))
    if devanagari_splice and rng.random() < 0.15:
        text = _splice(text, rng.choice(_DEVANAGARI_SPLICES))
    return text


def _splice(text: str, insertion: str) -> str:
    """Insert `insertion` before any trailing whitespace `text` already
    carries, then restore that whitespace -- so a caller that appends an
    entity value immediately after this chunk (no space in between) never
    gets the splice glued directly onto the identifier value (e.g.
    "...karo pe" + splice + "9876543210" running together into
    "...karo9876543210")."""
    stripped = text.rstrip(" \n\t")
    trailing_ws = text[len(stripped) :]
    return f"{stripped} {insertion}{trailing_ws}"
