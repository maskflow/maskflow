"""Per-session masking daemon.

One process per Claude Code session, listening on a 0600 unix socket. It
owns the session's `maskflow.Session` -- the only place real values live,
in memory, never on disk -- and serialises every request through one lock,
so hooks firing in parallel for parallel tool calls always see one
consistent value <-> placeholder mapping.

Requests and responses are single JSON lines (see protocol.py). Nothing in
a request is ever logged; the log carries lifecycle events and counts only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import secrets
import signal
import socket
import socketserver
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import __version__, paths

_TOKEN_RE = re.compile(r"<([A-Z][A-Z_]*?)_\d+(?:_[0-9a-f]+)?>")
_MAX_REQUEST = 256 * 1024 * 1024
DEFAULT_IDLE_SECONDS = 6 * 3600
TICKET_TTL = 600.0
_NOISY_PROMPT_TYPES = frozenset({"PERSON_NAME", "INDIAN_ADDRESS", "PERSON", "LOCATION"})

log = logging.getLogger("maskflow_agent.daemon")


class _ProblemCounter(logging.Handler):
    """Counts WARNING+ records so a clean session's log can be deleted at
    shutdown while a log with something worth reading is kept."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.count = 0

    def emit(self, record: logging.LogRecord) -> None:
        self.count += 1


_problems = _ProblemCounter()
log.addHandler(_problems)


class _KnownValues:
    """Every value this session has already masked, matched literally in
    later text whatever its context -- a bare mobile in a `grep` hit is
    masked because the same number was identified earlier under a `mobile`
    header. Aho-Corasick (linear time), rebuilt only when the mapping grows.
    A match must not continue an alphanumeric run on either side, so a known
    number inside a longer number is left alone."""

    def __init__(self) -> None:
        self._size = -1
        self._automaton: Any = None

    def _rebuild(self, mapping: Any) -> None:
        import ahocorasick

        automaton = ahocorasick.Automaton()
        for token in mapping:
            entry = mapping[token]
            original = getattr(entry, "original", None)
            if entry.reversible and isinstance(original, str) and len(original) >= 4:
                automaton.add_word(original, (original, token))
        self._automaton = automaton if len(automaton) else None
        if self._automaton is not None:
            self._automaton.make_automaton()
        self._size = len(mapping)

    def apply(self, text: str, mapping: Any) -> str:
        if len(mapping) != self._size:
            self._rebuild(mapping)
        if self._automaton is None or not text:
            return text
        hits: list[tuple[int, int, str]] = []
        for end, (original, token) in self._automaton.iter(text):
            start = end - len(original) + 1
            before = text[start - 1] if start > 0 else ""
            after = text[end + 1] if end + 1 < len(text) else ""
            if (original[0].isalnum() and before.isalnum()) or (
                original[-1].isalnum() and after.isalnum()
            ):
                continue
            hits.append((start, end + 1, token))
        if not hits:
            return text
        # Longest-first, then left-most, non-overlapping.
        hits.sort(key=lambda h: (-(h[1] - h[0]), h[0]))
        taken: list[tuple[int, int, str]] = []
        for hit in hits:
            if all(hit[1] <= t[0] or hit[0] >= t[1] for t in taken):
                taken.append(hit)
        taken.sort()
        out, cursor = [], 0
        for start, end, token in taken:
            out.append(text[cursor:start])
            out.append(token)
            cursor = end
        out.append(text[cursor:])
        return "".join(out)


