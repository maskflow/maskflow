"""The Flow model and its stable identity.

A flow is one call site at which text can leave for a provider. Its ID has
to survive edits that have nothing to do with it, because `--ci` diffs this
report against a committed baseline: if the ID moved every time a line was
inserted above the call, every refactor would read as a wall of new
unmasked flows and the gate would be ignored within a week.

So the ID is a hash of (file, enclosing function, resolved call path,
occurrence index within that function) and deliberately **not** the line
number. The line is still reported -- it is what a human needs -- but it is
not part of the identity.

Nothing on these objects holds source text. A flow carries identifiers
(file paths, function names, column names, argument names) and nothing a
value could hide in: the report data model inherits that property, which is
what makes "does the report leak PII?" answerable by inspection.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

#: Masking status, in the precedence order resolve() applies.
MASKED_VIA_MASK_CALL = "masked_via_mask_call"
MASKED_VIA_GATEWAY = "masked_via_gateway_base_url"
MASKED_VIA_INTEGRATION = "masked_via_integration"
UNMASKED = "unmasked"
UNKNOWN = "unknown"

MASKING_STATUSES: tuple[str, ...] = (
    MASKED_VIA_MASK_CALL,
    MASKED_VIA_GATEWAY,
    MASKED_VIA_INTEGRATION,
    UNMASKED,
    UNKNOWN,
)

#: Statuses that mean "this path is guarded".
MASKED_STATUSES = frozenset({MASKED_VIA_MASK_CALL, MASKED_VIA_GATEWAY, MASKED_VIA_INTEGRATION})

#: How much the report is willing to claim about a flow's source.
CONFIDENCE_CONFIRMED = "confirmed"  # a canary escaped here (M2)
CONFIDENCE_HIGH = "high"  # traced to a named column / field
CONFIDENCE_MEDIUM = "medium"  # traced to a call we could not follow further
CONFIDENCE_LOW = "low"  # the argument is dynamic
CONFIDENCE_UNKNOWN = "unknown"  # we could not trace it at all

CONFIDENCE_LEVELS: tuple[str, ...] = (
    CONFIDENCE_CONFIRMED,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    CONFIDENCE_UNKNOWN,
)

#: Where a sink's payload came from.
SOURCE_DB_COLUMN = "db_column"
SOURCE_REQUEST_FIELD = "request_field"
SOURCE_FILE_READ = "file_read"
SOURCE_TOOL_RESULT = "tool_result"
SOURCE_PARAMETER = "parameter"
SOURCE_LITERAL = "literal"
SOURCE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class Source:
    """One traced origin of a sink's payload.

    `detail` is an identifier -- a column name, a request field, a callee
    name -- never content. A string literal is recorded as kind `literal`
    with an empty detail precisely so the literal's text cannot ride along
    into the report.
    """

    kind: str
    detail: str = ""
    predicted_entity_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class Flow:
    """One egress call site."""

    flow_id: str
    file: str  # repo-relative, POSIX separators, for stable IDs across OSes
    line: int
    function: str  # enclosing qualified name; "" at module level
    sink_id: str
    category: str
    provider: str
    call_path: str  # the resolved dotted path, e.g. openai.OpenAI...create
    host: str = ""  # resolved destination host, "" when not statically known
    masking_status: str = UNKNOWN
    masking_reason: str = ""
    payload_args: tuple[str, ...] = ()  # which arguments carried the text
    sources: tuple[Source, ...] = ()
    confidence: str = CONFIDENCE_UNKNOWN
    explanation: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_masked(self) -> bool:
        return self.masking_status in MASKED_STATUSES


def flow_id(file: str, function: str, call_path: str, occurrence: int) -> str:
    """A stable identity for a call site.

    Not line-based on purpose -- see the module docstring. Twelve hex
    characters is 48 bits, which is far more than enough to keep a single
    repository's flows distinct while staying readable in a PR comment.
    """
    payload = "\x1f".join((file, function, call_path, str(occurrence)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
