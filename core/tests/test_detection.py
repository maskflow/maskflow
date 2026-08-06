import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fixtures.pii_samples import NEGATIVE_SAMPLES, POSITIVE_SAMPLES
from maskflow_core.detection import detect

ACCURACY_TARGET = 0.95


def _found_pairs(text: str) -> set[tuple]:
    return {(f.type, f.value) for f in detect(text)}


def test_all_positive_samples_are_detected():
    """Every expected (type, value) pair must show up in detect()'s output."""
    misses = []
    total_expected = 0

    for sample in POSITIVE_SAMPLES:
        found = _found_pairs(sample.text)
        for expected in sample.expected:
            total_expected += 1
            if expected not in found:
                misses.append((sample.text, expected))

    accuracy = 1 - (len(misses) / total_expected)
    assert accuracy >= ACCURACY_TARGET, (
        f"Detection accuracy {accuracy:.2%} below {ACCURACY_TARGET:.0%} target. "
        f"Misses:\n" + "\n".join(f"  {text!r} -> expected {exp}" for text, exp in misses)
    )


def test_negative_samples_produce_no_findings():
    false_positives = []
    for text in NEGATIVE_SAMPLES:
        findings = detect(text)
        if findings:
            false_positives.append((text, findings))

    assert not false_positives, (
        "False positives on PII-free / invalid text:\n"
        + "\n".join(f"  {text!r} -> {findings}" for text, findings in false_positives)
    )


def test_findings_are_non_overlapping_and_sorted():
    text = (
        "Hi, this is Jane Doe. My email is jane.doe@example.com and my phone is "
        "415-555-0198. My SSN is 245-11-2222 for the background check."
    )
    findings = detect(text)
    for a, b in zip(findings, findings[1:]):
        assert a.end <= b.start, f"Overlapping or unsorted findings: {a} and {b}"
