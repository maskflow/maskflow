"""Column-header lookup for tabular text (CSV/TSV, psql, mysql box, sqlite
`-header`, markdown tables).

context.py's keyword proximity only sees WINDOW chars either side of a
match, so in a table the one word that says what a value is -- its column
header -- is usually out of reach after the first row or two. This module
finds table blocks and answers "which header sits above this cell?" so
context.py can treat the header as one more context source.

Single linear pass over lines, no regex: delimiter counts are computed once
per line, block growth stops at the first mismatch, and every limit below
fails toward "no table context" (i.e. today's behaviour), never toward a
guess. Nothing here stores or reports cell *values* -- only offsets and the
header row's text, and callers must not put either into an explanation.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache
from itertools import accumulate

# Order is the tie-break when two delimiters give equally long blocks.
_DELIMITERS = ("\t", "|", ",", ";")
# Delimiters that follow CSV double-quote rules; "|" output (psql, mysql,
# markdown) never quotes.
_QUOTED = frozenset({"\t", ",", ";"})

MIN_BLOCK_LINES = 3  # header + at least two data rows
MAX_LINES = 200_000
MAX_LINE_LENGTH = 64 * 1024
MAX_COLUMNS = 256
MAX_HEADER_CELL = 40
MAX_HEADER_WORDS = 4

_SEPARATOR_CHARS = frozenset("-+=|: ")


def _is_separator(line: str) -> bool:
    """`----+----` (psql), `+----+` (mysql), `|---|:--|` (markdown)."""
    stripped = line.strip()
    return (
        bool(stripped)
        and ("-" in stripped or "=" in stripped)
        and all(ch in _SEPARATOR_CHARS for ch in stripped)
    )


def _split_cells(line: str, delim: str) -> list[tuple[int, int]] | None:
    """Cell (start, end) offsets within `line`, or None when the line can't
    be split safely (unbalanced quote, too many columns). Outer pipes of a
    `| a | b |` row are dropped so column indexes line up with the header."""
    cells: list[tuple[int, int]] = []
    quoted = delim in _QUOTED and '"' in line
    if not quoted:
        if line.count(delim) > MAX_COLUMNS:
            return None
        cell_start = 0
        cut = line.find(delim)
        while cut != -1:
            cells.append((cell_start, cut))
            cell_start = cut + 1
            cut = line.find(delim, cell_start)
        cells.append((cell_start, len(line)))
        return _trim_outer_pipes(line, cells) if delim == "|" else cells
    in_quotes = False
    cell_start = 0
    for i, ch in enumerate(line):
        if quoted and ch == '"':
            in_quotes = not in_quotes
        elif ch == delim and not in_quotes:
            cells.append((cell_start, i))
            cell_start = i + 1
            if len(cells) > MAX_COLUMNS:
                return None
    if in_quotes:
        return None
    cells.append((cell_start, len(line)))
    return cells


def _trim_outer_pipes(line: str, cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if len(cells) >= 2 and not line[cells[0][0] : cells[0][1]].strip():
        cells = cells[1:]
    if len(cells) >= 2 and not line[cells[-1][0] : cells[-1][1]].strip():
        cells = cells[:-1]
    return cells


def _cell_text(line: str, cell: tuple[int, int]) -> str:
    return line[cell[0] : cell[1]].strip().strip('"').strip()


def _looks_like_header(cells: list[str]) -> bool:
    """Every non-empty cell is a short label (a letter, at most
    MAX_HEADER_WORDS words, no ? or !) and no cell is a bare
    number; at least half the cells are non-empty (a pandas index column
    leaves the first header cell blank). The word/punctuation limits keep a
    run of comma-bearing prose lines from being read as a table whose
    "header" is a sentence."""
    filled = [c for c in cells if c]
    if len(filled) * 2 < len(cells):
        return False
    for cell in filled:
        if len(cell) > MAX_HEADER_CELL or not any(ch.isalpha() for ch in cell):
            return False
        if len(cell.split()) > MAX_HEADER_WORDS or any(ch in "?!" for ch in cell):
            return False
        if cell.replace(".", "", 1).replace("-", "", 1).isdigit():
            return False
    return True


@dataclass(frozen=True)
class _Block:
    first: int  # line index of the header row
    stop: int  # one past the last line of the block
    delim: str
    headers: tuple[str, ...]


@dataclass(frozen=True)
class TableIndex:
    """Table blocks of one document. Data rows are split into cells lazily,
    only for the line a lookup lands on -- most rows never hold a match."""

    _lines: tuple[str, ...]
    _offsets: tuple[int, ...]  # absolute offset of each line
    _separator: tuple[bool, ...]
    _block_firsts: tuple[int, ...]
    _blocks: tuple[_Block, ...]

    def header_for(self, start: int, end: int) -> str | None:
        """Header text of the column whose cell fully contains [start, end),
        or None if the span isn't inside a single data cell."""
        if not self._blocks:
            return None
        k = bisect_right(self._offsets, start) - 1
        b = bisect_right(self._block_firsts, k) - 1
        if k < 0 or b < 0:
            return None
        block = self._blocks[b]
        if not (block.first < k < block.stop) or self._separator[k]:
            return None
        line = self._lines[k]
        base = self._offsets[k]
        if end > base + len(line):
            return None
        cells = _split_cells(line, block.delim)
        if cells is None:
            return None
        for col, (cell_start, cell_end) in enumerate(cells):
            if base + cell_start <= start and end <= base + cell_end:
                if col < len(block.headers) and block.headers[col]:
                    return block.headers[col]
                return None
        return None

    def __bool__(self) -> bool:
        return bool(self._blocks)


