"""TASK 050 (R-5/R-6) — derived trust tier + `--min-trust`.

Derivation matrix (Python), the batched `find_verified_slugs` DAL, the SQL
pre-LIMIT floor on all three query shapes, SQL↔Python alignment (Q-050-3),
and the wiki-query e2e plumbing (annotation, hash fold, drift, edge gate).
"""

from __future__ import annotations

import collections
import contextlib
import io
import json
import random
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Page, PageRef, Vault
from scripts.wiki_index.policy import (
    EXTERNAL_PROVENANCE_KEYS,
    TRUST_TIERS,
    trust_tier,
)
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_index.sqlite_repository._search import _EXTERNAL_ORIGIN_SQL
from scripts.wiki_skills import wiki_query

VID = "trust-vault"


# =============================================================================
# 050-07 — derivation matrix (Python half)
# =============================================================================

@pytest.mark.parametrize("fm,path,verified,expected", [
    ({}, "_sources/a.md", False, "internal"),
    ({}, "_sources/a.md", True, "verified"),
    ({}, "_raw/cap.md", False, "external"),
    ({}, "_raw/cap.md", True, "external"),                 # MIN-rule: origin taints
    ({}, "Lessons/x/_raw/cap.md", False, "external"),
    ({}, "_RAW/cap.md", False, "external"),                # ASCII-ci ≡ SQLite LIKE
    ({}, "Xraw/cap.md", False, "internal"),                # `_` escape non-match
    ({"source": "https://x.test/a"}, "_sources/a.md", False, "external"),
    ({"source": "HTTP://x.test/a"}, "_sources/a.md", False, "external"),
    ({"URL": "http://x.test"}, "_sources/a.md", False, "external"),
    ({"url": "https://x.test"}, "_sources/a.md", False, "external"),
    # TASK 061-06 — the CASE VARIANTS. `Source:` is the observed leak: 19 live
    # pages carry the KEY, 18 carry an http scalar under it, and **13 actually
    # failed open** (5 were already `external` via a canonical key). 13 is the
    # number a security claim may cite — see the reconciled census + the re-runnable
    # query on `policy.EXTERNAL_PROVENANCE_KEYS`.
    # `SOURCE`/`Url` have 0 live pages (defense-in-depth).
    ({"Source": "https://x.test/a"}, "_sources/a.md", False, "external"),
    ({"SOURCE": "https://x.test/a"}, "_sources/a.md", False, "external"),
    ({"Url": "https://x.test"}, "_sources/a.md", False, "external"),
    # MIN-rule still holds for the newly-caught keys: origin taints (Q-050-1).
    ({"Source": "https://x.test/a"}, "_sources/a.md", True, "external"),
    # HONEST LIMIT (stated, not merely true): this closes the observed leak, not
    # the CLASS. A typo-shaped key still fails OPEN — no tool emits these.
    ({"uRL": "https://x.test"}, "_sources/a.md", False, "internal"),
    ({"Source_URL": "https://x.test"}, "_sources/a.md", False, "internal"),
    ({"source": "httpx://not-web"}, "_sources/a.md", False, "internal"),
    ({"source": "_raw/local.md"}, "_sources/a.md", False, "internal"),
    ({"source": None}, "_sources/a.md", True, "verified"),

    # -------------------------------------------------------------------------
    # 061 VDD fix-loop / H2 — the VALUE SHAPES. The pre-fix predicate required
    # `isinstance(val, str)`, so a LIST-valued provenance key derived `internal`
    # on BOTH halves. They agreed — and agreement is not the security property;
    # FAIL-CLOSED is. These are the two LIVE shapes (17 pages).
    # -------------------------------------------------------------------------
    # shape 2 — list of scalars. The real Айва partnership note: a business
    # document whose provenance is two external URLs. Derived `internal` pre-fix.
    ({"sources": ["https://aiva-pro.tech", "https://t.me/tm_aiva"]},
     "_sources/a.md", False, "external"),
    # shape 3 — list of OBJECTS (the TASK 023 `{id, url, file}` element that
    # `generate-detailed-meeting-summary` emits). 16 live course summaries.
    ({"sources": [{"id": "059RZHWA5Qg", "url": "https://youtu.be/059RZHWA5Qg",
                   "file": "059RZHWA5Qg.ru.txt"}]},
     "_sources/a.md", False, "external"),
    # origin still TAINTS through a list (MIN-rule, Q-050-1)
    ({"sources": ["https://aiva-pro.tech"]}, "_sources/a.md", True, "external"),
    # a mixed list — one http member is enough
    ({"sources": [None, 5, True, "local.md", "https://x.test"]},
     "_sources/a.md", False, "external"),
    # `sources` is the PLURAL key the trust predicate had simply FORGOTTEN,
    # though it is the framework's own canonical one (`all_cited_sources`).
    # It works as a scalar too.
    ({"sources": "https://x.test"}, "_sources/a.md", False, "external"),

    # -- NOT external: same shapes, no http (the shape must not be the signal) --
    ({"sources": ["notes/local.md", "other.md"]}, "_sources/a.md", False,
     "internal"),
    ({"sources": [{"id": "x", "file": "a.ru.txt"}]}, "_sources/a.md", False,
     "internal"),
    ({"sources": []}, "_sources/a.md", False, "internal"),

    # -------------------------------------------------------------------------
    # 061 VDD iteration-2 / LOW-3 — shape 4: a TOP-LEVEL OBJECT. Now EXTERNAL.
    # 0 live pages, and closed anyway: "no tool emits it" is a fact about TOOLS,
    # and vault frontmatter is HAND-AUTHORED and untrusted (H-6). `source:`
    # carrying a mapping is a natural thing for a human to type — and "our own
    # writers use the canonical shape" is the exact excuse that waved `Source:`
    # through for 13 live pages. One `isinstance` branch, one type-exclusive SQL
    # arm, both halves symmetric, no live page's tier changes.
    # -------------------------------------------------------------------------
    ({"source": {"url": "https://x.test"}}, "_sources/a.md", False, "external"),
    ({"sources": {"URL": "http://x.test"}}, "_sources/a.md", False, "external"),
    ({"source": {"url": "https://x.test"}}, "_sources/a.md", True, "external"),
    # ...but the inner key set IS `EXTERNAL_PROVENANCE_KEYS`: `u` is not one.
    ({"URL": {"u": "https://x.test"}}, "_sources/a.md", False, "internal"),
    ({"source": {"href": "https://x.test"}}, "_sources/a.md", False, "internal"),
    # ...and the shape is not the signal: a top-level object with no URL stays in.
    ({"source": {"url": "notes/local.md"}}, "_sources/a.md", False, "internal"),

    # -- THE STATED BOUNDARY (0 live pages each). Each remaining shape needs a
    # -- walk level BELOW an already-walked container — a genuinely recursive
    # -- descent, not one more fixed position — so the walk stops here rather
    # -- than becoming an unbounded `json_tree` on the hot search path.
    # -- Pinned so the limit is VISIBLE, not merely true. Both halves agree.
    # LOW-3: this one was the HOLE — four sibling boundary shapes were pinned and
    # this one was not, so the enumeration that proves the boundary had a gap in
    # exactly the place a gap is invisible.
    ({"sources": [{"url": ["https://x.test"]}]}, "_sources/a.md", False,
     "internal"),
    ({"source": {"url": ["https://x.test"]}}, "_sources/a.md", False, "internal"),
    ({"sources": [["https://x.test"]]}, "_sources/a.md", False, "internal"),
    ({"sources": [{"meta": {"url": "https://x.test"}}]}, "_sources/a.md", False,
     "internal"),
    ({"source": {"meta": {"url": "https://x.test"}}}, "_sources/a.md", False,
     "internal"),
    # the inner key set IS `EXTERNAL_PROVENANCE_KEYS` — `href` is not one
    ({"sources": [{"href": "https://x.test"}]}, "_sources/a.md", False,
     "internal"),
])
def test_trust_tier_matrix(fm, path, verified, expected):
    assert trust_tier(fm, path, verified) == expected


