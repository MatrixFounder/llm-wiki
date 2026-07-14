"""Candidate schema, the anti-fabrication mechanisms, slugs, G1 and G2 (TASK 063).

PURE VALIDATION — no repo, no filesystem writes, no `emit`. That is not a style
preference: it is what makes *"a contract violation writes ZERO files"* true BY
CONSTRUCTION rather than by care. A validator that COULD touch the DB would have to
be audited for not doing so; one that cannot reach it needs no audit.

The three anti-fabrication mechanisms (R-063-7) live here, and they are MECHANISMS,
not prompt wording:

  1. `CANDIDATE_COUNT_MIN = 0` — an empty set is SUCCESS. The precedent
     (`wiki_extract_concepts`) uses 1; cloning it would make "this note has no
     decisions" an exit-4 FAILURE, and the model's cheapest route to a green run
     would be to invent one.
  2. A MANDATORY verbatim `source_quote` that must occur in the source body. A
     fabricated decision has no quote to point at, so fabrication becomes
     mechanically expensive rather than merely discouraged.
  3. NO `WIKI_EXTRACT_NO_QUOTE_CHECK` ESCAPE. The precedent honours that env var.
     This rail does not — an escape hatch on an anti-fabrication check IS the
     fabrication path, and it gets reached exactly when someone is in a hurry.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from scripts.wiki_index.layout_config import LayoutConfig, _apply_slug_strategy
from scripts.wiki_source.parsing import extract_refs

from ._errors import ExtractionParseError

# ★ ZERO. See the module docstring. Do not "restore parity" with the precedent's 1.
CANDIDATE_COUNT_MIN = 0
CANDIDATE_COUNT_MAX = 200

# Overflow REFUSES, never truncates (R-063-11). Silent truncation would drop the last
# decisions in a batch without a word — this task's own disease.
CANDIDATES_MAX_BYTES = 512 * 1024
FIELD_CAPS: dict[str, int] = {
    "title": 300,
    "status": 60,
    "date": 32,
    "body": 20_000,
    "source_quote": 2_000,
}

REQUIRED_KEYS = frozenset({"class", "title", "status", "body", "source_quote"})
OPTIONAL_KEYS = frozenset({"date", "edges"})
KNOWN_KEYS = REQUIRED_KEYS | OPTIONAL_KEYS

# The SAME slug regex the concepts rail uses. DUPLICATED rather than cross-imported —
# a private module of a sibling skill is not an API, and Decision-16 keeps the skills
# uncoupled. The duplication is GATED: `test_slug_regex_matches_the_house_precedent`
# pins the two patterns EQUAL, so this copy cannot quietly weaken into a laxer gate.
SLUG_RE = re.compile(r"^[^\W_][\w-]*\Z", re.UNICODE)
SLUG_MAX_LEN = 120


def is_valid_slug(slug: str) -> bool:
    """Traversal-safe, Unicode-aware slug gate. `../../etc/passwd` is REFUSED, never
    NORMALISED: a candidate is model output about untrusted text — two layers of
    untrust — and normalising a traversal is how you end up writing outside the vault
    while believing you sanitised it."""
    return bool(slug) and len(slug) <= SLUG_MAX_LEN and bool(SLUG_RE.match(slug))


def _norm(text: str) -> str:
    """NFC + whitespace collapse — the normalisation applied to BOTH sides of the
    quote check, so a quote that differs only in line wrapping or in a
    combining-accent encoding still grounds."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def has_yaml_breakout(value: str) -> bool:
    """★ THE FRONTMATTER-BREAKOUT GUARD (H-6).

    A field that lands in YAML (`status:`, `title:`, `date:`) containing a line that
    is exactly `---` CLOSES the frontmatter block early: everything after it becomes
    injected markdown, and anything before it, injected YAML. The input is an
    untrusted transcript, so this is reachable by saying the right sentence in a
    meeting.

    Control characters are refused for the same reason (CWE-117) — they corrupt the
    document and every log line that later quotes it."""
    if any(ch < " " and ch not in "\n\t" for ch in value):
        return True
    return any(line.strip() in {"---", "..."} for line in value.splitlines())


