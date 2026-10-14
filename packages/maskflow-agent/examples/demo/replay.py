"""Replay a captured session in the terminal, for recording the demo video.

    python replay.py session-with-guard.json kyc.db --title "Claude Code + maskflow-agent"

Prints exactly the lines render_svg.py draws (same capture, same rules:
real values red, placeholders green), with typing pauses. It replays a real
transcript; it does not call Claude.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time

from render_svg import CHARS, _db_values, _leaked, _panel_lines, _row, _spans

ANSI = {
    "#ff7b72": "\033[1;31m",  # real value
    "#3fb950": "\033[1;32m",  # placeholder / success
    "#79c0ff": "\033[34m",  # command
    "#8b949e": "\033[2m",  # dim
}
RESET = "\033[0m"


def _paint(text: str, base: str, raw: dict[str, str]) -> str:
    out = []
    for run, colour in _spans(text, raw):
        out.append(f"{ANSI.get(colour or base, '')}{run}{RESET}")
    return "".join(out)


def _type(text: str, delay: float) -> None:
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("session")
    parser.add_argument("db")
    parser.add_argument("--title", required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()
    with open(args.session, encoding="utf-8") as f:
        data = json.load(f)
    raw = _db_values(args.db)
    lines = _panel_lines(data, raw, _row(args.db, 4))

    print(f"\033[1m{args.title}\033[0m\n")
    pause = 0.5 / args.speed
    prompt_lines = len(textwrap.wrap(data["prompt"], CHARS - 2))
    for i, (text, base) in enumerate(lines):
        if i < prompt_lines:  # the user's prompt is typed, everything else appears
            _type(text, 0.012 / args.speed)
        else:
            print(_paint(text, base, raw))
        time.sleep(pause if text else pause / 2)
    leaked = _leaked(data, raw)
    time.sleep(pause)
    if leaked:
        print(f"\033[1;31mSent to the model: {', '.join(leaked)}{RESET}")
    else:
        print(f"\033[1;32mSent to the model: no personal data. Row updated.{RESET}")
    time.sleep(4 / args.speed)


if __name__ == "__main__":
    main()