class _State:
    def __init__(self, session_id: str, patterns_only: bool) -> None:
        # maskflow_core's config loader rejects unknown MASKFLOW_* variables;
        # ours are consumed already (paths.home() is cached).
        paths.home()
        for name in [n for n in os.environ if n.startswith("MASKFLOW_AGENT_")]:
            del os.environ[name]
        import maskflow  # heavy: engine + packs + (lazily) spaCy

        self.session_id = session_id
        self.ner = not patterns_only and _spacy_model_available()
        if not patterns_only and not self.ner:
            log.warning(
                "spaCy model en_core_web_sm not installed: masking IDs/numbers only, "
                "not names/addresses (python -m spacy download en_core_web_sm)"
            )
        self.session = maskflow.Session(ttl_seconds=None, patterns_only=not self.ner)
        self.lock = threading.Lock()
        self.last_seen = time.monotonic()
        self.started = time.time()
        self.masked_occurrences: Counter[str] = Counter()
        self.prompt_findings: Counter[str] = Counter()
        self.unmask_calls = 0
        self.tool_results = 0
        self.withheld = 0
        self.known = _KnownValues()
        # Single-use run-time-unmask tickets: sha256(command) -> (ticket, expiry).
        self.tickets: dict[str, tuple[str, float]] = {}

    # -- helpers -----------------------------------------------------------
    def tokens(self) -> set[str]:
        return set(self.session.mapping)

    def mask_text(self, text: str) -> str:
        masked = self.known.apply(self.session.mask(text), self.session.mapping)
        if masked != text:
            for match in _TOKEN_RE.finditer(masked):
                if match.group(0) in self.session.mapping:
                    self.masked_occurrences[match.group(1)] += 1
        return masked

    def mask_value(self, value: Any, depth: int = 0) -> Any:
        if depth > 64:
            raise ValueError("value nested too deeply")
        if isinstance(value, str):
            return self.mask_text(value)
        if isinstance(value, list):
            return [self.mask_value(v, depth + 1) for v in value]
        if isinstance(value, dict):
            return {k: self.mask_value(v, depth + 1) for k, v in value.items()}
        return value

    def distinct_values(self) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for entry in self.session.mapping.values():
            counts[str(entry.entity_type)] += 1
        return dict(counts)

    def summary(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "maskflow_agent": __version__,
            "ner": self.ner,
            "started_at": self.started,
            "ended_at": time.time(),
            "tool_results_masked": self.tool_results,
            "masked_occurrences_by_type": dict(self.masked_occurrences),
            "distinct_values_by_type": self.distinct_values(),
            "prompt_findings_by_type": dict(self.prompt_findings),
            "run_time_unmask_calls": self.unmask_calls,
        }


def _digest(command: str) -> str:
    return hashlib.sha256(command.encode("utf-8")).hexdigest()


def _spacy_model_available() -> bool:
    try:
        from maskflow_core.ner import _get_nlp

        _get_nlp()
    except (OSError, ImportError):
        return False
    return True


def _handle(state: _State, request: dict[str, Any], stop: Callable[[], None]) -> dict[str, Any]:
    op = request.get("op")
    if op == "ping":
        return {"ok": True, "version": __version__, "pid": os.getpid(), "ner": state.ner}
    if op == "mask_value":
        before = len(state.session.mapping)
        masked = state.mask_value(request.get("value"))
        state.tool_results += 1
        return {
            "ok": True,
            "value": masked,
            "changed": masked != request.get("value"),
            "new_values": len(state.session.mapping) - before,
        }
    if op == "issue_ticket":
        # Only the PreToolUse hook asks for these, for the exact command it
        # has just checked against the allowlist and the user's rules.
        command = str(request.get("command", ""))
        ticket = secrets.token_hex(16)
        now = time.monotonic()
        state.tickets = {k: v for k, v in state.tickets.items() if v[1] > now}
        state.tickets[_digest(command)] = (ticket, now + TICKET_TTL)
        return {"ok": True, "ticket": ticket}
    if op == "unmask_text":
        # Never without a ticket: neither a model-crafted `maskflow-agent exec`
        # call nor a direct socket client can recover a value.
        text = str(request.get("text", ""))
        issued = state.tickets.pop(_digest(text), None)
        if (
            issued is None
            or issued[1] < time.monotonic()
            or not secrets.compare_digest(issued[0], str(request.get("ticket", "")))
        ):
            return {"ok": False, "error": "no valid ticket"}
        state.unmask_calls += 1
        return {"ok": True, "text": state.session.unmask(text)}
    if op == "tokens_in":
        text = str(request.get("text", ""))
        known = state.tokens()
        found = sorted({m.group(0) for m in _TOKEN_RE.finditer(text)} & known)
        return {"ok": True, "tokens": found}
    if op == "scan":
        # Prompt warnings use the precise pattern recognizers only: NER
        # name/address guesses on short instructions ("SELECT", "PAN") are
        # noise the user would learn to ignore.
        from maskflow_core.detection import detect_patterns_only

        counts = Counter(
            str(s.entity_type)
            for s in detect_patterns_only(str(request.get("text", "")))
            if str(s.entity_type) not in _NOISY_PROMPT_TYPES
        )
        state.prompt_findings.update(counts)
        return {"ok": True, "counts": dict(counts)}
    if op == "reserve":
        tokens = [t for t in request.get("tokens", []) if isinstance(t, str)]
        if tokens:
            # Session.mask() reserves every placeholder look-alike in its
            # input, so values masked from now on never reuse these names.
            state.session.mask(" ".join(sorted(set(tokens))))
        return {"ok": True, "reserved": len(set(tokens))}
    if op == "stats":
        return {"ok": True, "summary": state.summary()}
    if op == "end":
        summary = state.summary()
        try:
            out = paths.summary_path(state.session_id)
            out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            os.chmod(out, 0o600)
        except OSError:
            log.warning("could not write session summary")
        stop()
        return {"ok": True, "summary": summary}
    return {"ok": False, "error": "unknown op"}


