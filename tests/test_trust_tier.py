"""TASK 050 (R-5/R-6) — derived trust tier + `--min-trust`.

Derivation matrix (Python), the batched `find_verified_slugs` DAL, the SQL
pre-LIMIT floor on all three query shapes, SQL↔Python alignment (Q-050-3),
and the wiki-query e2e plumbing (annotation, hash fold, drift, edge gate).
"""

from __future__ import annotations

import contextlib
import io
import json
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
    # TASK 061-06 — the CASE VARIANTS. `Source:` is the observed leak (18 live
    # pages); `SOURCE`/`Url` have 0 live pages (defense-in-depth).
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
    ({"source": ["https://x.test"]}, "_sources/a.md", False, "internal"),  # non-scalar
    ({"URL": {"u": "https://x.test"}}, "_sources/a.md", False, "internal"),
    ({"source": None}, "_sources/a.md", True, "verified"),
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
    # TASK 061-06: the CASE VARIANT that failed open (18 live pages carried
    # `Source:` and derived `internal`). Joins the shared corpus rather than
    # forking a parallel one, so it is exercised by the 3-shape floor test.
    r.upsert_page(_page("cap-note", fm_extra={"Source": "https://x.test/b",
                                              "status": "open"}))
    # TASK 061-06 / Q-061-4: the KNOWN RESIDUAL, in the same corpus so it is
    # continuously exercised — a vault-specific provenance key still derives
    # `internal` (fail-open). See the pin test below.
    r.upsert_page(_page("tube-note", fm_extra={"youtube": "https://youtu.be/x",
                                               "status": "open"}))
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
    # Q-061-4 — the KNOWN RESIDUAL, asserted in its known-WRONG state so it
    # stays visible: a vault-specific provenance key still derives `internal`.
    "tube-note": "internal",
}

# The pages carrying `status: open` — i.e. the population the metadata-scan
# shape can see at all. `verdict` has no status, so it is not in it.
_STATUS_OPEN = {"plain-note", "verified-note", "raw-capture", "web-note",
                "cap-note", "tube-note"}


@pytest.mark.parametrize("floor,expected", [
    ("external", {"plain-note", "verified-note", "raw-capture", "web-note",
                  "cap-note", "tube-note"}),
    # `cap-note` (Source:) now DROPS OUT here — the 061-06 behavior flip.
    # `tube-note` (youtube:) does NOT — the Q-061-4 residual, still fail-open.
    ("internal", {"plain-note", "verified-note", "tube-note"}),
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

@pytest.mark.parametrize("scheme", ("http", "https"))
@pytest.mark.parametrize("key", EXTERNAL_PROVENANCE_KEYS)
def test_every_provenance_key_is_external_on_both_halves(repo, key, scheme):
    """TC-04-1 — for EVERY key in `policy.EXTERNAL_PROVENANCE_KEYS` x scheme,
    the Python half derives `external` AND the SQL half's `--min-trust internal`
    floor excludes the page.

    The corpus is generated FROM the constant, so adding a key automatically
    extends the gate on both halves — that auto-growth IS the anti-drift
    property Q-050-3 demands (061-06 grows the tuple 3 -> 6 keys and this test
    goes 6 -> 12 cases with no edit; a key rendered into only ONE half fails
    here immediately)."""
    repo.upsert_page(_page(
        "key-probe", fm_extra={key: f"{scheme}://x.test/a", "status": "open"}))
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


def test_external_origin_sql_renders_every_key():
    """TC-04-2 — the SQL literal carries exactly 2 path disjuncts + 2 per key
    (http, https), and names each key's JSON path. Guards a HALF-APPLIED edit:
    a key added to the Python constant but not rendered into SQL is precisely
    the Q-050-3 drift this bead exists to make impossible."""
    assert _EXTERNAL_ORIGIN_SQL.count("LIKE") == (
        2 + 2 * len(EXTERNAL_PROVENANCE_KEYS))
    for key in EXTERNAL_PROVENANCE_KEYS:
        assert f"'$.{key}'" in _EXTERNAL_ORIGIN_SQL


# =============================================================================
# 061-06 (R-061-3, behavior half) — case variants close the observed leak;
# the vault-specific-key residual is PINNED, not hidden
# =============================================================================

def test_case_variant_keys_are_covered():
    """TC-06-1 — `Source:`/`SOURCE:`/`Url:` are in the constant, so both halves
    render them (the SQL count is asserted by TC-04-2, the 12 key x scheme
    alignment cases by TC-04-1 — which grew 6 -> 12 with NO edit: that is the
    061-04 anti-drift property doing its job)."""
    assert set(EXTERNAL_PROVENANCE_KEYS) == {
        "source", "Source", "SOURCE", "url", "Url", "URL"}
    # Enumeration, not case-folding, is forced by Q-050-3: SQLite json_extract
    # matches its path key CASE-SENSITIVELY, so a true fold would need
    # json_each + lower(key) in SQL ONLY — the asymmetry Q-050-3 forbids.
    assert len(EXTERNAL_PROVENANCE_KEYS) == 6


def test_vault_specific_provenance_key_still_internal_q0614(repo):
    """TC-06-3 — Q-061-4 (KNOWN RESIDUAL, tracked): a page whose provenance is
    an http(s) URL under a VAULT-SPECIFIC key (`youtube:` 9 live pages,
    `teachable:` 9) still derives `internal`. The trust contract is about
    external ORIGIN, not key spelling, so this IS a defect — it is deferred by
    MECHANISM (it needs a per-vault `external_keys:` config surface, which does
    not belong in a fix task), NOT by defect.

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
