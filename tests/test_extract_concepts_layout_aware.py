"""TASK 037 — `wiki-extract-concepts` is layout-aware (PARA `_concepts/` support).

The pilot (article import into a real obsidian-personal vault) surfaced that
extract-concepts hard-required the Karpathy `_sources/` layout and refused a PARA
note in its native folder. TASK 037 makes it layout-aware, mirroring TASK 024 for
`wiki-index-upsert`. These tests pin:

  R-1  PARA source resolution by vault-relative path (slug via the layout
       slug_strategy, so it equals `pages.slug`).
  R-2  H-1 anti-loop: a source inside a generated dir (`_concepts/` …) is refused.
  R-3  concept pages land in the source note's own `<folder>/_concepts/` for PARA;
       Karpathy stays `parent.parent/_concepts` (byte-identical).
  R-4  `_all_concepts_dirs` finds nested PARA `_concepts/` dirs.
  R-5  entity `file_path` + manifest `path` carry the REAL vault-relative path.
  R-6  obsidian-personal indexes the generated concept page as db_type concept
       (no UnmappedTypeError) AND its slug resolves the source's inbound wikilink.
  Karpathy golden anchor: vault-tier concepts_rel == "_concepts" (unchanged).
  Unicode: a Cyrillic concept slug round-trips end-to-end.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills.wiki_extract_concepts import _sourcing
from scripts.wiki_skills.wiki_extract_concepts._validation import _is_valid_slug


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _schema(root: Path, vault_id: str, layout: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "WIKI_SCHEMA.md").write_text(
        f'---\nvault_id: {vault_id}\nschema_version: "2.0"\nlanguage: ru\n'
        f'layout: {layout}\n---\n', encoding="utf-8")


def _make_repo(db_path: Path, vault_id: str, root: Path) -> SQLiteRepository:
    repo = SQLiteRepository(db_path)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=vault_id, name=vault_id, root_path=root,
        schema_version="2.0", registered_at=datetime(2026, 6, 17)))
    return repo


def _run(*args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.wiki_skills.wiki_extract_concepts", *args],
        input=stdin, capture_output=True, check=False,
    )


def _candidate(slug: str, name: str, quote: str) -> dict:
    return {
        "slug": slug, "name": name, "definition": f"{name} — определение.",
        "source_quote": quote, "source_span": "L3-L3", "entity_type": "concept",
    }


# --------------------------------------------------------------------------- #
# R-1 / R-2 — source resolution (fast, in-process leaf calls)
# --------------------------------------------------------------------------- #

def test_para_source_resolved_by_relpath_with_layout_slug(tmp_path: Path) -> None:
    """R-1: a PARA note (NOT under `_sources/`) resolves; slug is the layout
    slug_strategy result (preserve-unicode), matching `pages.slug`."""
    root = tmp_path / "vault"
    _schema(root, "personal", "obsidian-personal")
    note = root / "05 - Материалы/Квантовые вычисления/Заметка Икс.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("# Заметка Икс\n\nтело.\n", encoding="utf-8")

    rel = "05 - Материалы/Квантовые вычисления/Заметка Икс.md"
    resolved = _sourcing._resolve_source_inside_sources(rel, root)
    assert isinstance(resolved, tuple), f"expected (path, slug), got {resolved}"
    path, slug = resolved
    assert path == note.resolve()
    assert slug == "заметка-икс"  # preserve-unicode, NOT the raw stem


def test_para_source_in_generated_dir_refused(tmp_path: Path) -> None:
    """R-2: a note inside a `_concepts/` dir is refused (anti-loop) — extraction
    must never run on its own output."""
    root = tmp_path / "vault"
    _schema(root, "personal", "obsidian-personal")
    concept = root / "05 - Материалы/Квантовые вычисления/_concepts/x.md"
    concept.parent.mkdir(parents=True, exist_ok=True)
    concept.write_text("---\ntype: concept\n---\n# X\n", encoding="utf-8")

    rel = "05 - Материалы/Квантовые вычисления/_concepts/x.md"
    out = _sourcing._resolve_source_inside_sources(rel, root)
    assert isinstance(out, dict) and out["error"] == "INVALID_SOURCE_PATH"
    assert "generated" in out["reason"]


def test_all_concepts_dirs_finds_nested_para(tmp_path: Path) -> None:
    """R-4: the drift sweep finds `_concepts/` dirs nested under PARA folders."""
    root = tmp_path / "vault"
    nested = root / "05 - Материалы/Квантовые вычисления/_concepts"
    nested.mkdir(parents=True)
    (root / "_concepts").mkdir()  # vault-tier too (Karpathy-style)
    found = _sourcing._all_concepts_dirs(root)
    assert nested in found and (root / "_concepts") in found


def test_all_concepts_dirs_prunes_system_dirs(tmp_path: Path) -> None:
    """vdd-multi perf SEV-2 / R-26: the sweep does NOT descend `.git`/`_raw`/etc.,
    so a `_concepts/` buried in a pruned dir is never returned (and the walk is
    bounded), while a real PARA `_concepts/` still is."""
    root = tmp_path / "vault"
    real = root / "05 - Материалы/Квантовые вычисления/_concepts"
    real.mkdir(parents=True)
    for junk in (".git/_concepts", "_raw/_concepts", ".obsidian/_concepts"):
        (root / junk).mkdir(parents=True)
    found = _sourcing._all_concepts_dirs(root)
    assert real in found
    assert not any(".git" in p.parts or "_raw" in p.parts or ".obsidian" in p.parts
                   for p in found)


def test_root_level_concepts_dir_indexed(tmp_path: Path) -> None:
    """vdd-multi logic MED: a root-level / MOC source note's `_concepts/` lands at
    `<root>/_concepts/` — the new root-anchored glob indexes it as db_type concept
    (pre-fix: matched no glob → silently dropped → inbound wikilink never resolved)."""
    root = tmp_path / "vault"
    _schema(root, "personal", "obsidian-personal")
    cp = root / "_concepts/некий-концепт.md"
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text("---\ntype: concept\ntitle: Некий концепт\n---\n# Некий концепт\n",
                  encoding="utf-8")
    repo = _make_repo(tmp_path / "r.db", "personal", root)
    reindex_full(repo, "personal")
    row = repo._connect().execute(
        "SELECT type, project FROM pages WHERE vault_id='personal' AND slug=?",
        ("некий-концепт",)).fetchone()
    repo.close()
    assert row is not None, "root-level _concepts/ page was dropped (no matching glob)"
    assert row[0] == "concept" and row[1] == "_concepts"


# --------------------------------------------------------------------------- #
# R-3 / R-5 / R-6 — end-to-end PARA round-trip (prepare → apply → reindex)
# --------------------------------------------------------------------------- #

def test_para_round_trip_creates_indexed_concept_and_resolves_wikilink(
    tmp_path: Path,
) -> None:
    """R-3/R-5/R-6 + Unicode: a PARA note with an inbound `[[Сущность Икс]]`
    wikilink → extract-concepts writes `<folder>/_concepts/сущность-икс.md`, the
    entity file_path is that real path, and after reindex the concept page is
    indexed as db_type concept AND the source's previously-orphan wikilink
    resolves to it."""
    root = tmp_path / "vault"
    db = tmp_path / "index.db"
    _schema(root, "personal", "obsidian-personal")
    note_rel = "05 - Материалы/Квантовые вычисления/Заметка.md"
    note = root / note_rel
    note.parent.mkdir(parents=True, exist_ok=True)
    # body line 3 holds the quote; wikilink target slugifies to сущность-икс.
    note.write_text(
        "# Заметка\n\nСущность Икс это пример. См. [[Сущность Икс]].\n",
        encoding="utf-8")

    repo = _make_repo(db, "personal", root)
    reindex_full(repo, "personal")
    # pre-state: the wikilink ref is an orphan (no сущность-икс page yet).
    conn = repo._connect()
    assert conn.execute(
        "SELECT count(*) FROM pages WHERE vault_id='personal' AND slug=?",
        ("сущность-икс",)).fetchone()[0] == 0
    note_slug = conn.execute(
        "SELECT slug FROM pages WHERE vault_id='personal' AND type='summary'"
    ).fetchone()[0]
    assert note_slug == "заметка"
    repo.close()

    prep = _run("prepare", "--vault", "personal", "--vault-root", str(root),
                "--source-page", note_rel, "--db-path", str(db))
    assert prep.returncode == 0, prep.stderr.decode()
    source_hash = json.loads(prep.stdout)["source_hash"]

    cand = _candidate("сущность-икс", "Сущность Икс", "Сущность Икс это пример.")
    app = _run("apply", "--vault", "personal", "--vault-root", str(root),
               "--source-page", note_rel, "--source-hash", source_hash,
               "--db-path", str(db), "--candidates-stdin",
               stdin=json.dumps([cand]).encode("utf-8"))
    assert app.returncode == 0, app.stderr.decode()
    manifest = json.loads(app.stdout)

    # R-3: concept page in the source note's OWN _concepts/, not vault root.
    concept_file = root / "05 - Материалы/Квантовые вычисления/_concepts/сущность-икс.md"
    assert concept_file.is_file()
    assert not (root / "_concepts").exists()
    # R-5: manifest path is the real vault-relative path.
    assert manifest["written"][0]["path"] == (
        "05 - Материалы/Квантовые вычисления/_concepts/сущность-икс.md")

    conn2 = sqlite3.connect(db)
    conn2.row_factory = sqlite3.Row
    try:
        # R-5: entity row file_path matches the on-disk page.
        ent = conn2.execute(
            "SELECT slug, file_path FROM entities WHERE vault_id='personal'"
        ).fetchone()
        assert ent["slug"] == "сущность-икс"
        assert ent["file_path"] == (
            "05 - Материалы/Квантовые вычисления/_concepts/сущность-икс.md")
    finally:
        conn2.close()

    # R-6: reindex the new concept page → indexed as db_type concept (no
    # UnmappedTypeError), project = the note's PARA project, and the source
    # note's wikilink now resolves (orphan gone).
    repo2 = _make_repo(tmp_path / "index2.db", "personal", root)
    reindex_full(repo2, "personal")
    row = repo2._connect().execute(
        "SELECT type, project FROM pages WHERE vault_id='personal' AND slug=?",
        ("сущность-икс",)).fetchone()
    assert row is not None, "concept page was dropped (UnmappedTypeError?)"
    assert row[0] == "concept"
    assert row[1] == "Материалы/Квантовые вычисления"
    repo2.close()


# --------------------------------------------------------------------------- #
# Karpathy golden anchor — vault-tier concepts_rel unchanged
# --------------------------------------------------------------------------- #

def test_karpathy_concepts_rel_byte_identical(tmp_path: Path) -> None:
    """Karpathy `_sources/` source → concept page in vault-tier `_concepts/`,
    manifest path == `_concepts/<slug>.md` (byte-identical to pre-037)."""
    root = tmp_path / "vault"
    db = tmp_path / "k.db"
    _schema(root, "kvault", "karpathy")
    src = root / "_sources/lesson-x.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("---\ntype: summary\ntitle: Lesson X\n---\n"
                   "Backtesting is a method. See [[Backtesting]].\n",
                   encoding="utf-8")
    repo = _make_repo(db, "kvault", root)
    reindex_full(repo, "kvault")
    repo.close()

    prep = _run("prepare", "--vault", "kvault", "--vault-root", str(root),
                "--source-page", "lesson-x", "--db-path", str(db))
    assert prep.returncode == 0, prep.stderr.decode()
    source_hash = json.loads(prep.stdout)["source_hash"]

    cand = _candidate("backtesting", "Backtesting", "Backtesting is a method.")
    app = _run("apply", "--vault", "kvault", "--vault-root", str(root),
               "--source-page", "lesson-x", "--source-hash", source_hash,
               "--db-path", str(db), "--candidates-stdin",
               stdin=json.dumps([cand]).encode("utf-8"))
    assert app.returncode == 0, app.stderr.decode()
    manifest = json.loads(app.stdout)
    assert manifest["written"][0]["path"] == "_concepts/backtesting.md"
    assert (root / "_concepts/backtesting.md").is_file()


def test_karpathy_course_tier_concepts_rel(tmp_path: Path) -> None:
    """R-5: a Karpathy course-tier source (`Lessons/<C>/_sources/`) writes its
    concept page to the sibling `Lessons/<C>/_concepts/` — and the manifest +
    entity path now reflect that REAL nested path (pre-037 they hard-coded the
    vault-tier `_concepts/<slug>.md`, which pointed at a nonexistent file)."""
    root = tmp_path / "vault"
    db = tmp_path / "c.db"
    _schema(root, "kvault", "karpathy")
    src = root / "Lessons/Trading/_sources/lesson-y.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("---\ntype: summary\ntitle: Lesson Y\n---\n"
                   "Hedging is a method. See [[Hedging]].\n", encoding="utf-8")
    repo = _make_repo(db, "kvault", root)
    reindex_full(repo, "kvault")
    repo.close()

    prep = _run("prepare", "--vault", "kvault", "--vault-root", str(root),
                "--source-page", "lesson-y", "--db-path", str(db))
    assert prep.returncode == 0, prep.stderr.decode()
    source_hash = json.loads(prep.stdout)["source_hash"]
    cand = _candidate("hedging", "Hedging", "Hedging is a method.")
    app = _run("apply", "--vault", "kvault", "--vault-root", str(root),
               "--source-page", "lesson-y", "--source-hash", source_hash,
               "--db-path", str(db), "--candidates-stdin",
               stdin=json.dumps([cand]).encode("utf-8"))
    assert app.returncode == 0, app.stderr.decode()
    manifest = json.loads(app.stdout)
    assert manifest["written"][0]["path"] == "Lessons/Trading/_concepts/hedging.md"
    assert (root / "Lessons/Trading/_concepts/hedging.md").is_file()


# --------------------------------------------------------------------------- #
# MED-1 / MAJOR-1 (review) — slug gate hardening + length-cap decoupling
# --------------------------------------------------------------------------- #

def test_is_valid_slug_rejects_trailing_newline() -> None:
    """MED-1: `\\Z` (not `$`) anchors the end so a trailing newline cannot smuggle
    a name-injection slug through the gate."""
    assert _is_valid_slug("алгоритм-шора") is True
    assert _is_valid_slug("alpha\n") is False
    assert _is_valid_slug("alpha\r") is False


def test_is_valid_slug_length_cap_decoupled() -> None:
    """MAJOR-1: the 120-char cap bounds CANDIDATE/concept slugs (filename safety)
    but `max_len=None` opts an already-indexed SOURCE slug out — a long preserve-
    unicode slug is traversal-safe and must not be length-rejected."""
    long_slug = "-".join(["слово"] * 30)  # 30*5 + 29 = 179 chars, valid charset
    assert len(long_slug) > 120
    assert _is_valid_slug(long_slug) is False           # default cap rejects
    assert _is_valid_slug(long_slug, max_len=None) is True  # source-slug path accepts


def test_para_long_title_slug_stays_extractable(tmp_path: Path) -> None:
    """MAJOR-1 integration: a PARA note whose title slugifies to >120 chars is
    indexed by reindex (no cap) AND resolves for extraction (no false
    INVALID_SOURCE_SLUG) — the indexer and extractor agree."""
    root = tmp_path / "vault"
    _schema(root, "personal", "obsidian-personal")
    title = ("Очень длинное название заметки про постквантовую криптографию "
             "и квантовые вычисления в блокчейнах Биткоин и Эфириум сегодня")
    rel = f"05 - Материалы/Квантовые вычисления/{title}.md"
    note = root / rel
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(f"# {title}\n\nтело.\n", encoding="utf-8")

    repo = _make_repo(tmp_path / "long.db", "personal", root)
    reindex_full(repo, "personal")
    slug = repo._connect().execute(
        "SELECT slug FROM pages WHERE vault_id='personal' AND type='summary'"
    ).fetchone()[0]
    repo.close()
    assert len(slug) > 120, f"expected a >120-char slug, got {len(slug)}"

    resolved = _sourcing._resolve_source_inside_sources(rel, root)
    assert isinstance(resolved, tuple), f"long-title note wrongly rejected: {resolved}"
    assert resolved[1] == slug  # extractor slug == indexed pages.slug


def test_anti_loop_case_insensitive(tmp_path: Path) -> None:
    """LOW-1: a source inside a `_Concepts/` dir (non-canonical casing) is still
    refused — the anti-loop guard casefolds, so macOS/Windows can't defeat it."""
    root = tmp_path / "vault"
    _schema(root, "personal", "obsidian-personal")
    p = root / "05 - Материалы/Квантовые вычисления/_Concepts/x.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# X\n", encoding="utf-8")
    out = _sourcing._resolve_source_inside_sources(
        "05 - Материалы/Квантовые вычисления/_Concepts/x.md", root)
    assert isinstance(out, dict) and out["error"] == "INVALID_SOURCE_PATH"
