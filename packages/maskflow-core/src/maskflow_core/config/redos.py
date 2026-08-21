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
     inputs under a hard per-probe time budget, in a child process so a
     genuine hang gets killed rather than wedging the CLI.
  3. safe_match() -- a size-capped match wrapper, used by the probe step
     above and exposed for whatever eventually runs these patterns against
     real text (not called anywhere else in this package yet).
"""

from __future__ import annotations

import multiprocessing
import re
from dataclasses import dataclass

MAX_MATCH_LEN = 10_000
_PROBE_LENGTHS = (20, 40, 80)
_PROBE_TIMEOUT_SECONDS = 0.5


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


def _run_probe(pattern: str, probe: str, result_queue: multiprocessing.Queue[bool]) -> None:
    compiled = re.compile(pattern)
    compiled.search(probe)
    result_queue.put(True)


def _adversarial_probe(pattern: str) -> None:
    """Run `pattern` against several generated pathological inputs, each
    under a hard per-probe timeout in a child process. Raises
    UnsafePatternError on the first timeout."""
    alphabet_chars = sorted(set(re.sub(r"[^A-Za-z0-9]", "", pattern)))
    probe_char = alphabet_chars[0] if alphabet_chars else "a"

    for length in _PROBE_LENGTHS:
        for probe in (probe_char * length, (probe_char * length) + "!"):
            probe = probe[:MAX_MATCH_LEN]
            ctx = multiprocessing.get_context("spawn")
            queue: multiprocessing.Queue[bool] = ctx.Queue()
            proc = ctx.Process(target=_run_probe, args=(pattern, probe, queue))
            proc.start()
            proc.join(timeout=_PROBE_TIMEOUT_SECONDS)
            if proc.is_alive():
                proc.terminate()
                proc.join()
                raise UnsafePatternError(
                    f"unsafe pattern: took longer than {_PROBE_TIMEOUT_SECONDS}s to "
                    f"match against a {length}-character adversarial probe -- likely "
                    "catastrophic backtracking. Rewrite with bounded repeats."
                )
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
