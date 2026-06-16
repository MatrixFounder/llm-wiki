"""TASK 035 (R-X3-MF-SCAN, membership branch; ADR-005) — the metadata-only
`tags`-membership path narrows through the already-existing `pages_fts.tags`
index ("FTS narrows, json_each confirms") instead of scanning the partition.

The contract is **behaviour-preserving**: the result LIST (order included) must be
byte-identical to the plain scan. These tests prove that by running each filter
twice over the SAME input — once via the production FTS path, once via the private
`_use_fts_narrowing=False` seam that drives the REAL scan path — and asserting
equality across an adversarial tag corpus (M-arch-1), plus:
  * the EXPLAIN positive signature (pages_fts is the driving table) — R-1 / 035-00,
  * the FTS column-name is a fixed literal; a non-`tags` field never takes the FTS
    branch — R-1 / M-task-2,
  * the FTS-empty→scan safety net catches an isalnum-true / no-token value (`½`) and
    a literal-punctuation tag (`+`) — R-3 / M-arch-2,
  * the `json_each` confirm is load-bearing (a deterministic FTS over-match) — R-3 /
    M-plan-5,
  * composition with --as-of/--types/--project/2nd-where/--vault all — R-4,
  * injection via the tag value is inert — R-6,
  * a >limit ORDER-BY-boundary slice is identical — M-plan-4.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Page, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository

VAULT_ID = "fts-mem"
VAULT_B = "fts-mem-b"


def _page(slug: str, *, vault: str = VAULT_ID, project: str = "_vault_",
          tags: object = ("t",), body: str = "body", ptype: str = "concept",
          extra_fm: dict[str, object] | None = None,
          page_date: date | None = None) -> Page:
    fm: dict[str, object] = {"tags": list(tags) if isinstance(tags, tuple) else tags}
    if extra_fm:
        fm.update(extra_fm)
    return Page(
        vault_id=vault, slug=slug, project=project, type=ptype,
        title=slug.replace("-", " ").title(), file_path=f"_concepts/{vault}-{slug}.md",
        date=page_date or date(2026, 6, 1), last_modified=datetime(2026, 6, 1),
        file_hash=f"h-{vault}-{project}-{slug}", frontmatter_json=fm,
        body_excerpt=body, tags=["t"], tldr="tldr",
    )


# A corpus deliberately exercising every tokenization edge the FTS-superset claim
# must survive (M-arch-1). Each entry: (slug, tags-list).
_CORPUS: list[tuple[str, list[object]]] = [
    ("p-plain", ["decision", "eg"]),
    ("p-hyphen", ["AI-Agents"]),
    ("p-numlead", ["9-stadii"]),
    ("p-cyr", ["Идея"]),
    ("p-cyr-yo", ["ещё"]),
    ("p-upper", ["Decision"]),                  # case fold vs exact
    ("p-agent", ["agent"]),                      # substring-of "agents"/"AI-Agents"
    ("p-agents", ["agents"]),
    ("p-space", ["Product Marketing"]),          # interior whitespace / phrase
    ("p-quote", ['foo"bar']),                    # embedded double-quote
    ("p-backslash", ["foo\\bar"]),               # embedded backslash
    ("p-sev2", ["SEV-2"]),                        # tokenizes to sev + 2
    ("p-scalar", "scalardec"),                    # tags is a SCALAR, not a list
    ("p-punct", ["+"]),                           # zero-token (isalnum False)
    ("p-frac", ["½"]),                            # isalnum True, no unicode61 token
    ("p-multi", ["decision", "agents", "Идея"]),  # multi-member page
    ("p-mixed", ["Product Marketing", "decision"]),  # multi-WORD elem in a MULTI-elem array
    ("p-frac-mix", ["½", "decision"]),            # tokenless elem alongside a tokenizable sibling
]


@pytest.fixture
def repo(tmp_path: Path):
    r = SQLiteRepository(tmp_path / "fts-mem.db")
    r.apply_schema()
    for vid in (VAULT_ID, VAULT_B):
        r.register_vault(Vault(
            vault_id=vid, name=vid, root_path=tmp_path / vid,
            schema_version="7.0", registered_at=datetime(2026, 6, 1)))
    for slug, tags in _CORPUS:
        r.upsert_page(_page(slug, tags=tags, body=f"body of {slug}"))
    yield r
    r.close()


def _keys_fts(repo, value: str, **kw) -> list[tuple[str, str, str]]:
    hits = repo.search_pages(None, where_fields=[("tags", value)],
                             _use_fts_narrowing=True, **kw)
    return [(h.page.vault_id, h.page.project, h.page.slug) for h in hits]


def _keys_scan(repo, value: str, **kw) -> list[tuple[str, str, str]]:
    hits = repo.search_pages(None, where_fields=[("tags", value)],
                             _use_fts_narrowing=False, **kw)
    return [(h.page.vault_id, h.page.project, h.page.slug) for h in hits]


# =============================================================================
# R-1 / 035-00 — the FTS narrowing actually happens (positive plan signature)
# =============================================================================

def _trace(repo, **call) -> list[str]:
    conn = repo._connect()
    seen: list[str] = []
    conn.set_trace_callback(seen.append)
    try:
        repo.search_pages(**call)
    finally:
        conn.set_trace_callback(None)
    return seen


def test_metadata_only_tag_uses_fts_join(repo) -> None:
    seen = _trace(repo, query=None, where_fields=[("tags", "decision")],
                  vaults=[VAULT_ID])
    fts_stmts = [s for s in seen if "pages_fts MATCH" in s]
    assert fts_stmts, "metadata-only --tag did not take the pages_fts narrowing path"
    # Positive EXPLAIN signature: pages_fts is the driving (virtual) table.
    plan = repo._connect().execute(
        "EXPLAIN QUERY PLAN " + fts_stmts[0]).fetchall()
    plantext = " ".join(str(row[-1]) for row in plan)
    assert "pages_fts" in plantext


def test_non_tags_field_never_uses_fts(repo) -> None:
    # M-task-2: the FTS column name is a fixed literal `tags`; a non-tags scalar
    # field must NOT take the FTS branch (it has no FTS projection).
    seen = _trace(repo, query=None, where_fields=[("status", "open")],
                  vaults=[VAULT_ID])
    assert not any("pages_fts MATCH" in s for s in seen)


def test_fts_query_path_unchanged(repo) -> None:
    # A real FTS query + --tag stays on the body-MATCH path (json_each on the small
    # candidate set), NOT the tags-narrowing path — that branch is `has_match`.
    seen = _trace(repo, query="body", where_fields=[("tags", "decision")],
                  vaults=[VAULT_ID])
    fts = [s for s in seen if "pages_fts MATCH" in s]
    assert fts and all("tags :" not in s for s in fts)


# =============================================================================
# R-2 / M-arch-1 — result list byte-identical across the adversarial corpus
# =============================================================================

@pytest.mark.parametrize("value", [
    "decision", "AI-Agents", "9-stadii", "Идея", "ещё", "Decision", "decision",
    "agent", "agents", "Product Marketing", 'foo"bar', "foo\\bar", "SEV-2",
    "scalardec", "+", "½", "missing-tag", "ag", "AI", "2",
    # M-arch-1 / critic-logic MED: a multi-WORD element inside a MULTI-element
    # array, and a cross-element-boundary phrase that the confirm must reject.
    "Marketing decision", "decisionmarketing", "Marketing",
])
def test_fts_equals_scan(repo, value: str) -> None:
    assert _keys_fts(repo, value, vaults=[VAULT_ID]) == _keys_scan(repo, value, vaults=[VAULT_ID])


def test_non_str_tag_value_no_crash(repo) -> None:
    # vdd-multi critic-logic MED: a non-str library-caller value (int) crashed the
    # FTS path (`any(c.isalnum() for c in 7)` → TypeError) while the scan path bound
    # it into json_each fine. The isinstance guard sends non-str straight to scan →
    # both paths equal, no raise. (The CLI only ever sends str; this is the DAL
    # library-caller defense the docstring promises.)
    repo.upsert_page(_page("p-int", tags=[7], body="int tag"))
    fts = repo.search_pages(None, where_fields=[("tags", 7)], vaults=[VAULT_ID],
                            _use_fts_narrowing=True)
    scan = repo.search_pages(None, where_fields=[("tags", 7)], vaults=[VAULT_ID],
                             _use_fts_narrowing=False)
    keys = lambda hs: [(h.page.project, h.page.slug) for h in hs]
    assert keys(fts) == keys(scan) == [("_vault_", "p-int")]


def test_cross_element_boundary_phrase_rejected_by_confirm(repo) -> None:
    # critic-logic MED: `p-mixed` has tags ["Product Marketing", "decision"]. The
    # FTS text tokenizes to ...marketing decision... (adjacent across the JSON `,`),
    # so a phrase "Marketing decision" OVER-matches in FTS — but no page has that
    # exact tag element, so the json_each confirm must reject it. Both paths → [].
    assert _keys_fts(repo, "Marketing decision", vaults=[VAULT_ID]) == []
    assert _keys_scan(repo, "Marketing decision", vaults=[VAULT_ID]) == []


def test_tokenless_value_found_even_with_tokenizable_sibling(repo) -> None:
    # critic-logic LOW: prove the FTS-empty→scan net finds ALL `½`-tagged pages,
    # including p-frac-mix whose sibling `decision` IS tokenizable. The probe value
    # `½` yields no FTS token → FTS ∅ → scan fallback → both literal-`½` pages.
    assert {k[2] for k in _keys_fts(repo, "½", vaults=[VAULT_ID])} == {"p-frac", "p-frac-mix"}
    assert _keys_fts(repo, "½", vaults=[VAULT_ID]) == _keys_scan(repo, "½", vaults=[VAULT_ID])


def test_known_membership_results(repo) -> None:
    # Sanity: the equivalence isn't trivially "both empty". `decision` matches the
    # two pages carrying it as an exact member (p-plain, p-multi), and `Decision`
    # (capital) matches only its own page (exact, case-sensitive at the confirm).
    assert {k[2] for k in _keys_fts(repo, "decision", vaults=[VAULT_ID])} == {
        "p-plain", "p-multi", "p-mixed", "p-frac-mix"}
    assert {k[2] for k in _keys_fts(repo, "Decision", vaults=[VAULT_ID])} == {"p-upper"}
    assert {k[2] for k in _keys_fts(repo, "agents", vaults=[VAULT_ID])} == {"p-agents", "p-multi"}


# =============================================================================
# R-3 / M-arch-2 — the FTS-empty→scan safety net; confirm is load-bearing
# =============================================================================

def test_zero_token_punctuation_tag_still_found(repo) -> None:
    # `+` is isalnum-False → straight to scan; the literal-`+`-tagged page is found.
    assert {k[2] for k in _keys_fts(repo, "+", vaults=[VAULT_ID])} == {"p-punct"}


def test_isalnum_true_but_no_fts_token_safety_net(repo) -> None:
    # `½`.isalnum() is True (so the perf guard ATTEMPTS the FTS probe), but unicode61
    # yields no token → FTS ∅ → the empty→scan safety net (ADR-005 D3) re-runs the
    # scan and finds the literal-`½`-tagged page. This is the M-arch-2 hole.
    assert "½".isalnum()
    assert {k[2] for k in _keys_fts(repo, "½", vaults=[VAULT_ID])} == {"p-frac", "p-frac-mix"}


def test_confirm_is_load_bearing(repo) -> None:
    # A deterministic FTS over-match: `SEV-2` tokenizes to `sev`+`2`, so a raw FTS
    # column-match for the phrase "sev" matches the p-sev2 page — but no page has the
    # EXACT tag `sev`, so search_pages(tags=sev) must return []. This proves the
    # json_each confirm (not FTS alone) decides membership.
    conn = repo._connect()
    raw = conn.execute(
        "SELECT p.slug FROM pages_fts JOIN pages p ON pages_fts.rowid=p.id "
        "WHERE pages_fts MATCH ? AND p.vault_id=?", ('tags : "sev"', VAULT_ID)
    ).fetchall()
    assert "p-sev2" in {r[0] for r in raw}          # FTS alone over-matches
    assert _keys_fts(repo, "sev", vaults=[VAULT_ID]) == []   # confirm excludes it
    assert _keys_scan(repo, "sev", vaults=[VAULT_ID]) == []  # same as the scan


# =============================================================================
# R-6 — injection via the tag value is inert (phrase-quote + confirm)
# =============================================================================

@pytest.mark.parametrize("payload", [
    'a" OR pages_fts MATCH "b', "*", "tags:foo", "a OR b", "^decision",
    "decision NOT eg", 'x" ; DROP TABLE pages --',
    # critic-security optional: NUL / Unicode separators / trailing backslash —
    # all inert inside the doubled-quote phrase; pinned for parity with the scan.
    "a\x00b", "a b", "ab", "foo\\", 'tags : "decision',
])
def test_injection_value_is_inert(repo, payload: str) -> None:
    # No crash, and identical to the scan (which is itself injection-safe via the
    # bound json_each param). The FTS operators are neutralised by the phrase-quote.
    assert _keys_fts(repo, payload, vaults=[VAULT_ID]) == _keys_scan(repo, payload, vaults=[VAULT_ID])


# =============================================================================
# R-4 — composition with the other filters (each identical to the scan)
# =============================================================================

def test_compose_types(repo) -> None:
    for use in (True, False):
        hits = repo.search_pages(None, where_fields=[("tags", "decision")],
                                 types=["summary"], vaults=[VAULT_ID],
                                 _use_fts_narrowing=use)
        assert hits == []   # corpus is all type=concept
    assert (_keys_fts(repo, "decision", vaults=[VAULT_ID], types=["concept"])
            == _keys_scan(repo, "decision", vaults=[VAULT_ID], types=["concept"]))


def test_compose_project(repo) -> None:
    repo.upsert_page(_page("proj-dec", project="alpha", tags=["decision"]))
    assert (_keys_fts(repo, "decision", vaults=[VAULT_ID], project="alpha")
            == _keys_scan(repo, "decision", vaults=[VAULT_ID], project="alpha")
            == [(VAULT_ID, "alpha", "proj-dec")])


def test_compose_second_where_field(repo) -> None:
    repo.upsert_page(_page("dec-open", tags=["decision"], extra_fm={"status": "open"}))
    fts = repo.search_pages(None, where_fields=[("tags", "decision"), ("status", "open")],
                            vaults=[VAULT_ID], _use_fts_narrowing=True)
    scan = repo.search_pages(None, where_fields=[("tags", "decision"), ("status", "open")],
                             vaults=[VAULT_ID], _use_fts_narrowing=False)
    assert [h.page.slug for h in fts] == [h.page.slug for h in scan] == ["dec-open"]


def test_compose_vault_all_tiebreak(repo) -> None:
    # M-task-4 / R-4: a same (project, slug) in two vaults must tie-break by vault_id
    # identically under the FTS path (ORDER BY p.project, p.slug, p.vault_id).
    repo.upsert_page(_page("shared", vault=VAULT_ID, tags=["decision"]))
    repo.upsert_page(_page("shared", vault=VAULT_B, tags=["decision"]))
    # vaults=None → all vaults
    assert _keys_fts(repo, "decision") == _keys_scan(repo, "decision")


def test_compose_as_of(repo) -> None:
    # --tag + --as-of on the metadata-only path: the temporal clause rides along
    # unchanged; FTS-narrowed == scan. dec-v1 superseded by dec-v2 on 2026-05-01.
    repo.upsert_page(_page("dec-v1", tags=["decision"], page_date=date(2026, 1, 1)))
    repo.upsert_page(_page("dec-v2", tags=["decision"], page_date=date(2026, 5, 1)))
    conn = repo._connect()
    conn.execute(
        "INSERT INTO page_entity_refs (vault_id, page_slug, page_project, entity_slug, "
        "ref_type) VALUES (?,?,'_vault_',?,'superseded-by')", (VAULT_ID, "dec-v1", "dec-v2"))
    conn.commit()
    for as_of in ("2026-03-01", "2026-06-01"):
        assert (_keys_fts(repo, "decision", vaults=[VAULT_ID], as_of=as_of)
                == _keys_scan(repo, "decision", vaults=[VAULT_ID], as_of=as_of))


# =============================================================================
# M-plan-4 — >limit ORDER-BY boundary slice is identical
# =============================================================================

def test_limit_order_boundary(repo) -> None:
    for i in range(30):
        repo.upsert_page(_page(f"bulk-{i:02d}", project=f"pr{i % 3}", tags=["bulk"]))
    fts = repo.search_pages(None, where_fields=[("tags", "bulk")], vaults=[VAULT_ID],
                            limit=20, _use_fts_narrowing=True)
    scan = repo.search_pages(None, where_fields=[("tags", "bulk")], vaults=[VAULT_ID],
                             limit=20, _use_fts_narrowing=False)
    fk = [(h.page.project, h.page.slug) for h in fts]
    sk = [(h.page.project, h.page.slug) for h in scan]
    assert len(fk) == 20
    assert fk == sk            # identical top-20 slice AND order
    assert fk == sorted(fk)    # deterministic (project, slug) ordering preserved


def test_user_version_unchanged(repo) -> None:
    # TASK 035 is zero-DDL.
    assert repo._connect().execute("PRAGMA user_version").fetchone()[0] == 7
