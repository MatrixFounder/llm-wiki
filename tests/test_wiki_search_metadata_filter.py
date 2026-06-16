"""TASK 013 (R-X3-META-FILTER) — wiki-search frontmatter metadata filter.

Covers beads 013-00 (no-regression anchor), 013-01 (DAL `where_fields` +
query-less non-FTS path), 013-02 (CLI `--where`/`--status`/`--severity`).

The metadata filter compiles to a parameterized
`json_extract(frontmatter_json, '$.<field>') = ?` predicate over the already-
stored column (zero DDL); the field name is allow-list validated and the JSON
path + value are bound parameters (injection-safe). When no FTS query is given a
non-FTS listing ordered by (project, slug) is returned.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Page, Vault
from scripts.wiki_index.repository import validate_filter_field
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_search

VAULT_ID = "meta-vault"


def _page(slug: str, *, project: str = "_vault_", status: str | None = None,
          severity: str | None = None, body: str = "body text here",
          ptype: str = "concept", extra_fm: dict[str, object] | None = None) -> Page:
    fm: dict[str, object] = {"tags": ["t"]}
    if status is not None:
        fm["status"] = status
    if severity is not None:
        fm["severity"] = severity
    if extra_fm:
        fm.update(extra_fm)
    return Page(
        vault_id=VAULT_ID, slug=slug, project=project, type=ptype,
        title=slug.replace("-", " ").title(), file_path=f"_concepts/{slug}.md",
        date=date(2026, 6, 1), last_modified=datetime(2026, 6, 1),
        file_hash=f"h-{project}-{slug}", frontmatter_json=fm,
        body_excerpt=body, tags=["t"], tldr="tldr",
    )


@pytest.fixture
def repo(tmp_path: Path):
    r = SQLiteRepository(tmp_path / "meta.db")
    r.apply_schema()
    r.register_vault(Vault(
        vault_id=VAULT_ID, name="v", root_path=tmp_path / "v",
        schema_version="5.0", registered_at=datetime(2026, 6, 1),
    ))
    # 4 issue-like pages + 1 plain page with no status frontmatter.
    r.upsert_page(_page("issue-a", status="open", severity="SEV-2",
                        body="alpha drift problem"))
    r.upsert_page(_page("issue-b", status="open", severity="SEV-3",
                        body="beta walk cost"))
    r.upsert_page(_page("issue-c", status="fixed", severity="SEV-2",
                        body="gamma resolved"))
    r.upsert_page(_page("issue-d", status="open", body="delta no severity"))
    r.upsert_page(_page("plain-note", body="just a source with drift mention"))
    # Numeric + boolean frontmatter values (stored as JSON int/bool, not text).
    # No `status` so this page stays out of the status=open assertions above.
    r.upsert_page(_page("issue-num",
                        extra_fm={"priority": 1, "blocking": True},
                        body="numeric frontmatter page"))
    yield r
    r.close()


# =============================================================================
# 013-00 — no-regression anchor
# =============================================================================

def test_no_flag_fts_search_unchanged(repo) -> None:
    """Adding `where_fields` (default None) does not alter the plain FTS path."""
    hits = repo.search_pages("drift")
    slugs = {h.page.slug for h in hits}
    assert slugs == {"issue-a", "plain-note"}
    # bm25 score is still a real float on the FTS path.
    assert all(isinstance(h.bm25_score, float) for h in hits)


# =============================================================================
# 013-01 — DAL where_fields + query-less path
# =============================================================================

def test_where_fields_filter_by_status(repo) -> None:
    hits = repo.search_pages(None, where_fields=[("status", "open")])
    assert {h.page.slug for h in hits} == {"issue-a", "issue-b", "issue-d"}


def test_where_fields_and_semantics(repo) -> None:
    hits = repo.search_pages(
        None, where_fields=[("status", "open"), ("severity", "SEV-2")])
    assert {h.page.slug for h in hits} == {"issue-a"}


def test_where_field_absent_excludes_page(repo) -> None:
    # issue-d has no `severity` → json_extract NULL → excluded, no error.
    hits = repo.search_pages(None, where_fields=[("severity", "SEV-3")])
    assert {h.page.slug for h in hits} == {"issue-b"}


def test_where_hyphenated_value_is_equality_not_fts(repo) -> None:
    # `SEV-2` would be an invalid FTS expression; equality path handles it fine.
    hits = repo.search_pages(None, where_fields=[("severity", "SEV-2")])
    assert {h.page.slug for h in hits} == {"issue-a", "issue-c"}


def test_query_less_listing_ordered_by_project_slug(repo) -> None:
    repo.upsert_page(_page("aaa", project="zproj", status="open"))
    repo.upsert_page(_page("zzz", project="aproj", status="open"))
    hits = repo.search_pages(None, where_fields=[("status", "open")])
    ordered = [(h.page.project, h.page.slug) for h in hits]
    assert ordered == sorted(ordered)  # (project, slug) ascending


def test_query_less_bm25_is_zero(repo) -> None:
    hits = repo.search_pages(None, where_fields=[("status", "open")])
    assert all(h.bm25_score == 0.0 and h.snippet == "" for h in hits)


def test_fts_query_plus_where_fields_intersect(repo) -> None:
    # "drift" matches issue-a + plain-note; status=open keeps only issue-a.
    hits = repo.search_pages("drift", where_fields=[("status", "open")])
    assert {h.page.slug for h in hits} == {"issue-a"}


def test_both_empty_raises(repo) -> None:
    with pytest.raises(ValueError):
        repo.search_pages(None)
    with pytest.raises(ValueError):
        repo.search_pages("", where_fields=[])


def test_dal_rejects_invalid_field(repo) -> None:
    with pytest.raises(ValueError):
        repo.search_pages(None, where_fields=[("a;DROP TABLE pages", "x")])


def test_dal_value_is_parameterized_no_injection(repo) -> None:
    # A SQL/JSON-path payload in the VALUE is a bound param → 0 rows, no error.
    hits = repo.search_pages(None, where_fields=[("status", "open' OR '1'='1")])
    assert hits == []


def test_validate_filter_field_allowlist() -> None:
    assert validate_filter_field("status") == "status"
    assert validate_filter_field("trust_level") == "trust_level"
    # vdd-multi critic-security LOW: trailing/embedded newlines must be rejected
    # (fullmatch, not .match+`$` which matches before a trailing \n).
    for bad in ["Status", "a-b", "a.b", "$.x", "a b", "", "1abc", "a'b",
                "status\n", "a\nb", "status\t", " status"]:
        with pytest.raises(ValueError):
            validate_filter_field(bad)


def test_where_matches_numeric_frontmatter_value(repo) -> None:
    # `priority: 1` is stored as a JSON integer; the CAST(... AS TEXT) makes the
    # string filter "1" match it (without the cast, INTEGER 1 != TEXT '1').
    hits = repo.search_pages(None, where_fields=[("priority", "1")])
    assert {h.page.slug for h in hits} == {"issue-num"}
    # A non-matching numeric value still excludes correctly.
    assert repo.search_pages(None, where_fields=[("priority", "2")]) == []


def test_where_matches_boolean_frontmatter_as_int(repo) -> None:
    # JSON `true` is extracted as SQLite integer 1 → CAST AS TEXT '1'. This
    # documents the representation: filter with "1"/"0", not "true"/"false".
    assert {h.page.slug for h in repo.search_pages(
        None, where_fields=[("blocking", "1")])} == {"issue-num"}
    assert repo.search_pages(None, where_fields=[("blocking", "true")]) == []


def test_where_string_value_still_byte_identical(repo) -> None:
    # The CAST must not change string matching (the common status/severity case).
    assert {h.page.slug for h in repo.search_pages(
        None, where_fields=[("severity", "SEV-2")])} == {"issue-a", "issue-c"}


def test_query_less_ordering_tiebreak_by_vault_id(repo) -> None:
    # vdd-multi critic-logic LOW: identical (project, slug) in two vaults must
    # order deterministically by vault_id. (Single-vault repo here, but the
    # ORDER BY now includes vault_id; assert full-identity sort.)
    hits = repo.search_pages(None, where_fields=[("status", "open")])
    keys = [(h.page.project, h.page.slug, h.page.vault_id) for h in hits]
    assert keys == sorted(keys)


def test_user_version_unchanged(repo) -> None:
    # The metadata filter (TASK 013/033) is itself zero-DDL; the live schema pin
    # advanced to 7 in TASK 034 (an unrelated edge-set bump in the same DDL file).
    ver = repo._connect().execute("PRAGMA user_version").fetchone()[0]
    assert ver == 7


# =============================================================================
# 013-02 — CLI surface
# =============================================================================

def _hits(capsys) -> set[str]:
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    return {h["slug"] for h in out["hits"]}


def _payload(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_cli_status_sugar(repo, capsys) -> None:
    rc = wiki_search.main(["--status", "open", "--vaults", VAULT_ID,
                           "--db-path", str(repo.db_path)])
    assert rc == 0
    assert _hits(capsys) == {"issue-a", "issue-b", "issue-d"}


def test_cli_where_repeatable_and(repo, capsys) -> None:
    rc = wiki_search.main(["--where", "status=open", "--where", "severity=SEV-2",
                           "--vaults", VAULT_ID, "--db-path", str(repo.db_path)])
    assert rc == 0
    assert _hits(capsys) == {"issue-a"}


def test_cli_severity_hyphen_sugar(repo, capsys) -> None:
    rc = wiki_search.main(["--severity", "SEV-2", "--vaults", VAULT_ID,
                           "--db-path", str(repo.db_path)])
    assert rc == 0
    assert _hits(capsys) == {"issue-a", "issue-c"}


def test_cli_fts_query_plus_status(repo, capsys) -> None:
    rc = wiki_search.main(["drift", "--status", "open", "--vaults", VAULT_ID,
                           "--db-path", str(repo.db_path)])
    assert rc == 0
    assert _hits(capsys) == {"issue-a"}


def test_cli_malformed_where_no_equals(repo, capsys) -> None:
    rc = wiki_search.main(["--where", "statusopen", "--vaults", VAULT_ID,
                           "--db-path", str(repo.db_path)])
    assert rc == 2
    assert _payload(capsys)["error"] == "INVALID_FILTER"


def test_cli_invalid_field(repo, capsys) -> None:
    rc = wiki_search.main(["--where", "bad field=open", "--vaults", VAULT_ID,
                           "--db-path", str(repo.db_path)])
    assert rc == 2
    assert _payload(capsys)["error"] == "INVALID_FILTER"


def test_cli_bare_no_query_no_filter(repo, capsys) -> None:
    rc = wiki_search.main(["--vaults", VAULT_ID, "--db-path", str(repo.db_path)])
    assert rc == 2
    assert _payload(capsys)["error"] == "INVALID_QUERY"


def test_cli_envelope_never_echoes_value(repo, capsys) -> None:
    secret = "TOPSECRETVALUE123"
    rc = wiki_search.main(["--where", f"bad field={secret}", "--vaults", VAULT_ID,
                           "--db-path", str(repo.db_path)])
    assert rc == 2
    raw = capsys.readouterr().out
    assert secret not in raw  # CWE-209/117: the value is never echoed


def test_cli_duplicate_field_status_and_where_rejected(repo, capsys) -> None:
    # vdd-multi critic-logic MED: --status open + --where 'status=fixed' would
    # silently never match → INVALID_FILTER instead.
    rc = wiki_search.main(["--status", "open", "--where", "status=fixed",
                           "--vaults", VAULT_ID, "--db-path", str(repo.db_path)])
    assert rc == 2
    payload = _payload(capsys)
    assert payload["error"] == "INVALID_FILTER"
    assert payload["field"] == "status"


def test_cli_duplicate_where_field_rejected(repo, capsys) -> None:
    rc = wiki_search.main(["--where", "severity=SEV-2", "--where", "severity=SEV-3",
                           "--vaults", VAULT_ID, "--db-path", str(repo.db_path)])
    assert rc == 2
    assert _payload(capsys)["error"] == "INVALID_FILTER"


def test_cli_where_composes_with_types(repo, capsys) -> None:
    # All pages are type=concept here; a non-matching --types yields nothing.
    rc = wiki_search.main(["--status", "open", "--types", "summary",
                           "--vaults", VAULT_ID, "--db-path", str(repo.db_path)])
    assert rc == 0
    assert _hits(capsys) == set()


def test_cli_no_flag_search_schema_unchanged(repo, capsys) -> None:
    rc = wiki_search.main(["drift", "--vaults", VAULT_ID,
                           "--db-path", str(repo.db_path)])
    assert rc == 0
    payload = _payload(capsys)
    assert payload["action"] == "searched"
    assert payload["query"] == "drift"
    assert set(payload["hits"][0].keys()) == {
        "vault_id", "slug", "project", "type", "title", "bm25_score", "snippet"}


# =============================================================================
# TASK 033 — list-membership predicate (033-00 DAL) + --tag sugar (033-01 CLI)
# =============================================================================

@pytest.fixture
def tagrepo(repo):
    """The shared `repo` plus typed-class pages whose `tags[]` carries the class
    (the TASK-031 routing) — for list-membership assertions."""
    repo.upsert_page(_page("dec-rabbitmq", extra_fm={"tags": ["eg-demo", "decision"]},
                           body="use rabbitmq broker"))
    repo.upsert_page(_page("dec-kafka", extra_fm={"tags": ["eg-demo", "decision"]},
                           body="switch to kafka broker"))
    repo.upsert_page(_page("risk-spof", extra_fm={"tags": ["eg-demo", "risk"]},
                           body="single point of failure"))
    return repo


def test_where_list_membership_matches_member(tagrepo) -> None:
    # AC-1: `tags=decision` matches a MEMBER of tags[]; the risk page is excluded.
    hits = tagrepo.search_pages(None, where_fields=[("tags", "decision")])
    assert {h.page.slug for h in hits} == {"dec-rabbitmq", "dec-kafka"}


def test_where_membership_and_scalar_backcompat_same_block(tagrepo) -> None:
    # B-1 (arch-review): the SAME predicate code must serve list-membership AND
    # keep scalar equality byte-identical — asserted together so a swapped
    # (path,value,path,value) param order can't pass one half silently.
    membership = {h.page.slug for h in tagrepo.search_pages(
        None, where_fields=[("tags", "risk")])}
    scalar = {h.page.slug for h in tagrepo.search_pages(
        None, where_fields=[("status", "open")])}
    assert membership == {"risk-spof"}                       # list member
    assert scalar == {"issue-a", "issue-b", "issue-d"}        # scalar unchanged


def test_where_membership_absent_field_excludes(tagrepo) -> None:
    # A page with no `tags` member 'decision' (and the fixture pages whose tags
    # are ["t"]) are excluded; json_each over the absent/non-matching list → 0 rows.
    hits = tagrepo.search_pages(None, where_fields=[("tags", "decision")])
    assert "plain-note" not in {h.page.slug for h in hits}
    assert "issue-a" not in {h.page.slug for h in hits}


def test_where_membership_plus_scalar_anded(tagrepo) -> None:
    # AND across a membership field and a scalar field, both bound correctly.
    tagrepo.upsert_page(_page("dec-open", status="open",
                              extra_fm={"tags": ["decision"]}, body="open decision"))
    hits = tagrepo.search_pages(
        None, where_fields=[("tags", "decision"), ("status", "open")])
    assert {h.page.slug for h in hits} == {"dec-open"}


def test_where_scalar_cast_still_matches_numeric(tagrepo) -> None:
    # M-1 guard: the scalar CAST branch is retained, so numeric `priority: 1`
    # still matches "1" (the membership branch is additive, not a replacement).
    assert {h.page.slug for h in tagrepo.search_pages(
        None, where_fields=[("priority", "1")])} == {"issue-num"}


def test_cli_tag_sugar_equals_where_tags(tagrepo, capsys) -> None:
    # AC-2: --tag decision ≡ --where tags=decision (via the CLI main).
    rc = wiki_search.main(["--tag", "decision", "--vaults", VAULT_ID,
                           "--db-path", str(tagrepo.db_path)])
    assert rc == 0
    via_tag = _hits(capsys)
    rc = wiki_search.main(["--where", "tags=decision", "--vaults", VAULT_ID,
                           "--db-path", str(tagrepo.db_path)])
    assert rc == 0
    assert via_tag == _hits(capsys) == {"dec-rabbitmq", "dec-kafka"}


def test_cli_tag_dup_with_where_tags_rejected(tagrepo, capsys) -> None:
    # AC-4: --tag x + --where tags=y → one-predicate-per-field guard fires.
    rc = wiki_search.main(["--tag", "decision", "--where", "tags=risk",
                           "--vaults", VAULT_ID, "--db-path", str(tagrepo.db_path)])
    assert rc == 2
    payload = _payload(capsys)
    assert payload["error"] == "INVALID_FILTER"
    assert payload["field"] == "tags"


def test_cli_tag_no_value_echo_on_bad_combo(tagrepo, capsys) -> None:
    # The dup-guard envelope names only the field, never a value.
    rc = wiki_search.main(["--tag", "SECRETTAG", "--where", "tags=OTHER",
                           "--vaults", VAULT_ID, "--db-path", str(tagrepo.db_path)])
    assert rc == 2
    raw = capsys.readouterr().out
    assert "SECRETTAG" not in raw and "OTHER" not in raw


def test_cli_tag_plus_fts_and_types(tagrepo, capsys) -> None:
    # AC-6: --tag combines with an FTS query (AND-ed). "rabbitmq" + tag=decision.
    rc = wiki_search.main(["rabbitmq", "--tag", "decision", "--vaults", VAULT_ID,
                           "--db-path", str(tagrepo.db_path)])
    assert rc == 0
    assert _hits(capsys) == {"dec-rabbitmq"}


def test_cli_tag_no_query_listing(tagrepo, capsys) -> None:
    # AC-6 (listing path): --tag with no FTS query → non-FTS listing.
    rc = wiki_search.main(["--tag", "risk", "--vaults", VAULT_ID,
                           "--db-path", str(tagrepo.db_path)])
    assert rc == 0
    assert _hits(capsys) == {"risk-spof"}
