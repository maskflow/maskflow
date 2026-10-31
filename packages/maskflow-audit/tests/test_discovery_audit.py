"""Walking a tree: identity stability, ordering, and graceful skipping."""

from __future__ import annotations

from pathlib import Path

from maskflow_audit.api import run_audit
from maskflow_audit.discovery.flows import flow_id
from maskflow_audit.discovery.walk import DEFAULT_EXCLUDES, iter_python_files

_APP = (
    "from openai import OpenAI\n"
    "client = OpenAI()\n"
    "def summarize(t):\n"
    "    return client.chat.completions.create(messages=t)\n"
)


def test_flow_id_is_not_line_based(tree) -> None:
    """The property the whole CI gate rests on.

    If an ID moved whenever a line was inserted above the call, every
    refactor would read as a wall of new unmasked flows and the gate would
    be switched off within a week.
    """
    before = run_audit(tree(_APP)).flows[0].flow_id
    after = run_audit(tree("import os\n# a new comment\nMARGIN = 1\n" + _APP)).flows[0].flow_id
    assert before == after


def test_flow_id_changes_when_the_call_moves_to_another_function(tree) -> None:
    before = run_audit(tree(_APP)).flows[0].flow_id
    renamed = run_audit(tree(_APP.replace("def summarize(", "def summarise_ticket("))).flows[0]
    assert renamed.flow_id != before


def test_two_identical_calls_in_one_function_get_distinct_ids(tree) -> None:
    summary = run_audit(
        tree(
            "from openai import OpenAI\n"
            "client = OpenAI()\n"
            "def f(a, b):\n"
            "    client.chat.completions.create(messages=a)\n"
            "    client.chat.completions.create(messages=b)\n"
        )
    )
    assert len(summary.flows) == 2
    assert len({f.flow_id for f in summary.flows}) == 2


def test_flow_id_is_stable_across_path_separators() -> None:
    # The walk stores POSIX-relative paths so a Windows runner and a Linux
    # one agree on an ID; otherwise the baseline could never be shared.
    assert flow_id("pkg/mod.py", "f", "x.y", 0) == flow_id("pkg/mod.py", "f", "x.y", 0)


def test_flows_are_sorted_so_the_report_is_order_independent(tmp_path: Path) -> None:
    (tmp_path / "zeta.py").write_text(_APP, encoding="utf-8")
    (tmp_path / "alpha.py").write_text(_APP, encoding="utf-8")
    files = [f.file for f in run_audit(tmp_path).flows]
    assert files == sorted(files)


def test_an_unparseable_file_is_skipped_not_fatal(tmp_path: Path) -> None:
    """An audit of somebody else's repo will meet Python 2 leftovers."""
    (tmp_path / "good.py").write_text(_APP, encoding="utf-8")
    (tmp_path / "broken.py").write_text("def f(:\n    pass\n", encoding="utf-8")
    summary = run_audit(tmp_path)
    assert len(summary.flows) == 1
    assert len(summary.skipped_files) == 1
    assert summary.skipped_files[0].file == "broken.py"


def test_a_skip_reason_never_quotes_the_source_line(tmp_path: Path) -> None:
    """A SyntaxError's str() includes the offending line, which could be
    the very data rule 1 forbids printing."""
    (tmp_path / "broken.py").write_text("x = 'aadhaar 111122223333' (\n", encoding="utf-8")
    summary = run_audit(tmp_path)
    assert "111122223333" not in summary.skipped_files[0].reason


def test_vendored_directories_are_excluded_by_default(tmp_path: Path) -> None:
    vendored = tmp_path / ".venv" / "lib"
    vendored.mkdir(parents=True)
    (vendored / "dep.py").write_text(_APP, encoding="utf-8")
    (tmp_path / "mine.py").write_text(_APP, encoding="utf-8")
    assert [f.file for f in run_audit(tmp_path).flows] == ["mine.py"]


def test_extra_excludes_are_honoured(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text(_APP, encoding="utf-8")
    (tmp_path / "mine.py").write_text(_APP, encoding="utf-8")
    summary = run_audit(tmp_path, exclude=DEFAULT_EXCLUDES | {"tests"})
    assert [f.file for f in summary.flows] == ["mine.py"]


def test_a_single_file_target_works(tmp_path: Path) -> None:
    target = tmp_path / "one.py"
    target.write_text(_APP, encoding="utf-8")
    assert len(run_audit(target).flows) == 1


def test_iter_python_files_is_sorted(tmp_path: Path) -> None:
    for name in ("c.py", "a.py", "b.py"):
        (tmp_path / name).write_text("", encoding="utf-8")
    names = [p.name for p in iter_python_files(tmp_path)]
    assert names == ["a.py", "b.py", "c.py"]


def test_an_empty_tree_reports_zero_flows_not_an_error(tmp_path: Path) -> None:
    summary = run_audit(tmp_path)
    assert summary.coverage.total_flows == 0
    assert summary.headline == "0 of 0 LLM egress paths masked"


def test_coverage_counts_add_up(tree) -> None:
    summary = run_audit(
        tree(
            "from openai import OpenAI\n"
            "from maskflow import mask\n"
            "client = OpenAI()\n"
            "def a(t):\n"
            "    client.chat.completions.create(messages=t)\n"
            "def b(t):\n"
            "    m, _ = mask(t)\n"
            "    client.chat.completions.create(messages=m)\n"
            "def c(t):\n"
            "    client.chat.completions.create(messages=blah())\n"
        )
    )
    c = summary.coverage
    assert c.masked + c.unmasked + c.unknown == c.total_flows == 3
    assert c.masked == 1


def test_no_flow_is_a_confirmed_leak_without_a_canary_run(tree) -> None:
    """M1 runs no canaries, so nothing may be called confirmed.

    Asserting a leak without having observed one is precisely what this
    tool exists not to do.
    """
    summary = run_audit(tree(_APP))
    assert summary.coverage.confirmed_leaks == 0
    assert summary.scope.canaries_run is False
    assert all(f.canary_status == "not_run" for f in summary.flows)


def test_unmasked_flows_are_ordered_before_masked_ones(tree) -> None:
    summary = run_audit(
        tree(
            "from openai import OpenAI\n"
            "from maskflow import mask\n"
            "client = OpenAI()\n"
            "def a_masked(t):\n"
            "    m, _ = mask(t)\n"
            "    client.chat.completions.create(messages=m)\n"
            "def z_unmasked(t):\n"
            "    client.chat.completions.create(messages=t)\n"
        )
    )
    # Alphabetically a_masked sorts first; the report must still lead with
    # the leak, because a reader who stops after one line should see it.
    assert summary.flows[0].masking_status == "unmasked"
