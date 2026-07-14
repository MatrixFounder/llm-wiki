"""★ TASK 064 / F10 — `wiki-lint`'s `near-duplicate-concept` category.

THE GAP IT CLOSES. The very pairs the extractor's near-duplicate metric was calibrated ON
are sitting on disk in the operator's 720-page vault RIGHT NOW — `виталик-бутерин` /
`vitalik-buterin`, `сатоши-накамото` / `сатоси-накамото`, `бессрочный-фьючерс` /
`бессрочные-фьючерсы` — and `wiki-lint --strict` was **GREEN over every one of them**. Its
only duplicate check is `cross-vault-duplicate`: EXACT slug, ACROSS vaults, severity `info`.
It catches 0 of 5. So a gate could stop tomorrow's split while today's stayed unenumerable,
and `wiki-merge` — the correct repair — had no work queue to draw from. This is that queue.

★★ AND IT MUST NEVER GATE `--strict`. That is a SAFETY property, not a preference, and it is
the reason this file exists rather than a single detection test. The metric behind the
category is ANTI-CORRELATED WITH MEANING — it scores `централизация`/`децентрализация` at
0.941 and `serialization`/`deserialization` at 0.929, i.e. it rates ANTONYMS as harder
duplicates than the real live pair it was built for (0.927). Gating CI on it would fail
every rail over pairs of concepts that are OPPOSITES. The same measurement demoted the
extractor's own gate from a refusal to an advisory (F2); the lint category inherits that
demotion, and `test_never_gates_strict_even_though_it_reports` is what keeps it inherited.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_index.lint import (
    NEAR_DUPLICATE_CATEGORY,
    check_near_duplicate_concepts,
)
from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_lint import main as lint_main

# The operator's REAL live splits. `виталик-бутерин`/`vitalik-buterin` is the load-bearing
# one: the two are 100% dissimilar as raw strings — no character-ratio metric will EVER
# relate them — and identical once transliterated. If the category ever stops keying on the
# transliterated form, that pair goes back to being invisible and this test says so.
_DUP_PAIRS = [
    ("виталик-бутерин", "vitalik-buterin"),
    ("бессрочный-фьючерс", "бессрочные-фьючерсы"),
]
# Concepts that must NOT be reported against each other (they are unrelated, not near-dups).
_DISTINCT = ["ликвидация", "оракул"]


def _seed(tmp_path: Path, slugs: list[str], *, vault_id: str = "dupv",
          ) -> tuple[SQLiteRepository, Path]:
    root = tmp_path / "vault"
    (root / "_concepts").mkdir(parents=True)
    (root / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: dupv\nschema_version: "2.0"\nlanguage: ru\nlayout: karpathy\n---\n',
        encoding="utf-8")
    for slug in slugs:
        (root / "_concepts" / f"{slug}.md").write_text(
            f"---\ntype: concept\nname: {slug}\n---\n\n# {slug}\n", encoding="utf-8")
    repo = SQLiteRepository(tmp_path / "d.db")
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=vault_id, name=vault_id, root_path=root,
                              schema_version="2.0", registered_at=datetime(2026, 7, 14)))
    # Index through the REAL indexer, not hand-rolled `pages` rows: a fake `file_hash` would
    # light up `hash-mismatch` and this file would then be asserting the exit code of a
    # DIFFERENT check than the one it is about.
    assert reindex_full(repo, vault_id)["skipped"] == []
    return repo, root


def _run_lint(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict[str, Any]]:
    rc = lint_main(argv)
    out = capsys.readouterr().out.strip().splitlines()[-1]
    return rc, json.loads(out)


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #

def test_finds_the_live_splits_including_the_cross_script_one(tmp_path: Path) -> None:
    """★ The pairs `wiki-lint --strict` was green over. The cross-script pair is the proof
    the check keys on the TRANSLITERATED form and not on raw string similarity."""
    slugs = [s for pair in _DUP_PAIRS for s in pair] + _DISTINCT
    repo, _ = _seed(tmp_path, slugs)
    try:
        issues = check_near_duplicate_concepts(repo, "dupv")
    finally:
        repo.close()

    found = {frozenset((i.page_slug, str(i.details["duplicate_of"]))) for i in issues}
    for a, b in _DUP_PAIRS:
        assert frozenset((a, b)) in found, f"{a}/{b} still invisible to wiki-lint"

    # …and it does not cry wolf over unrelated concepts.
    reported = {s for i in issues for s in (i.page_slug, str(i.details["duplicate_of"]))}
    assert not (set(_DISTINCT) & reported), reported


def test_severity_is_warning_and_the_hint_points_at_wiki_merge(tmp_path: Path) -> None:
    """It is a work queue for a HUMAN wielding `wiki-merge`, so it must say so — and it must
    say the other half too: string similarity cannot tell an antonym from a plural."""
    repo, _ = _seed(tmp_path, [*_DUP_PAIRS[0]])
    try:
        issues = check_near_duplicate_concepts(repo, "dupv")
    finally:
        repo.close()
    assert len(issues) == 1
    (issue,) = issues
    assert issue.category == NEAR_DUPLICATE_CATEGORY
    assert issue.severity == "warning"
    assert "wiki-merge" in issue.details["hint"]
    assert 0.0 < float(issue.details["similarity"]) <= 1.0


def test_a_clean_vault_reports_nothing(tmp_path: Path) -> None:
    repo, _ = _seed(tmp_path, _DISTINCT)
    try:
        assert check_near_duplicate_concepts(repo, "dupv") == []
    finally:
        repo.close()


# --------------------------------------------------------------------------- #
# ★★ THE SAFETY PROPERTY: it REPORTS, and it NEVER GATES.
# --------------------------------------------------------------------------- #

def test_never_gates_strict_even_though_it_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """★★ THE ONE THAT MUST NOT REGRESS.

    A vault whose ONLY lint issues are near-duplicates must still exit **0** under
    `--strict`. If this ever flips, every CI rail in the project starts failing over pairs
    of concepts that are OPPOSITES (`централизация`/`децентрализация` scores 0.941), because
    the metric is anti-correlated with meaning. Reporting and gating are different jobs, and
    conflating them is how an advisory becomes a bypass.

    Note what is asserted: the issues are PRESENT in the envelope (so this is not passing
    merely because nothing was found) AND the exit code is 0.
    """
    repo, root = _seed(tmp_path, [s for pair in _DUP_PAIRS for s in pair])
    repo.close()

    rc, out = _run_lint(capsys, [
        "--vault", "dupv", "--vault-root", str(root),
        "--db-path", str(tmp_path / "d.db"), "--strict",
    ])

    near = out["by_category"].get(NEAR_DUPLICATE_CATEGORY, 0)
    assert near >= len(_DUP_PAIRS), (
        f"the category vanished from the report — it must still REPORT: {out['by_category']}")
    assert out["total_issues"] >= near          # counted, not swept under the rug
    assert rc == 0, (
        "near-duplicate-concept must NEVER gate --strict: the metric rates ANTONYMS as "
        f"duplicates, so gating CI on it breaks every rail. Got rc={rc}, out={out}")


def test_the_exclusion_is_not_a_blanket_strict_bypass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """The mirror of the above, and the reason it is safe: excluding ONE advisory category
    must not disarm `--strict` in general. A genuinely gating issue alongside the
    near-duplicates must still exit 1 — otherwise the F10 fix would have quietly turned the
    CI rail off, which is a far worse bug than the one it set out to fix.

    `missing-on-disk` is the gating issue here: a `pages` row whose file was deleted.
    """
    repo, root = _seed(tmp_path, [s for pair in _DUP_PAIRS for s in pair])
    repo.close()
    # Delete one concept's FILE but leave its `pages` row → a real, gating lint issue.
    (root / "_concepts" / "vitalik-buterin.md").unlink()

    rc, out = _run_lint(capsys, [
        "--vault", "dupv", "--vault-root", str(root),
        "--db-path", str(tmp_path / "d.db"), "--strict",
    ])

    cats = {c for c, n in out["by_category"].items() if n}
    assert NEAR_DUPLICATE_CATEGORY in cats          # still reported…
    assert cats - {NEAR_DUPLICATE_CATEGORY}, f"expected a gating issue to coexist: {cats}"
    assert rc == 1, f"--strict must still gate on real issues; categories={cats}"
