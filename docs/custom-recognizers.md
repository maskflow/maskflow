# Writing a custom recognizer

A recognizer finds candidate spans of one PII type in text. MaskFlow ships
two kinds of built-in recognizer packs (`maskflow-pack-intl`,
`maskflow-pack-india`); this doc is for adding your own, either inside your
own application or as a separate installable pack.

## The interface

Every recognizer implements `maskflow_core.recognizer.Recognizer`:

```python
from collections.abc import Iterable

from maskflow_core.entities import Span
from maskflow_core.recognizer import AnalysisContext, Recognizer


class MyRecognizer(Recognizer):
    entity_type = "EMPLOYEE_ID"
    default_threshold = 0.0

    def analyze(self, text: str, ctx: AnalysisContext) -> Iterable[Span]:
        ...  # yield Span objects
```

`analyze()` receives the full text and an `AnalysisContext` (the current
language, any disabled entity types, and -- for recognizers that need
NLP -- a lazily parsed, memoised `ctx.nlp_doc`; see "Sharing the NLP
pass" below). It's the extension point third parties implement directly.

Three base classes cover the match strategies core already supports and
save you from writing `analyze()` by hand:

- **`PatternRecognizer`** -- one `(regex, base_confidence, validator)` rule.
- **`GazetteerRecognizer`** -- a lookup/automaton scan (e.g.
  [pyahocorasick](https://pypi.org/project/pyahocorasick/) for a large word
  list) returning raw `(start, end, text, confidence)` hits.
- **`NlpRecognizer`** -- maps one spaCy entity label (`ent.label_`) onto a
  PII type.

## A complete example

A `PatternRecognizer` for a fictional internal employee ID shaped like
`EMP-123456`, with a Luhn-style check digit:

```python
import re

from maskflow_core.recognizer import PatternRecognizer, RecognizerRegistry

EMPLOYEE_ID_RE = re.compile(r"\bEMP-(\d{6})\b")


def validate_employee_id(value: str) -> float | None:
    digits = [int(d) for d in value]
    checksum = sum(digits[:-1]) % 10
    if checksum != digits[-1]:
        return None  # reject the match outright -- no Span is emitted
    return 0.95  # confidence once the check digit passes


def load_recognizers():
    return [
        PatternRecognizer(
            "EMPLOYEE_ID",
            EMPLOYEE_ID_RE,
            base_confidence=0.4,  # below DEFAULT_MIN_CONFIDENCE alone
            validator=validate_employee_id,
            context_keywords=("employee id", "emp id", "staff number"),
        ),
    ]
```

## Registering it

### Inside your own application

Call `.register()` directly -- this is the same thing
`register_pattern()`/`register_custom_recognizer()`/`register_ner_recognizer()`
do under the hood, just via the recognizer object instead of a bare function
call:

```python
for recognizer in load_recognizers():
    recognizer.register()

# now detect()/mask() are aware of EMPLOYEE_ID
```

### As an installable pack

Expose `load_recognizers` as a `"maskflow.recognizers"` entry point in your
package's `pyproject.toml`:

```toml
[project.entry-points."maskflow.recognizers"]
myapp = "myapp.recognizers:load_recognizers"
```

Anyone with your package installed can then discover and register it
without importing your module directly:

```python
from maskflow_core.recognizer import RecognizerRegistry

RecognizerRegistry().register_all()
```

Discovery is lazy: `RecognizerRegistry()` itself does nothing, and merely
having your package installed has no effect. Your `load_recognizers`
function -- and therefore any heavy dependency it needs (a large gazetteer,
an ML model) -- is only imported the first time `.recognizers` or
`.register_all()` is actually accessed.

`Recognizer.register()` is idempotent per instance: calling it twice on the
same object (e.g. once from your own eager import, once via
`RecognizerRegistry`) registers the pattern once, not twice.

## Sharing the NLP pass

If your recognizer needs spaCy, subclass `NlpRecognizer` rather than
building `Recognizer` from scratch and parsing text yourself:

```python
from maskflow_core.recognizer import NlpRecognizer

NlpRecognizer("ORG", "EMPLOYER_NAME", base_confidence=0.5)
```

`NlpRecognizer.analyze()` reads `ctx.nlp_doc`, which `AnalysisContext`
computes lazily and memoises per instance -- however many `NlpRecognizer`s
share one `AnalysisContext` in a single run, the underlying parse happens
exactly once. Parsing text yourself inside `analyze()` (instead of going
through `ctx.nlp_doc`) means your recognizer runs its own, separate parse.
