"""TASK 019 — end-to-end acceptance for the `wiki-sync` re-summarization policy,
over a self-contained fixture mirroring the operator's `samples/Demand-generation`
shape (patterns A group-key, B same-dir stem, C date-key + D2a provenance).

Durable + committed (the live `samples/` tree is gitignored scratch). Exercises the
FULL `_build_entries` pipeline: classify → policy gate → plan, plus `--force` and the
re-run no-op (AC-5/6/9).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.models import Page, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_index.sync_config import load_sync_config
from scripts.wiki_skills.wiki_sync import _build_entries, _hash_file
import re

VID = "demand-gen"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _repo(tmp_path: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=VID, name=VID, root_path=tmp_path,
        schema_version="5.0", registered_at=datetime(2026, 6, 7),
    ))
    return repo


def _mk(p: Path, text: str = "body") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _yaml(d: Path, text: str) -> None:
    (d / ".wiki").mkdir(parents=True, exist_ok=True)
    (d / ".wiki" / "sync.yaml").write_text(text, encoding="utf-8")


def _summary_page(repo: SQLiteRepository, slug: str, sources: list[str]) -> None:
    repo.upsert_page(Page(
        vault_id=VID, slug=slug, project="_vault_", type="summary", title=slug,
        file_path=f"Module-01/Summary/{slug}.md", date=None,
        last_modified=datetime(2026, 6, 7), file_hash="h-" + slug,
        frontmatter_json={"sources": sources}, body_excerpt="", tags=[],
    ))


def _plan(repo: SQLiteRepository, tmp_path: Path, zone: Path, *, force: bool = False):
    cfg = load_sync_config(tmp_path)
    layout = resolve_layout_config(tmp_path)
    return {e["path"]: e for e in
            _build_entries(repo, VID, zone, tmp_path, cfg, layout, force=force)}


def test_e2e_provenance_zone(tmp_path: Path) -> None:
    """D2a: an indexed summary citing N transcripts → those transcripts skip;
    re-run is a no-op; `--force` re-arms them."""
    repo = _repo(tmp_path)
    _yaml(tmp_path,
          "resummarize:\n  mode: if-missing\n  detect:\n"
          "    source_state: false\n    provenance_ref:\n      enabled: true\n")
    mod = tmp_path / "Module-01"
    _mk(mod / "Transcripts" / "02-1.txt")
    _mk(mod / "Transcripts" / "02-2.txt")
    _summary_page(repo, "02 - Решение vs транзакция",
                  ["Module-01/Transcripts/02-1.txt", "Module-01/Transcripts/02-2.txt"])

    by = _plan(repo, tmp_path, mod)
    for rel in ("Module-01/Transcripts/02-1.txt", "Module-01/Transcripts/02-2.txt"):
        assert by[rel]["action"] == "skip"
        assert by[rel]["reason"] == "summary-exists:provenance"

    # re-run is a byte-identical no-op
    assert _plan(repo, tmp_path, mod) == by

    # --force re-arms every raw
    forced = _plan(repo, tmp_path, mod, force=True)
    for rel in ("Module-01/Transcripts/02-1.txt", "Module-01/Transcripts/02-2.txt"):
        assert forced[rel]["action"] == "ingest" and forced[rel]["reason"] == "forced"


def test_e2e_mirror_group_key_zone(tmp_path: Path) -> None:
    """D2b group-key (pattern A): transcripts share a lesson number with a summary."""
    repo = _repo(tmp_path)
    mod = tmp_path / "Module-01"
    _yaml(mod,
          "resummarize:\n  mode: if-missing\n  detect:\n    source_state: false\n"
          "    mirror:\n      enabled: true\n      raw_dirs: [Transcripts]\n"
          "      summary_dir: Summary\n      match: group-key\n      group_key: '^(\\d+)'\n")
    _mk(mod / "Transcripts" / "02-1 Решение.txt")
    _mk(mod / "Transcripts" / "08-1 New.txt")            # no `08 - …` summary
    _mk(mod / "Summary" / "02 - Решение vs транзакция.md")

    by = _plan(repo, tmp_path, mod / "Transcripts")
    assert by["Module-01/Transcripts/02-1 Решение.txt"]["reason"] == "summary-exists:mirror"
    assert by["Module-01/Transcripts/08-1 New.txt"]["action"] == "ingest"  # uncovered


def test_e2e_same_dir_stem(tmp_path: Path) -> None:
    """D2b stem-relpath same-dir (pattern B): `Resources/X.docx` ↔ `Resources/X.md`."""
    repo = _repo(tmp_path)
    res = tmp_path / "Module-04" / "Resources"
    _yaml(tmp_path / "Module-04",
          "resummarize:\n  mode: if-missing\n  detect:\n    source_state: false\n"
          "    mirror:\n      enabled: true\n      raw_dirs: [Resources]\n"
          "      summary_dir: '.'\n      match: stem-relpath\n")
    _mk(res / "Алгоритм.docx")
    _mk(res / "Алгоритм.md")
    _mk(res / "Orphan.pdf")

    by = _plan(repo, tmp_path, res)
    assert by["Module-04/Resources/Алгоритм.docx"]["reason"] == "summary-exists:mirror"
    assert by["Module-04/Resources/Orphan.pdf"]["action"] == "convert+ingest"  # uncovered


# ---------------------------------------------------------------------------
# TASK 051 / R-18 (051-03) — `if-changed` mode at the scan layer
# ---------------------------------------------------------------------------


def test_e2e_if_changed_unchanged_skips_no_delegate(tmp_path: Path) -> None:
    """051-03: `if-changed` — a marker file whose recorded `source_state` hash
    matches the file plans `skip:summary-unchanged` with NO `delegate` emitted;
    `--force` re-arms it."""
    repo = _repo(tmp_path)
    _yaml(tmp_path, "resummarize:\n  mode: if-changed\n")
    mod = tmp_path / "Module-01"
    raw = mod / "Transcripts" / "02-1.txt"
    _mk(raw, "body")
    rel = "Module-01/Transcripts/02-1.txt"
    repo.set_source_state(VID, "sync", rel, "source_hash", _hash_file(raw))

    by = _plan(repo, tmp_path, mod)
    assert by[rel]["action"] == "skip"
    assert by[rel]["reason"] == "summary-unchanged"
    assert "delegate" not in by[rel]

    forced = _plan(repo, tmp_path, mod, force=True)
    assert forced[rel]["action"] == "ingest" and forced[rel]["reason"] == "forced"


def test_e2e_if_changed_changed_reingests(tmp_path: Path) -> None:
    """051-03: a source whose content changed since the recorded hash re-summarises
    (ingest + delegate)."""
    repo = _repo(tmp_path)
    _yaml(tmp_path, "resummarize:\n  mode: if-changed\n")
    mod = tmp_path / "Module-01"
    raw = mod / "Transcripts" / "02-1.txt"
    _mk(raw, "NEW body")
    rel = "Module-01/Transcripts/02-1.txt"
    repo.set_source_state(VID, "sync", rel, "source_hash", "stale-hash-value")

    by = _plan(repo, tmp_path, mod)
    assert by[rel]["action"] == "ingest"
    assert "delegate" in by[rel]


def test_e2e_if_changed_markerless_ingests(tmp_path: Path) -> None:
    """051-03: no recorded hash → ingest (never a `None == None` silent skip)."""
    repo = _repo(tmp_path)
    _yaml(tmp_path, "resummarize:\n  mode: if-changed\n")
    mod = tmp_path / "Module-01"
    _mk(mod / "Transcripts" / "02-1.txt")
    by = _plan(repo, tmp_path, mod)
    assert by["Module-01/Transcripts/02-1.txt"]["action"] == "ingest"


def test_e2e_if_changed_upsert_keeps_source_hash(tmp_path: Path) -> None:
    """051-03 (plan-review MAJOR-1): the hoist-fallback preserves `source_hash` +
    `is_unchanged` on a non-ACTIONABLE `upsert` (ready-note) entry — the hoist for
    ACTIONABLE candidates must NOT strip the executor's upsert marker."""
    repo = _repo(tmp_path)
    _yaml(tmp_path, "resummarize:\n  mode: if-changed\n")
    mod = tmp_path / "Module-01"
    ready = mod / "note.md"
    _mk(ready, "---\ntype: lesson-summary\n---\n\na real ready-note body with content")
    rel = "Module-01/note.md"

    by = _plan(repo, tmp_path, mod)
    assert by[rel]["action"] == "upsert"
    assert _HEX64.match(by[rel]["source_hash"] or "")
    assert by[rel]["is_unchanged"] is False  # no marker yet

    repo.set_source_state(VID, "sync", rel, "source_hash", _hash_file(ready))
    by2 = _plan(repo, tmp_path, mod)
    assert by2[rel]["is_unchanged"] is True
