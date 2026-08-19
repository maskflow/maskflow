# MaskFlow — Project Context for Claude Code

## What this is
Detects PII in text, replaces it with reversible typed placeholders before
text reaches an LLM provider, restores originals in the response.

## Strategy
Presidio owns generic PII (free, mature); mask-privacy ships session HMAC
tokens (EN/ES). We compete on neither. MaskFlow exists for INDIAN PII —
Aadhaar, PAN, GSTIN, UPI, IFSC, ABHA, Indian names/addresses — for buyers
facing the DPDP deadline 13 May 2027. Therefore: Indian coverage & precision
win any tradeoff; accuracy is MEASURED and published, never asserted; this
repo is MIT free forever — never add license gates, paid flags, or telemetry.

## Non-negotiable rules (release blockers)
1. NEVER log/print/embed raw PII anywhere — not DEBUG, exceptions, test
   failures, or __repr__. Span.text & MappingEntry.original repr-excluded;
   exceptions carry offsets + entity types only.
2. NEVER commit real PII; fixtures synthetic; checksum-valid IDs GENERATED
   and comment-marked synthetic.
3. No unbounded regex (backtracking = DoS).
4. NEVER break maskflow-sdk 0.1.0 API: mask(), unmask(), mask_and_call()
   identical; deprecate with warnings one minor version before removal.
5. Round-trip sacred: unmask(mask(t).masked_text, mapping) == t exactly —
   unicode, emoji, RTL, zero-width, placeholder-lookalikes included.

## Target architecture (uv workspace)
packages/maskflow-core (engine only, zero recognizers, <5MB, <200ms import,
spaCy optional behind [nlp]) · packages/maskflow-sdk (thin, compatible) ·
packages/maskflow-cli · packages/maskflow-gateway (later) ·
packages/maskflow-js (later, unified fixtures) · packs/maskflow-pack-intl
(existing 12) · packs/maskflow-pack-india (the moat) · bench/indiapii.

## Design decisions (implement, don't relitigate)
1. Everything is a Span (start, end, entity_type, score, recognizer,
   validated, text repr-excluded, explanation:list[str]); central
   resolution: drop below-threshold → sort validated desc, score desc,
   length desc, start asc → greedy non-overlap. A checksum-VALIDATED span
   always beats an overlapping unvalidated one.
2. Tier-0 excision: deterministic matches tokenized BEFORE the NER pass.
3. Placeholders typed+stable+collision-proof: <AADHAAR_1>; same value →
   same token per session; input pre-scanned for <[A-Z_]+_\d+>, collision →
   nonce form <AADHAAR_1_a4f9>.
4. Mapping object + pluggable MappingStore (in-memory TTL default, Redis,
   AES-GCM file). Plaintext never unencrypted on disk.
5. Recognizers are entry-point plugins ("maskflow.recognizers") sharing a
   memoised AnalysisContext — spaCy runs EXACTLY ONCE per document.

## Confidence
score = base × validator_mult(pass ×1.6 clamp 1.0 / fail ×0.0)
      + context_boost(+0.15..0.35) − negative_context(−0.3:
      example/test/sample/dummy). Every decision appends span.explanation.

## Commands
uv sync --all-extras · uv run pytest · pytest -m benchmark · pytest -m leak
· ruff check . · mypy packages/maskflow-core --strict

## Done means
ruff+mypy(core)+pytest green · core coverage ≥85% · recognizers ship with
positive/negative/hard-negative tests, documented threshold, context words,
docs entry · no new core dep without asking · CHANGELOG updated.

## Working with me
Plan before coding on anything non-trivial and WAIT. One work order per
session. Ask when identifier formats are ambiguous. Tell me when I'm wrong.
