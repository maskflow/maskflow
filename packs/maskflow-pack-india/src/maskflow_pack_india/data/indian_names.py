"""Bundled Indian person-name gazetteer for PERSON_NAME (Indian) L1 matching
(../gazetteer.py). The bulk of the data lives in the sibling
`indian_names.txt` (one lowercase name per line) and is loaded lazily via
`load_indian_names()` -- see gazetteer.py's module docstring for why (keeps
bare `import maskflow_pack_india` fast; the file is only read the first time
a gazetteer automaton is actually built).

Sources (fetched 2026-08-26, merged and deduplicated into indian_names.txt):

1. `swami93/indian-names-1.5M` (HuggingFace, https://huggingface.co/
   datasets/swami93/indian-names-1.5M). Dataset card declares MIT, but that
   license is SELF-DECLARED by a single contributor with NO documented
   upstream provenance -- and despite the "1.5M" name, the actual bundled
   file is 114,239 deduplicated lowercase name tokens (no given/surname or
   frequency tagging), not 1.5 million. Bundled anyway (explicit decision,
   this session) with this caveat recorded rather than silently treated as
   fully verified.
2. `indian-names` (PyPI 0.3, BSD-3-Clause, https://github.com/ByteBaker/
   indian-names): 566 female given names, 576 male given names, 352
   surnames -- small but cleanly licensed and explicitly given/surname
   split in the original package (folded into one flat pool here since L1
   doesn't act on kind, only on frequency tier -- see TIER_COMMON/TIER_RARE
   in gazetteer.py).
3. A ~60-entry hand-curated list of well-known Indian surnames (general
   knowledge, not drawn from either dataset above -- same category as this
   pack's existing hand-curated state/UT name list in __init__.py) folded
   in and force-tiered "common" below, since several of these are too
   generic/frequent to be distinctive standalone evidence.

Combined total: 114,536 unique romanized name tokens after merge/dedupe --
short of the work order's 150k+ target. No license-clean surname corpus at
that scale could be found this session (a Harvard Dataverse electoral-roll
dataset was CC0-labeled but its actual access terms restrict it to
research-only, non-commercial use; several GitHub name-list gists carry no
license at all) -- see the L1 precision/recall report for the full
sourcing writeup, and CHANGELOG.md for this decision's record.

Frequency tiering: per CLAUDE.md's spec ("common names need context, rare
may fire alone"), the bundled pool defaults to "rare" (fires standalone)
since raw dataset membership carries no real frequency signal -- most
entries are, on their face, distinctive tokens. Two small, hand-curated
override sets pull specific entries to "common" (needs nearby context to
clear DEFAULT_MIN_CONFIDENCE):

  - _COMMON_INDIAN_SURNAMES: extremely high-frequency Indian surnames
    (general knowledge) too generic to be distinctive alone, e.g. "Kumar",
    "Devi", "Singh".
  - _COMMON_WORD_COLLISIONS: entries that are also common English
    dictionary words, e.g. "Angel", "Rose", "Hope" -- exactly the
    ambiguity the L1 hard-negative fixtures target.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources

_COMMON_INDIAN_SURNAMES: frozenset[str] = frozenset(
    {
        "kumar", "sharma", "singh", "kaur", "patel", "reddy", "rao", "gupta",
        "verma", "nair", "iyer", "iyengar", "pillai", "menon", "chatterjee",
        "banerjee", "mukherjee", "das", "dutta", "ghosh", "sen", "bose",
        "mishra", "mistry", "tripathi", "tiwari", "pandey", "yadav",
        "chauhan", "rathore", "thakur", "bhatt", "joshi", "desai", "shah",
        "mehta", "agarwal", "aggarwal", "jain", "khan", "ali", "ahmed",
        "hussain", "sheikh", "syed", "malik", "chowdhury", "dey", "roy",
        "naidu", "chettiar", "gowda", "hegde", "kulkarni", "deshmukh",
        "more", "jadhav", "pawar", "shinde", "gaikwad", "devi",
    }
)  # fmt: skip

_COMMON_WORD_COLLISIONS: frozenset[str] = frozenset(
    {
        "angel", "rose", "lily", "hope", "grace", "faith", "joy", "may",
        "june", "ivy", "dawn", "sunny", "happy", "rich", "bill", "will",
        "mark", "summer", "autumn", "star", "rain", "sky", "hazel", "daisy",
        "jasmine", "olive", "ruby", "pearl", "amber", "crystal", "destiny",
        "harmony", "melody", "precious", "true", "noble", "royal", "prince",
        "king", "queen", "glory", "victory", "liberty",
        # Common nouns discovered (not English function words, so not in
        # EXCLUDED_NAMES, but common enough to need context) while
        # smoke-testing this layer against fixtures -- residual noise from
        # the swami93 corpus's lack of documented provenance (see this
        # module's docstring); not an exhaustive sweep, see the L1 report.
        "ship", "india", "sun",
        # This pack's OWN entity-type acronyms/abbreviations ("ABHA", "PAN",
        # "VID", "EPIC", "DL") are, coincidentally, also real gazetteer
        # entries (Abha is a given name, Pan/Vid/Epic/Dl are pool noise) --
        # downgraded rather than excluded, since e.g. "Abha" IS a genuine
        # name in running prose, just not when it's this product's own
        # ABHA_NUMBER/ABHA_ADDRESS keyword (see NEGATIVE_SAMPLES[18] in
        # pii_samples.py, which caught this).
        "abha", "pan", "vid", "epic", "dl",
    }
)  # fmt: skip

_COMMON_OVERRIDES = _COMMON_INDIAN_SURNAMES | _COMMON_WORD_COLLISIONS

# English function words (articles, pronouns, auxiliary/modal verbs,
# conjunctions, prepositions) that turned up in the swami93 corpus -- exactly
# the kind of noise its lack of documented provenance warned about (see this
# module's docstring). Unlike _COMMON_WORD_COLLISIONS (a real name that's
# ALSO a common noun, still worth matching with context), these can never be
# a person's name in running English text -- every sentence starts with one
# capitalized ("The", "My", "Is", ...), so they're EXCLUDED from the
# gazetteer entirely rather than merely tier-downgraded.
EXCLUDED_NAMES: frozenset[str] = frozenset(
    {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "do", "does", "did", "have", "has", "had", "will", "shall", "should",
        "would", "may", "might", "must", "can", "could", "not", "no", "yes",
        "and", "or", "but", "if", "then", "else", "so", "as", "at", "in",
        "on", "to", "of", "for", "from", "with", "by", "about", "above",
        "after", "again", "against", "all", "am", "any", "because",
        "before", "below", "between", "both", "down", "during", "each",
        "few", "further", "here", "how", "into", "itself", "just", "more",
        "most", "other", "over", "own", "same", "than", "under", "until",
        "up", "very", "what", "when", "where", "which", "while", "who",
        "whom", "why", "you", "your", "yours", "me", "my", "mine", "we",
        "us", "our", "ours", "he", "him", "his", "she", "her", "hers", "it",
        "its", "they", "them", "their", "theirs", "this", "that", "these",
        "those",
        # Romanized Hindi/Hinglish function words (pronouns, copulas,
        # postpositions) -- MaskFlow's India text mixes scripts (see this
        # pack's Devanagari context keywords elsewhere), so the same
        # "never a name" reasoning applies here as for the English set
        # above, e.g. "Mera naam Sanjiv hai" ("My name is Sanjiv").
        "mera", "tera", "yeh", "hum", "aap", "hai", "tha", "thi", "ka",
        "ki", "ke", "se", "par",
        # This pack's own L2 structural vocabulary (patterns.py's
        # PERSON_NAME_HONORIFIC_RE alternation, plus "name" the label word)
        # -- these are titles/labels, not names, and L2's dedicated
        # honorific/form-field patterns already handle "Shri Ramesh" etc.
        # structurally. Left in the gazetteer, "Shri" (etc.) would coalesce
        # onto the front of the following real name (match_person_names()'s
        # multi-token bonus) and get included in the matched span, e.g.
        # "Shri Ramesh Chandra Verma" instead of "Ramesh Chandra Verma".
        "shri", "sri", "smt", "kum", "mrs", "name",
    }
)  # fmt: skip

TIER_COMMON = "common"
TIER_RARE = "rare"

# A 2-letter pool entry is almost never a genuine standalone Indian name
# (real short names like "Om"/"Raj" are 3 chars) and disproportionately
# turns up as noise in the swami93 corpus (~324 of its 114k entries are
# length <= 2) -- dropped entirely rather than tier-downgraded, same
# reasoning as EXCLUDED_NAMES.
_MIN_NAME_LENGTH = 3


@lru_cache(maxsize=1)
def load_indian_names() -> dict[str, str]:
    """name (lowercase) -> frequency tier ("common" | "rare"). Cached after
    first call -- see this module's docstring for the lazy-load rationale.
    """
    # Deferred import: data/indian_places imports nothing from here, so this
    # isn't a cycle, but importing it lazily keeps this module's own load
    # order independent of package __init__ import order.
    from .indian_places import INDIAN_PLACE_NAMES

    # Exclude both the full place name ("lucknow") and each individual word
    # of a multi-word one ("uttar", "pradesh" from "Uttar Pradesh") -- a
    # state-name fragment that also happens to sit in the noisy person-name
    # pool (see this module's provenance caveat) would otherwise coalesce
    # into a fake multi-token PERSON_NAME match (match_person_names()'s
    # MULTI_TOKEN_BONUS) that outscores and beats the real INDIAN_ADDRESS
    # span for the same text in resolve()'s overlap competition.
    place_names: set[str] = set()
    for place in INDIAN_PLACE_NAMES:
        lowered = place.lower()
        place_names.add(lowered)
        place_names.update(lowered.split())

    raw = resources.files(__package__).joinpath("indian_names.txt").read_text(encoding="utf-8")
    names: dict[str, str] = {}
    for line in raw.splitlines():
        name = line.strip()
        if not name or len(name) < _MIN_NAME_LENGTH or name in EXCLUDED_NAMES:
            continue
        # A place name (e.g. "delhi", "mumbai") shouldn't also compete as a
        # PERSON_NAME candidate from the same automaton pass.
        if name in place_names:
            continue
        names[name] = TIER_COMMON if name in _COMMON_OVERRIDES else TIER_RARE
    return names
