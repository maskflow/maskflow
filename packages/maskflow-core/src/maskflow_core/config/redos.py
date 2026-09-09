"""Safety checks for user-supplied regex (custom.<NAME>.pattern,
exclusions.patterns) -- untrusted input that gets compiled and run against
every masked document, so a catastrophic-backtracking pattern is a DoS.

Three layers, in order:
  1. check_pattern_safety() -- a static, deliberately conservative scan for
     the classic nested-unbounded-quantifier / quantified-alternation
     shapes. Not a sound or complete analysis (it flags some safe patterns
     that happen to share the shape) -- see the module-level note in
     docs/configuration.md for why google-re2 (linear-time, but no
     backreferences/lookaround) is recommended as a future opt-in engine
     rather than adopted here.
  2. _adversarial_probe() -- after the static check passes, actually run
     the compiled pattern against a handful of generated pathological
     inputs in a child process (so a genuine hang gets killed rather than
     wedging the CLI). The child times each `re.search()` call on its own
     and reports the elapsed seconds; the parent flags a pattern whose
     *match* exceeds a small budget, or whose child never returns a result.
     Interpreter-`spawn` startup latency is deliberately excluded from that
     budget -- otherwise a slow/loaded CI runner would falsely flag a
     trivial pattern.
  3. safe_match() -- a size-capped match wrapper, used by the probe step
     above and exposed for whatever eventually runs these patterns against
     real text (not called anywhere else in this package yet).
"""

from __future__ import annotations

import multiprocessing
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from queue import Empty as _QueueEmpty

MAX_MATCH_LEN = 10_000
_PROBE_LENGTHS = (20, 40, 80)

# Wall-clock budget for the regex match *itself*, measured inside the child
# process so interpreter-`spawn` startup latency is excluded. Any pattern
# that isn't catastrophically backtracking matches an <=80-char probe in
# well under a millisecond; 0.2s is a generous margin for a loaded CI box.
_PROBE_MATCH_BUDGET_SECONDS = 0.2

# How long to wait for the child's *first* result -- covers `spawn`
# interpreter startup + module import + the first probe match. Spawn is
# ~0.1-2s in practice; 15s is comfortably clear of that without letting a
# genuine hang on the first probe wedge the caller indefinitely.
_PROBE_STARTUP_CEILING_SECONDS = 15.0

# Once the child is warm, every subsequent probe result should arrive almost
# immediately; if one doesn't within this window, that probe is hanging.
_PROBE_HANG_TIMEOUT_SECONDS = 2.0


class UnsafePatternError(ValueError):
    """Raised when a user-supplied pattern fails a ReDoS safety check."""


@dataclass(frozen=True)
class _Group:
    start: int
    end: int  # index of the matching ')'
    inner: str


def _group_spans(pattern: str) -> list[_Group]:
    """Every parenthesised group's span, at any nesting depth, correctly
    skipping character classes ([...]) and escaped parens (\\( \\)) --
    unlike a naive `[^()]*` regex, which breaks on nested groups."""
    groups: list[_Group] = []
    stack: list[int] = []
    i = 0
    n = len(pattern)
    in_class = False
    while i < n:
        c = pattern[i]
        if c == "\\":
            i += 2
            continue
        if in_class:
            if c == "]":
                in_class = False
            i += 1
            continue
        if c == "[":
            in_class = True
        elif c == "(":
            stack.append(i)
        elif c == ")" and stack:
            start = stack.pop()
            groups.append(_Group(start=start, end=i, inner=pattern[start + 1 : i]))
        i += 1
    return groups


_UNBOUNDED_QUANTIFIER_AT_END_RE = re.compile(r"(?:[+*]|\{\d*,\})\s*$")
_TOP_LEVEL_ALTERNATION_RE = re.compile(r"\|")


def _has_top_level_alternation(inner: str) -> bool:
    """True if `inner` contains a `|` not nested inside a deeper group --
    nested alternation is already covered when that inner group itself gets
    scanned."""
    depth = 0
    i = 0
    n = len(inner)
    in_class = False
    while i < n:
        c = inner[i]
        if c == "\\":
            i += 2
            continue
        if in_class:
            if c == "]":
                in_class = False
            i += 1
            continue
        if c == "[":
            in_class = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "|" and depth == 0:
            return True
        i += 1
    return False


