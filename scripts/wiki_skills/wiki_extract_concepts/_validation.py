"""Validation and sanitization leaf for wiki-extract-concepts (TASK 016).

Dependency rule: imports ONLY stdlib + `._errors` + `scripts.wiki_skills._common`.
No import from the facade (`__init__`) or any other leaf.

★ TASK 064 — THE ANTI-GARBAGE GATES. The operator's ask, in his words:
*"definitions for the KEY concepts, which COMPLEMENT the source page, WITHOUT
GARBAGE DATA"* — and the rail must hold on WEAK models, which obey quotas far more
literally than strong ones. Five of the gates live in this file, and every one of
them is a MECHANISM, not prompt wording (the prompt is advice; a validator is not):

  G0  `_CANDIDATE_COUNT_MIN = 0` — **AN EMPTY EXTRACTION IS A SUCCESS.** This was
      **1**, and it is the root of every other garbage class: on a thin source, a
      floor of 1 makes the model's ONLY green path an invention. `wiki-extract-
      decisions` refused to clone that 1 and said so in its module docstring; the
      concepts rail never got the fix. It has it now.
  G1  `_FIELD_MIN_WORDS` + `DEFINITION_IS_QUOTE` + `DEFINITION_NOT_PROSE` — the
      definition must COMPLEMENT the source, not echo it and not smuggle markdown.
  G2  the quote receipt is LOAD-BEARING: a real clause, and compared NFC-normalised so
      a line-wrapped quote grounds instead of failing for the wrong reason.
  G3  ★ **NO `WIKI_EXTRACT_NO_QUOTE_CHECK` ESCAPE, AND NO MENTION OF ONE.** The env
      read is deleted. So is the string that TAUGHT it: the old refusal put
      *"(set WIKI_EXTRACT_NO_QUOTE_CHECK=1 to skip)"* into the envelope the model
      reads AT THE EXACT MOMENT IT IS STUCK — a fabrication tutorial in the failure
      path. No env var may appear in any refusal reason on this rail.
  G4  `person` is NOT an entity type here — an attendee belongs in `participants:`.
  G6  `check_in_batch_collisions` — two candidates, one slug: the second silently
      OVERWRITES the first. One file, one row, one concept gone, ZERO lint issues,
      because the count is right.
  G9  the `source_span` is CHECKED against the body (it was pure honour system, and
      it lands in `page_entity_refs` as if it were provenance).
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path
from typing import Any

from scripts.wiki_skills._common import (
    _LINE_LEADING_MD_ACTIVES,
    sanitize_markdown_text as _sanitize_markdown_text,
)
from ._errors import ExtractionParseError


# L-2 (vdd-multi 2026-05-28): `\d` in Python 3 matches Unicode digits
# (Arabic-Indic, Devanagari, ...) by default. We want ASCII-only digits
# in source-span line numbers — anchor with re.ASCII so the schema
# rejects e.g. `L١-L٢` at validation rather than silently coercing.
_SOURCE_SPAN_RE = re.compile(r"^L\d+-L\d+$", re.ASCII)
# TASK 037: the slug CHARSET must admit preserve-unicode slugs (Cyrillic/CJK) so
# `wiki-extract-concepts` works on PARA layouts (obsidian-personal), whose
# slug_strategy keeps Unicode. `str` patterns are Unicode by default, so `\w`
# matches Unicode letters/digits/underscore; `[^\W_]` = a word char that is NOT
# `_`, forcing the first char to be a letter/digit (never `_`/`-`/`.`/sep).
# Forbids `/ \ . space` → path-traversal-safe. ASCII kebab (Karpathy) is a strict
# subset. `\Z` (NOT `$`) anchors the END so a trailing newline cannot smuggle
# through (`$` matches before a final `\n`). Length is INTENTIONALLY not in the
# regex — `_is_valid_slug(max_len=...)` enforces it, so an already-indexed SOURCE
# slug (a `pages.slug` off a long PARA title — unbounded by the indexer) is never
# length-rejected, while CANDIDATE/concept slugs (which become `<slug>.md`
# filenames) stay bounded. Lowercase is enforced by `_is_valid_slug` (not
# charset-expressible for Unicode).
_SLUG_RE = re.compile(r"^[^\W_][\w-]*\Z", re.UNICODE)
# Concept/candidate slug length cap (filename safety: ≤120 Unicode chars → ≤240
# bytes + ".md" stays under the 255-byte filename limit). `None` opts out for the
# already-on-disk SOURCE page (its slug length is the indexer's business).
_SLUG_MAX_LEN = 120
# ★ G4 (TASK 064) — `person` IS GONE, and it is gone on purpose. The operator's
# standing rule is the opposite of what this set used to say: a meeting attendee
# belongs in the note's `participants:` frontmatter and a cited author in the note
# body — never as a `_concepts/` page. `wiki-import` already enforces this, but only
# under `grammar == "pyramid"` (`_authoring.derive_candidates`), so the ARTICLE path
# leaks (`уоррен-баффет`, `гарри-марковиц` are live in the operator's vault) and THIS
# rail had no guard at all. A `person` candidate now gets its OWN refusal code with a
# reason that TEACHES the fix — not the generic parse error, which teaches nothing.
_ALLOWED_ENTITY_TYPES = {
    "concept", "company", "product",
    "group", "event", "work", "external",
}
# Refused with a SPECIFIC, teaching reason (vs an unknown type → EXTRACTION_PARSE_ERROR).
_REFUSED_ENTITY_TYPES = {"person"}

# C-1 (vdd-multi 2026-05-28): operator-supplied sha256-hex must match
# /^[0-9a-f]{64}$/ exactly. Without this, an uppercased hex value (e.g.,
# PowerShell `toupper` pipeline) silently misroutes to
# SOURCE_CHANGED_DURING_EXTRACTION; and unvalidated values become a
# CWE-117 log-injection vector in the envelope reason field.
_SOURCE_HASH_RE = re.compile(r"^[0-9a-f]{64}$")

# H-8 (003-v3-05): operator-supplied attribution string that flows into
# `entities.canonicalized_by`. Strict charset: lowercase alphanumerics +
# `._:@-` (allows model names like `claude-opus-4-7@vendor`). Cap at
# 64 chars; rejects newlines, control chars, and shell metachars.
from scripts.wiki_skills._common import ORCH_ID_RE

_ORCHESTRATOR_ID_RE = ORCH_ID_RE  # TASK 050: shared shape (explicit re-export for the facade)

# v3.1 strict-validator caps (003-v3-02 / H-2 / H-6 / H-9):
_REQUIRED_CANDIDATE_KEYS = {
    "slug", "name", "definition", "source_quote", "entity_type",
}
# ★★ `source_span` IS NO LONGER REQUIRED — TASK 066, and the reason is a MEASUREMENT.
#
# The weak-model harness ran 33 fresh Haiku contexts over the 11 fixtures and produced 56
# candidates. Of those:
#
#     source_quote VERBATIM in the body      56/56  (100%)   ← the anti-fabrication gate WORKS
#     the model's source_span is CORRECT     40/56  ( 71%)   ← it is COUNTING LINES, and failing
#     the span is DERIVABLE from the quote   56/56  (100%)
#
# NINE of the thirteen failing runs were a bad span — the single largest failure class, hitting
# 8 of the 11 fixtures. The model is off-by-3 on one fixture (it miscounted the frontmatter),
# off-by-1 on another, and on a third it emitted `L407` where the truth is `L34`.
#
#     WE WERE ASKING A LANGUAGE MODEL TO DO ARITHMETIC ON LINE NUMBERS.
#     THE SPAN IS A COMPUTATION, NOT A JUDGEMENT.
#
# So `apply` DERIVES it (`derive_source_span`). A supplied span is now only a HINT, used to
# disambiguate a quote that occurs more than once.
#
# ★ DERIVATION IS STRICTLY STRONGER THAN THE CHECK IT REPLACES. G9 existed because the span
# was an honour system — `L9999-L9999` on a 3-line body was written into `page_entity_refs` as
# provenance. A DERIVED span cannot be fabricated: it is computed from a quote that is itself
# verified verbatim. There is nothing left to lie about.
_OPTIONAL_CANDIDATE_KEYS = {"source_span"}
# ★★ G0 (TASK 064) — ZERO. THE MOST IMPORTANT LINE IN THIS FILE.
#
# This was 1. A floor of 1 means: on a source with no extractable concepts, EVERY
# honest answer is an exit-4 FAILURE, and the model's ONLY green path is to INVENT
# one. It is the pump behind every garbage class the operator found in his live vault
# (a Dune tutorial minting `тултип` and `hex-код-цвета`; `coalesce` and `row_number`
# becoming "concepts") — the model was not being careless, it was obeying a quota.
#
# `wiki_extract_decisions/__init__.py` names THIS FILE as the anti-pattern it refused
# to clone: *"cloning it here would make 'no decisions in this note' an exit-4 failure
# and hand the model a reason to fabricate one."* The concepts rail never got the fix.
# It has it now, and the two rails finally agree.
#
# An empty extraction is SUCCESS: `apply` emits `action: no_candidates` and exits 0.
# Do NOT "restore parity" with the old 1 — the 0 IS the safety property.
_CANDIDATE_COUNT_MIN = 0
_CANDIDATE_COUNT_MAX = 25
_FIELD_CAPS = {
    "name": 200,
    "definition": 2000,
    "source_quote": 500,
}

# ★ G1 + G2 (TASK 064) — the FLOORS. Caps alone accepted `definition: ""` and
# `source_quote: "и"`: the quote receipt was a bare `in` substring test with NO
# minimum, so a single Russian letter "grounded" against any Cyrillic body, and the
# prompt's "10-50 words verbatim" was enforced by NOTHING.
#
# ★★ F8 (TASK 064 FIX-LOOP) — THE FLOOR IS **WORDS**, NOT CHARACTERS, AND IT IS 4.
#
# The first cut used a 40-CHAR floor, and 40 chars sits ABOVE the natural length of a
# terse-but-COMPLETE definition. Measured refusals of CORRECT work:
#
#   «Спред — разница между bid и ask.»        32 chars  ✗ refused   (6 words)
#   «Форк — расхождение цепочки блоков.»      34 chars  ✗ refused   (4 words)
#   «Гамма — скорость изменения дельты.»      34 chars  ✗ refused   (4 words)
#   «AMM — автоматический маркет-мейкер.»     35 chars  ✗ refused   (4 words)
#
# A floor that refuses those **teaches the model to PAD** — the exact opposite of the
# anti-garbage goal. On `source_quote` it is worse in kind: it refuses the source's OWN
# best defining sentence whenever that sentence is short, forcing a LESS relevant, longer
# quote to serve as the receipt. A character count was never what the rule was reaching
# for; "is this a phrase, or is it a token?" was. Count words.
#
# ★ WHY 4 AND NOT THE 5 THE REVIEW PRESCRIBED — MEASURED, and the review's own examples
# are what force it: three of the four CORRECT definitions above are FOUR words (`Форк —
# расхождение цепочки блоков.` = форк/расхождение/цепочки/блоков). A floor of 5 refuses
# three of the four inputs the fix exists to admit; it would have shipped the same defect
# in a new unit. 4 admits every one of them and still kills what it must:
#
#   ""            0 words  ✗   "Метрика."   1 word   ✗   "Это концепция."  2 words  ✗
#   source_quote "и" / "The" / "The Sharpe Ratio"     1/1/3 words          ✗
#
# `name` stays a CHARACTER floor: a name is a noun phrase, not a sentence — "AMM" is a
# perfectly good one-word name, and a word floor there would refuse every acronym.
_NAME_MIN_CHARS = 2
_FIELD_MIN_WORDS = {
    "definition": 4,
    "source_quote": 4,
}
# `\w+` over Unicode: `маркет-мейкер` counts 2, an em-dash counts 0. Both are what we want
# — the question is "how much CONTENT", and punctuation is not content.
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))

# v3.1 (003-v3-04) markdown sanitization helpers — H-7 / Q13 defense in
# depth against prompt-injection-style content surfacing in the concept
# page body or frontmatter.

# Iteration-2 N-5: allow Unicode word chars (Cyrillic, diacritics) by
# anchoring the regex with re.UNICODE flag.
_NAME_ALLOWLIST = re.compile(
    r"^[\w\s\-.,:;()\'\"!?]{1,200}$", flags=re.UNICODE,
)

_SPAN_REGEX = re.compile(r"^L(\d+)-L(\d+)$", re.ASCII)  # L-2: ASCII-only digits


def _norm(text: str) -> str:
    """NFC + collapse-whitespace + casefold — applied to BOTH sides of every
    content comparison on this rail (the quote-vs-body check, the quote-vs-span
    check, the definition-vs-quote check).

    Mirrors `wiki_extract_decisions._validation._norm` (which omits the casefold —
    it compares a quote it will render verbatim). DEFINED LOCALLY, not imported:
    this leaf's dependency rule is stdlib + `._errors` + `_common`, and a private
    module of a sibling skill is not an API (Decision-16). The duplication is
    deliberate and gated by a test that pins the two behaviours equal on the
    normalisation cases that matter.

    Why it matters: a quote copied out of a hard-wrapped source differs from the
    body only in line breaks. Without normalisation it fails the grounding check
    for a reason that has nothing to do with grounding — and a gate that fires on
    innocent inputs is a gate the operator learns to route around.
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def _definition_is_prose(definition: str) -> bool:
    """★ G1 — is this a DEFINITION, or is it markdown wearing one as a costume?

    The definition IS the page (`_pages.py`: body = ``# {name}\\n\\n{definition}``).
    Today a definition carrying `[[`, a backtick, a newline or a line-leading
    markdown marker is SILENTLY ESCAPED by `sanitize_markdown_text` and lands in the
    filed page as visible backslash litter — `See \\[\\[write-ahead-log\\]\\]`. The
    vault gets scarred and nobody is told.

    REFUSING BEATS MANGLING. The model gets told and re-emits one clean sentence;
    the operator's page never carries the scar. The sanitizer stays as
    defense-in-depth for the paths that do not run this validator.

    ★ F9 (TASK 064 FIX-LOOP) — A MARKER IS ONLY MARKDOWN WHEN A SPACE FOLLOWS IT.
    The first cut refused any definition whose FIRST character was one of `#>|*+-~`.
    Newlines are refused separately, so that reduced to *"does it happen to start with one
    of seven ASCII characters"* — and it refused correct definitions outright:

        «-EV — отрицательное математическое ожидание ставки.»      (poker/betting)
        «*args — упаковка позиционных аргументов в кортеж.»        (Python)
        «#DeFi — хештег, под которым …»                            (a tag)

    Real markdown REQUIRES the marker be followed by whitespace (`- item`, `# Heading`,
    `> quote`) — `-EV` is not a list item in any renderer, and `sanitize_markdown_text`
    escapes it only because it uses the same conservative first-char test. Requiring the
    trailing space makes the gate fire on markdown and nothing else. (The other passing
    cases stay passing: an em-dash lead, a `*` inside prose, and math expressions were
    never caught by this branch and are untouched.)
    """
    if "\n" in definition or "[[" in definition or "`" in definition:
        return False
    stripped = definition.strip()
    if not stripped or stripped[0] not in _LINE_LEADING_MD_ACTIVES:
        return True
    rest = stripped[1:]
    # A bare marker (`-`) or a marker + whitespace (`- item`) is markdown; a marker glued
    # to a word (`-EV`, `*args`, `#DeFi`) is prose.
    return bool(rest) and not rest[0].isspace()


