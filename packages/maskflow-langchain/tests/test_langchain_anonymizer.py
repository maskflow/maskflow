"""MaskflowAnonymizer + MaskflowReversibleAnonymizer core behavior."""

from __future__ import annotations

import warnings

import pytest
from maskflow_langchain import (
    MaskflowAnonymizer,
    MaskflowReversibleAnonymizer,
    ReversibleAnonymizerBase,
)
from maskflow_langchain.base import AnonymizerBase

PAN = "ABCPE1234F"  # synthetic, structurally valid
EMAIL = "alice@example.com"


def test_non_reversible_anonymize_masks_and_is_independent_per_call() -> None:
    a = MaskflowAnonymizer(add_default_faker_operators=False)
    out1 = a.anonymize(f"PAN {PAN}")
    out2 = a.anonymize(f"PAN {PAN}")
    assert PAN not in out1 and "<PAN_1>" in out1
    assert out1 == out2  # each call starts fresh -> same first-counter token


def test_reversible_round_trip() -> None:
    a = MaskflowReversibleAnonymizer()
    masked = a.anonymize(f"My PAN is {PAN}, mail {EMAIL}")
    assert PAN not in masked and EMAIL not in masked
    assert a.deanonymize(f"the answer references {masked.split()[3].rstrip(',')}") == (
        f"the answer references {PAN}"
    )
    assert a.deanonymize(masked) == f"My PAN is {PAN}, mail {EMAIL}"


def test_reversible_keeps_identity_across_calls() -> None:
    a = MaskflowReversibleAnonymizer()
    m1 = a.anonymize(f"PAN {PAN}")
    m2 = a.anonymize(f"again PAN {PAN}")
    assert "<PAN_1>" in m1 and "<PAN_1>" in m2


def test_deanonymizer_mapping_shape_matches_presidio() -> None:
    a = MaskflowReversibleAnonymizer()
    a.anonymize(f"PAN {PAN} and mail {EMAIL} and again {EMAIL}")
    m = a.deanonymizer_mapping
    assert set(m) == {"PAN", "EMAIL"}
    assert m["PAN"] == {"<PAN_1>": PAN}
    assert m["EMAIL"] == {"<EMAIL_1>": EMAIL}
    # anonymizer_mapping is the inverse
    assert a.anonymizer_mapping["PAN"] == {PAN: "<PAN_1>"}


def test_reset_clears_mapping_and_identity() -> None:
    a = MaskflowReversibleAnonymizer()
    a.anonymize(f"PAN {PAN}")
    assert a.deanonymizer_mapping
    a.reset_deanonymizer_mapping()
    assert a.deanonymizer_mapping == {}
    # a fresh value gets <PAN_1> again
    assert "<PAN_1>" in a.anonymize("PAN ABCPE9999K")


def test_deanonymize_without_mapping_warns_and_passes_through() -> None:
    a = MaskflowReversibleAnonymizer()
    with pytest.warns(UserWarning, match="No deanonymizer mapping"):
        assert a.deanonymize("nothing here") == "nothing here"


def test_analyzed_fields_restricts_detection() -> None:
    a = MaskflowReversibleAnonymizer(analyzed_fields=["EMAIL"])
    out = a.anonymize(f"PAN {PAN} mail {EMAIL}")
    assert PAN in out  # PAN not in analyzed_fields -> left alone
    assert EMAIL not in out


def test_allow_list_from_constructor_is_respected() -> None:
    a = MaskflowReversibleAnonymizer(allow_list=[EMAIL])
    out = a.anonymize(f"PAN {PAN} mail {EMAIL}")
    assert EMAIL in out and "<PAN_1>" in out


def test_per_call_allow_list_mismatch_raises() -> None:
    a = MaskflowReversibleAnonymizer()
    with pytest.raises(ValueError, match="constructor"):
        a.anonymize("PAN ABCPE1234F", allow_list=["something"])


def test_operators_surrogate_produces_fake_reversible_value() -> None:
    a = MaskflowReversibleAnonymizer(operators={"EMAIL": "surrogate"})
    masked = a.anonymize(f"mail {EMAIL}")
    assert EMAIL not in masked
    assert "@" in masked  # a plausible fake email, not a <TOKEN>
    assert a.deanonymize(masked) == f"mail {EMAIL}"


def test_isinstance_contract() -> None:
    a = MaskflowReversibleAnonymizer()
    assert isinstance(a, ReversibleAnonymizerBase)
    assert isinstance(a, AnonymizerBase)
    assert isinstance(MaskflowAnonymizer(), AnonymizerBase)


def test_faker_seed_accepted_with_warning() -> None:
    with pytest.warns(UserWarning, match="faker_seed"):
        MaskflowReversibleAnonymizer(faker_seed=42)


def test_language_non_en_warns() -> None:
    a = MaskflowAnonymizer()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        a.anonymize("PAN ABCPE1234F", language="de")
    assert any("language" in str(w.message) for w in caught)