# =============================================================================
# DAL fixture — corpus covering every tier, plus a verifies ref
# =============================================================================

def _page(slug: str, *, vault: str = VID, fm_extra: dict | None = None,
          file_path: str | None = None, ptype: str = "summary",
          body: str = "trust corpus body") -> Page:
    fm: dict[str, object] = {"tags": ["t"]}
    if fm_extra:
        fm.update(fm_extra)
    return Page(
        vault_id=vault, slug=slug, project="_vault_", type=ptype, title=slug,
        file_path=file_path or f"_sources/{slug}.md", date=date(2026, 7, 8),
        last_modified=datetime(2026, 7, 8), file_hash=f"h-{vault}-{slug}",
        frontmatter_json=fm, body_excerpt=body, tags=["t"],
        tldr="t",
    )


@pytest.fixture
def repo(tmp_path: Path):
    r = SQLiteRepository(tmp_path / "t.db")
    r.apply_schema()
    for vid in (VID, "other-vault"):
        r.register_vault(Vault(
            vault_id=vid, name=vid, root_path=tmp_path / vid,
            schema_version="7.0", registered_at=datetime(2026, 7, 8)))
    r.upsert_page(_page("plain-note", fm_extra={"status": "open"}))
    r.upsert_page(_page("verified-note", fm_extra={"status": "open"}))
    r.upsert_page(_page("raw-capture", file_path="_raw/raw-capture.md",
                        fm_extra={"status": "open"}))
    r.upsert_page(_page("web-note", fm_extra={"source": "https://x.test/a",
                                              "status": "open"}))
    # TASK 061-06: the CASE VARIANT that failed open (13 live pages carried
    # `Source:` with an http URL AND derived `internal`). Joins the shared corpus
    # rather than forking a parallel one, so the 3-shape floor test exercises it.
    r.upsert_page(_page("cap-note", fm_extra={"Source": "https://x.test/b",
                                              "status": "open"}))
    # TASK 061-06 / Q-061-4: the KNOWN RESIDUAL, in the same corpus so it is
    # continuously exercised — a vault-specific provenance key still derives
    # `internal` (fail-open). See the pin test below.
    r.upsert_page(_page("tube-note", fm_extra={"youtube": "https://youtu.be/x",
                                               "status": "open"}))
    # 061 VDD fix-loop / H2 — the two LIVE VALUE SHAPES that failed open (17
    # pages). They join the SHARED corpus, so the 3-query-shape floor test and
    # the SQL<->Python alignment test exercise them on every run rather than in
    # a private fixture nobody else touches.
    r.upsert_page(_page("aiva-note", fm_extra={          # list of scalars (1 live)
        "sources": ["https://aiva-pro.tech", "https://t.me/tm_aiva"],
        "status": "open"}))
    r.upsert_page(_page("course-note", fm_extra={        # list of objects (16 live)
        "sources": [{"id": "059RZHWA5Qg", "url": "https://youtu.be/059RZHWA5Qg",
                     "file": "059RZHWA5Qg.ru.txt"}],
        "status": "open"}))
    # NEGATIVE control, same SHAPE, no http — proves the fix keys on the URL and
    # not merely on "the value is a list" (without this, `sources: [a.md]` pages
    # would silently become external and the corpus above would not notice).
    r.upsert_page(_page("local-src-note", fm_extra={
        "sources": [{"id": "x", "file": "local.ru.txt"}, "notes/local.md"],
        "status": "open"}))
    # 061 VDD iteration-2 / LOW-3 — shape 4 (top-level object). 0 live pages, but
    # it joins the SHARED corpus so the 3-query-shape floor test exercises it on
    # every run, exactly like the shapes that DID have a live population.
    r.upsert_page(_page("obj-note", fm_extra={
        "source": {"url": "https://x.test/obj"}, "status": "open"}))
    r.upsert_page(_page("verdict", ptype="verification", body="verdict body"))
    r.replace_refs(VID, "verdict", "_vault_", [PageRef(
        vault_id=VID, page_slug="verdict", page_project="_vault_",
        entity_slug="verified-note", ref_type="verifies")])
    yield r
    r.close()


def _slugs(hits) -> set[str]:
    return {h.page.slug for h in hits}


# =============================================================================
# 050-07 — find_verified_slugs (pairs semantics)
# =============================================================================

def test_find_verified_slugs_pairs(repo):
    got = repo.find_verified_slugs([
        (VID, "verified-note"), (VID, "plain-note"),
        ("other-vault", "verified-note"),        # cross-vault: NOT verified
    ])
    assert got == {(VID, "verified-note")}
    assert repo.find_verified_slugs([]) == set()


# =============================================================================
# 050-09a — SQL floor on the three shapes + alignment + LIMIT window
# =============================================================================