_EMPTY = TableIndex((), (), (), (), ())


def _count(line: str, delim: str) -> int:
    """Delimiter count for block matching; -1 means "can't be part of a
    block" (too long, unbalanced quotes, too many columns)."""
    if len(line) > MAX_LINE_LENGTH:
        return -1
    if delim not in line:
        return 0
    if delim != "|" and '"' not in line:
        n = line.count(delim)
        return n if n <= MAX_COLUMNS else -1
    cells = _split_cells(line, delim)
    return -1 if cells is None else len(cells) - 1


@lru_cache(maxsize=4)
def find_tables(text: str) -> TableIndex:
    """Index every table block in `text`. Memoised so the scan runs once per
    document however many matches ask for a header."""
    if "\n" not in text:
        return _EMPTY
    lines = text.split("\n")
    if len(lines) > MAX_LINES:
        return _EMPTY

    separator = [_is_separator(line) for line in lines]
    counts = {d: [_count(line, d) for line in lines] for d in _DELIMITERS}

    blocks: list[_Block] = []
    i = 0
    n = len(lines)
    while i < n:
        if separator[i] or not lines[i].strip():
            i += 1
            continue
        best_delim, best_end, best_rows = "", i, 0
        for delim in _DELIMITERS:
            want = counts[delim][i]
            if want < 1:
                continue
            j, content_rows = i, 0
            while j < n and (separator[j] or counts[delim][j] == want):
                content_rows += not separator[j]
                j += 1
            if content_rows > best_rows:
                best_delim, best_end, best_rows = delim, j, content_rows
        if best_rows < MIN_BLOCK_LINES:
            i += 1
            continue
        header_line = lines[i]
        headers = [_cell_text(header_line, c) for c in _split_cells(header_line, best_delim) or []]
        if _looks_like_header(headers):
            blocks.append(_Block(i, best_end, best_delim, tuple(headers)))
        i = best_end

    if not blocks:
        return _EMPTY
    offsets = [0, *accumulate(len(line) + 1 for line in lines[:-1])]
    return TableIndex(
        tuple(lines),
        tuple(offsets),
        tuple(separator),
        tuple(b.first for b in blocks),
        tuple(blocks),
    )
