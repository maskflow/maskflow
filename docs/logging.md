# Protecting your own logger from PII

MaskFlow's own code never emits raw PII into logs, exceptions, or reprs
(`Span.text`/`MappingEntry.original` are excluded from `repr()`, and every
package's test suite runs under a `pytest -m leak` gate that fails the build
if that ever regresses). But that only covers MaskFlow's *own* log calls.
Nothing stops your application -- or a third-party recognizer plugin -- from
logging a raw value before it's ever run through `mask()`:

```python
logger.info(f"validation failed for {raw_input}")   # leaks raw_input
logger.debug(span.text)                             # a careless recognizer
```

`maskflow_core.logging_filter` closes that gap for logs going through the
standard library `logging` module.

## Usage

```python
from maskflow_core import install_pii_filter

install_pii_filter()  # attaches to the root logger, once, at startup
```

Any log record that flows through the root logger (i.e. any logger that
doesn't set `propagate = False`) is now scrubbed: a detected value is
replaced with `<ENTITY_TYPE>` before the record reaches any handler.

```python
logger.info("processing %s", "AADHAAR-shaped-value")
# -> "processing <AADHAAR>"
```

Pass a specific logger to scope it narrower:

```python
install_pii_filter(logging.getLogger("myapp.ingest"))
```

`install_pii_filter()` is idempotent per logger -- calling it again returns
the already-installed filter instead of attaching a duplicate.

## What it does *not* cover

- **NER-only entity types** (bare names, addresses) are not detected. The
  filter runs `detect_patterns_only()` -- checksum/regex-validated patterns
  only, no spaCy -- because it runs on every log call in your process, a very
  different cost profile from a per-request `mask()` call. Only entity types
  with a registered pattern or custom recognizer (Aadhaar, PAN, GSTIN, email,
  credit card, ...) are caught.
- **`exc_info`/traceback text.** A `Formatter` renders the traceback after
  filters run, so a `logging.Filter` can't reliably rewrite it. Don't log
  raw PII into an exception message in the first place (see the exception
  guidance above) and this doesn't matter; it's called out here so the gap
  is explicit rather than assumed away.
- **Non-standard-library logging.** If your app uses `structlog`, `loguru`,
  or logs by writing directly to a file/stream, `logging.Filter` never runs.
