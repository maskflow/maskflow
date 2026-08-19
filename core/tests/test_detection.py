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

    for idx, sample in enumerate(POSITIVE_SAMPLES):
        found = _found_pairs(sample.text)
        for expected in sample.expected:
            total_expected += 1
            if expected not in found:
                # Report the sample index + entity type only -- never the raw
                # sample text or matched value, which may be real PII once
                # someone reproduces a bug report with a real-world string.
                misses.append((idx, expected[0]))

    accuracy = 1 - (len(misses) / total_expected)
    assert accuracy >= ACCURACY_TARGET, (
        f"Detection accuracy {accuracy:.2%} below {ACCURACY_TARGET:.0%} target. "
        f"Misses (index into POSITIVE_SAMPLES, expected type):\n"
        + "\n".join(f"  POSITIVE_SAMPLES[{idx}] -> {pii_type}" for idx, pii_type in misses)
    )


def test_negative_samples_produce_no_findings():
    false_positives = []
    for idx, text in enumerate(NEGATIVE_SAMPLES):
        findings = detect(text)
        if findings:
            false_positives.append((idx, [f.type for f in findings]))

    assert not false_positives, (
        "False positives on PII-free / invalid text "
        "(index into NEGATIVE_SAMPLES, types found):\n"
        + "\n".join(f"  NEGATIVE_SAMPLES[{idx}] -> {types}" for idx, types in false_positives)
    )


def test_findings_are_non_overlapping_and_sorted():
    text = (
        "Hi, this is Jane Doe. My email is jane.doe@example.com and my phone is "
        "415-555-0198. My SSN is 245-11-2222 for the background check."
    )
    findings = detect(text)
    for a, b in zip(findings, findings[1:]):
        assert a.end <= b.start, f"Overlapping or unsorted findings: {a} and {b}"