_CORPUS_TIERS = {
    "plain-note": "internal", "verified-note": "verified",
    "raw-capture": "external", "web-note": "external",
    # TASK 061-06 — the fix: a `Source:`-keyed page is now `external` on BOTH
    # halves (pre-061 it derived `internal` and sailed through the floor).
    "cap-note": "external",
    # 061 VDD fix-loop / H2 — the two LIVE list shapes, now `external` on both
    # halves (pre-fix BOTH derived `internal`: the halves agreed, and were both
    # wrong — 17 live pages sailed through the `--min-trust internal` floor).
    "aiva-note": "external",
    "course-note": "external",
    # 061 VDD iteration-2 / LOW-3 — shape 4 (top-level object), now external.
    "obj-note": "external",
    # ...and the same shapes WITHOUT an http URL stay `internal` — the fix keys
    # on the URL, not on the container type.
    "local-src-note": "internal",
    # Q-061-4 — the KNOWN RESIDUAL, asserted in its known-WRONG state so it
    # stays visible: a vault-specific provenance key still derives `internal`.
    "tube-note": "internal",
}

# The pages carrying `status: open` — i.e. the population the metadata-scan
# shape can see at all. `verdict` has no status, so it is not in it.
_STATUS_OPEN = {"plain-note", "verified-note", "raw-capture", "web-note",
                "cap-note", "tube-note", "aiva-note", "course-note",
                "local-src-note", "obj-note"}


@pytest.mark.parametrize("floor,expected", [
    ("external", {"plain-note", "verified-note", "raw-capture", "web-note",
                  "cap-note", "tube-note", "aiva-note", "course-note",
                  "local-src-note", "obj-note"}),
    # `cap-note` (Source:) drops out here — the 061-06 behavior flip.
    # `aiva-note`/`course-note` (list-valued `sources:`) drop out too — the H2
    # flip; pre-fix they SURVIVED this floor, which is the whole finding.
    # `obj-note` (top-level object) drops out — the LOW-3 flip.
    # `local-src-note` does NOT drop (list-valued, but no http URL).
    # `tube-note` (youtube:) does NOT drop — the Q-061-4 residual, still fail-open.
    ("internal", {"plain-note", "verified-note", "tube-note", "local-src-note"}),
    ("verified", {"verified-note"}),
])
def test_sql_floor_matches_python_on_all_shapes(repo, floor, expected):
    # sanity: the Python derivation agrees with the declared corpus tiers
    verified = repo.find_verified_slugs([(VID, s) for s in _CORPUS_TIERS])
    for slug, tier in _CORPUS_TIERS.items():
        page = repo.get_page(VID, slug, "_vault_")
        assert trust_tier(page.frontmatter_json, page.file_path,
                          (VID, slug) in verified) == tier
    # FTS shape
    fts = repo.search_pages('"trust corpus"', vaults=[VID], min_trust=floor)
    assert _slugs(fts) == expected
    # metadata-scan shape
    scan = repo.search_pages(None, vaults=[VID],
                             where_fields=[("status", "open")],
                             min_trust=floor)
    assert _slugs(scan) == expected & _STATUS_OPEN
    # FTS-narrowed tags shape ≡ forced scan (verdict page joins the tag
    # corpus as an `internal`-tier extra — equality of the two paths is the
    # contract here)
    prod = repo.search_pages(None, vaults=[VID], where_fields=[("tags", "t")],
                             min_trust=floor)
    forced = repo.search_pages(None, vaults=[VID], where_fields=[("tags", "t")],
                               min_trust=floor, _use_fts_narrowing=False)
    assert [h.page.slug for h in prod] == [h.page.slug for h in forced]


def test_min_trust_rejects_unknown(repo):
    with pytest.raises(ValueError):
        repo.search_pages('"trust corpus"', vaults=[VID], min_trust="bogus")


# =============================================================================
# 061-04 (R-061-3) — ONE key constant renders BOTH halves of the Q-050-3
# alignment contract, and the alignment corpus is PARAMETRIZED FROM it
# =============================================================================

# The VALUE SHAPES declared on `policy.EXTERNAL_PROVENANCE_KEYS`, as factories
# from a URL. The alignment corpus below is the CROSS PRODUCT of the constant and
# THIS table — so a new key OR a new shape auto-extends the gate on both halves,
# and neither can be added to one half alone. (061 VDD fix-loop / H2: the pre-fix
# corpus enumerated keys but NOT shapes, which is exactly how a list-valued
# `sources:` stayed fail-open on both halves for 17 live pages while a test named
# "every provenance key is external on both halves" passed.)
_VALUE_SHAPES = {
    # shape 1 — the scalar (all that pre-H2 was covered)
    "scalar": lambda url: url,
    # shape 2 — a list of scalars (the LIVE Айва partnership note)
    "list_of_scalars": lambda url: ["notes/local.md", url],
    # shape 3 — a list of objects (the LIVE `{id, url, file}` course summaries).
    # The INNER key is drawn from the SAME constant — never a second list.
    "list_of_objects": lambda url, k="url": [{"id": "x", k: url, "file": "f.txt"}],
    # shape 4 — a TOP-LEVEL object (061 VDD iteration-2 / LOW-3). 0 live pages;
    # closed because frontmatter is hand-authored and untrusted (H-6), not
    # because a census demanded it.
    "top_level_object": lambda url, k="url": {"id": "x", k: url},
}

# NOTE — the LIMIT of this table, stated (061 VDD iteration-2 / MED-1). It is a
# hand-maintained TEST table and **neither half renders from it** (a value shape
# is control flow, not data — there is nothing for the halves to share). So it
# CANNOT catch a Python-only widening: a dev who taught `_value_is_external` a new
# shape and forgot the SQL would keep all 72 cases below green. The gate that DOES
# catch that is the differential property test at the bottom of this file — do not
# mistake this cross product for it.