def check_in_batch_collisions(candidates: list[dict[str, Any]]) -> None:
    """★ G6 — TWO CANDIDATES → ONE SLUG IS A CONTRACT VIOLATION. Refuse the batch.

    Ported from `wiki_extract_decisions._validation.check_in_batch_collisions`, whose
    reasoning transfers verbatim: `classify_candidates` dedups only against the KNOWN
    set, so two candidates sharing a slug BOTH classify `create`; the second
    `write_concept_page` sees different bytes and returns `updated` — a silent
    overwrite. One file, one DB row, one concept gone, and **ZERO lint issues, because
    the count is right.** "Last one wins" does not show up in lint. That is precisely
    why it needs its own gate.

    Zero false positives: two candidates with the same slug are never both wanted.
    """
    seen: dict[str, int] = {}
    collisions: list[dict[str, Any]] = []
    for i, cand in enumerate(candidates):
        slug = str(cand.get("slug", ""))
        if slug in seen:
            # Model-authored values only (the slug it chose, the indices it sent) —
            # never source-body content. CWE-209 safe.
            collisions.append({"slug": slug, "indices": [seen[slug], i]})
        else:
            seen[slug] = i
    if collisions:
        raise ExtractionParseError(
            f"{len(collisions)} in-batch slug collision(s) — the second candidate "
            f"would silently overwrite the first",
            error="IN_BATCH_SLUG_COLLISION",
            field="slug",
            reason=("two candidates derive the same slug; the second would "
                    "OVERWRITE the first's page with zero lint issues. Merge them "
                    "into one candidate, or give them distinct names."),
            violations=collisions,
        )


