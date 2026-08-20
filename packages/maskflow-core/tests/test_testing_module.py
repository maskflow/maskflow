"""Direct unit coverage for maskflow_core.testing's internals -- the pieces
test_leak_gate.py's session-wide integration test exercises indirectly
(logging/exception capture actually happening during a real pytest run) but
doesn't itself prove in isolation.
"""

from types import SimpleNamespace

from maskflow_core import testing


def test_assert_no_leaks_passes_when_nothing_matches() -> None:
    testing.assert_no_leaks(["some log line", "another"], ["245-11-2222"])


def test_assert_no_leaks_fails_when_a_secret_is_present() -> None:
    try:
        testing.assert_no_leaks(["oops: 245-11-2222 leaked"], ["245-11-2222"])
    except AssertionError as exc:
        assert "245-11-2222" in str(exc)
    else:
        raise AssertionError("expected assert_no_leaks to raise")


def test_capturing_handler_appends_formatted_log_messages() -> None:
    import logging

    pool: list[str] = []
    handler = testing._CapturingHandler(pool)
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )

    handler.emit(record)

    assert pool == ["hello world"]


def test_pytest_exception_interact_ignores_calls_with_no_excinfo() -> None:
    before = list(testing.LEAK_POOL)
    testing.pytest_exception_interact(node=None, call=SimpleNamespace(excinfo=None), report=None)
    assert testing.LEAK_POOL == before


def test_pytest_exception_interact_captures_exception_text() -> None:
    # A benign marker, not a real (or fixture-shaped) PII value -- this test
    # deliberately appends to the *shared* LEAK_POOL that test_leak_gate.py
    # scans at the end of the session, so it must never inject anything that
    # would make that check misfire.
    marker = "unit-test-exception-marker-not-real-pii"
    before_len = len(testing.LEAK_POOL)
    fake_excinfo = SimpleNamespace(
        value=ValueError(f"boom {marker}"),
        getrepr=lambda style: f"traceback text {marker}",
    )
    fake_call = SimpleNamespace(excinfo=fake_excinfo)
    testing.pytest_exception_interact(node=None, call=fake_call, report=None)

    assert len(testing.LEAK_POOL) == before_len + 2
    assert marker in testing.LEAK_POOL[-2]
    assert marker in testing.LEAK_POOL[-1]
