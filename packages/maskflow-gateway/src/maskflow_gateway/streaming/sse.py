"""Minimal incremental Server-Sent-Events codec.

Just enough of the SSE wire format (https://html.spec.whatwg.org/#server-sent-events)
for the OpenAI / Anthropic streaming APIs: ``data:`` (possibly multi-line,
joined with ``\\n``), an optional ``event:`` name, events separated by a
blank line. Comments (``:`` prefix) and ``id:`` / ``retry:`` are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SSEEvent:
    data: str
    event: str | None = None


class SSEDecoder:
    """``feed()`` returns the events completed by the text so far; a
    partial trailing event is retained until its terminating blank line."""

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, text: str) -> list[SSEEvent]:
        self._buf += text
        self._buf = self._buf.replace("\r\n", "\n").replace("\r", "\n")
        events: list[SSEEvent] = []
        while "\n\n" in self._buf:
            raw, self._buf = self._buf.split("\n\n", 1)
            parsed = _parse_block(raw)
            if parsed is not None:
                events.append(parsed)
        return events

    def flush(self) -> list[SSEEvent]:
        """Any trailing block not terminated by a blank line (some servers
        omit the final one before closing the connection)."""
        remainder = self._buf.strip("\n")
        self._buf = ""
        if not remainder:
            return []
        parsed = _parse_block(remainder)
        return [parsed] if parsed is not None else []


def _parse_block(raw: str) -> SSEEvent | None:
    event_name: str | None = None
    data_lines: list[str] = []
    for line in raw.split("\n"):
        if not line or line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            data_lines.append(value)
        elif field == "event":
            event_name = value
    if not data_lines and event_name is None:
        return None
    return SSEEvent(data="\n".join(data_lines), event=event_name)


def format_sse(data: str, event: str | None = None) -> str:
    """Serialize one event. ``data`` is emitted as a single ``data:`` line
    (the JSON payloads we send never contain a newline)."""
    prefix = f"event: {event}\n" if event is not None else ""
    return f"{prefix}data: {data}\n\n"