def _is_valid_slug(slug: str, max_len: int | None = _SLUG_MAX_LEN) -> bool:
    """Traversal-safe, lowercase, Unicode-aware slug check (TASK 037).

    The single gate replacing the bare ``_SLUG_RE.match`` at every call site
    (candidate-schema validation, ``write_concept_page``, source-page resolution).
    Accepts Unicode word-chars + hyphens — so preserve-unicode Cyrillic/CJK slugs
    validate for PARA layouts — while STILL forbidding ``/ \\ . space``, a leading
    ``_``/``-``, and a trailing newline (``\\Z`` anchor) — path-traversal /
    name-injection guard — and enforcing lowercase so the slug equals what the
    layout slug_strategy + the wikilink ref-extractor produce (otherwise a freshly
    written concept page would not resolve its inbound ``[[Wikilink]]``). ASCII
    lowercase kebab (Karpathy) is a strict subset, so the pre-037 contract is
    unchanged for those inputs.

    ``max_len`` bounds CANDIDATE/concept slugs (default 120 → safe ``<slug>.md``
    filename). Pass ``max_len=None`` for an already-indexed SOURCE-page slug: it is
    a `pages.slug` the indexer produced with no length cap, is not turned into a
    NEW filename here, and must not be length-rejected (else a long-titled PARA
    note would index yet be un-extractable).
    """
    if not _SLUG_RE.match(slug) or slug != slug.lower():
        return False
    return max_len is None or len(slug) <= max_len