def validate_candidates_schema(
    candidates: Any, *, source_body: str, roster: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Strict schema + the anti-fabrication mechanisms. Raises `ExtractionParseError`
    (exit 4) carrying **ALL** violations — never just the first.

    All-at-once is not politeness. A validator that stops at the first error makes
    the caller iterate BLIND: it repairs one thing, re-runs, meets the next — and a
    model repairing blind starts GUESSING what else might be wrong. The payload is
    cheap; the round-trip is not.
    """
    if not isinstance(candidates, list):
        raise ExtractionParseError(
            "candidates payload must be a JSON list",
            error="EXTRACTION_PARSE_ERROR", reason="NOT_A_LIST")

    if not (CANDIDATE_COUNT_MIN <= len(candidates) <= CANDIDATE_COUNT_MAX):
        raise ExtractionParseError(
            f"candidate count {len(candidates)} outside "
            f"[{CANDIDATE_COUNT_MIN}, {CANDIDATE_COUNT_MAX}]",
            error="CANDIDATES_TOO_LARGE", reason="COUNT_OUT_OF_BOUNDS")

    body_norm = _norm(source_body)
    violations: list[dict[str, Any]] = []

    for i, cand in enumerate(candidates):
        if not isinstance(cand, dict):
            violations.append({"index": i, "kind": "shape",
                               "detail": "candidate is not an object"})
            continue

        unknown = sorted(set(cand) - KNOWN_KEYS)
        if unknown:
            # A misspelled `sorce_quote` must NOT silently disable grounding. Strict
            # is what keeps mechanism 2 a mechanism instead of a suggestion.
            violations.append({"index": i, "kind": "unknown_field",
                               "detail": f"unknown field(s): {unknown}"})
        missing = sorted(REQUIRED_KEYS - set(cand))
        if missing:
            violations.append({"index": i, "kind": "missing_field",
                               "detail": f"missing required field(s): {missing}"})
            continue

        for key, cap in FIELD_CAPS.items():
            value = cand.get(key)
            if isinstance(value, str) and len(value) > cap:
                violations.append({"index": i, "kind": "field_too_long",
                                   "detail": f"`{key}` exceeds {cap} chars"})

        malformed = False
        for key in sorted(REQUIRED_KEYS):
            value = cand.get(key)
            if not isinstance(value, str) or not value.strip():
                violations.append({"index": i, "kind": "shape",
                                   "detail": f"`{key}` must be a non-empty string"})
                malformed = True
        if malformed:
            continue

        cls = str(cand["class"])
        if cls not in roster:
            # Q-063-3 — THE ROSTER IS WHAT KEEPS MEETING PARTICIPANTS OUT OF THE
            # GRAPH. `class: person` is refused here; the `wiki-import` pyramid guard
            # does not cover this rail, so the operator's rule ("attendees go in
            # `participants:`, not `_concepts/`") has no other enforcement point on
            # this path.
            violations.append({"index": i, "kind": "roster",
                               "detail": f"class `{cls}` is not in the roster "
                                         f"{list(roster)}"})

        for key in ("title", "status", "date"):
            value = cand.get(key)
            if isinstance(value, str) and has_yaml_breakout(value):
                # NEVER echo the value (CWE-117) — it IS the payload.
                violations.append({"index": i, "kind": "yaml_breakout",
                                   "detail": f"`{key}` contains a YAML delimiter or "
                                             f"a control character"})

        # ★ MECHANISM 2. No env escape is consulted — deliberately. Grep this package
        # for NO_QUOTE_CHECK: it is ABSENT, not merely unused.
        if _norm(str(cand["source_quote"])) not in body_norm:
            violations.append({
                "index": i, "kind": "quote_not_in_body",
                "detail": "`source_quote` does not occur in the source body "
                          "(verbatim grounding is mandatory)"})

        edges = cand.get("edges") or {}
        if not isinstance(edges, dict):
            violations.append({"index": i, "kind": "shape",
                               "detail": "`edges` must be an object"})
            continue
        for edge, targets in edges.items():
            if not isinstance(targets, list):
                violations.append({"index": i, "kind": "shape",
                                   "detail": f"`edges.{edge}` must be a list"})
                continue
            for t in targets:
                if not isinstance(t, str) or not is_valid_slug(t):
                    # The TRAVERSAL GATE. `supersedes: ["../../etc/passwd"]` is
                    # refused here, not normalised.
                    violations.append({
                        "index": i, "kind": "invalid_target",
                        "detail": f"`edges.{edge}` target is not a valid slug"})

    if violations:
        raise ExtractionParseError(
            f"{len(violations)} candidate contract violation(s)",
            error=_error_code_for(violations), violations=violations)
    return list(candidates)


def _error_code_for(violations: list[dict[str, Any]]) -> str:
    """The envelope's single stable code. `violations[]` carries the full detail;
    this picks the code the orchestrator branches on, preferring the most SPECIFIC
    mechanism so an operator reading only the code still learns the real cause."""
    kinds = {v["kind"] for v in violations}
    for kind, code in (
        ("quote_not_in_body", "FIELD_QUOTE_NOT_IN_BODY"),
        ("unknown_field", "UNKNOWN_FIELD"),
        ("field_too_long", "FIELD_TOO_LONG"),
        ("roster", "ONTOLOGY_VIOLATION"),
    ):
        if kind in kinds:
            return code
    return "EXTRACTION_PARSE_ERROR"


def derive_slugs(candidates: list[dict[str, Any]], config: LayoutConfig) -> list[str]:
    """Every slug via `_apply_slug_strategy` — THE LAYOUT'S OWN function, imported,
    never reimplemented.

    Never a naive kebab. cybos declares `slug_strategy: transliterate` and the
    operator's protocols are RUSSIAN; a hand-rolled slugifier would derive a
    different slug from the one `iter_pages` derives for the same file, and the page
    would index under a slug that nothing links to."""
    return [_apply_slug_strategy(str(c["title"]), config.slug_strategy)
            for c in candidates]


def check_in_batch_collisions(
    candidates: list[dict[str, Any]], slugs: list[str]
) -> None:
    """★ TWO CANDIDATES → ONE SLUG IS A CONTRACT VIOLATION. Refuse the batch.

    NOT the same rule as an existing-page collision (a benign drop), and fusing the
    two would be a real bug. cybos transliterates, the protocols are Russian, and two
    decisions whose titles transliterate alike would see the second SILENTLY
    OVERWRITE the first: one file, one DB row, one decision gone, ZERO lint issues.
    Invisible to the delta property AND to a naive written-page count — because the
    count is RIGHT. "Last one wins" does not show up in lint. That is precisely why
    it needs its own gate."""
    seen: dict[str, int] = {}
    collisions: list[dict[str, Any]] = []
    for i, slug in enumerate(slugs):
        if slug in seen:
            collisions.append({
                "slug": slug,
                "indices": [seen[slug], i],
                "titles": [str(candidates[seen[slug]]["title"]),
                           str(candidates[i]["title"])],
            })
        else:
            seen[slug] = i
    if collisions:
        raise ExtractionParseError(
            f"{len(collisions)} in-batch slug collision(s) — the second candidate "
            f"would silently overwrite the first",
            error="IN_BATCH_SLUG_COLLISION", violations=collisions)


def validate_ontology(
    candidates: list[dict[str, Any]],
    *,
    ontology: dict[str, Any],
    batch_classes: dict[str, str],
    db_classes: dict[str, str],
) -> None:
    """★ G1 — every candidate against the declared ontology, BEFORE any write. Raises
    with ALL violations at once. An empty ontology ⇒ the roster check alone (done in
    the schema pass), and `prepare` marks that run `vacuous_validation`.

      roster   class ∈ the roster              (schema pass)
      domain   candidate.class ∈ edge.frm
      RANGE    target.class    ∈ edge.to
      status   status          ∈ the class's enum

    ⚠️ THE RANGE CHECK MUST RESOLVE OUT-OF-BATCH TARGETS FROM THE DB. A range check
    that only sees targets INSIDE the batch is a range check that does not exist — an
    edge into the EXISTING graph (`supersedes: dec-old-thing`) is exactly where a
    range error hides, because that is where the model reasons about a page it never
    read. `db_classes` is that lookup, and it is the difference between a real gate
    and one that passes its own example vacuously.

    ⚠️ AN UNRESOLVED TARGET IS NOT A G1 CONCERN. G1 SKIPS it — exactly as the
    read-side `find_ontology_violations` does — because it can only judge a target
    whose class it can resolve. Orphan links are G2's surface, and the split is
    deliberate: THE ONTOLOGY CHECK CANNOT CATCH AN ORPHAN LINK. Fusing them would
    leave one population unexamined while the code looked complete.
    """
    if not ontology:
        return
    edges_by_name = {e["edge"]: e for e in ontology.get("edges", [])}
    enum_by_class = {
        p["class"]: p["enum"]
        for p in ontology.get("properties", []) if p["field"] == "status"
    }
    violations: list[dict[str, Any]] = []

    for i, cand in enumerate(candidates):
        cls = str(cand["class"])
        status = str(cand["status"])

        enum = enum_by_class.get(cls)
        if enum is not None and status not in enum:
            violations.append({"index": i, "class": cls, "kind": "status",
                               "detail": f"status `{status}` not in {enum}"})

        for edge, targets in (cand.get("edges") or {}).items():
            rule = edges_by_name.get(edge)
            if rule is None:
                if ontology.get("closed_types"):
                    violations.append({
                        "index": i, "class": cls, "kind": "domain",
                        "detail": f"edge `{edge}` is not declared in the ontology"})
                continue
            if cls not in rule["from"]:
                violations.append({
                    "index": i, "class": cls, "kind": "domain",
                    "detail": f"a `{cls}` may not author `{edge}` "
                              f"(domain: {rule['from']})"})
            for target in targets:
                target_class = batch_classes.get(target) or db_classes.get(target)
                if target_class is None:
                    continue           # → G2's surface, not G1's
                if target_class not in rule["to"]:
                    violations.append({
                        "index": i, "class": cls, "kind": "range",
                        "detail": f"`{edge}` → `{target}` is a `{target_class}`, "
                                  f"but the range is {rule['to']}"})

    if violations:
        raise ExtractionParseError(
            f"{len(violations)} ontology violation(s)",
            error="ONTOLOGY_VIOLATION", violations=violations)


def plan_reconciliation(
    candidates: list[dict[str, Any]],
    *,
    config: LayoutConfig,
    target_status: dict[str, str],
    target_class: dict[str, str],
) -> list[dict[str, Any]]:
    """★ G3 — the supersede reconciliation plan. DRIFT-RULE-DRIVEN, NEVER HARDCODED.

    A `supersedes` edge must reconcile the target's `status`, or the vault's own drift
    rule (`{class: decision, edge: superseded-by, expect_status: superseded}`) fires
    and it is no longer `--strict`-clean. G3 is GUARANTEED to be needed, not
    hypothetical.

    ★★ THE TWO BUGS THIS FUNCTION EXISTS TO NOT REPEAT — both were written, both were
    caught, and both are the same mistake one field apart:

      v2 hardcoded `status: superseded` — and that VIOLATES G1. `supersedes` is legal
         `requirement → requirement`, and the requirement enum is
         [draft, approved, implemented, dropped]: THERE IS NO `superseded`. The fix for
         G3 authored the exact contradiction G1 exists to prevent.

      v3 fixed the VALUE but left the PRECONDITION hardcoded as {proposed, accepted} —
         a decision-specific set. `workflow`'s enum is [draft, active, deprecated,
         superseded], so v3 would NEVER patch a workflow and drift would fire anyway.

    So BOTH come from config:
      value        = the matching rule's `expect_status`
      precondition = THE DRIFT RULE'S OWN FIRING CONDITION (`_health_rules.py:290-325`):
                     a SCALAR text status that differs from `expect_status`. An absent
                     or non-scalar status never drifts, so it is never patched — no
                     gratuitous Class-A edit.

    ⚠️ A `forbid_status`-SHAPED RULE PATCHES NOTHING (plan-review M-9). `DriftRule`
    carries exactly ONE of `expect_status` / `forbid_status`, and an operator may
    legitimately declare the forbid shape for `(class, superseded-by)`. Then
    `expect_status is None` and THERE IS NO VALUE TO PATCH TO — `forbid_status` says
    what a status must NOT be, which does not determine what it SHOULD be. Same branch
    as "no rule at all". This is the shape neither v2 nor v3 caught, and it is
    reachable from CONFIG, not from code.

    ★ THE PROTECTED-STATUS REFUSAL, ALSO DERIVED FROM CONFIG. Superseding a REJECTED
    decision is a semantic contradiction: the operator already moved past it, and
    overwriting `rejected` with `superseded` would DESTROY that fact. But which
    statuses are "already moved past"? Hardcoding `{rejected}` would be v2's disease a
    third time. So it is derived: **a class's `forbid_status` rules enumerate the
    statuses the vault still considers LIVE** (cybos: `invalidated-by` forbids
    [proposed, accepted] — i.e. those are the states an incident may still void). A
    status OUTSIDE that live set is one the operator has already resolved, and the rail
    refuses the batch (REQUIRES_STATUS_RECONCILIATION) rather than paper over it.

    STATED BOUNDARY: when a class declares NO `forbid_status` rule at all, there is no
    live-set signal, and every drift-firing status is patched (cybos `workflow` is such
    a class). That is a real gap in what config can tell us, and it is named here
    rather than left to be discovered. Returning nothing there would be worse: drift
    would fire and the vault would not be strict-clean.
    """
    rules = {
        (r.page_class, r.edge): r for r in config.drift_rules
        if r.edge == "superseded-by"
    }
    live_by_class: dict[str, set[str]] = {}
    for r in config.drift_rules:
        if r.forbid_status:
            live_by_class.setdefault(r.page_class, set()).update(r.forbid_status)

    plan: list[dict[str, Any]] = []
    protected: list[dict[str, Any]] = []
    for cand in candidates:
        for target in (cand.get("edges") or {}).get("supersedes", []):
            cls = target_class.get(target)
            if cls is None:
                continue                     # not a page we can see — G2's surface
            rule = rules.get((cls, "superseded-by"))
            if rule is None or rule.expect_status is None:
                continue                     # no rule, or the forbid shape ⇒ NO PATCH
            status = target_status.get(target)
            if not isinstance(status, str) or not status:
                continue                     # absent/non-scalar ⇒ never drifts
            if status == rule.expect_status:
                continue                     # already reconciled — idempotent

            live = live_by_class.get(cls)
            if live is not None and status not in live:
                protected.append({
                    "target": target, "page_class": cls, "status": status,
                    "detail": f"`{target}` is a `{cls}` with status `{status}`, which "
                              f"this vault does not treat as live "
                              f"(live: {sorted(live)}). Superseding it would DESTROY "
                              f"that status. Resolve it by hand."})
                continue

            plan.append({"slug": target, "page_class": cls, "field": "status",
                         "from": status, "to": rule.expect_status})

    if protected:
        raise ExtractionParseError(
            f"{len(protected)} supersede target(s) carry a status the operator must "
            f"adjudicate",
            error="REQUIRES_STATUS_RECONCILIATION", violations=protected)
    return plan


def page_refs(page_text: str, config: LayoutConfig) -> list[str]:
    """Every ref target the LAYOUT'S OWN `ref_extraction` rules find in the rendered
    page — slugified exactly as `reindex._body_refs` does.

    ⚠️ NOT "the wikilinks". cybos ships an `id-ref` rule, so **"это отменяет DEC-004"
    IN PROSE IS A REF** — and `find_orphan_links` scans `page_entity_refs` with NO
    `ref_type` filter, so there is nowhere for such a ref to hide at lint time. A
    validator that looked only at `[[wikilinks]]` would ACCEPT a page that `wiki-lint`
    then REJECTS: the delta property broken by our own hand.

    Same invariant as G4 — validate the write side against the layout's READ GRAMMAR,
    never against an assumption about it — wearing the ref costume."""
    return [
        _apply_slug_strategy(target, config.slug_strategy)
        for target, _line, _quote in extract_refs(
            page_text, config.ref_extraction,
            operator_supplied=config.ref_extraction_operator_supplied)
    ]


def validate_refs(
    rendered: list[str], *, config: LayoutConfig, resolvable: set[str],
) -> int:
    """★ G2 — every extracted target must resolve. Returns `links_checked`.

    Resolvable = existing page slugs ∪ entity slugs ∪ entity ALIASES ∪ the post-drop
    batch's own slugs. The aliases matter: the operator's vault resolves `[[Айва]]`
    onto the `aiva` entity through an alias row, and an alias-blind check would refuse
    a CORRECT batch — teaching the operator to reach for `--force`, which is how a
    safety gate dies."""
    unresolved: list[dict[str, Any]] = []
    checked = 0
    for idx, text in enumerate(rendered):
        for target in page_refs(text, config):
            checked += 1
            if target not in resolvable:
                unresolved.append({"index": idx, "target": target})
    if unresolved:
        raise ExtractionParseError(
            f"{len(unresolved)} unresolved ref(s) — the written page would be an "
            f"orphan-link source that `wiki-lint` then reports",
            error="UNRESOLVED_REF", violations=unresolved)
    return checked
