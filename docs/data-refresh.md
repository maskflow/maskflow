# Refreshing maskflow-pack-india's bundled reference data

Five files under `packs/maskflow-pack-india/src/maskflow_pack_india/data/`
bundle curated, provenance-tracked reference data the India recognizers
validate against. None of them are exhaustive by design (see each file's own
docstring for its exact scope) -- a false negative on an obscure/regional
value is preferred over inventing a check the underlying identifier doesn't
actually have. This doc is the one place that lists all five, what backs
them, and how to refresh each.

`scripts/refresh_india_reference_data.py` (repo root, run via
`uv run python scripts/refresh_india_reference_data.py <command>`) automates
the fetch-and-diff step for two of the five. It never writes the data files
itself -- every command prints a diff for a human to review and fold in by
hand. That's deliberate: an automated feed can't tell curated scope (e.g.
"major scheduled commercial banks" excluding thousands of tiny co-operative
banks) from noise, and a corrupted/bad-scope fetch silently overwriting a
recognizer's structural-validation set is exactly the kind of precision
regression this pack can't afford.

## `ifsc_bank_codes.py` -- IFSC bank-code prefixes

**Source:** [`razorpay/ifsc`](https://github.com/razorpay/ifsc)
(`src/banks.json`) -- MIT-licensed code, public-domain dataset,
RBI-cross-checked. Its `type` field is more granular than this pack wants
(state/urban/district co-operative banks are out of scope); the script's
`IN_SCOPE_TYPES`/`PSB_ALLOWLIST` constants encode which types to keep --
update them there if the pack's scope changes, not just the data file.

**Refresh:**
```
uv run python scripts/refresh_india_reference_data.py ifsc
```
Review the printed additions against `IFSC_BANK_CODES`, add the ones you
want, bump the "Last refreshed" line in the file's docstring. Codes flagged
as "not present in this fetch" are never auto-removed -- retired codes stay
valid on old documents indefinitely.

## `upi_handles.py` -- UPI PSP handles

**Source:** no machine-readable authoritative NPCI feed exists (checked
again 2026-08-27; NPCI publishes member-bank lists, not a live handle
registry). Refresh is manual: check each PSP's own UPI help/documentation
page against `UPI_PSP_HANDLES`.

**Refresh:**
```
uv run python scripts/refresh_india_reference_data.py upi
```
prints the procedure and where to look. Never remove a retired handle --
historical VPAs may still reference it.

## `indian_state_rto_codes.py` -- vehicle-registration (RTO) state/UT codes

**Source:** MoRTH's Vahan/Sarathi portals
(https://vahan.parivahan.gov.in, https://sarathi.parivahan.gov.in). No
public bulk feed; this list changes only when a state/UT is created, renamed,
or split, so it's checked by hand against the portals rather than scripted.
Never remove a retired code.

## `indian_places.py` -- state/UT names + city gazetteer

**Sources:**
- States/UTs: hand-curated, 36 entries, stable (India hasn't added a
  state/UT since Jammu & Kashmir's 2019 reorganization).
- Cities: unioned from two sources -- Wikipedia's
  [List of cities in India by population](https://en.wikipedia.org/wiki/List_of_cities_in_India_by_population)
  (CC-BY-SA 4.0 + GFDL) and India's Census 2011 town-population figures
  (Government of India, GODL-India -- population counts are official
  statistics, not a copyrightable compilation), filtered to population
  >= 100,000.

**Refresh:**
```
uv run python scripts/refresh_india_reference_data.py cities --input <census.csv>
```
`<census.csv>` needs `name_of_city` and `population_total` columns. Census
2011 town-population data doesn't have a stable direct-download URL without
a registered data.gov.in API key (which this repo won't embed) -- download a
fresh export from data.gov.in's Census 2011 town-population catalog, or from
a CSV mirror of the same figures (e.g. Kaggle's "Top 500 Indian Cities"
dataset), before running the command. Review the printed additions, add the
ones you want, bump the "Last refreshed" line and the entry count in the
file's docstring.

## `indian_names.py` / `indian_names.txt` -- person-name gazetteer

**Source:** see the file's own docstring for the full sourcing writeup.
114,536 unique romanized name tokens, short of a 150k+ target -- no
license-clean corpus at that scale has been found as of 2026-08-27 (checked
again this session; every larger candidate found was either the same
provenance already bundled, smaller, or carried no license at all). This is
a deliberate, documented shortfall, not an oversight -- tracked as a
follow-up issue on the repo (search "name gazetteer" if one turns up).
There's no refresh script for this file: growing it means finding a new
source, not re-fetching an existing one.

## Spelling-variant rules

`gazetteer.py`'s `generate_spelling_variants()` (suffix/substring rules,
e.g. Krishna/Krishnaa, Lakshmi/Laxmi) applies at automaton-build time, not
per-request -- the automaton is built once and `@lru_cache`'d. These rules
are hand-maintained in code, not a refreshable dataset; add a rule there
directly if you find a common variant the gazetteer misses.