def _path_is_absolute(p: Path | str) -> bool:
    """Cross-platform absolute-path detection (M-6).

    `Path.is_absolute()` treats `/foo` as non-absolute on Windows (it's
    drive-relative there) and `C:\\foo` as non-absolute on POSIX. For the
    skill's input-validation gates we want "looks absolute on EITHER
    platform" semantics so the same operator mistake (`--source-page
    /etc/passwd`) produces the same envelope regardless of OS.
    """
    s = str(p)
    if not s:
        return False
    if Path(s).is_absolute():
        return True
    # POSIX-style absolute path on Windows (drive-relative under Windows
    # path rules but operator-intent is clearly "absolute").
    if s.startswith("/") or s.startswith("\\"):
        return True
    # Windows drive prefix on POSIX (e.g. "C:\foo" or "C:/foo").
    if len(s) >= 2 and s[1] == ":" and s[0].isalpha():
        return True
    return False


def _validate_source_hash(value: str) -> str:
    """argparse `type=` validator for `--source-hash`.

    C-1 invariant: case-normalize to lowercase + reject anything that
    isn't exactly 64 hex chars. Without this validator, an upper-cased
    hex pipeline (PowerShell `toupper`, awk transforms) silently
    misroutes to SOURCE_CHANGED_DURING_EXTRACTION, AND the unvalidated
    value lands unescaped in stdout JSON (CWE-117 log-injection vector
    via embedded ANSI/JSON-breaking sequences). Both vectors close by
    forcing the value through this lowercased-hex gate at argparse time.
    """
    normalized = value.lower()
    if not _SOURCE_HASH_RE.match(normalized):
        raise argparse.ArgumentTypeError(
            "--source-hash must be exactly 64 lowercase hex chars "
            "(sha256 hex digest from `prepare`'s envelope)"
        )
    return normalized


def _validate_orchestrator_id(value: str) -> str:
    """argparse `type=` validator for `--orchestrator-id`.

    On regex fail, raises ``argparse.ArgumentTypeError`` so the operator
    sees an argparse-level usage error (exit 2 / SystemExit 2) rather
    than the exit-4 EXTRACTION_PARSE_ERROR envelope.
    """
    if not _ORCHESTRATOR_ID_RE.fullmatch(value):  # fullmatch: `$` alone admits a trailing \n
        raise argparse.ArgumentTypeError(
            f"--orchestrator-id must match regex "
            f"{_ORCHESTRATOR_ID_RE.pattern!r}"
        )
    return value