@pytest.mark.parametrize("shape", sorted(_VALUE_SHAPES))
@pytest.mark.parametrize("scheme", ("http", "https"))
@pytest.mark.parametrize("key", EXTERNAL_PROVENANCE_KEYS)
def test_every_provenance_key_is_external_on_both_halves(repo, key, scheme,
                                                         shape):
    """TC-04-1 — for EVERY (key in `policy.EXTERNAL_PROVENANCE_KEYS`) x scheme x
    VALUE SHAPE, the Python half derives `external` AND the SQL half's
    `--min-trust internal` floor excludes the page.

    The corpus is generated FROM the constant and FROM `_VALUE_SHAPES`, so
    adding a key or a shape automatically extends the gate on both halves — that
    auto-growth IS the anti-drift property Q-050-3 demands (061-06 grew the tuple
    3 -> 6 keys and took this test 6 -> 12 cases with no edit; the H2 fix grows it
    to 9 keys x 2 schemes x 3 shapes = 54, again with no per-case edit). A key or
    a shape rendered into only ONE half fails here immediately."""
    value = _VALUE_SHAPES[shape](f"{scheme}://x.test/a")
    repo.upsert_page(_page(
        "key-probe", fm_extra={key: value, "status": "open"}))
    page = repo.get_page(VID, "key-probe", "_vault_")

    # (a) Python half.
    assert trust_tier(page.frontmatter_json, page.file_path, False) == "external"

    # POSITIVE CONTROL, and it is load-bearing: "the floor excludes it" is
    # VACUOUSLY true for a page that never matched the query at all. This task
    # exists because a check that examined nothing reported green — so prove the
    # page IS retrievable on both shapes before asserting the floor removes it.
    assert "key-probe" in _slugs(
        repo.search_pages('"trust corpus"', vaults=[VID]))
    assert "key-probe" in _slugs(repo.search_pages(
        None, vaults=[VID], where_fields=[("status", "open")]))

    # (b) SQL half — the floor drops it on the FTS and metadata-scan shapes.
    assert "key-probe" not in _slugs(repo.search_pages(
        '"trust corpus"', vaults=[VID], min_trust="internal"))
    assert "key-probe" not in _slugs(repo.search_pages(
        None, vaults=[VID], where_fields=[("status", "open")],
        min_trust="internal"))


@pytest.mark.parametrize("shape", sorted(_VALUE_SHAPES))
@pytest.mark.parametrize("key", EXTERNAL_PROVENANCE_KEYS)
def test_non_http_value_is_not_external_on_either_half(repo, key, shape):
    """TC-04-1b — the NEGATIVE half of the same cross product, and it is what
    keeps the positive half honest: the signal must be the http(s) URL, not the
    key and not the container shape. A predicate that answered "external" for
    `sources: [local.md]` would pass every assertion above while quietly
    reclassifying 64 more live pages (81 carry `sources:`; only 17 carry a URL)."""
    value = _VALUE_SHAPES[shape]("notes/local.md")
    repo.upsert_page(_page(
        "local-probe", fm_extra={key: value, "status": "open"}))
    page = repo.get_page(VID, "local-probe", "_vault_")

    assert trust_tier(page.frontmatter_json, page.file_path, False) == "internal"
    # the SQL half agrees: it SURVIVES the internal floor on both query shapes
    assert "local-probe" in _slugs(repo.search_pages(
        '"trust corpus"', vaults=[VID], min_trust="internal"))
    assert "local-probe" in _slugs(repo.search_pages(
        None, vaults=[VID], where_fields=[("status", "open")],
        min_trust="internal"))


def test_external_origin_sql_renders_every_key():
    """TC-04-2 — the SQL literal names every key from the constant, in ALL THREE
    of its `IN` lists: the top-level key walk, the top-level OBJECT-member walk
    (shape 4, added by LOW-3), and the list-member's object walk (shape 3). Guards
    a HALF-APPLIED edit: a key added to the Python constant but not rendered into
    SQL is precisely the Q-050-3 drift this gate exists to make impossible.

    The count is derived from the SQL's own structure, not hard-coded to a magic
    3: `_member_sql` is rendered at each member POSITION and each render emits one
    `IN` list, so the expected count IS the number of member positions + 1 for the
    top-level key test."""
    positions = _EXTERNAL_ORIGIN_SQL.count("json_each(")     # blob + each member
    for key in EXTERNAL_PROVENANCE_KEYS:
        assert _EXTERNAL_ORIGIN_SQL.count(f"'{key}'") == 3, key
    # ...and 3 is not a magic number: 1 top-level key test + 1 per object-member
    # walk, of which there are 2 (top-level object, list-member object).
    assert positions == 4        # p.frontmatter_json + je.value x2 + jm.value


def test_external_origin_sql_parses_the_blob_exactly_once():
    """M2 (perf), pinned STRUCTURALLY rather than by a timing assertion.

    The old form emitted one `json_extract(p.frontmatter_json, …)` per
    (key x scheme) — 12 independent re-parses of the SAME blob per candidate row,
    growing by 2 with every key added. SQLite does no CSE on row-dependent calls,
    and this predicate lands on the metadata query shape, which has no index and
    scans the partition — so the LIMIT does not bound predicate evaluation and
    per-row cost IS the cost.

    The one-`json_each` form parses the blob ONCE per row for ALL keys and ALL
    shapes. These are the invariants that actually bound per-row cost:
      * exactly ONE walk of `p.frontmatter_json`;
      * ZERO `json_extract` (a reintroduced one is a re-parse);
      * a CONSTANT LIKE count, INDEPENDENT of the key count — which is what makes
        growing the constant cheap, and is why `SOURCE`/`Url`/`Sources` are
        affordable defense-in-depth. It scales with the number of member
        POSITIONS (a fixed 4), never with the 9 keys."""
    assert _EXTERNAL_ORIGIN_SQL.count("json_each(p.frontmatter_json)") == 1
    assert _EXTERNAL_ORIGIN_SQL.count("json_extract") == 0
    # 10 = 2 path + 2 per member position x 4 positions (je scalar, je object
    # member, jm scalar, jm object member). LOW-3 took this 8 -> 10 by adding the
    # top-level-object position; it did NOT make it grow with the key count, which
    # is the property under guard.
    assert _EXTERNAL_ORIGIN_SQL.count("LIKE") == 10
    # ...and the nested walks are over the MEMBER's text, never the page blob
    # again (that would re-parse it). `json_each(je.value)` appears TWICE — the
    # object arm and the array arm — but `je.type` is ONE value, so at most one
    # arm can fire per `je` row: two occurrences in the TEXT, one member walk at
    # RUNTIME. No `json_tree`: the positions are fixed, never a recursive descent.
    assert _EXTERNAL_ORIGIN_SQL.count("json_each(je.value)") == 2
    assert _EXTERNAL_ORIGIN_SQL.count("json_each(jm.value)") == 1
    assert "json_tree" not in _EXTERNAL_ORIGIN_SQL
    # the two arms ARE type-exclusive — that claim is load-bearing for the "one
    # walk at runtime" argument above, so pin it rather than assert it in prose.
    assert _EXTERNAL_ORIGIN_SQL.count("je.type = 'object'") == 1
    assert _EXTERNAL_ORIGIN_SQL.count("je.type = 'array'") == 1


# =============================================================================
# 061-06 (R-061-3, behavior half) — case variants close the observed leak;
# the vault-specific-key residual is PINNED, not hidden
# =============================================================================

