"""Score `maskflow audit` against the audit-fixtures corpus.

The open-benchmark discipline applied to the audit itself. Three metrics,
each answering a question a buyer actually asks:

  * **discovery recall** -- of the egress paths that exist, how many did we
    find? A missed sink is a clean report for a leaking app, which is the
    worst failure mode this tool has.
  * **classification accuracy** -- of the paths we found, how many did we
    label correctly (masked / unmasked / unknown)?
  * **leak-confirmation precision and recall** -- of the paths that leak,
    how many did a canary prove, and of the ones we called proven, how
    many really leak?

Ground truth is each fixture's committed `expected.json`. Run:

    uv run python -m bench.auditbench.score --out bench/reports/auditbench-v1

`--check` re-scores and fails if any metric has dropped more than the
tolerance below the committed baseline, which is what `make
rebaseline-audit` regenerates.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _ROOT / "audit-fixtures"
_BASELINE = _ROOT / "bench" / "baselines-audit.json"

VERSION = "auditbench-v1.0"

#: Percentage points a metric may drop before `--check` fails. Same
#: tolerance, and the same units, as the F1 gates in bench/indiapii.
MAX_DROP = 2.0

_MASKED = "masked"


@dataclass(frozen=True)
class Score:
    """One metric, as a fraction and as counts."""

    name: str
    hits: int
    total: int

    @property
    def value(self) -> float | None:
        """None when undefined -- never silently 0.0, which would read as
        a measured failure rather than an absent measurement."""
        return (self.hits / self.total) if self.total else None

    def as_dict(self) -> dict[str, object]:
        return {"hits": self.hits, "total": self.total, "value": self.value}


def _fixtures() -> list[Path]:
    return sorted(p for p in _FIXTURES.iterdir() if p.is_dir())


def score_all(*, prove: bool = False) -> dict[str, Score]:
    """Score every fixture. `prove` also runs the canary harness."""
    from maskflow_audit.api import run_audit
    from maskflow_audit.discovery.walk import discover
    from maskflow_audit.prove import run_canary_proof
    from maskflow_audit.sinks.loader import default_registry

    registry = default_registry()

    discovery_hits = discovery_total = 0
    classification_hits = classification_total = 0
    leak_tp = leak_fp = leak_fn = 0

    for directory in _fixtures():
        expected = json.loads((directory / "expected.json").read_text(encoding="utf-8"))
        want_flows = expected["flows"]

        proof = None
        if prove:
            flows, _, _ = discover(directory, registry, exclude=frozenset())
            proof = run_canary_proof(directory, flows, allow_env=True)

        summary = run_audit(directory, sinks=registry, prove=proof)
        got = list(summary.flows)

        # Discovery recall: one expected flow is "found" when a reported
        # flow matches it on (file, sink_id).
        discovery_total += len(want_flows)
        unmatched = list(got)
        for want in want_flows:
            match = next(
                (f for f in unmatched if f.file == want["file"] and f.sink_id == want["sink_id"]),
                None,
            )
            if match is not None:
                discovery_hits += 1
                unmatched.remove(match)
                classification_total += 1
                if match.masking_status == want["masking_status"]:
                    classification_hits += 1

        # Leak confirmation, only meaningful when canaries ran.
        if prove:
            for want in want_flows:
                leaks = expected["verdict"] == "leaks" and want["masking_status"] == "unmasked"
                match = next(
                    (f for f in got if f.file == want["file"] and f.sink_id == want["sink_id"]),
                    None,
                )
                proven = match is not None and match.canary_status == "escaped"
                if leaks and proven:
                    leak_tp += 1
                elif proven and not leaks:
                    leak_fp += 1
                elif leaks and not proven:
                    leak_fn += 1

    scores = {
        "discovery_recall": Score("discovery_recall", discovery_hits, discovery_total),
        "classification_accuracy": Score(
            "classification_accuracy", classification_hits, classification_total
        ),
    }
    if prove:
        scores["leak_precision"] = Score("leak_precision", leak_tp, leak_tp + leak_fp)
        scores["leak_recall"] = Score("leak_recall", leak_tp, leak_tp + leak_fn)
    return scores


def to_markdown(scores: dict[str, Score]) -> str:
    rows = "\n".join(
        f"| {name} | "
        + (f"{score.value:.1%}" if score.value is not None else "—")
        + f" | {score.hits}/{score.total} |"
        for name, score in sorted(scores.items())
    )
    return (
        f"# {VERSION}\n\n"
        f"`maskflow audit` scored against the {len(_fixtures())} applications in "
        "`audit-fixtures/`, each with committed expected results.\n\n"
        "A dash means the metric is undefined (nothing to measure), never a "
        "measured zero.\n\n"
        "| metric | value | counts |\n|---|---|---|\n" + rows + "\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bench.auditbench.score")
    parser.add_argument("--out", type=Path, help="Directory for results.json / results.md.")
    parser.add_argument(
        "--prove", action="store_true", help="Also run the canary harness (needs the SDKs)."
    )
    parser.add_argument("--rebaseline", action="store_true", help=f"Overwrite {_BASELINE.name}.")
    parser.add_argument(
        "--check", action="store_true", help="Fail if a metric regressed beyond the tolerance."
    )
    args = parser.parse_args(argv)

    scores = score_all(prove=args.prove)
    payload = {
        "version": VERSION,
        "fixtures": len(_fixtures()),
        "metrics": {name: score.as_dict() for name, score in sorted(scores.items())},
    }

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "results.json").write_text(json.dumps(payload, indent=2) + "\n", "utf-8")
        (args.out / "results.md").write_text(to_markdown(scores), encoding="utf-8")
        print(f"wrote {args.out / 'results.json'} and {args.out / 'results.md'}", file=sys.stderr)

    print(to_markdown(scores))

    if args.rebaseline:
        new = {name: score.value for name, score in sorted(scores.items())}
        old = json.loads(_BASELINE.read_text(encoding="utf-8")) if _BASELINE.exists() else {}
        for name in sorted(set(old) | set(new)):
            if old.get(name) != new.get(name):
                print(f"{name}: {old.get(name)} -> {new.get(name)}", file=sys.stderr)
        _BASELINE.write_text(json.dumps(new, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {_BASELINE}", file=sys.stderr)

    if args.check:
        if not _BASELINE.exists():
            print(f"no baseline at {_BASELINE} -- run with --rebaseline first", file=sys.stderr)
            return 0
        baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
        # Iterate the BASELINE's keys: a metric that does not exist yet
        # must not retroactively fail a build, same rule as the F1 gates.
        regressions = []
        for name, was in baseline.items():
            if was is None:
                continue
            now = scores[name].value if name in scores else None
            if now is None:
                regressions.append(f"{name}: baseline {was:.4f}, now undefined")
                continue
            drop = (was - now) * 100
            if drop > MAX_DROP:
                regressions.append(
                    f"{name}: baseline {was:.4f} -> {now:.4f} "
                    f"({drop:.1f} points, max allowed {MAX_DROP})"
                )
        if regressions:
            print("regression(s) beyond baseline:", file=sys.stderr)
            for line in regressions:
                print(f"  - {line}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
