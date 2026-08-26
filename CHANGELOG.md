# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
for each published package (`maskflow-core`, `maskflow-pack-intl`, `maskflow-sdk`,
`@maskflow/detection`).

## [Unreleased]

### Added

- `scripts/refresh_india_reference_data.py` and `docs/data-refresh.md`
  (issue #28): closes the one item on that issue with zero prior progress --
  every `maskflow-pack-india` reference-data file documented its own refresh
  procedure as prose, but nothing was scripted or consolidated. The script
  has `ifsc`/`cities` subcommands, each a pure diff function (unit-tested in
  `packs/maskflow-pack-india/tests/test_reference_data_refresh.py`, no
  network) plus a fetch/parse wrapper; it never writes the bundled data
  files itself, matching the "curated, not auto-merged" philosophy those
  files already documented. `upi` prints the still-manual PSP-handle
  procedure -- no machine-readable NPCI feed exists. `docs/data-refresh.md`
  is the single doc covering sourcing/licensing/refresh cadence for all five
  data files (IFSC codes, UPI handles, RTO codes, place gazetteer, name
  gazetteer); each file's docstring now points to it instead of duplicating
  the procedure prose.
- `maskflow-core` (still unreleased `0.6.0`, no separate bump -- see the
  `0.5.0` -> `0.6.0` entry below): also adds `maskflow_core.logging_filter`
  (closes the last open item on issue #23) -- `PIIRedactionFilter`, a
  `logging.Filter` that scrubs a LogRecord's formatted message through the
  new `detect_patterns_only()` (regex/checksum-validated patterns, no NER --
  cheap enough for a hot logging path) before emission, and
  `install_pii_filter(logger=None, ...)` to attach one (default: root
  logger; idempotent per logger). Opt-in only -- importing `maskflow_core`
  never touches global logging state on its own. This protects a *downstream
  app's own* logger calls (e.g. `logger.info(f"...{raw_input}")` before
  `mask()` ever runs, or a careless third-party recognizer plugin doing
  `logger.debug(span.text)`), which repr-exclusion and the `pytest -m leak`
  gate never covered -- those two only protect MaskFlow's own test session.
  `detect_patterns_only()` is also now public on `detect.py`/`maskflow_core`
  (the existing tier-0-excision computation inside `detect()`, factored out
  and reused rather than duplicated). NER-only entity types (bare names,
  addresses) and `exc_info`/traceback text are explicitly out of scope --
  see `docs/logging.md`.
- `maskflow-core` `0.5.0` -> `0.6.0`: adds `maskflow_core.recognizer` (issue
  #21's pluggable recognizer architecture) -- a `Recognizer` ABC
  (`entity_type`/`supported_languages`/`default_threshold`/
  `analyze(text, ctx) -> Iterable[Span]`), `AnalysisContext` (per-`detect()`-
  call state including a lazily computed, memoised NLP doc -- however many
  NER-dependent recognizers share one context, the underlying parse happens
  exactly once), three base helpers (`PatternRecognizer`,
  `GazetteerRecognizer`, `NlpRecognizer`) covering the three match
  strategies core already supported, and `RecognizerRegistry` (lazy
  discovery via the `"maskflow.recognizers"` entry-point group -- enumerating
  entry points never imports a pack; only actually accessing
  `.recognizers`/`.register_all()` does). `Recognizer.register()` populates
  the *existing* `PATTERNS`/`CUSTOM_RECOGNIZERS`/`NER_RECOGNIZERS` dicts
  `detect()`/`detect_ner()` already read, and is idempotent per instance --
  detection.py/ner.py's resolution pipeline is otherwise unchanged. Purely
  additive: no existing function's signature changed, `register_pattern()`/
  `register_custom_recognizer()`/`register_ner_recognizer()` still work
  exactly as before. `docs/custom-recognizers.md` added.
- `maskflow-pack-intl` `0.2.0` -> `0.3.0` and `maskflow-pack-india` `0.3.0`
  -> `0.4.0`: internal registration migrated from bare
  `register_pattern()`/`register_custom_recognizer()`/
  `register_ner_recognizer()` calls to declarative `PatternRecognizer`/
  `GazetteerRecognizer`/`NlpRecognizer` objects, and both packs now expose a
  `load_recognizers()` entry point (group `"maskflow.recognizers"`) for
  `RecognizerRegistry`-based discovery. **Behavior-identical**: each pack's
  `__init__.py` still registers everything at import time exactly as
  before (same patterns, same confidences, same context-keyword unions, same
  order) -- verified by the full existing test suite (both packs' positive/
  negative/hard-negative fixtures, `-m leak`, `-m benchmark`) passing
  unchanged. Both packs now require `maskflow-core>=0.6.0,<0.7`. Explicitly
  out of scope for this round: `maskflow-sdk`/`maskflow-cli` still activate
  both packs via the original side-effect `import maskflow_pack_intl` /
  `import maskflow_pack_india` (unchanged) rather than
  `RecognizerRegistry`-based discovery -- migrating their activation
  mechanism is a separate, later decision, not required for this issue's
  scope (the pluggable interface itself, and packs being *capable* of
  entry-point discovery).
- `maskflow-sdk` `0.4.0` -> `0.5.0` and `maskflow-cli` `0.3.0` -> `0.4.0`:
  no code changes in either package -- dependency bounds widened for the
  `maskflow-core`/`maskflow-pack-intl`/`maskflow-pack-india` bumps above
  (`maskflow-core` floor raised to `0.6.0` since the packs now hard-require
  `maskflow_core.recognizer`), so this bump exists purely to publish those
  widened bounds as a new release.

### Changed

- `maskflow-pack-india` `0.4.0` -> `0.5.0` (issue #28 closeout): grows two of
  the pack's bundled reference datasets using the new refresh script above.
  `IFSC_BANK_CODES` 56 -> 94 entries: cross-checked against
  `razorpay/ifsc`'s public-domain data and added every code in scope
  (foreign/private/small-finance/payments/local-area banks, plus 3
  legitimate merged/retired PSU codes) that this pack's manual curation had
  missed; also relabels `ESFB` (was miscommented "ESAF Small Finance Bank",
  actually Equitas per the cross-check -- the `ESFB` *value* is unchanged,
  only its comment). `INDIAN_CITIES` 368 -> 554 entries: unions the existing
  Wikipedia-sourced list with Census 2011 town-population data (population
  >= 100,000), clearing the "top-500" target from issue #28. **Behavior
  change**: IFSC/VEHICLE_REG/DRIVING_LICENCE and INDIAN_ADDRESS's L1
  gazetteer will now validate/match values they previously rejected/missed
  -- e.g. an IFSC starting `IPPB`/`ESFB`/`USFB`/... now passes structural
  validation, and 186 more real city names are recognized as address
  context. No API change. `maskflow-sdk`/`maskflow-cli`'s
  `maskflow-pack-india` bound widened from `<0.5` to `<0.6`. The
  `PERSON_NAME` (Indian) gazetteer target (150k+ names) and India-specific
  negative context terms remain open -- see docs/data-refresh.md and the two
  follow-up issues filed from #28.
- `maskflow-sdk` `0.5.0` -> `0.6.0` and `maskflow-cli` `0.4.0` -> `0.5.0`:
  no code changes in either package -- dependency bounds widened for the
  `maskflow-pack-india` bump above, so this bump exists purely to publish
  those widened bounds as a new release.
- `maskflow-sdk` `0.2.0` -> `0.3.0`: now depends on `maskflow-pack-india`
  (`>=0.1.0,<0.2`) in addition to `maskflow-pack-intl`, registered the same
  side-effect-import way in `maskflow/__init__.py`. This is a **behavior
  change, not just a new capability**: text that previously passed through
  `mask()` untouched because it merely *looked like* an Aadhaar/PAN/GSTIN/
  IFSC/UPI VPA will now be masked. `mask()`/`unmask()`/`mask_and_call()`'s
  signatures are unchanged (CLAUDE.md rule 4), so this is additive at the
  API level and a minor version bump, not a major one.
- `maskflow-cli` `0.1.0` -> `0.2.0`: now also depends on `maskflow-pack-india`
  (`>=0.1.0,<0.2`), registered in `app.py` the same way as `maskflow-pack-intl`.
  `maskflow doctor` and `maskflow explain` are entirely registry-driven, so
  no command-specific code changed -- the 6 India entity types just start
  showing up in `doctor`'s entity table and `explain`'s pattern hits.
  `maskflow config validate`'s soft entity-name cross-check now recognizes
  `entities.AADHAAR`/`PAN`/`GSTIN`/`IFSC`/`UPI_VPA` as known types instead
  of warning on them. Also removes `doctor.py`'s now-dead "maskflow-pack-
  india not installed" hint, since it's a hard dependency now, not an
  optional one to nudge users toward installing.
- `maskflow-pack-india` `0.1.0` -> `0.2.0`: adds the 9 new entity types
  listed below (INDIAN_MOBILE through BANK_ACCOUNT_IN) -- additive only, no
  API change. `maskflow-sdk` and `maskflow-cli`'s `maskflow-pack-india`
  dependency bound widened from `<0.2` to `<0.3` so a future release of
  either can pick up this version; their own published versions on PyPI
  still declare the old `<0.2` bound until they're next released.
- `maskflow-core` `0.4.0` -> `0.5.0`: adds `registry.register_custom_recognizer()`
  alongside the existing `register_pattern`/`register_ner_recognizer` --
  lets a pack register a non-regex match source (e.g. a gazetteer
  automaton) that still goes through the same validator/context-boost/
  tier-0-excision/resolve pipeline as every other recognizer. Also adds
  `NerMapping.agreement_boost` (default `0.0`, so every existing NER
  registration is unaffected) and `detect_ner()`'s new `agreement_spans`
  keyword: when a spaCy entity overlaps a pattern/custom-recognizer
  candidate of the same type (even one that scored below its own
  threshold), `agreement_boost` is added to its confidence before the
  context boost -- `detect()` now passes every pattern-pass candidate
  through as agreement evidence. Both additions are purely additive; no
  existing function's signature changed, no existing recognizer's output
  changed (agreement_boost only has an effect when a pack explicitly opts
  in). `maskflow-sdk`, `maskflow-cli`, and `maskflow-pack-intl`'s
  `maskflow-core` dependency bound widened from `<0.5` to `<0.6`.
- `maskflow-pack-india` `0.2.0` -> `0.3.0`: adds PERSON_NAME (Indian) and
  INDIAN_ADDRESS across all three built layers (L1 gazetteer, L2
  structural, L3 NLP agreement -- L4 fine-tuning not started, see Added
  below and the cumulative precision/recall report). Now depends on
  `pyahocorasick` and `maskflow-core[nlp]` (spaCy -- previously spaCy-free)
  `>=0.5.0,<0.6`. `PIN_CODE`'s state/UT name list moved from `__init__.py`
  to `data/indian_places.py` (now shared with INDIAN_ADDRESS's gazetteer)
  -- same 36 values, no behavior change. `maskflow-sdk`/`maskflow-cli`'s
  `maskflow-pack-india` bound widened from `<0.3` to `<0.4`.
- **Behavior change for `maskflow-pack-intl`'s PERSON_NAME when
  `maskflow-pack-india` is also installed** (i.e. the actual
  `maskflow-sdk`/`maskflow-cli` bundled configuration): pack-india's L3
  registers the same spaCy `"PERSON"` label pack-intl does
  (`register_ner_recognizer`'s `NER_RECOGNIZERS` dict holds one mapping
  per label; pack-india imports after pack-intl in the bundled
  configuration, so its registration wins). The standalone base confidence
  (`0.75`) is unchanged from pack-intl's own -- deliberately NOT
  down-weighted, to avoid regressing non-Indian-name recall -- but a name
  that also matches this pack's L1 gazetteer or L2 structural patterns now
  scores higher (`0.75` -> `0.95`) and records that agreement in
  `span.explanation`.
- `maskflow-sdk` `0.3.0` -> `0.4.0` and `maskflow-cli` `0.2.0` -> `0.3.0`:
  no code changes in either package -- both already declared
  `maskflow-pack-india>=0.1.0,<0.4` and `maskflow-core>=0.5.0,<0.6` (widened
  earlier in this same round of changes, see above), so this bump exists
  purely to publish those already-widened bounds as a new release. Since
  `maskflow-pack-india<0.4` and `maskflow-core<0.6` already permitted
  0.3.0/0.5.0, this is what actually lets `pip install maskflow-sdk`/
  `maskflow-cli` pick up PERSON_NAME (Indian)/INDIAN_ADDRESS -- their
  previously-published versions (`0.3.0`/`0.2.0`) are unaffected and still
  resolve to the pre-this-session `maskflow-pack-india`/`maskflow-core`.
  Minor bump, not patch, for the same reason earlier pack-india dependency
  bumps in this file were treated as minor: `mask()`'s output changes for
  previously-untouched text (new entity types get masked that weren't
  before), even though neither package's own API changed.

### Added

- New package `maskflow-pack-india` (`packs/maskflow-pack-india`, `0.1.0`,
  published to PyPI): AADHAAR (12-digit UID and
  16-digit VID, Verhoeff checksum), AADHAAR_MASKED (display-masked form,
  e.g. `XXXX XXXX 9012`, unvalidated/context-gated), PAN (structural
  holder-category check; no public checksum exists for the final letter),
  GSTIN (state-code range + embedded-PAN structural check + base-36
  checksum -- also emits the embedded PAN as its own candidate span, which
  `spanset.py`'s containment resolution correctly drops in favor of the
  longer GSTIN), IFSC (bank code checked against a bundled, documented-
  refresh-procedure RBI code list), and UPI_VPA (PSP handle checked against
  a bundled NPCI handle list; a `handle@domain.tld` that isn't a known PSP
  handle is left alone so a general email recognizer claims it instead).
  Positive context keywords are English, Hindi (Devanagari), and Hinglish
  transliterations; core has no negative-context ("example"/"test"/"dummy"
  suppression) mechanism yet, so that part of CLAUDE.md's confidence
  formula isn't implemented for this pack either -- noted as follow-up work.
- `maskflow-pack-india`: 9 more India entity types -- INDIAN_MOBILE (`+91`/
  `0`-prefixed numbers get full confidence unconditionally; a bare 10-digit
  number needs a nearby context keyword), PIN_CODE (unvalidated, always
  context-required -- pin/pincode/a state or UT name/address), VOTER_ID
  (EPIC number, structural only, no public checksum), INDIAN_PASSPORT
  (the inline 8-char number, structural only, plus a full TD3
  machine-readable-zone block recognizer validated against all 4 ICAO 9303
  check digits -- document number, DOB, expiry, and composite), DRIVING_LICENCE
  and VEHICLE_REG (both validated against a bundled, documented-refresh-
  procedure state/UT RTO code list), ABHA_NUMBER (unvalidated, always
  context-required, no checksum), ABHA_ADDRESS (`handle@abdm`/`handle@sbx`,
  same design as UPI_VPA), and BANK_ACCOUNT_IN (9-18 digits, unvalidated,
  always context-required). Every context-required type ships a dedicated
  hard-negative test asserting zero detections on invoice/order-ID/
  timestamp text of the same digit shape.
- `maskflow-pack-india`: PERSON_NAME (Indian) and INDIAN_ADDRESS, built
  through **L1 gazetteer, L2 structural, and L3 NLP-agreement** (L4
  fine-tuning NOT started -- measured recall after L1-L3 is well above the
  work order's 0.85 gate, see the report below).

  **L1 (gazetteer):** new `gazetteer.py` matches a ~115k-entry Indian name
  gazetteer and a 368-entry state/UT + city gazetteer via `pyahocorasick`
  (lazily built + `lru_cache`d, so bare `import maskflow_pack_india` stays
  fast), routed through the new `register_custom_recognizer()` core hook.
  PERSON_NAME contiguous hits (e.g. a given name immediately followed by a
  surname) coalesce into one span; frequency-tiered confidence (common
  names/words need nearby context, rarer ones fire standalone); a small
  programmatic spelling-variant rule table (Krishna/Krishnaa, Lakshmi/
  Laxmi); English- and Hinglish-function-word and this pack's own
  entity-name-acronym collisions (`the`, `mera`, `abha`, `pan`, ...)
  excluded/downgraded -- see `data/indian_names.py`'s docstring.
  INDIAN_ADDRESS's gazetteer alone is deliberately low-confidence (a bare
  place mention isn't an address).
  Gazetteer sourcing fell short of the 150k-name target: the largest
  license-clean candidate found (`swami93/indian-names-1.5M` on
  HuggingFace, MIT-labeled) is self-declared with no documented upstream
  provenance despite the dataset name, and turned out to contain
  meaningful noise (English/Hindi function words, fragments); several
  larger candidates were excluded outright (a CC0-labeled electoral-roll
  dataset whose actual access terms are research-only/non-commercial; a
  ~28k-name GitHub gist set with no license at all). Bundled anyway with
  the provenance gap and every exclusion documented in `data/indian_names.py`,
  per an explicit decision this session rather than silently overstating
  coverage.

  **L2 (structural):** new patterns in `patterns.py` -- PERSON_NAME
  honorifics (Shri/Sri/Smt/Kum/Mr/Mrs/Ms/Dr/Prof/Late + capitalised run),
  relational markers (S/o, D/o, W/o, C/o, "son of"/"daughter of"/"wife of",
  emitting both the subject's and the relative's name as separate
  candidates), dotted initials ("K.S. Rao", high confidence) and undotted
  trailing initials ("Srinivasan K", context-gated -- too ambiguous
  standalone), form-field labels ("Name:", "Applicant", "Customer Name");
  INDIAN_ADDRESS unit markers (H.No./Flat/Plot/Sector/Block/Phase/Door No.
  + number), landmark-relative phrases (near/opposite/behind/beside +
  proper noun), locality-word suffixes (Nagar/Colony/Vihar/Puram/Layout/
  Extension/Marg), and **mutual PIN_CODE reinforcement** (a place hit
  within 20 chars of a PIN-shaped number is boosted 0.3 -> 0.65 in
  `gazetteer.py`; PIN_CODE's own context keywords gained the locality-word
  set for the reverse direction). Two documented, deliberately-not-"fixed"
  precision limitations: "Dr. Reddy's" (the pharma brand) is structurally
  indistinguishable from "Dr. Reddy" the person; a capitalised common noun
  after "near"/"behind"/etc. is indistinguishable from a real landmark --
  both need real-world entity knowledge (L3/L4), not more regex.

  **L3 (NLP agreement):** `NerMapping.agreement_boost` (new in
  maskflow-core, see Changed above) wired up for PERSON_NAME via spaCy's
  `PERSON` label (standalone confidence deliberately left at pack-intl's
  existing `0.75` -- see the pack-intl behavior-change note above -- with
  `agreement_boost=0.2`). A GPE/LOC mapping for INDIAN_ADDRESS was
  implemented, measured, and **deliberately dropped**: unlike PERSON_NAME,
  spaCy tagging a place and the gazetteer agreeing it's a place doesn't
  resolve INDIAN_ADDRESS's actual ambiguity (is this bare mention part of
  an address, vs. just a place named in passing) -- it measurably promoted
  plain sentences like "Mumbai is a city in India." past threshold with no
  address context at all. INDIAN_ADDRESS recall beyond L1+L2 is left to a
  future landmark/context gazetteer instead. This pack now depends on
  `maskflow-core[nlp]` (spaCy) unconditionally -- previously spaCy-free.

  **Cumulative L1+L2+L3 report** (`bench/indiapii/report.py`, against a
  small hand-built fixture set under `packs/maskflow-pack-india/tests/
  fixtures/india_l{1,2,3}_samples.py` -- not a general accuracy claim,
  and iterated against directly while building, so treat as "known bug
  classes fixed" rather than production accuracy): PERSON_NAME 79.3%
  precision / 100% recall; INDIAN_ADDRESS 92.9% / 100%. PERSON_NAME's
  remaining false positives are entirely documented, known limitations
  (common-word/name collisions inherited from maskflow-pack-intl's own
  pre-existing PERSON NER, confirmed present even with pack-india NOT
  installed; the "Dr. Reddy's" ambiguity above) -- not new regressions
  from this session's recognizers. Re-run `bench/indiapii/report.py` if
  L4 is ever taken up.
- `maskflow-cli`: `maskflow doctor` -- checks installed maskflow-core/cli/pack
  versions, spaCy + `en_core_web_sm` model presence, `.maskflowrc` validity,
  and prints which entities are consequently enabled/disabled (an NER-backed
  entity like `PERSON_NAME` reports "disabled -- spaCy model unavailable"
  when the model isn't installed; an entity turned off via
  `.maskflowrc`'s `entities.<X>.enabled = false` reports that instead).
  Also flags the still-unimplemented `RedisMappingStore` as an informational
  warning. Exits 0 only when every check passes. Adds `rich` as a
  `maskflow-cli`-only dependency for the table output.
- `maskflow-cli`: `maskflow explain "<text>"` -- shows, span by span, why
  each piece of text was (or wasn't) detected as PII: the pattern/NER hit,
  checksum result, context boost, and the threshold decision behind it.
  Spans that scored below their entity's threshold are listed separately as
  NEAREST MISSES, along with the `.maskflowrc` threshold change that would
  have caught them. Matched text is truncated to 8 characters by default
  (`--full` shows the entire match) -- never printed unbounded, per this
  repo's no-raw-PII-in-output rule. Supports `--config`/`--set` like
  `maskflow config`, so explanations reflect the same resolved config a
  real `mask()` call would use.
- `maskflow-core`: `detect()` gained an opt-in `return_rejected` keyword
  (default `False`, zero behavior/cost change for existing callers) that
  changes the return shape to `(accepted, rejected)`, where `rejected` is
  every candidate span dropped for scoring below its entity type's
  threshold in the resolve pass. `Span.explanation` changed from
  `list[str]` to `list[ExplanationStep]` (a new structured dataclass:
  `rule`, `outcome`, `delta`, `detail`) so decision trails can be rendered,
  serialized, or asserted on by field instead of by substring match. This
  is the core support `maskflow explain` is built on.

## [core 0.3.0, pack-intl 0.2.0, sdk 0.2.0] - 2026-08-21

### Added

- `maskflow-core`: `.maskflowrc` configuration file support --
  `maskflow_core.config`, TOML (primary, stdlib `tomllib`/`tomli`), YAML
  (optional `maskflow-core[yaml]` extra), and JSON. Config resolves
  through five precedence levels (schema defaults < user file
  `~/.config/maskflow/config.toml` < project file, discovered by walking up
  from cwd and stopping at the repo root < environment variables
  (`MASKFLOW_*`) < CLI `--set`/`--config`), tracking per-field provenance.
  Validation (hand-rolled dataclasses + validators -- no pydantic, to keep
  core's footprint essentially unchanged) rejects unknown keys with a
  did-you-mean suggestion (`entities.PAN.threshod` -> "did you mean
  'threshold'?") and reports every problem found in one pass, annotated
  with file:line when known. User-supplied regex (`custom.<NAME>.pattern`,
  `exclusions.patterns`) goes through a ReDoS safety check (static shape
  check + timeboxed adversarial probe) before being accepted. See
  `docs/configuration.md` for the full schema and precedence reference.
- `maskflow-core`: `detect()` and `mask_with_policy()` gain five
  keyword-only params (`per_entity_threshold`, `disabled_types`,
  `extra_patterns`, `exclusion_values`, `exclusion_patterns`) -- how
  resolved `.maskflowrc` config reaches detection/masking
  (`maskflow_core.config.engine.compile_config()`). Every one defaults to
  "no effect", so existing calls are unmodified both in output and in the
  code path they run; `maskflow_core.masking.mask()` itself is untouched.
  Also exports `surrogate_substitute` (renamed from the former private
  `_surrogate_substitute`, no behavior change).
- `maskflow-cli` (new package, 0.1.0): `maskflow config validate` and
  `maskflow config show [--resolved]`, built on `maskflow_core.config`.
  `exclusions.values` is redacted in all CLI output.
- `maskflow-core`/`maskflow-pack-intl`: added `py.typed` markers (PEP 561)
  so downstream packages can be type-checked against them without
  `ignore_missing_imports` -- no behavior change.
- `maskflow-sdk`: `mask()`, `mask_and_call()`, `session()`/`async_session()`
  all gain an optional `config=` parameter (a `maskflow_core.config.
  RootConfig`) that changes which entities are detected
  (threshold/enabled/custom patterns/exclusions) and how they're
  substituted (strategy: replace/redact/mask/hash/surrogate).
  `config=None` (the default) uses the ambient `.maskflowrc` discovered
  from the filesystem, cached once per process -- a long-running server
  doesn't re-stat the filesystem on every call; `maskflow.reload_config()`
  forces a fresh discovery. Passing `config=` explicitly bypasses
  discovery entirely, for a library embedded in someone else's
  application. **With no `.maskflowrc` anywhere and no `config=` passed,
  output is byte-identical to before this change** -- proven with a
  10,000-example hypothesis property test
  (`maskflow-core/tests/test_masking.py::
  test_mask_with_policy_default_matches_mask`) asserting
  `mask_with_policy(text, MaskPolicy())` is byte-identical to `mask(text)`
  for arbitrary text and threshold, which is what the config-aware
  `mask()` wrapper delegates to. Non-reversible substitutions
  (redact/mask/hash) are simply omitted from `MaskResult.mapping` rather
  than requiring a type change. `Session` compiles its config once at
  construction (not per call); numeric `mask_json()` leaves keep their
  numeric-surrogate scheme regardless of configured strategy, preserving
  the documented "leaf's JSON type never changes" invariant.
- `maskflow-sdk`: `maskflow.session()` / `maskflow.async_session()` --
  session-scoped masking for multi-turn/multi-tool-call agents. Unlike
  `mask()` (counters and value->token identity reset every call), a
  `Session` keeps that identity stable for its whole lifetime, so the same
  PII value always gets the same `<TYPE_n>` token across separate
  `.mask()`/`.mask_json()` calls instead of each call independently
  restarting its own numbering (see `docs/agent-sessions.md` for the
  concrete before/after). `Session.mask_json()` walks a nested
  dict/list/tuple structure, masking string leaf *values* only -- dict keys
  are never touched, and a PII-shaped integer leaf is replaced with a
  same-digit-count integer surrogate rather than a schema-breaking string,
  so a masked tool-call payload keeps its original JSON shape. Sessions are
  closeable (`with maskflow.session() as s: ...`, or `s.close()`) and
  TTL-bounded (`ttl_seconds`, default 3600); either purges the mapping, and
  any further call raises the new `SessionClosedError` instead of silently
  no-op'ing. `AsyncSession`/`async_session()` wrap the same `Session` via
  `asyncio.to_thread` with no changes to core. Neither `Session` nor
  `AsyncSession` is thread-safe -- documented explicitly rather than
  silently assumed. No change to `mask()`/`unmask()`/`mask_and_call()`.

### Fixed

- `maskflow-core`: `pytest -m leak` run on its own used to deselect every
  test except the leak-gate assertion itself, so `LEAK_POOL` -- filled only
  by whatever ran earlier in the same process -- stayed empty and the gate
  passed trivially even with an active PII leak elsewhere in the code
  (verified: adding a deliberate `logger.debug(span.text)` to a recognizer
  and running `pytest -m leak` alone did not fail). `pytest_configure` in
  `maskflow_core.testing` now neutralizes any `-m`/markexpr mentioning
  "leak" so the whole session still runs -- the marker is for ordering
  (leak-gate test runs last) and identification, not selection.

### Changed

- `maskflow-core` / `maskflow-sdk` / `maskflow-pack-intl`: raised the minimum
  supported Python from 3.9 to 3.10 (`requires-python = ">=3.10"`). Python
  3.9 reached upstream end-of-life on 2025-10-05 and no longer receives
  security patches; it was also the direct cause of CI's slowest jobs
  (~15 min) -- spaCy's `blis` dependency has no prebuilt wheel for 3.9 on
  several platforms, forcing a from-source build every run. `ci.yml`'s test
  matrix drops 3.9 (and the Windows+3.9 exclude workaround it needed) in
  favor of 3.10/3.11/3.13; `ruff`'s `target-version` and ambient code style
  move to `py310` accordingly (e.g. `Union[X, Y]` -> `X | Y`, `zip()` calls
  now specify `strict=` explicitly, newly enforceable now that all
  supported versions have it).

### Added

- `maskflow-core`: `mask_with_policy(text, policy, min_confidence)` alongside
  the untouched `mask()`/`unmask()`/`mask_and_call()` (`maskflow-sdk`'s
  0.1.0 API is unchanged -- new capability lives entirely in new functions).
  Five substitution strategies, selected per entity type via
  `MaskPolicy(default_strategy, per_entity_strategy)`: `REPLACE` (the
  existing typed-placeholder behavior), `REDACT` (constant
  `[REDACTED_TYPE]` marker), `MASK` (partial reveal, e.g. `XXXX XXXX 9012`,
  configurable via `MaskConfig`), `HASH` (HMAC-SHA256, stable per value,
  keyed via `HashConfig` or `MASKFLOW_HASH_KEY`), and `SURROGATE` (a
  plausible fake of the same type, via `register_surrogate_generator()`;
  falls back to `REPLACE` for any type with no registered generator).
  `REPLACE`/`SURROGATE` are reversible via the same `unmask()`; `REDACT`/
  `MASK`/`HASH` are intentionally one-way. `mask_with_policy()` returns a
  `PolicyMaskResult` whose mapping is a `Mapping` (token -> `MappingEntry`),
  not a plain dict -- `MappingEntry.original` is repr-excluded like
  `Span.text` (rule 1).
- `maskflow-core`: `MappingStore` protocol plus `InMemoryMappingStore`
  (TTL-expiring, process-local, the default), `EncryptedFileMappingStore`
  (AES-GCM at rest, key from `MASKFLOW_MAPPING_KEY` or passed explicitly --
  requires the new optional `maskflow-core[store]` extra), and
  `RedisMappingStore` (interface-only stub this round -- every method
  raises `NotImplementedError`). Masking itself stays pure/stateless; a
  `MappingStore` is an opt-in way for a caller to persist a `Mapping`
  across requests/processes.
- `maskflow-core`: 10,000-example Hypothesis property test
  (`unmask(mask(t).masked_text, mapping) == t` for arbitrary `st.text()`)
  plus explicit empty-string/index-0/final-index/combining-character cases,
  proving CLAUDE.md's "round-trip sacred" guarantee (rule 5) rather than
  just asserting it. Offsets are documented as Python `str` code-point
  offsets throughout (`detect()`/`mask()`/`mask_with_policy()`), not byte
  offsets -- consistent, and safe for non-ASCII PII.
- `maskflow-core` / `maskflow-pack-intl`: whole-session leak gate
  (`maskflow_core.testing`, `pytest -m leak`) -- captures every log record
  and exception raised during a package's test session and asserts none of
  its known PII fixture values ever appeared in either, in addition to the
  existing per-class repr checks. Runs as part of each package's normal
  `pytest` step in CI (the marker doesn't exclude, so no separate CI job
  was needed).
- `maskflow-pack-intl`: `Strategy.SURROGATE` generators for EMAIL, PHONE,
  SSN, CREDIT_CARD, IBAN, PERSON_NAME, and ADDRESS, each drawing from a
  documented reserved/invalid range or embedded synthetic corpus (see the
  package README's surrogate table) so a generated value never collides
  with something a real issuer could plausibly assign.

### Changed

- `maskflow-core`: `mask()` now reuses the same `<TYPE_n>` token for a
  repeated identical PII value within one call, instead of minting a new
  numbered token for every occurrence (CLAUDE.md design decision #3,
  "same value -> same token per session"). Round-trip behavior is
  unaffected either way (`str.replace()` already restores every occurrence
  of a token); output for text with no repeated values is unchanged.
- `maskflow-core`: replaced the ad hoc per-recognizer overlap merge with a
  central `SpanSet.resolve(config)` pipeline (`maskflow_core.spanset`).
  `Finding` is renamed `Span` (`type`/`value` fields renamed
  `entity_type`/`text`); every span now also carries `recognizer` and an
  `explanation` trail. Overlap resolution supports a configurable per-entity
  policy -- `STRICT` (default, no overlaps survive), `CONTAINED` (a more
  specific nested span wins over a same-status containing one), `MERGE`
  (adjacent same-type spans separated by whitespace/a punctuation character
  join into one) -- while the existing invariant is unchanged: a
  checksum-validated span never loses to an overlapping unvalidated one.
  Detection now runs a tier-0 excision pass -- confidently-resolved regex
  spans are blanked out (same-length filler, so char offsets are preserved)
  before the NER pass runs over the remainder, rather than NER scanning raw
  PII text. No change to `mask()`/`unmask()`/`mask_and_call()` signatures or
  behavior. `maskflow-sdk` and `maskflow-pack-intl` updated accordingly
  (`Finding` -> `Span` in `maskflow-sdk`'s exports too).

## [sdk 0.1.1] - 2026-08-20

### Changed

- `maskflow-sdk`: now depends on `maskflow-core>=0.2.0,<0.3` and
  `maskflow-pack-intl>=0.1.0,<0.2` (previously `maskflow-core>=0.1.0,<0.2` with
  recognizers bundled directly into core). No public API change --
  `mask()`/`unmask()`/`mask_and_call()` are identical -- this just moves
  `pip install maskflow-sdk` onto the split core/pack-intl architecture
  published in `core 0.2.0, pack-intl 0.1.0` below.

## [core 0.2.0, pack-intl 0.1.0] - 2026-08-19

### Changed

- **Workspace restructure**: the repo is now a real [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/)
  rooted at `pyproject.toml`, with members under `packages/*` and `packs/*`. `core/` moved to
  `packages/maskflow-core`, `sdk/python/` moved to `packages/maskflow-sdk`, and
  `packages/detection/` moved to `packages/maskflow-js` (npm package name unchanged --
  still publishes as `@maskflow/detection`). No published-artifact behavior changes; import
  paths (`from maskflow_core import ...`, `from maskflow import ...`) are unaffected.
- `maskflow-core` no longer ships any recognizers -- `patterns.py` and the PERSON_NAME/
  DATE_OF_BIRTH NER logic moved to a new package, **`maskflow-pack-intl`**, which registers
  all 12 original types (email, phone, SSN, credit card, IP, AWS/API keys, JWT, IBAN, address,
  person name, date of birth) against core on import. `maskflow-sdk` now depends on
  `maskflow-pack-intl` automatically, so `pip install maskflow-sdk` behaves identically to
  before -- this only matters for code importing `maskflow_core` directly without a pack.
- `maskflow-core`: `registry.py` gained `register_ner_recognizer()` alongside the existing
  `register_pattern()`, so spaCy-label-based recognizers (like PERSON_NAME/DATE_OF_BIRTH) are
  now pack content too, registered the same way regex-based ones are. Both registration
  functions accept an optional `context_keywords` argument, replacing the previously-hardcoded
  `CONTEXT_KEYWORDS` table.
- `maskflow-core`: spaCy moved from a required dependency to an optional one
  (`maskflow-core[nlp]`). Without it installed, the NER pass is skipped with a single warning
  and pattern-based recognizers are unaffected.

### Fixed

- `maskflow-core` / `maskflow-pack-intl`: fixed a latent Python 3.9 incompatibility (`X | None`
  return/parameter annotations evaluated eagerly instead of deferred) that would have broken
  on 3.9 the first time CI actually tested that version -- added `from __future__ import
  annotations` to the affected modules.

- `maskflow-core`: `Finding.value` no longer appears in default `repr()`
  output, and test-failure messages no longer interpolate raw sample text or
  matched values -- closes a PII leak surface in test/debug output. Registered
  the `benchmark`/`leak` pytest markers referenced by CLAUDE.md's commands.
- `maskflow-core` / `@maskflow/detection`: bounded the two unbounded `\w*`
  quantifiers in the generic-secret-assignment regex (was O(n^2) on long
  word-runs with no `:`/`=`).

- `maskflow-core` / `@maskflow/detection`: `mask()` now pre-scans input text
  for placeholder-lookalike substrings (e.g. a prompt that already contains
  `<EMAIL_1>`) and falls back to a nonce-suffixed token on collision.

### Added

- `maskflow-core` / `@maskflow/detection`: unicode/emoji/RTL/zero-width
  round-trip test coverage for `mask()`/`unmask()`.
- `maskflow-core` / `@maskflow/detection`: `Finding.validated` -- true when a
  structural validator (Luhn, IBAN mod-97, SSN area-code check) confirmed the
  match. Central overlap resolution now sorts by (validated desc, confidence
  desc, length desc, start asc), so a checksum-validated span always beats an
  overlapping unvalidated one.
- `maskflow-core`: `PIIType` is now an open registry (`PIIType.register(...)`)
  instead of a closed `Enum`, and `register_pattern()` lets a future pack
  (e.g. `maskflow-pack-india`) add new PII types and recognizer rules without
  editing `maskflow-core` itself. Existing built-in types and their `.value`/
  equality/`isinstance` behavior are unchanged.

## [0.1.0] - 2026-08-06

### Added

- `maskflow-core`: PII detection and reversible masking engine. Three-layer detection pipeline
  (regex + structural validation, keyword-context confidence boosting, spaCy NER) covering 12 PII
  types: email, phone, SSN, credit card, IPv4/IPv6, AWS access key, API key/generic secret, JWT,
  IBAN, street address, person name, date of birth.
- `maskflow-sdk`: Python SDK built on `maskflow-core`, with `mask_and_call` for masking a prompt,
  calling any LLM, and unmasking the response.
- `@maskflow/detection`: TypeScript port of the regex/structural detection layer.

[unreleased]: https://github.com/maskflow/maskflow/compare/sdk-py-v0.1.1...HEAD
[sdk 0.1.1]: https://github.com/maskflow/maskflow/compare/sdk-py-v0.1.0...sdk-py-v0.1.1
[core 0.2.0, pack-intl 0.1.0]: https://github.com/maskflow/maskflow/compare/core-v0.1.1...core-v0.2.0
[0.1.0]: https://github.com/maskflow/maskflow/releases/tag/v0.1.0