def test_case_variant_keys_are_covered():
    """TC-06-1 — `Source:`/`SOURCE:`/`Url:` are in the constant, so both halves
    render them (the SQL render is asserted by TC-04-2, the key x scheme x shape
    alignment cases by TC-04-1 — which grew 6 -> 12 -> 54 with NO per-case edit:
    that is the 061-04 anti-drift property doing its job).

    061 VDD fix-loop / H2 adds `sources` (PLURAL) + its case variants. It is not
    a nice-to-have: it is the framework's OWN canonical provenance key — the DAL
    method `all_cited_sources` harvests `sources[]`, and wiki-sync's D2a detector
    defaults to `fields: (source, sources)`. The trust predicate had simply
    forgotten it, and 81 live pages carry it."""
    assert set(EXTERNAL_PROVENANCE_KEYS) == {
        "source", "Source", "SOURCE",
        "sources", "Sources", "SOURCES",
        "url", "Url", "URL"}
    assert len(EXTERNAL_PROVENANCE_KEYS) == 9
    # Enumeration (not case-folding) is a Q-061-2 decision, held here. NOTE: its
    # stated rationale — "a fold needs json_each + lower(key) in SQL only, so it
    # would de-align the halves" — is OVERTAKEN: the SQL half is a json_each walk
    # now (it had to be, to see inside a list), so a fold would today be
    # SYMMETRIC. Flipping it is a deliberate follow-up (it reverses a RESOLVED
    # open question and un-pins the `uRL:` case below), never a silent widening.
    assert all(k.lower() in {"source", "sources", "url"}
               for k in EXTERNAL_PROVENANCE_KEYS)


def test_vault_specific_provenance_key_still_internal_q0614(repo):
    """TC-06-3 — Q-061-4 (KNOWN RESIDUAL, tracked): a page whose provenance is
    an http(s) URL under a VAULT-SPECIFIC key still derives `internal`. The trust
    contract is about external ORIGIN, not key spelling, so this IS a defect — it
    is deferred by MECHANISM (it needs a per-vault `external_keys:` config
    surface, which does not belong in a fix task), NOT by defect.

    CENSUS CORRECTED (061 VDD fix-loop): the live population is **9 PAGES**, not
    the 18 claimed by the TASK 061 spec, `policy.py` and `security.md`. Every one
    of the 9 carries `youtube:` AND `teachable:` — "18" was two KEY-occurrence
    counts (9 + 9) summed as if they were disjoint PAGE sets. That is the exact
    count-the-wrong-noun bug TASK 061 exists to kill, recurring inside TASK 061's
    own residual accounting. Of the 9, one already derives `external` via another
    key, so **8 pages actually fail open**.

    DISJOINT from the H2 fix (checked on the live DB, not assumed: none of the 9
    carries a `sources:` array), so the shape-completion neither closes nor
    shrinks this set.

    This asserts the known-WRONG state on BOTH halves, so the two stay pinned
    together even while wrong, and an invisible residual is instead a visible,
    tracked one.

    WHEN Q-061-4 LANDS: FLIP these assertions to `external` / excluded — do not
    delete this test."""
    # Python half — still internal (fail-open).
    assert trust_tier({"youtube": "https://youtu.be/x"},
                      "_sources/a.md", False) == "internal"
    assert trust_tier({"teachable": "https://x.teachable.com/c"},
                      "_sources/a.md", False) == "internal"
    # SQL half AGREES (still fail-open): `tube-note` SURVIVES the internal
    # floor on the FTS and metadata-scan shapes.
    assert "tube-note" in _slugs(repo.search_pages(
        '"trust corpus"', vaults=[VID], min_trust="internal"))
    assert "tube-note" in _slugs(repo.search_pages(
        None, vaults=[VID], where_fields=[("status", "open")],
        min_trust="internal"))


def test_blast_radius_default_output_unchanged(repo):
    """TC-06-4 — the blast radius, asserted in BOTH directions. The 061-06 flip
    changes NOTHING for a default caller: with no `--min-trust`, the
    `Source:`-keyed page still ranks and returns. ONLY an explicit
    `--min-trust internal|verified` caller sees it drop out."""
    # Direction 1 — no floor: `cap-note` is returned (default output UNCHANGED).
    assert "cap-note" in _slugs(
        repo.search_pages('"trust corpus"', vaults=[VID]))
    assert "cap-note" in _slugs(repo.search_pages(
        None, vaults=[VID], where_fields=[("status", "open")]))
    # ...and the `external` floor imposes no clause, so it is returned there too.
    assert "cap-note" in _slugs(repo.search_pages(
        '"trust corpus"', vaults=[VID], min_trust="external"))
    # Direction 2 — explicit floor: it drops out (this is the ONLY visible
    # change; pre-061 it wrongly survived).
    assert "cap-note" not in _slugs(repo.search_pages(
        '"trust corpus"', vaults=[VID], min_trust="internal"))
    assert "cap-note" not in _slugs(repo.search_pages(
        '"trust corpus"', vaults=[VID], min_trust="verified"))


def test_live_list_shapes_flip_e2e_through_wiki_query(tmp_path):
    """H2 (e2e) — the two LIVE shapes through the REAL CLI, authored as REAL
    YAML frontmatter (not a hand-built dict), so the whole chain is exercised:
    the frontmatter parser -> `frontmatter_json` -> the SQL floor -> the
    always-on `trust` annotation.

    These are transcriptions of the actual live pages: the Айва partnership note
    (`sources:` = two external URLs) and a course summary (`sources:` = the TASK
    023 `{id, url, file}` objects). Both derived `internal` pre-fix and passed
    `--min-trust internal` — the filter whose ENTIRE purpose is the H-6 contract
    ("never ground on un-reviewed captured web text")."""
    vault, db = _seed_vault(tmp_path)
    (vault / "_sources/aiva.md").write_text(
        "---\ntype: summary\ntitle: Aiva\ndate: 2026-07-08\ntags: [t]\n"
        "sources:\n  - https://aiva-pro.tech\n  - https://t.me/tm_aiva\n"
        "---\n\nHermes trust corpus partnership.\n")
    (vault / "_sources/course.md").write_text(
        "---\ntype: summary\ntitle: Course\ndate: 2026-07-08\ntags: [t]\n"
        "sources:\n  - id: 059RZHWA5Qg\n"
        "    url: https://youtu.be/059RZHWA5Qg\n"
        "    file: 059RZHWA5Qg.ru.txt\n"
        "---\n\nHermes trust corpus lesson.\n")
    # NEGATIVE control in the same vault, same shape, no URL — it must NOT flip.
    (vault / "_sources/local-cited.md").write_text(
        "---\ntype: summary\ntitle: Local\ndate: 2026-07-08\ntags: [t]\n"
        "sources:\n  - _raw/local-transcript.txt\n"
        "---\n\nHermes trust corpus local.\n")
    repo = SQLiteRepository(db)
    reindex_full(repo, VID)
    repo.close()

    code, env = _run(vault, db, ["prepare", "hermes trust corpus"])
    assert code == 0
    tiers = {h["slug"]: h["trust"] for h in env["hits"]}
    assert tiers["aiva"] == "external"           # was `internal` pre-fix
    assert tiers["course"] == "external"         # was `internal` pre-fix
    assert tiers["local-cited"] == "internal"    # same shape, no URL: unchanged
    assert tiers["plain-note"] == "internal"     # unchanged

    code, env = _run(vault, db, ["prepare", "hermes trust corpus",
                                 "--min-trust", "internal"])
    assert code == 0
    # the two capture-backed pages are now FLOORED; the locally-cited one stays.
    assert {h["slug"] for h in env["hits"]} == {"plain-note", "local-cited"}


