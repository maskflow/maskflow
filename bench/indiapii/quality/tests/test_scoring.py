from __future__ import annotations

import json

from bench.indiapii.quality.scoring import bootstrap_ci, has_leak, score_fields


class TestHasLeak:
    def test_plain_token_detected(self) -> None:
        assert has_leak("Please confirm <PAN_1> is correct.")

    def test_nonce_token_detected(self) -> None:
        assert has_leak("Please confirm <PAN_1_a4f9> is correct.")

    def test_clean_text_not_flagged(self) -> None:
        assert not has_leak("Please confirm your PAN is correct.")


class TestScoreFields:
    def _gold(self) -> dict[str, str | None]:
        return {
            "applicant_name": "Priya Iyer",
            "pan": "ABCDE1234F",
            "address": None,
        }

    def test_all_correct(self) -> None:
        response = json.dumps(
            {"applicant_name": "Priya Iyer", "pan": "ABCDE1234F", "address": None}
        )
        result = score_fields(response, self._gold())
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1 == 1.0

    def test_normalization_ignores_case_and_whitespace(self) -> None:
        response = json.dumps({"applicant_name": "  priya   iyer ", "pan": "abcde1234f"})
        result = score_fields(response, self._gold())
        assert result.recall == 1.0

    def test_missing_field_hurts_recall(self) -> None:
        response = json.dumps({"applicant_name": "Priya Iyer"})
        result = score_fields(response, self._gold())
        assert result.recall == 0.5
        assert result.precision == 1.0

    def test_wrong_value_hurts_precision_and_recall(self) -> None:
        response = json.dumps({"applicant_name": "Someone Else", "pan": "ABCDE1234F"})
        result = score_fields(response, self._gold())
        assert result.precision == 0.5
        assert result.recall == 0.5

    def test_hallucinated_field_not_in_document_hurts_precision(self) -> None:
        gold = {"applicant_name": "Priya Iyer", "aadhaar": None}
        response = json.dumps({"applicant_name": "Priya Iyer", "aadhaar": "234567890124"})
        result = score_fields(response, gold)
        assert result.precision == 0.5
        assert result.recall == 1.0

    def test_unparseable_response_scores_zero(self) -> None:
        result = score_fields("not json at all", self._gold())
        assert result.precision == 0.0
        assert result.recall == 0.0
        assert result.f1 == 0.0

    def test_no_gold_fields_returns_none(self) -> None:
        result = score_fields("{}", {})
        assert result.precision is None
        assert result.recall is None
        assert result.f1 is None

    def test_json_embedded_in_prose_is_still_parsed(self) -> None:
        response = (
            'Sure, here you go:\n{"applicant_name": "Priya Iyer", "pan": "ABCDE1234F"}\n'
            "Let me know."
        )
        result = score_fields(response, self._gold())
        assert result.recall == 1.0


class TestBootstrapCi:
    def test_empty_values(self) -> None:
        assert bootstrap_ci([]) == (0.0, 0.0, 0.0)

    def test_single_value(self) -> None:
        assert bootstrap_ci([3.0]) == (3.0, 3.0, 3.0)

    def test_mean_matches_plain_average(self) -> None:
        mean, lo, hi = bootstrap_ci([1.0, 2.0, 3.0, 4.0], seed=1)
        assert mean == 2.5
        assert lo <= mean <= hi

    def test_deterministic_for_same_seed(self) -> None:
        values = [1.0, -1.0, 2.0, 0.5, -0.5, 3.0]
        assert bootstrap_ci(values, seed=5) == bootstrap_ci(values, seed=5)

    def test_all_zero_deltas_gives_zero_width_interval(self) -> None:
        mean, lo, hi = bootstrap_ci([0.0, 0.0, 0.0, 0.0])
        assert (mean, lo, hi) == (0.0, 0.0, 0.0)
