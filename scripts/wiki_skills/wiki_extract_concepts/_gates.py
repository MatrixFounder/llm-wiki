"""The LAYOUT-AWARE gates for wiki-extract-concepts (TASK 064).

Why this file exists at all: `_validation.py` is a PURE leaf whose dependency rule is
stdlib + `._errors` + `_common`. That rule is what makes *"a contract violation writes
ZERO files"* true by CONSTRUCTION rather than by care — a validator that cannot reach
the DB or the layout engine needs no audit to prove it didn't. G5/G8/G10 need the
layout (and G5 needs the vault's known slugs), so they get their own leaf rather than
weakening that rule.

  G5  near-duplicate — **ADVISORY, NEVER A REFUSAL** (see `near_duplicate_warnings`).
  G8  `SLUG_NOT_DERIVED_FROM_NAME` — the slug is the LAYOUT'S to derive. Runs on the
      CREATE list only, and only when the derivation is well-defined.
  G10 `LAYOUT_CANNOT_INDEX_CONCEPTS` — refuse to write pages the layout cannot SEE.
      TASK 063's G4 lesson, unrepaired here until now.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from slugify import slugify

from scripts.wiki_index.layout import CONCEPTS_SUBDIR
from scripts.wiki_index.layout_config import (
    LayoutConfig,
    _apply_slug_strategy,
    derive_discovered_page,
)

from ._errors import ExtractionParseError
from ._validation import _is_valid_slug

# ★★ G5 — THE CUTOFF, AND WHY IT NO LONGER REFUSES ANYTHING (TASK 064 FIX-LOOP).
#
# The first cut of this gate REFUSED a create whose slug scored ≥ 0.88 against a known
# slug, and the refusal instructed the model to re-file the candidate as a MENTION of the
# near-match. It was calibrated on SIX pairs. Re-measured on a realistic population, the
# bands COMPLETELY OVERLAP — there is no scalar cutoff, at any value:
#
#   type-i-error       / type-ii-error          0.960   ← a DIFFERENT concept
#   supervised-learning/ unsupervised-learning  0.950   ← a DIFFERENT concept
#   централизация      / децентрализация        0.941   ← the OPPOSITE concept
#   precision          / recision               0.941
#   serialization      / deserialization        0.929   ← the INVERSE operation
#   бессрочный-фьючерс / бессрочные-фьючерсы    0.927   ← the REAL duplicate it was built for
#   micro-service      / macro-service          0.923
#   шифрование         / дешифрование           0.917   ← the INVERSE operation
#   ликвидность        / неликвидность          0.909   ← the NEGATION
#   uniswap-v2         / uniswap-v3             0.900   ← a DIFFERENT version
#   llama-3-1          / llama-3-2              0.889   ← a DIFFERENT model
#   python-2           / python-3               0.875   ← one nudge below the cutoff
#
# ★ THE GATE IS ANTI-CORRELATED WITH MEANING. It scores `type-i-error`/`type-ii-error`
# (0.960) as a HARDER duplicate than the real live pair it exists for (0.927). Structural
# law: a 2-char negating prefix (`de`/`не`) on any base ≥ 8 chars crosses 0.88 — so the
# metric systematically rates ANTONYMS as duplicates.
#
# And the refusal was BATCH-FATAL and CORRUPTING: three good new concepts lost to one
# false positive, and a compliant model told to file `decentralized-exchange` as a MENTION
# of `centralized-exchange` writes a FALSIFIED provenance receipt into `page_entity_refs`
# at exit 0. **An anti-duplicate gate that manufactures false knowledge is worse than no
# gate.**
#
# So it is ADVISORY: it emits `warnings[]` in the exit-0 envelope, names the similar
# slugs, and lets the MODEL decide. The real defence against a duplicate is STEP 3 of the
# SKILL (reuse the exact known slug from `known_concepts`) — a judgement, made by the only
# component that can tell `децентрализация` from `централизация`. The SKILL's honesty
# ledger says exactly this.
NEAR_DUP_CUTOFF = 0.88


@lru_cache(maxsize=8192)
def _dup_key(slug: str) -> str:
    """The comparison key: NFC, then TRANSLITERATED to ASCII.

    Transliteration is the whole trick. `виталик-бутерин` and `vitalik-buterin` are
    100% dissimilar as raw strings — no character-ratio metric will ever relate them —
    but they are the SAME KEY once transliterated, and they are the operator's most
    expensive live split: two pages, two entity rows, one person, and every backlink
    landing on whichever the writer happened to type.

    ★ MEMOISED — and that is a PERF fix, not a style choice. `build_dup_keys` is called
    from `_apply_write`, which runs **once per BATCH ENTRY**; the known-slug set is
    essentially the same 720 slugs every time, so an un-cached `slugify()` sweep is re-paid
    in full per source. `_dup_key` is a PURE function of its argument (no vault, no config,
    no clock), so caching it is safe by construction and hoists the sweep out of the
    per-entry loop without threading yet another shared set through five call frames.
    """
    return slugify(unicodedata.normalize("NFC", slug), lowercase=True, separator="-")


def build_dup_keys(known_slugs: set[str]) -> dict[str, str]:
    """`{known_slug: _dup_key(known_slug)}` — the slugify sweep, paid ONCE.

    ★ PERF (TASK 064 FIX-LOOP). Measured on a synthetic 720-page vault, the first cut cost
    **0.212 s per source** and RE-PAID IT PER ENTRY on the batch path. Three separate
    defects, all fixed:

      1. `slugify()` was called PER PAIR → now once per KNOWN slug (this function), and
         `_dup_key` is `lru_cache`d on top, so across batch entries it is paid ONCE
         PER PROCESS rather than once per source;
      2. `SequenceMatcher.ratio()` was computed TWICE per pair (once to filter, once to
         score) → now ONCE, behind an inlined `real_quick_ratio` length bound that discards
         most of the corpus before the O(n·m) matcher is ever constructed;
      3. both loops were nested inside the per-candidate scan → hoisted.

    Now ~15 ms per source, of which the slugify sweep is ~0. What REMAINS per-source is the
    scoring loop itself, and that is irreducible: it depends on the candidates, which differ
    per source. It is not a bug that it runs per source — it is the work.
    """
    return {s: _dup_key(s) for s in known_slugs}


def near_duplicate_warnings(
    create_list: list[dict[str, Any]], known_keys: dict[str, str],
) -> list[dict[str, Any]]:
    """★ G5 — ADVISE, NEVER REFUSE. Returns `warnings[]`; raises NOTHING.

    ★ THIS FUNCTION MUST NOT ACQUIRE A `raise`. Read the `NEAR_DUP_CUTOFF` comment first:
    the metric rates ANTONYMS (`централизация`/`децентрализация`, 0.941) as harder
    duplicates than the real live split it was built for (0.927). Any refusal built on it
    blocks correct work, and any instruction to "re-file as a mention of the near-match"
    writes a FALSIFIED provenance receipt for a concept the source never discussed.

    The advisory names the similar slugs and states BOTH branches, so the model — the only
    component that can tell an inverse operation from a plural — decides:

      * SAME concept  → re-emit with the existing slug ⇒ `classify_candidates` files a
        `mention` and the existing page gains a source in its `BEGIN-AUTO:mentions` ledger.
      * DIFFERENT concept → ignore it and file the new page.

    ⚠️ An EXACT match is skipped: a candidate whose slug EQUALS a known slug but still
    classified `create` is the TASK-053/R3 GHOST ROW (entity row alive, page deleted). It
    is a self-heal, not a duplicate — and self-similarity is 1.000, which would have made
    the advisory scream at the very repair the classifier just asked for.
    """
    warnings: list[dict[str, Any]] = []
    for cand in create_list:
        slug = str(cand["slug"])
        key = _dup_key(slug)
        klen = len(key)
        scored: list[tuple[float, str]] = []
        for known, kkey in known_keys.items():
            if known == slug:
                continue  # exact ⇒ ghost-row self-heal, NOT a near-duplicate
            # `real_quick_ratio`'s bound, inlined: ratio ≤ 2·min(len)/(len1+len2). A pure
            # length test, no matching — it discards most of the 720-entry corpus before
            # the O(n·m) matcher is ever constructed.
            total = klen + len(kkey)
            if total and 2.0 * min(klen, len(kkey)) / total < NEAR_DUP_CUTOFF:
                continue
            ratio = difflib.SequenceMatcher(None, key, kkey).ratio()  # ONE ratio per pair
            if ratio >= NEAR_DUP_CUTOFF:
                scored.append((ratio, known))
        if scored:
            scored.sort(reverse=True)
            warnings.append({
                "code": "NEAR_DUPLICATE_SLUG",
                "slug": slug,
                "nearest": [k for _r, k in scored],
                "similarity": round(scored[0][0], 3),
                "advice": (
                    "these existing slugs look similar to yours. If yours is the SAME "
                    "concept, re-emit it with the existing slug so it files as a mention "
                    "of the page that is already there. If it is a DIFFERENT concept "
                    "(an inverse, a negation, a different version — `serialization` vs "
                    "`deserialization` scores 0.929 here), ignore this: string similarity "
                    "cannot tell those apart, and you can."),
            })
    return warnings


def _normalise_derived_slug(derived: str) -> str | None:
    """The layout's derived slug, pushed through the SAME rules every OTHER gate enforces
    — or `None` when the derivation is DEGENERATE.

    ★ F4 (TASK 064 FIX-LOOP) — G8 AND `INVALID_SLUG_CHARSET` WERE MUTUALLY UNSATISFIABLE.
    `preserve-unicode`'s slugify regex is `[^\\w\\-]` and `\\w` INCLUDES `_`, so
    `_apply_slug_strategy("self_attention", "preserve-unicode")` returns `self_attention`
    verbatim. G8 demanded EXACTLY that slug; the charset gate refuses any `_`. **No string
    satisfied both**, the two refusal reasons contradicted each other, and a model obeying
    them loops forever. So the derived slug is normalised through the charset rule (`_` →
    `-`) BEFORE it is compared or handed back.

    Degenerate derivations return `None` and the caller SKIPS the gate entirely — G8 must
    never demand a slug that another gate would refuse:
      * `_apply_slug_strategy("...", "transliterate")` → `""` — an empty slug is not a
        demand anyone can satisfy;
      * anything that still fails `_is_valid_slug` after normalisation.
    (The OTHER degeneracy — two DISTINCT names collapsing onto ONE slug, e.g. `C++` and
    `C#` both → `c`, which G6 would then refuse as an in-batch collision — is detected in
    `check_slugs_derived_from_names`, where the whole batch is visible.)
    """
    s = re.sub(r"-{2,}", "-", derived.replace("_", "-")).strip("-").lower()
    return s if s and _is_valid_slug(s) else None


def derive_concept_slug(name: str, slug_strategy: str) -> str | None:
    """The slug the LAYOUT would derive from this name — or `None` when the layout
    declares no name→slug function, or when the derivation is degenerate.

    ★ THE `identity` CARVE-OUT, AND WHY IT IS NOT A HOLE.

    `_apply_slug_strategy` maps a FILE STEM to a slug. Under `identity` (karpathy) it
    is the IDENTITY FUNCTION: the stem IS the slug, verbatim. So for karpathy there is
    no name→slug derivation to check a candidate against — `_apply_slug_strategy(
    "Sharpe Ratio", "identity")` is `"Sharpe Ratio"`, which is not a slug at all, and
    asserting `slug == that` would refuse EVERY karpathy candidate ever written. The
    layout's own statement is "whatever the filename says, that is the slug"; a
    candidate's slug IS its filename-to-be, so it is self-consistent by definition and
    there is nothing here to verify. We return `None` and the caller skips the gate.

    That is not the hole it looks like. The bug G8 exists to kill is a WIKILINK
    RESOLUTION bug on the SLUGIFYING layouts: on the operator's `obsidian-personal`
    vault (`preserve-unicode`, Russian), a model obeying the SKILL's (ASCII-only, and
    WRONG) slug regex emits `vitalik-buterin` for «Виталик Бутерин», while every
    inbound `[[Виталик Бутерин]]` in the vault resolves — through this same function —
    to `виталик-бутерин`. The page is written and NOTHING EVER LINKS TO IT. That is
    exactly the live `виталик-бутерин` / `vitalik-buterin` pair. On karpathy, links to
    concepts are written AS the slug, so the failure mode does not arise.
    """
    if not layout_derives_slugs(slug_strategy):
        return None
    return _normalise_derived_slug(_apply_slug_strategy(name, slug_strategy))


# ★ DF-064-3 — THE SENTINEL WAS ANSWERING TWO DIFFERENT QUESTIONS, AND A CALLER CONFLATED THEM.
#
# `derive_concept_slug` returns `None` for TWO unrelated reasons: *"this layout declares no
# name→slug function"* (identity) and *"the derivation is degenerate"*. `wiki-import`'s
# `derive_candidates` read the first as the second and SKIPPED the candidate as `invalid-slug`
# — so a caller passing `layout.slug_strategy` straight through would file **zero concepts on
# every karpathy vault, at exit 0**, reporting `invalid-slug` for perfectly valid names.
#
# It never fired only because `wiki_import_article._mint_strategy` happens to substitute
# `preserve-unicode` for `identity` at the call site. That is a fix living in the caller —
# i.e. a fix the NEXT caller does not inherit.
#
# So the two questions are now two functions, and neither can be mistaken for the other:
#
#   layout_derives_slugs()  — "is there a rule to CHECK a slug against?"  → the GATE asks this
#   mint_concept_slug()     — "give me a slug I can USE"                  → the PRODUCER asks this
#
# A gate that mints, or a producer that skips because there is no rule, is now a type error in
# spirit even where Python will not catch it.


def layout_derives_slugs(slug_strategy: str) -> bool:
    """Does this layout define a NAME → SLUG function at all?

    `False` for `identity` alone: `_apply_slug_strategy` maps a file **stem** to a slug, and
    under `identity` that is the identity function — the stem IS the slug. There is no rule to
    check a candidate's slug against, and `check_slugs_derived_from_names` must skip.

    **`False` does NOT mean "this name has no valid slug".** It means "the layout has no
    opinion about it" — the producer still mints one (see :func:`mint_concept_slug`).
    """
    return slug_strategy != "identity"


def mint_concept_slug(name: str, slug_strategy: str) -> str | None:
    """A slug a concept page can actually be FILED under — for the PRODUCER, never the gate.

    Unlike :func:`derive_concept_slug`, this never returns `None` merely because the layout
    declares no derivation. On `identity` it mints in the `preserve-unicode` keyspace, which is
    what `wiki_import_article._mint_strategy` already reasons its way to: `identity` preserves
    source-FILENAME case and is therefore not mint-valid, while `preserve-unicode` round-trips
    the already-lowercase `<slug>.md` stems wiki-import writes (karpathy byte-identity).

    `None` here means one thing only: **the derivation is degenerate** (empty, or still not a
    valid slug after normalisation) — a genuine `invalid-slug`.
    """
    strategy = slug_strategy if layout_derives_slugs(slug_strategy) else "preserve-unicode"
    return _normalise_derived_slug(_apply_slug_strategy(name, strategy))


def check_slugs_derived_from_names(
    candidates: list[dict[str, Any]], config: LayoutConfig,
) -> None:
    """★ G8 — the slug is DERIVED from the name BY THE LAYOUT, never chosen by the model.

    ★★ RUN THIS ON THE **CREATE LIST ONLY**, AFTER CLASSIFICATION (F3, TASK 064 FIX-LOOP).
    The first cut ran it in `_apply_validate`, over EVERY candidate — including the ones
    that are `mention`s of pages that ALREADY EXIST. Consequence: any existing page whose
    slug is not exactly `slugify(name)` — **every acronym page** (`amm`, `wal`, `pos`,
    `nft`, `dex`), every hand-authored page, every page written before TASK 064 — could
    never be MENTIONED again. And the prescribed repair MANUFACTURED A DUPLICATE: told to
    re-emit `amm` as `автоматический-маркет-мейкер`, a compliant model does so; that slug
    is unknown, so it classifies `create`, the near-dup advisory scores it 0.188 against
    `amm` and says nothing — **and a second page for AMM is written.** The gate is only
    meaningful for a slug that does not exist yet; the caller filters accordingly.

    The violation carries the DERIVED slug so the model can simply re-send it. That is
    model output (its own name, run through a pure function), not source content — no
    CWE-209 concern.
    """
    derived_by_index: dict[int, str] = {}
    for i, cand in enumerate(candidates):
        derived = derive_concept_slug(str(cand["name"]), config.slug_strategy)
        if derived is None:
            continue  # no name→slug function (identity), or a degenerate derivation
        derived_by_index[i] = derived

    # ★ F4 (part 2) — the DEGENERATE COLLAPSE. `_apply_slug_strategy("C++", "transliterate")`
    # and `..."C#"...` are BOTH `"c"`. Demanding both candidates take slug `c` is demanding
    # an in-batch collision that G6 refuses in the very same pass — two gates, contradictory
    # orders, and a model that cannot satisfy either. When a derived slug is claimed by more
    # than one DISTINCT name, the derivation carries no information: skip those candidates.
    names_per_derived: dict[str, set[str]] = {}
    for i, derived in derived_by_index.items():
        names_per_derived.setdefault(derived, set()).add(str(candidates[i]["name"]))

    violations: list[dict[str, Any]] = []
    for i, derived in derived_by_index.items():
        if len(names_per_derived[derived]) > 1:
            continue  # degenerate: the layout collapses distinct names onto one slug
        if str(candidates[i]["slug"]) != derived:
            violations.append(
                {"slug": str(candidates[i]["slug"]), "derived_slug": derived})
    if violations:
        raise ExtractionParseError(
            f"{len(violations)} candidate slug(s) not derived from their name",
            error="SLUG_NOT_DERIVED_FROM_NAME",
            field="slug",
            reason=(f"this vault's layout derives a concept's slug from its NAME "
                    f"(slug_strategy: {config.slug_strategy}). Your slug is not what "
                    f"that derivation produces, so every inbound `[[Name]]` wikilink "
                    f"would resolve to a DIFFERENT slug and the page you filed would "
                    f"be unreachable. Re-emit each candidate with the `derived_slug` "
                    f"given here — or change the `name` if the slug is the one you "
                    f"meant."),
            violations=violations,
        )


def concepts_dir_for_source(
    source_path: Path, vault_root: Path, config: LayoutConfig,
) -> Path:
    """The `_concepts/` dir a page extracted from `source_path` is filed into.

    ONE definition, used by BOTH the G10 preflight and the write path — because a
    preflight that checks a different directory than the writer uses is not a
    preflight. (TASK 040 / ADR-007: the source-nesting subdir is CONFIG, not a fork.
    karpathy nests the note under `_sources/`, so its `_concepts/` sibling hangs off
    `parent.parent`; PARA layouts keep the note in its own folder.)
    """
    sub = config.write.source_subdir
    if sub and source_path.parent.name == sub:
        return source_path.parent.parent / CONCEPTS_SUBDIR
    return source_path.parent / CONCEPTS_SUBDIR


def layout_indexes_concepts(
    config: LayoutConfig, vault_root: Path, concepts_dir: Path,
) -> bool:
    """★ G10 — would a `_concepts/<slug>.md` filed here actually be INDEXED?

    Two conjuncts, and BOTH are required:
      1. the layout maps a `concept` type at all (else `UnmappedTypeError` at reindex —
         the page is silently DROPPED);
      2. the layout's READ GLOBS reach the dir we are about to write into (else
         `iter_pages` never discovers it).

    ★ A PAGE THE WALKER CANNOT SEE IS A PAGE `wiki-lint` IS *STRUCTURALLY INCAPABLE* OF
    REPORTING. `apply` writes to a hardcoded `_concepts` dir on EVERY layout — including
    `dev-project`, which has neither conjunct. The pages are written, never indexed,
    never linted, and raise nothing. Invisible pages. Refusing costs the operator one
    message; not refusing costs them a directory of files they will never find again.

    Behaviourally equivalent to `wiki_import_article.__init__._layout_indexes_concepts`
    (which already refuses exactly this on the construct path). NOT imported from it:
    that would make two skills import each other (`wiki_import_article` already imports
    this package's `_validation`), and a private module of a sibling skill is not an API
    — Decision-16. The equivalence is PINNED by a test rather than by a comment.
    """
    if "concept" not in config.type_mapping:
        return False
    probe = concepts_dir / "concept-probe.md"  # hypothetical — never written
    return derive_discovered_page(probe, vault_root, config) is not None