def test_case_variant_flip_e2e_through_wiki_query(tmp_path):
    """TC-06-1 (e2e) — the flip through the REAL CLI, not just the DAL: a
    `Source:`-keyed page is annotated `external` (the `wiki_query.py:479`
    display half) and is filtered by `--min-trust internal` (the SQL half).
    Both halves share `_is_external`, so the one constant fixes both."""
    vault, db = _seed_vault(tmp_path)
    (vault / "_sources/cap-capture.md").write_text(
        "---\ntype: summary\ntitle: C\ndate: 2026-07-08\ntags: [t]\n"
        'Source: "https://x.test/cap2"\n---\n\nHermes trust corpus capitalized.\n')
    repo = SQLiteRepository(db)
    reindex_full(repo, VID)
    repo.close()
    code, env = _run(vault, db, ["prepare", "hermes trust corpus"])
    assert code == 0
    tiers = {h["slug"]: h["trust"] for h in env["hits"]}
    assert tiers["cap-capture"] == "external"      # was `internal` pre-061
    assert tiers["plain-note"] == "internal"       # unchanged
    code, env = _run(vault, db, ["prepare", "hermes trust corpus",
                                 "--min-trust", "internal"])
    assert code == 0
    assert {h["slug"] for h in env["hits"]} == {"plain-note"}


def test_floor_is_pre_limit(tmp_path):
    r = SQLiteRepository(tmp_path / "lim.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id=VID, name=VID, root_path=tmp_path / VID,
        schema_version="7.0", registered_at=datetime(2026, 7, 8)))
    # external page is the strongest match; floor must not let it evict the
    # weaker internal hit from a limit=1 window.
    strong = _page("strong-ext", file_path="_raw/strong-ext.md")
    strong = Page(**{**strong.__dict__,
                     "body_excerpt": "trust trust trust trust corpus"})
    r.upsert_page(strong)
    r.upsert_page(_page("weak-int"))
    try:
        hits = r.search_pages('"trust"', vaults=[VID], min_trust="internal",
                              limit=1)
        assert _slugs(hits) == {"weak-int"}
    finally:
        r.close()


# =============================================================================
# 050-08 / 050-09b — wiki-query e2e
# =============================================================================

def _seed_vault(tmp_path: Path) -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "WIKI_SCHEMA.md").write_text(
        f"---\nname: WIKI_SCHEMA\nvault_id: {VID}\n"
        "schema_version: '2.0'\nlanguage: en\nlayout: karpathy\n---\n\n# s\n")
    for rel, fm, body in [
        ("_sources/plain-note.md",
         "type: summary\ntitle: P\ndate: 2026-07-08\ntags: [t]",
         "Hermes trust corpus plain."),
        ("_sources/web-capture.md",
         "type: summary\ntitle: R\ndate: 2026-07-08\ntags: [t]\n"
         "source: \"https://x.test/cap\"",
         "Hermes trust corpus external capture."),
    ]:
        p = vault / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"---\n{fm}\n---\n\n{body}\n")
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=VID, name=VID, root_path=vault,
        schema_version="7.0", registered_at=datetime(2026, 7, 8)))
    reindex_full(repo, VID)
    repo.close()
    return vault, db