class _Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    # Claude Code runs tool calls -- and so their hooks -- in parallel. The
    # socketserver default backlog of 5 made Linux refuse the 6th concurrent
    # connect outright (EAGAIN), and that hook withheld its tool's output.
    request_queue_size = 128
    state: _State
    stop_event: threading.Event


class _RequestHandler(socketserver.StreamRequestHandler):
    server: _Server

    def handle(self) -> None:
        raw = self.rfile.read(_MAX_REQUEST + 1)
        if len(raw) > _MAX_REQUEST:
            self._reply({"ok": False, "error": "request too large"})
            return
        try:
            request = json.loads(raw.decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError
        except (UnicodeDecodeError, ValueError):
            self._reply({"ok": False, "error": "bad request"})
            return
        state = self.server.state
        with state.lock:
            state.last_seen = time.monotonic()
            try:
                response = _handle(state, request, self.server.stop_event.set)
            except Exception as exc:  # noqa: BLE001 -- report type only, never content
                log.error("request failed: %s", type(exc).__name__)
                response = {"ok": False, "error": type(exc).__name__}
        self._reply(response)

    def _reply(self, response: dict[str, Any]) -> None:
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")


def serve(session_id: str, idle_seconds: float, patterns_only: bool) -> int:
    sock_path = paths.socket_path(session_id)
    pid_file = paths.pid_path(session_id)
    other = paths.live_pid(session_id)
    if other is not None and other != os.getpid():
        log.info("another daemon (pid %d) owns this session", other)
        return 0
    # Written before the slow engine import, so a hook that arrives while we
    # load waits for us instead of starting a second daemon.
    pid_file.write_text(str(os.getpid()))
    try:
        swept = paths.sweep_stale()
        if swept:
            log.info("removed %d stale session file(s)", swept)
    except OSError:
        pass
    if sock_path.exists():
        # Another live daemon owns this session: don't steal its socket.
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(1.0)
                probe.connect(str(sock_path))
            log.info("daemon already running for this session")
            return 0
        except OSError:
            sock_path.unlink(missing_ok=True)

    state = _State(session_id, patterns_only)
    # Load the engine (and spaCy, unless patterns_only) before accepting
    # connections, so the first real request isn't the slow one.
    state.session.mask("warm-up")

    old_umask = os.umask(0o177)
    try:
        server = _Server(str(sock_path), _RequestHandler)
    finally:
        os.umask(old_umask)
    server.state = state
    server.stop_event = threading.Event()

    def _watch() -> None:
        while not server.stop_event.wait(5.0):
            if time.monotonic() - state.last_seen > idle_seconds:
                log.info("idle timeout")
                server.stop_event.set()
        server.shutdown()

    def _on_signal(signum: int, _frame: object) -> None:
        server.stop_event.set()

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    threading.Thread(target=_watch, daemon=True).start()
    log.info("daemon ready pid=%d", os.getpid())
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        Path(sock_path).unlink(missing_ok=True)
        if paths.live_pid(session_id) == os.getpid():
            pid_file.unlink(missing_ok=True)
        log.info("daemon stopped")
        paths.remove_session_files(session_id, keep_log=_problems.count > 0)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="maskflow-agent daemon")
    parser.add_argument("--session", required=True)
    parser.add_argument("--idle-seconds", type=float, default=DEFAULT_IDLE_SECONDS)
    parser.add_argument("--patterns-only", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    return serve(args.session, args.idle_seconds, args.patterns_only)