def _validate_candidates_schema(
    items: list[Any], source_body: str | None = None,
) -> None:
    """Strict-mode validation of the calling-agent's candidates payload.

    v3.1 (003-v3-02) established:
      * **strict-equality on keys** (H-9): rejects extra keys with
        UNKNOWN_FIELD (was: subset check that silently ignored extras).
      * **per-field caps** (H-6): name≤200, definition≤2000,
        source_quote≤500 → FIELD_TOO_LONG.
      * **CWE-117 / CWE-209 invariant**: the raised ExtractionParseError
        carries .error / .field / .reason structured attrs. The offending
        VALUE is NEVER included in any attribute. The apply() caller maps
        these into the JSON envelope without echoing content.

    TASK 064 turns it into an ANTI-GARBAGE gate (see the module docstring):
      * **count bound 0≤N≤25** (G0): an EMPTY array is now VALID — and
        `apply` treats it as SUCCESS. It used to be an exit-4 failure, which
        is what made fabrication the model's cheapest green path.
      * **field floors** (G1/G2): name≥2 CHARS; definition≥4 WORDS;
        source_quote≥4 WORDS → FIELD_TOO_SHORT. (Words, not chars — a char
        floor refused correct terse definitions and taught the model to PAD.)
      * **DEFINITION_IS_QUOTE / DEFINITION_NOT_PROSE** (G1): the definition
        must COMPLEMENT the source, and must be prose we can file unescaped.
      * **ENTITY_TYPE_NOT_ALLOWED** (G4): `person` is refused, with a reason
        that teaches `participants:` rather than inviting a retry as `group`.
      * **INVALID_SLUG_CHARSET** (G8): `_` in a slug is a code symbol tell.
      * **FIELD_QUOTE_NOT_IN_BODY** (G2/G3): MANDATORY whenever `source_body`
        is supplied — there is NO env bypass, and no refusal on this rail may
        name one. `WIKI_EXTRACT_NO_QUOTE_CHECK` is DELETED, not deprecated.
      * **SOURCE_SPAN_OUT_OF_RANGE / SOURCE_SPAN_QUOTE_MISMATCH** (G9): the
        span is verified against the body. **L1 = the file's first line** (the
        opening `---`), because `source_body` is the whole file as read.

    `source_body=None` (a library/test caller that has no body) skips ONLY the
    three body-relative checks. Everything else always runs.
    """
    # L-1 (vdd-multi 2026-05-28): defensive top-level type guard. The
    # apply caller goes through `_load_candidates` which already enforces
    # `isinstance(parsed, list)`, but `_validate_candidates_schema` is a
    # module-level public-ish symbol with other call sites (tests, future
    # library consumers). Reject non-lists here so envelopes stay
    # consistent regardless of entry point.
    if not isinstance(items, list):
        raise ExtractionParseError(
            "candidates payload top-level is not a list",
            error="EXTRACTION_PARSE_ERROR",
            field=None,
            reason=(f"payload is {type(items).__name__}, expected JSON array"),
        )

    # H-2: count bound
    if not (_CANDIDATE_COUNT_MIN <= len(items) <= _CANDIDATE_COUNT_MAX):
        raise ExtractionParseError(
            f"candidates count={len(items)} out of bounds "
            f"[{_CANDIDATE_COUNT_MIN}, {_CANDIDATE_COUNT_MAX}]",
            error="CANDIDATE_COUNT_OUT_OF_BOUNDS",
            field=None,
            reason=(f"count={len(items)} not in "
                    f"[{_CANDIDATE_COUNT_MIN}, {_CANDIDATE_COUNT_MAX}]"),
        )

    # L-1 (vdd-multi 2026-05-28): also type-check the non-capped fields
    # so a `null` slug / span / entity_type produces a clear
    # "not a string" envelope instead of `re.match` on coerced `"None"`.
    _NONCAPPED_STR_FIELDS = ("slug", "entity_type")
    _NONCAPPED_OPTIONAL_STR_FIELDS = ("source_span",)

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ExtractionParseError(
                f"candidate #{idx} not a dict",
                error="EXTRACTION_PARSE_ERROR",
                field=None,
                reason=f"item #{idx} is not a JSON object",
            )

        # H-9: strict on keys — no true extras, no missing REQUIRED ones. `source_span` is
        # now OPTIONAL (see `_OPTIONAL_CANDIDATE_KEYS`): the rail DERIVES it, and a supplied
        # one is only a disambiguation hint. Still allowed, so every existing caller and every
        # fixture keeps working byte-identically.
        extra = item.keys() - _REQUIRED_CANDIDATE_KEYS - _OPTIONAL_CANDIDATE_KEYS
        missing = _REQUIRED_CANDIDATE_KEYS - item.keys()
        if extra:
            offending = sorted(extra)[0]
            raise ExtractionParseError(
                f"candidate #{idx} has unknown key (envelope omits value)",
                error="UNKNOWN_FIELD",
                field=offending,
                reason=f"item #{idx} has unknown key {offending!r} "
                       "(strict mode rejects extras)",
            )
        if missing:
            offending = sorted(missing)[0]
            raise ExtractionParseError(
                f"candidate #{idx} missing keys {sorted(missing)}",
                error="EXTRACTION_PARSE_ERROR",
                field=offending,
                reason=f"item #{idx} missing keys {sorted(missing)}",
            )

        # H-6: per-field caps (length check; offending value NOT echoed).
        for field_name, cap in _FIELD_CAPS.items():
            value = item[field_name]
            if not isinstance(value, str):
                raise ExtractionParseError(
                    f"candidate #{idx} field {field_name!r} not a string",
                    error="EXTRACTION_PARSE_ERROR",
                    field=field_name,
                    reason=(f"item #{idx} field {field_name!r} is "
                            f"{type(value).__name__}, expected str"),
                )
            if len(value) > cap:
                raise ExtractionParseError(
                    f"candidate #{idx} field {field_name!r} exceeds cap",
                    error="FIELD_TOO_LONG",
                    field=field_name,
                    reason=(f"item #{idx} field {field_name!r} length "
                            f"{len(value)} exceeds cap {cap}"),
                )

        # L-1: type-check non-capped string fields first (so `null` slug
        # yields "not a string" instead of `re.match("None")` confusion).
        for field_name in _NONCAPPED_STR_FIELDS:
            value = item[field_name]
            if not isinstance(value, str):
                raise ExtractionParseError(
                    f"candidate #{idx} field {field_name!r} not a string",
                    error="EXTRACTION_PARSE_ERROR",
                    field=field_name,
                    reason=(f"item #{idx} field {field_name!r} is "
                            f"{type(value).__name__}, expected str"),
                )

        # Preserved v2 invariants: slug regex, span regex, entity_type whitelist.
        if not _is_valid_slug(item["slug"]):
            raise ExtractionParseError(
                f"candidate #{idx} slug fails slug validation",
                error="EXTRACTION_PARSE_ERROR",
                field="slug",
                reason=(f"item #{idx} slug must be a lowercase Unicode "
                        "kebab slug (word-chars + hyphens, no dots/seps, "
                        "≤120 chars; preserve-unicode admits Cyrillic/CJK)"),
            )
        # ★ G8 (charset half — the layout-dependent half lives in `_gates.py`).
        # `_SLUG_RE`'s `[\w-]` tail ADMITS `_`, and `preserve-unicode`'s slugify regex
        # (`[^\w\-]`) KEEPS an underscore that is already there — so neither gate stops
        # it. That is how `block_number`, `row_number` and `erc20_ethereum-evt_transfer`
        # became "concepts" in the operator's vault: they are SCHEMA COLUMNS and CODE
        # SYMBOLS, and the underscore is the tell.
        if "_" in item["slug"]:
            raise ExtractionParseError(
                f"candidate #{idx} slug contains an underscore",
                error="INVALID_SLUG_CHARSET",
                field="slug",
                reason=(f"item #{idx} slug contains `_`. Concept slugs use `-` as the "
                        "word separator; no layout slug-strategy emits `_`. A name like "
                        "`block_number` or `row_number` is a schema column or a code "
                        "symbol, not a concept — extract the CONCEPT it belongs to "
                        "(e.g. the table or the window function), or drop it."),
            )
        for field_name in _NONCAPPED_OPTIONAL_STR_FIELDS:
            if field_name in item and not isinstance(item[field_name], str):
                raise ExtractionParseError(
                    f"candidate #{idx} field {field_name!r} is not a string",
                    error="EXTRACTION_PARSE_ERROR",
                    field=field_name,
                    reason=(f"item #{idx} field {field_name!r} is "
                            f"{type(item[field_name]).__name__}, expected str"),
                )

        # A SUPPLIED span must still be well-formed — it is a hint, and a malformed hint is a
        # bug in the caller, not a thing to silently ignore.
        if "source_span" in item and not _SOURCE_SPAN_RE.match(item["source_span"]):
            raise ExtractionParseError(
                f"candidate #{idx} source_span fails Lstart-Lend regex",
                error="EXTRACTION_PARSE_ERROR",
                field="source_span",
                reason=(f"item #{idx} source_span does not match "
                        "^L\\d+-L\\d+$ (Decision-10)"),
            )
        # ★ G4: `person` gets its OWN code and a reason that TEACHES the rule.
        # The generic parse error would say "not in [company, concept, ...]" — true,
        # useless, and it invites the model to retry with `entity_type: group`.
        if item["entity_type"] in _REFUSED_ENTITY_TYPES:
            raise ExtractionParseError(
                f"candidate #{idx} entity_type is refused on this rail",
                error="ENTITY_TYPE_NOT_ALLOWED",
                field="entity_type",
                reason=("a person is not a concept on this rail — a meeting "
                        "attendee belongs in the note's `participants:` "
                        "frontmatter, a cited author in the note body. Drop the "
                        "candidate; do not re-file it under another type."),
            )
        if item["entity_type"] not in _ALLOWED_ENTITY_TYPES:
            raise ExtractionParseError(
                f"candidate #{idx} entity_type not in allowed set",
                error="EXTRACTION_PARSE_ERROR",
                field="entity_type",
                reason=(f"item #{idx} entity_type not in "
                        f"{sorted(_ALLOWED_ENTITY_TYPES)}"),
            )

        # ★ G1: the NAME floor stays a CHARACTER floor — a name is a noun phrase, and
        # `AMM` is a perfectly good one-word name.
        if len(str(item["name"]).strip()) < _NAME_MIN_CHARS:
            raise ExtractionParseError(
                f"candidate #{idx} field 'name' below the floor",
                error="FIELD_TOO_SHORT",
                field="name",
                reason=(f"item #{idx} name is shorter than {_NAME_MIN_CHARS} "
                        f"characters; that is not a concept name."),
            )

        # ★ G1 + G2: the CONTENT floors, counted in WORDS (F8 — a 40-CHAR floor refused
        # «Форк — расхождение цепочки блоков.» and taught the model to PAD; see the
        # `_FIELD_MIN_WORDS` comment for the measurements).
        for field_name, floor in _FIELD_MIN_WORDS.items():
            words = _word_count(str(item[field_name]))
            if words < floor:
                raise ExtractionParseError(
                    f"candidate #{idx} field {field_name!r} below the floor",
                    error="FIELD_TOO_SHORT",
                    field=field_name,
                    reason=(f"item #{idx} field {field_name!r} has {words} word(s); "
                            f"the floor is {floor}. A definition must COMPLEMENT the "
                            f"source — say what the concept IS. A source_quote must be "
                            f"a real verbatim phrase from the body, not a token. "
                            f"Terse is fine; empty is not — do NOT pad to clear this."),
                )

        # ★ G1: DEFINITION_IS_QUOTE. A definition that is a copy of the quote adds
        # NOTHING — the quote already lands in `page_entity_refs`, and the concept
        # page would just restate the sentence the source already says. Zero false
        # positives: nobody wants a page whose body is its own citation.
        if _norm(str(item["definition"])) == _norm(str(item["source_quote"])):
            raise ExtractionParseError(
                f"candidate #{idx} definition is a copy of the source_quote",
                error="DEFINITION_IS_QUOTE",
                field="definition",
                reason=(f"item #{idx} definition is the source_quote restated. The "
                        "quote is the RECEIPT (it is already stored as provenance); "
                        "the definition is what the reader learns. Write what the "
                        "concept IS, in your own words."),
            )

        # ★ G1: DEFINITION_NOT_PROSE — refuse rather than mangle (see the helper).
        if not _definition_is_prose(str(item["definition"])):
            raise ExtractionParseError(
                f"candidate #{idx} definition is not plain prose",
                error="DEFINITION_NOT_PROSE",
                field="definition",
                reason=(f"item #{idx} definition contains a newline, a `[[wikilink]]`, "
                        "a backtick, or a leading markdown marker. It is written into "
                        "the page body verbatim, where those are ESCAPED into visible "
                        "backslash litter. Send ONE plain sentence — no links, no code "
                        "spans, no lists, no headings."),
            )

        # ★ G2 + G3: THE QUOTE RECEIPT. Mandatory, un-bypassable, and the reason NEVER
        # names an env var — `wiki_extract_decisions._validation`: *"an escape hatch on
        # an anti-fabrication check IS the fabrication path, and it gets reached exactly
        # when someone is in a hurry."* The old code read
        # `os.environ.get("WIKI_EXTRACT_NO_QUOTE_CHECK")` as a bare truthiness test — so
        # `=0` and `=false` DISABLED it too — and then PRINTED the bypass into the
        # failure envelope. Both are gone.
        #
        # Raw substring first (the fast path, and the strictest); the NFC + whitespace-
        # collapsed compare is the fallback so a quote copied out of a hard-wrapped
        # source still grounds instead of failing for a reason unrelated to grounding.
        if source_body is not None:
            quote = str(item["source_quote"])
            if (quote not in source_body
                    and _norm(quote) not in _norm(source_body)):
                raise ExtractionParseError(
                    f"candidate #{idx} source_quote not found in body",
                    error="FIELD_QUOTE_NOT_IN_BODY",
                    field="source_quote",
                    reason=(f"item #{idx}: the quote is not verbatim in the source — "
                            "you paraphrased or mis-copied. Re-read the source and "
                            "copy the sentence exactly."),
                )

            # ★ G9: THE SPAN. Shape-validated three times, verified against the body
            # ZERO times — `L9999-L9999` on a 3-line body exited 0 and went straight
            # into `page_entity_refs.line_start/line_end` AS IF IT WERE PROVENANCE.
            #
            # ★ THE LINE ORIGIN, STATED (it was undefined, which is why the old fixtures
            # were wrong and nobody noticed): `source_body` is the WHOLE FILE as read,
            # frontmatter included — it is the same string the quote check grounds
            # against — so **L1 is the file's first line, i.e. the opening `---`.**
            #
            # ★★ F5 (TASK 064 FIX-LOOP) — `split("\n")`, **NEVER** `splitlines()`.
            # `str.splitlines()` ALSO breaks on `\x0b \x0c \x1c \x1d \x1e \x85 U+2028
            # U+2029`. EVERY tool the model counts lines with — the Read tool, `cat -n`,
            # any editor, `wc -l` — breaks on `\n` and nothing else. A FORM FEED (`\x0c`)
            # is a routine PDF→markdown page-break artifact, and `wiki-import` IS this
            # repo's PDF on-ramp: so on exactly the sources this rail is fed, a model that
            # counts CORRECTLY would be refused and only the WRONG span could pass. The
            # gate would have been actively teaching the wrong line numbers.
            # ★★ THE SPAN IS DERIVED, NOT TRUSTED — TASK 066.
            #
            # The quote is ALREADY proven verbatim in the body two checks above
            # (`FIELD_QUOTE_NOT_IN_BODY`). Its line range is therefore a COMPUTATION. The
            # model's span — which it got wrong 29% of the time, because we were asking a
            # language model to count lines — is downgraded to a HINT, used only to pick
            # between multiple occurrences of the same quote.
            #
            # This is STRICTLY STRONGER than the check it replaces: a derived span cannot be
            # fabricated. The `L9999-L9999`-on-a-3-line-body attack G9 was built for is not
            # detected here — it is UNREACHABLE.
            item["source_span"] = derive_source_span(
                source_body, quote, hint=item.get("source_span"))

            # A SELF-CHECK on our own derivation (the G1 discipline: gate your own write).
            # It cannot fire on correct code — which is exactly why it is cheap to keep, and
            # why a mutation of `derive_source_span` is caught HERE rather than in the vault.
            lines = source_body.split("\n")
            start, end = _parse_source_span(str(item["source_span"]))
            span_text = "\n".join(lines[start - 1:end])
            if not (1 <= start <= end <= len(lines)) or _norm(quote) not in _norm(span_text):
                raise ExtractionParseError(          # pragma: no cover - a derivation bug
                    f"candidate #{idx}: the DERIVED span does not contain its own quote",
                    error="SOURCE_SPAN_QUOTE_MISMATCH",
                    field="source_span",
                    reason=(f"item #{idx}: `derive_source_span` produced L{start}-L{end}, "
                            f"which does not contain the quote it was derived FROM. This is "
                            f"a bug in the rail, not in the candidate."),
                )