def _run(vault, db, argv) -> tuple[int, dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_query.main(argv + ["--vault", VID, "--vault-root",
                                       str(vault), "--db-path", str(db)])
    return code, json.loads(buf.getvalue())


def test_prepare_annotates_trust_and_filters(tmp_path):
    vault, db = _seed_vault(tmp_path)
    code, env = _run(vault, db, ["prepare", "hermes trust corpus"])
    assert code == 0
    tiers = {h["slug"]: h["trust"] for h in env["hits"]}
    assert tiers["plain-note"] == "internal"
    assert tiers["web-capture"] == "external"
    assert "min_trust" not in env
    code, env = _run(vault, db, ["prepare", "hermes trust corpus",
                                 "--min-trust", "internal"])
    assert code == 0
    assert {h["slug"] for h in env["hits"]} == {"plain-note"}
    assert env["min_trust"] == "internal"


def test_min_trust_external_folds_but_filters_nothing(tmp_path):
    vault, db = _seed_vault(tmp_path)
    _, off = _run(vault, db, ["prepare", "hermes trust corpus"])
    _, ext = _run(vault, db, ["prepare", "hermes trust corpus",
                              "--min-trust", "external"])
    assert {h["slug"] for h in off["hits"]} == {h["slug"] for h in ext["hits"]}
    assert off["question_hash"] != ext["question_hash"]     # flag-present folds


def test_min_trust_drift_fails_question_changed(tmp_path):
    import sys
    vault, db = _seed_vault(tmp_path)
    code, env = _run(vault, db, ["prepare", "hermes trust corpus",
                                 "--min-trust", "internal"])
    assert code == 0
    (vault / "c.json").write_text(json.dumps(["_vault_/plain-note"]))
    old_stdin = sys.stdin
    sys.stdin = io.TextIOWrapper(io.BytesIO(b"Grounded."), encoding="utf-8")
    try:
        code, out = _run(vault, db, [
            "apply", "--query-slug", env["query_slug"],
            "--question", "hermes trust corpus",
            "--question-hash", env["question_hash"],
            "--answer-stdin", "--citations-file", str(vault / "c.json")])
    finally:
        sys.stdin = old_stdin
    assert code == 2 and out["error"] == "QUESTION_CHANGED"  # no flag on apply


def test_follow_edges_floor_gate(tmp_path):
    vault, db = _seed_vault(tmp_path)
    # plain-note links to the external capture ONLY via a typed edge.
    p = vault / "_sources/plain-note.md"
    p.write_text(p.read_text().replace(
        "tags: [t]", "tags: [t]\nrelates_to: [raw-capture]"))
    repo = SQLiteRepository(db)
    reindex_full(repo, VID)
    repo.close()
    q = ["prepare", "corpus plain"]
    code, env = _run(vault, db, q + ["--follow-edges"])
    assert {h["slug"] for h in env["hits"]} == {"plain-note", "web-capture"}
    code, env = _run(vault, db, q + ["--follow-edges",
                                     "--min-trust", "internal"])
    assert {h["slug"] for h in env["hits"]} == {"plain-note"}


def test_tiers_constant_order():
    assert TRUST_TIERS == ("external", "internal", "verified")


# =============================================================================
# vdd-multi review fixes (reviewer MED-2 / LOW-1 / LOW-3)
# =============================================================================

def test_follow_edges_verified_floor_batch(tmp_path):
    """reviewer MED-2: the verified-floor batch path through _follow_edges —
    a VERIFIED neighbor passes the `--min-trust verified` edge gate, an
    unverified one is dropped."""
    vault, db = _seed_vault(tmp_path)
    p = vault / "_sources/plain-note.md"
    p.write_text(p.read_text().replace(
        "tags: [t]", "tags: [t]\nrelates_to: [edge-target]"))
    # the edge target + a verification page verifying it
    (vault / "_sources/edge-target.md").write_text(
        "---\ntype: summary\ntitle: ET\ndate: 2026-07-08\ntags: [t]\n---\n\n"
        "Edge target unique body.\n")
    (vault / "_verifications").mkdir(exist_ok=True)
    (vault / "_verifications/verify-et.md").write_text(
        "---\ntype: verification\ntitle: 'V: et'\nverifies: _vault_/edge-target\n"
        "verdict: pass\ncritics: [c1]\nanswer_hash: " + "a" * 64 + "\n"
        "date: '2026-07-08'\ntags: [verification]\n---\n\n_No findings._\n")
    repo = SQLiteRepository(db)
    reindex_full(repo, VID)
    repo.close()
    # plain-note itself must satisfy the floor too → verify it as well
    q = ["prepare", "corpus plain", "--follow-edges", "--min-trust", "verified"]
    code, env = _run(vault, db, q)
    # plain-note (unverified) is SQL-filtered; edge expansion starts from an
    # empty set → NO_CONTEXT. Now verify plain-note and re-run: the edge-pulled
    # VERIFIED target must appear; the unverified web-capture must not.
    assert code == 2 and env["error"] == "NO_CONTEXT"
    (vault / "_verifications/verify-plain.md").write_text(
        "---\ntype: verification\ntitle: 'V: p'\nverifies: _vault_/plain-note\n"
        "verdict: pass\ncritics: [c1]\nanswer_hash: " + "b" * 64 + "\n"
        "date: '2026-07-08'\ntags: [verification]\n---\n\n_No findings._\n")
    repo = SQLiteRepository(db)
    reindex_full(repo, VID)
    repo.close()
    code, env = _run(vault, db, q)
    assert code == 0
    slugs = {h["slug"] for h in env["hits"]}
    assert "plain-note" in slugs
    assert "edge-target" in slugs          # verified neighbor passes the gate
    assert "web-capture" not in slugs      # external stays out


def test_min_trust_composes_with_audience(tmp_path):
    """reviewer LOW-1: both scope flags fold and both filter."""
    vault, db = _seed_vault(tmp_path)
    # classify plain-note restricted; web-capture stays external+unclassified
    p = vault / "_sources/plain-note.md"
    p.write_text(p.read_text().replace(
        "tags: [t]", "tags: [t]\nclassification: restricted"))
    repo = SQLiteRepository(db)
    reindex_full(repo, VID)
    repo.close()
    base = ["prepare", "hermes trust corpus"]
    _, both = _run(vault, db, base + ["--audience", "internal",
                                      "--min-trust", "internal"])
    # audience internal drops restricted plain-note; min-trust internal drops
    # external web-capture → nothing left.
    assert both.get("error") == "NO_CONTEXT" or both["retrieved_count"] == 0 \
        or {h["slug"] for h in both["hits"]} == set()
    _, aud = _run(vault, db, base + ["--audience", "restricted",
                                     "--min-trust", "internal"])
    assert {h["slug"] for h in aud["hits"]} == {"plain-note"}
    assert aud["audience"] == "restricted" and aud["min_trust"] == "internal"
    _, off = _run(vault, db, base)
    assert off["question_hash"] != aud["question_hash"]


def test_find_verified_slugs_multi_chunk(repo):
    """reviewer LOW-3: >400 pairs exercises the chunk boundary."""
    pairs = [(VID, f"bulk-{i}") for i in range(950)] + [(VID, "verified-note")]
    got = repo.find_verified_slugs(pairs)
    assert got == {(VID, "verified-note")}


# =============================================================================
# 061 VDD iteration-2 / MED-1 — the DIFFERENTIAL gate: SQL <-> Python on
# GENERATED frontmatter. This is the only test here that can catch a HALF-widening.
# =============================================================================
#
# Everything above pins the halves against a HAND-WRITTEN table (`_VALUE_SHAPES`).
# Neither half renders from that table, so it cannot catch a Python-only widening:
# teach `_value_is_external` a new shape, forget the SQL, and all 72 cross-product
# cases stay green while the halves silently diverge. That is the H2 defect class
# one layer up — the alignment gate itself asserting a coverage it does not have.
#
# The fix is to stop asserting alignment from a table and start OBSERVING it:
# generate frontmatter neither half was written against, and require the two halves
# to AGREE case-by-case. Any widening applied to one half alone fails here.

_LEAVES: tuple[object, ...] = (
    # http(s) — the signal (incl. the ASCII-ci fold both halves must share)
    "https://x.test/a", "http://x.test/b", "HTTP://X.TEST/C",
    # look-alikes that must NOT match — the prefix is EXACT
    "httpx://not-web", "http", "https:/x.test", " https://x.test",
    "notes/local.md", "_raw/local.md", "",
    # non-TEXT scalars — `je.type = 'text'` <-> `isinstance(val, str)`
    None, 5, True, 3.5,
)
_DECOY_KEYS: tuple[str, ...] = (
    "href", "link", "meta", "id", "file", "title",   # non-provenance keys
    "uRL", "Source_URL", "youtube", "teachable",     # the KNOWN fail-open keys
)
_GEN_KEYS: tuple[str, ...] = tuple(EXTERNAL_PROVENANCE_KEYS) + _DECOY_KEYS


def _rand_value(rng: random.Random, depth: int) -> object:
    """A random frontmatter VALUE: scalars, lists, dicts, mixed, <= 4 deep.

    Deliberately NOT shape-aware — it does not know what `_value_is_external`
    looks for. A generator built from the predicate's own shape list would only
    re-test the shapes the predicate already knows, which is the trap this test
    exists to escape."""
    if depth >= 4 or rng.random() < 0.4:
        return rng.choice(_LEAVES)
    if rng.random() < 0.5:
        return [_rand_value(rng, depth + 1) for _ in range(rng.randint(0, 3))]
    return {rng.choice(_GEN_KEYS): _rand_value(rng, depth + 1)
            for _ in range(rng.randint(0, 3))}


def _gen_frontmatter(rng: random.Random) -> dict:
    return {rng.choice(_GEN_KEYS): _rand_value(rng, 0)
            for _ in range(rng.randint(1, 3))}


def test_sql_and_python_agree_on_generated_frontmatter(repo):
    """MED-1 — the SHAPE half of the Q-050-3 drift guard, which the key half
    never had: for 400 pieces of GENERATED frontmatter,

        `trust_tier(...) == "external"`  <=>  the row is dropped by
                                              `--min-trust internal`

    on BOTH query shapes. The `<=>` is the point: a widening (or narrowing) of
    EITHER half alone breaks it on some generated case, in EITHER direction.
    Mutation-verified — see the fix commit; reverting any single branch of
    `_value_is_external` OR of `_EXTERNAL_ORIGIN_SQL` fails this test.

    ANTI-VACUITY (this task's whole thesis, applied to this task's own gate):
    "the floor dropped it" is VACUOUSLY true of a page the query never retrieved,
    and "the halves agree" is vacuously true of a corpus with no interesting
    shapes in it. So this test asserts, BEFORE the `<=>`, that (a) every generated
    page IS retrievable with no floor on both shapes and (b) the generator
    actually REACHED each shape and both outcomes. A check that examined nothing
    must not be able to report green — least of all this one.

    WHAT THIS TEST CANNOT DO, stated rather than left true by luck. It proves the
    halves AGREE; it does not prove they are RIGHT. Revert a shape on BOTH halves
    and they agree again — this test goes green (mutation-verified: it does). That
    is the H2 lesson restated: *alignment is not the security property, fail-CLOSED
    is.* The BOUNDARY — which shapes must derive `external` at all — is pinned by
    `test_trust_tier_matrix` and `_CORPUS_TIERS`, which assert the VALUE, not the
    agreement. The two gates are complementary and NEITHER is redundant: the matrix
    says what is true, this says the halves both believe it. Deleting either one
    re-opens a live defect class (LOW-3 and MED-1 respectively)."""
    rng = random.Random(20260713)
    corpus: dict[str, dict] = {}
    for i in range(400):
        fm = _gen_frontmatter(rng)
        fm["status"] = "open"
        slug = f"gen-{i:04d}"
        repo.upsert_page(_page(slug, fm_extra=fm))
        corpus[slug] = fm
    generated = set(corpus)
    big = len(generated) + 50

    # (a) POSITIVE CONTROL. Without this the `<=>` below could be satisfied by an
    # empty result set on both sides.
    fts_open = _slugs(repo.search_pages('"trust corpus"', vaults=[VID], limit=big))
    scan_open = _slugs(repo.search_pages(
        None, vaults=[VID], where_fields=[("status", "open")], limit=big))
    assert generated <= fts_open, "generated pages are not retrievable at all"
    assert generated <= scan_open, "generated pages are not retrievable at all"

    # (b) the `<=>`, case by case, on both query shapes.
    fts_floor = _slugs(repo.search_pages(
        '"trust corpus"', vaults=[VID], min_trust="internal", limit=big))
    scan_floor = _slugs(repo.search_pages(
        None, vaults=[VID], where_fields=[("status", "open")],
        min_trust="internal", limit=big))
    py_external: set[str] = set()
    mismatches: list[str] = []
    for slug in sorted(generated):
        page = repo.get_page(VID, slug, "_vault_")
        py = trust_tier(page.frontmatter_json, page.file_path, False) == "external"
        if py:
            py_external.add(slug)
        sql_fts = slug not in fts_floor
        sql_scan = slug not in scan_floor
        if not (py is sql_fts is sql_scan):
            mismatches.append(
                f"{slug}: python_external={py} sql_dropped_fts={sql_fts} "
                f"sql_dropped_scan={sql_scan} fm={page.frontmatter_json!r}")
    assert not mismatches, (
        "SQL and Python DISAGREE on generated frontmatter — the two halves have "
        "drifted (Q-050-3):\n" + "\n".join(mismatches[:10]))

    # (c) ANTI-VACUITY: the corpus must be two-sided AND must have reached every
    # shape. A generator that only ever emitted `source: "local.md"` would satisfy
    # (b) perfectly while guarding nothing at all.
    assert 40 <= len(py_external) <= len(generated) - 40, (
        f"one-sided corpus: {len(py_external)}/{len(generated)} external — the "
        "<=> above proves little")
    seen: collections.Counter[str] = collections.Counter()
    for fm in corpus.values():
        for k in EXTERNAL_PROVENANCE_KEYS:
            v = fm.get(k, "__absent__")
            if v == "__absent__":
                continue
            if isinstance(v, str):
                seen["scalar"] += 1
            elif isinstance(v, dict):
                seen["top_object"] += 1                       # shape 4
                if any(isinstance(m, list) for m in v.values()):
                    seen["object_holding_list"] += 1          # a pinned boundary
            elif isinstance(v, list):
                for m in v:
                    if isinstance(m, str):
                        seen["list_scalar"] += 1              # shape 2
                    elif isinstance(m, dict):
                        seen["list_object"] += 1              # shape 3
                        if any(isinstance(x, list) for x in m.values()):
                            seen["list_object_holding_list"] += 1   # LOW-3's hole
                    elif isinstance(m, list):
                        seen["list_list"] += 1                # a pinned boundary
    for shape in ("scalar", "top_object", "list_scalar", "list_object",
                  "list_list", "object_holding_list",
                  "list_object_holding_list"):
        assert seen[shape] >= 1, (
            f"the generator never emitted `{shape}` — this test would pass "
            f"while guarding nothing there. seen={dict(seen)}")
