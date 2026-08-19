# maskflow-pack-intl

MaskFlow's original 12 intl/US-shaped PII recognizers, packaged separately from
[`maskflow-core`](../../packages/maskflow-core) so the engine itself can ship with zero
recognizers built in. Detects via a three-layer pipeline: regex + structural validation (Luhn for
cards, mod-97 for IBANs) -> keyword-context confidence boosting -> spaCy NER for names and dates.

## Install

Requires [uv](https://docs.astral.sh/uv/). Part of the same uv workspace as `maskflow-core` — run
from the **repo root**:

```bash
uv sync --all-extras
uv run python -m spacy download en_core_web_sm
```

## Usage

Importing this package is the whole API surface — it registers all 12 types against
`maskflow-core` as a side effect of import, then you use core's `detect`/`mask`/`unmask` directly:

```python
import maskflow_pack_intl  # noqa: F401 -- registers EMAIL, PHONE, SSN, ...
from maskflow_core import detect, mask, unmask

detect("Email me at alice@example.com or call 415-555-0132.")
# [Span(entity_type=PIIType.EMAIL, text='alice@example.com', ...), Span(entity_type=PIIType.PHONE, ...)]

result = mask("Email me at alice@example.com or call 415-555-0132.")
result.masked_text  # "Email me at <EMAIL_1> or call <PHONE_1>."
unmask(result.masked_text, result.mapping)  # original text, restored
```

`maskflow-sdk` already depends on this package and imports it for you — most users won't import
it directly unless they're using `maskflow-core` standalone.

## PII types

Email, phone, SSN, credit card, IP address (v4/v6), AWS access key, API key / generic secret,
JWT, IBAN, street address, person name, date of birth.

## Surrogate generators (`Strategy.SURROGATE`)

`maskflow-core`'s `mask_with_policy(text, MaskPolicy(default_strategy=Strategy.SURROGATE))` needs a
fake-value generator per type (see `maskflow-core`'s README) — this pack registers one for every
type where a genuinely plausible, guaranteed-non-colliding fake makes sense:

| Type | Reserved/invalid range or corpus |
|---|---|
| `EMAIL` | RFC 2606 reserved `example.com`/`.org`/`.net` domains |
| `PHONE` | NANP fictional range: exchange `555`, subscriber `0100`-`0199` |
| `SSN` | SSA-reserved-invalid area numbers `900`-`999` |
| `CREDIT_CARD` | publicly documented payment-industry test numbers (Stripe/Visa/Mastercard/Amex) |
| `IBAN` | mod-97-valid, with a synthetic `9`-prefixed bank code |
| `PERSON_NAME` | embedded synthetic first/last name corpus (`surrogates.py`, not real people) |
| `ADDRESS` | embedded synthetic street name corpus (`surrogates.py`) |

`AWS_KEY`, `API_KEY`, `JWT`, and `IP_ADDRESS` have no bespoke generator — there's no meaningful
"plausible fake" for an opaque secret, and a fabricated IP is no safer than a real one might be
misleading. `DATE_OF_BIRTH` is skipped too: it's detected via spaCy NER rather than a fixed regex,
so input date formats vary too widely to fake safely in the same shape without a date-parsing
dependency. All four fall back to `Strategy.REPLACE` automatically.

## Tests

```bash
uv run pytest packs/maskflow-pack-intl/tests
```

`tests/fixtures/pii_samples.py` has 100+ labeled examples; `test_detection.py` enforces a 95%
accuracy floor against them and checks that PII-free text produces zero findings.

## Known limitations

- spaCy's NER occasionally flags a capitalized sentence-starter as a `PERSON_NAME` false positive
  (e.g. "Email me at..." -> "Email" tagged as a name). Not a training data issue -- future phases
  add a `.maskflowrc.yml` exclude-config for exactly this kind of false positive.
- Phone/address regexes are US-shaped; international formats are a future improvement (see
  `maskflow-pack-india` for Indian-specific identifiers).