def derive_source_span(
    source_body: str, quote: str, *, hint: str | None = None
) -> str:
    """★ THE SPAN, COMPUTED FROM THE QUOTE (TASK 066). `L<start>-L<end>`, 1-indexed from the
    file's FIRST line — the opening `---` of the frontmatter is L1.

    Why this exists: the weak-model harness measured 56 candidates from 33 fresh Haiku
    contexts. **The quote was verbatim 56/56 (100%). The model's span was right 40/56 (71%).**
    Nine of the thirteen failing runs were a bad span — the largest single failure class,
    hitting 8 of 11 fixtures. *We were asking a language model to do arithmetic on line
    numbers.* The quote it copies; the span it must COUNT — and counting is not what it is for.

    ★ `split("\n")`, NEVER `splitlines()` (F5, TASK 064). `splitlines()` also breaks on
    `\x0b \x0c \x1c \x1d \x1e \x85 U+2028 U+2029`. Every tool a human or a model counts
    lines with — the Read tool, `cat -n`, an editor, `wc -l` — breaks on `\n` and nothing
    else. A FORM FEED is a routine PDF→markdown artifact, and `wiki-import` IS this repo's PDF
    on-ramp: on exactly the sources this rail is fed, `splitlines()` would compute a span that
    disagrees with every tool the operator can check it with.

    `hint` (the model's own span, now optional) is used for ONE thing: when the same quote
    occurs more than once in the body, it picks which occurrence. With no usable hint the
    FIRST occurrence wins — which is still a true provenance pointer, because the quote really
    is there.
    """
    # ★ THE OFFSETS MUST BE IN THE **ORIGINAL** BODY — and the first draft of this function
    # got that wrong, in the one way the self-check below was written to catch.
    #
    # `_norm` COLLAPSES WHITESPACE (`\s+` → one space). So an offset into `_norm(body)` cannot
    # be turned back into a LINE NUMBER — the newlines are gone. The first draft counted `\n`
    # in the normalised text, found none, and derived `L1-L1` for every candidate. The
    # self-check caught it on the first test run, which is exactly its job: **gate your own
    # write.**
    #
    # So: search the ORIGINAL (NFC + casefold, whitespace INTACT) with a pattern that tolerates
    # the whitespace differences `_norm` was tolerating — one `\s+` between the quote's tokens.
    # The match offsets are then real, and the line count is real.
    body_o = unicodedata.normalize("NFC", source_body).casefold()
    tokens = _norm(quote).split(" ")
    if not tokens or tokens == [""]:                 # pragma: no cover - a >=4-word floor
        raise ExtractionParseError(
            "the quote is empty",
            error="FIELD_QUOTE_NOT_IN_BODY", field="source_quote",
            reason="derive_source_span called on an empty quote",
        )
    pattern = re.compile(r"\s+".join(re.escape(tok) for tok in tokens))

    matches = list(pattern.finditer(body_o))
    if not matches:                                  # pragma: no cover - FIELD_QUOTE_NOT_IN_BODY
        raise ExtractionParseError(
            "the quote is not in the body",
            error="FIELD_QUOTE_NOT_IN_BODY", field="source_quote",
            reason="derive_source_span called on a quote that is not verbatim in the body",
        )

    def _span_of(m: "re.Match[str]") -> tuple[int, int]:
        # ★ split("\n"), NEVER splitlines() — see the docstring. Counting `\n` is the same
        # rule, expressed the same way.
        start = body_o.count("\n", 0, m.start()) + 1
        end = start + body_o.count("\n", m.start(), m.end())
        return start, end

    chosen = matches[0]
    if len(matches) > 1 and hint and _SOURCE_SPAN_RE.match(hint):
        h_start, h_end = _parse_source_span(hint)
        for m in matches:
            s, e = _span_of(m)
            if h_start <= s and e <= h_end:
                chosen = m
                break

    start, end = _span_of(chosen)
    return f"L{start}-L{end}"