def check_pattern_safety(pattern: str) -> None:
    """Raise UnsafePatternError if `pattern`'s *shape* matches a known
    catastrophic-backtracking cause. Does not compile or run the pattern --
    callers should also run it through _adversarial_probe() (or rely on
    schema.py's validator, which does both)."""
    try:
        re.compile(pattern)
    except re.error as exc:
        raise UnsafePatternError(f"not a valid regular expression: {exc}") from exc

    for group in _group_spans(pattern):
        followed_by = pattern[group.end + 1 :]
        quantified = bool(re.match(r"^(?:[+*]|\{\d*,\})", followed_by))
        if not quantified:
            continue

        if _UNBOUNDED_QUANTIFIER_AT_END_RE.search(group.inner):
            raise UnsafePatternError(
                f"unsafe pattern: group '({group.inner})' contains an unbounded "
                "quantifier and is itself unbounded-quantified -- this shape "
                "(e.g. (a+)+, (a*)*) causes catastrophic backtracking. Rewrite "
                "with a bounded repeat, e.g. `{1,20}` instead of `+`/`*`, or "
                "flatten the nested repetition."
            )

        if _has_top_level_alternation(group.inner):
            raise UnsafePatternError(
                f"unsafe pattern: group '({group.inner})' contains alternation "
                "and is itself unbounded-quantified -- this shape (e.g. "
                "(a|ab)*) can cause catastrophic backtracking when branches "
                "overlap. Rewrite with a bounded repeat, e.g. `{1,20}`, or "
                "restructure to avoid repeating an alternation."
            )


def _run_probes(
    pattern: str,
    probes: Sequence[str],
    result_queue: multiprocessing.Queue[float | str],
) -> None:
    """Child-process body: compile once, then time each probe's `search()`
    on its own and put the elapsed seconds on the queue. A `str` on the
    queue is an error message (compile failure) rather than a timing --
    normally unreachable, since the parent's static check already compiled
    the pattern, but `_adversarial_probe()` can be called directly."""
    try:
        compiled = re.compile(pattern)
    except re.error as exc:  # pragma: no cover - parent already compiled it
        result_queue.put(f"pattern failed to compile inside the probe: {exc}")
        return
    for probe in probes:
        start = time.perf_counter()
        compiled.search(probe)
        result_queue.put(time.perf_counter() - start)


def _adversarial_probe(pattern: str) -> None:
    """Run `pattern` against several generated pathological inputs in one
    child process, timing each match individually. Raises UnsafePatternError
    when a match exceeds `_PROBE_MATCH_BUDGET_SECONDS` or when a probe never
    reports back (a genuine hang). Interpreter-`spawn` startup latency is
    absorbed by `_PROBE_STARTUP_CEILING_SECONDS` and never counted against a
    pattern."""
    alphabet_chars = sorted(set(re.sub(r"[^A-Za-z0-9]", "", pattern)))
    probe_char = alphabet_chars[0] if alphabet_chars else "a"

    probes: list[tuple[int, str]] = []
    for length in _PROBE_LENGTHS:
        for text in (probe_char * length, (probe_char * length) + "!"):
            probes.append((length, text[:MAX_MATCH_LEN]))

    ctx = multiprocessing.get_context("spawn")
    result_queue: multiprocessing.Queue[float | str] = ctx.Queue()
    proc = ctx.Process(target=_run_probes, args=(pattern, [t for _, t in probes], result_queue))
    proc.start()
    try:
        for index, (length, _) in enumerate(probes):
            wait = _PROBE_STARTUP_CEILING_SECONDS if index == 0 else _PROBE_HANG_TIMEOUT_SECONDS
            try:
                outcome = result_queue.get(timeout=wait)
            except _QueueEmpty:
                raise UnsafePatternError(
                    f"unsafe pattern: matching a {length}-character adversarial probe "
                    "did not complete -- almost certainly catastrophic backtracking. "
                    "Rewrite with bounded repeats."
                ) from None
            if isinstance(outcome, str):
                raise UnsafePatternError(outcome)
            if outcome > _PROBE_MATCH_BUDGET_SECONDS:
                raise UnsafePatternError(
                    f"unsafe pattern: matching a {length}-character adversarial probe "
                    f"took {outcome:.3f}s, over the {_PROBE_MATCH_BUDGET_SECONDS}s "
                    "budget -- likely catastrophic backtracking. Rewrite with bounded "
                    "repeats."
                )
    finally:
        if proc.is_alive():
            proc.terminate()
        proc.join()
        proc.close()


def check_pattern_safety_with_probe(pattern: str) -> None:
    """Full safety check: static shape check, then adversarial timing
    probe. This is what schema.py's field validators call."""
    check_pattern_safety(pattern)
    _adversarial_probe(pattern)


def safe_match(
    compiled: re.Pattern[str], text: str, max_len: int = MAX_MATCH_LEN
) -> re.Match[str] | None:
    """Match wrapper that refuses to run a regex against oversized input,
    regardless of how the pattern was validated. Not called anywhere in
    this package today -- exposed as the sanctioned way for any future code
    that runs these user-supplied patterns against real text."""
    if len(text) > max_len:
        raise UnsafePatternError(
            f"refusing to match: input is {len(text)} chars, over the {max_len}-char cap"
        )
    return compiled.search(text)