def classify_candidates(
    llm_results: list[dict[str, Any]],
    known_slugs: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split LLM-extracted candidates into (create_list, mention_list).

    Each item is shallow-copied and annotated with ``action="create"`` or
    ``action="mention"`` (R-34) so 003-10 manifest builder and 003-08 refs
    upsert can dispatch off a single field. Defensive copy means callers
    can't surprise-mutate the LLM output through the classifier's return.
    """
    create_list: list[dict[str, Any]] = []
    mention_list: list[dict[str, Any]] = []
    for item in llm_results:
        annotated = {**item}
        if item["slug"] in known_slugs:
            annotated["action"] = "mention"
            mention_list.append(annotated)
        else:
            annotated["action"] = "create"
            create_list.append(annotated)
    return create_list, mention_list


# ★ THE INJECTION PREFIXES — AND ONLY THOSE. A markdown heading is `# ` (marker + SPACE); a
# YAML sequence item is `- ` (marker + SPACE); a frontmatter delimiter is `---`. A BARE marker
# glued to a word is none of them — `#DeFi` is not a heading, `-EV` is not a list item, and
# YAML parses `-EV` as the plain scalar it is.
#
# ★ The old rule was `name.lstrip("#").lstrip("-")`, which TRUNCATED rather than refused:
# the concept «-EV» (NEGATIVE expected value) was filed as «EV» — its own semantic opposite,
# in the H1, in the frontmatter, and in the entities row, at exit 0, with no warning and no
# lint issue. Stripping a character that carries meaning is not sanitisation; it is silent
# corruption, and it is worse than the injection it was guarding against.
_NAME_INJECTION_PREFIX = re.compile(r"^(?:[#>]+[ \t]|[-*+][ \t]|-{3,})+")


def _sanitize_name(name: str) -> str:
    """Sanitize a concept name for safe embedding into the H1 + frontmatter.

    Strips a leading markdown-heading / list-item / frontmatter-delimiter PREFIX — the
    sequences that are actually structural (`# `, `> `, `- `, `---`) — then enforces the
    `_NAME_ALLOWLIST` regex. A marker glued to a word (`-EV`, `#DeFi`) is CONTENT and is
    preserved verbatim. Failure of the allowlist raises
    ``ExtractionParseError(error="INVALID_NAME_FORMAT")``.
    """
    stripped = _NAME_INJECTION_PREFIX.sub("", name).strip()
    if not _NAME_ALLOWLIST.match(stripped):
        raise ExtractionParseError(
            "candidate name fails sanitization allowlist",
            error="INVALID_NAME_FORMAT",
            field="name",
            reason=("name contains disallowed characters after stripping a leading "
                    "markdown/YAML structural prefix and trimming whitespace"),
        )
    return stripped


def _sanitize_definition(definition: str) -> str:
    """Sanitize a candidate's definition for safe embedding in concept body.

    Delegates to the shared `_sanitize_markdown_text` (H-4 v3.2 — text-
    only allowlist replacing v3.1's denylist).
    """
    return _sanitize_markdown_text(definition)


def _parse_source_span(span: str) -> tuple[int, int]:
    """Parse Decision-10 ``"Lstart-Lend"`` format into (line_start, line_end).

    Raises ``ExtractionParseError`` on malformed format or inverted range.
    """
    m = _SPAN_REGEX.match(span)
    if not m:
        raise ExtractionParseError(
            f"Malformed source_span (expected 'L<start>-L<end>'): {span!r}"
        )
    start, end = int(m.group(1)), int(m.group(2))
    if end < start:
        raise ExtractionParseError(f"source_span end before start: {span!r}")
    return start, end


def _preflight_sanitize(candidates: list[Any]) -> None:
    """M-4: run per-candidate sanitizers in a dry pass.

    Raises `ExtractionParseError` on the first failure. After this
    function returns cleanly, the subsequent `write_concept_page` loop
    is guaranteed to succeed for the same inputs (same sanitizers run
    over the same data → same outcome). Closes the partial-commit
    window where item #N's sanitization failure left items #0..N-1
    written to disk.
    """
    for idx, cand in enumerate(candidates):
        try:
            _sanitize_name(str(cand["name"]))
            _sanitize_definition(str(cand["definition"]))
            _sanitize_markdown_text(str(cand["source_quote"]))
            if not _SOURCE_SPAN_RE.match(str(cand["source_span"])):
                raise ExtractionParseError(
                    f"candidate #{idx} source_span fails preflight regex",
                    error="INVALID_SOURCE_SPAN",
                    field="source_span",
                    reason=("source_span must match ^L\\d+-L\\d+$ "
                            "before embedding into _concepts body"),
                )
        except ExtractionParseError:
            raise
