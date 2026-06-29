"""TASK 045 — wiki-search: file_path + obsidian_url in CLI output (R-1..R-6, R-8).

Tests for the two new JSON fields added to every search hit and the OSC 8 / plain-URL
appendage in --format markdown.  All tests are self-contained: they spin up a real
SQLiteRepository in tmp_path (same pattern as test_wiki_search_alias_expansion.py),
so there is no mock of the DB layer.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_search

VAULT_ID = "test-vault"


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def vault_db(tmp_path: Path) -> tuple[Path, Path]:
    """Spin up a minimal vault with one concept page; return (vault_root, db_path)."""
    vault = tmp_path / "MyVault"
    (vault / "_concepts").mkdir(parents=True)
    (vault / "_concepts" / "foo.md").write_text(
        "---\ntype: concept\nslug: foo\ntitle: Foo\n"
        "date: 2026-01-01\ntags: [concept]\n---\n\nFoo content here.\n",
        encoding="utf-8",
    )
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=VAULT_ID,
        name="My Vault",
        root_path=vault,
        schema_version="2.0",
        registered_at=datetime(2026, 1, 1),
    ))
    reindex_full(repo, VAULT_ID)
    repo.close()
    return vault, db


# ---------------------------------------------------------------------------
# JSON output tests (R-1, R-2, R-3)
# ---------------------------------------------------------------------------


def test_search_json_includes_file_path_and_obsidian_url(
    vault_db: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """JSON hit contains file_path and a correct obsidian_url when vault is known (R-1, R-2)."""
    _vault_root, db = vault_db
    rc = wiki_search.main(["foo", "--vaults", VAULT_ID, "--db-path", str(db)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["count"] >= 1
    hit = next(h for h in out["hits"] if h["slug"] == "foo")
    # R-1: file_path present and verbatim
    assert hit["file_path"] == "_concepts/foo.md"
    # R-2: obsidian_url uses vault folder basename + encoded path
    assert hit["obsidian_url"] == "obsidian://open?vault=MyVault&file=_concepts/foo.md"


def test_search_json_obsidian_url_null_when_vault_unknown(
    vault_db: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """obsidian_url is null when repo.get_vault returns None for the vault (R-2d).

    The vault FK cascade prevents a real "stale pages" scenario (pages are deleted
    when the vault is removed), so we mock get_vault to return None to exercise the
    null-url code path directly — this is the correct test for R-2d behavior.
    """
    _vault_root, db = vault_db
    from scripts.wiki_index import sqlite_repository as _sr

    with patch.object(_sr.SQLiteRepository, "get_vault", return_value=None):
        rc = wiki_search.main(["foo", "--vaults", VAULT_ID, "--db-path", str(db)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["count"] >= 1
    hit = next(h for h in out["hits"] if h["slug"] == "foo")
    assert hit["file_path"] == "_concepts/foo.md"  # R-1: always present
    assert hit["obsidian_url"] is None              # R-2d: null when vault unknown


def test_search_json_vault_cache_called_once_per_unique_vault(
    vault_db: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """repo.get_vault is called at most once per unique vault_id, not once per hit (R-3)."""
    vault_root, db = vault_db
    # Add a second concept page so there are ≥2 hits from the same vault
    (vault_root / "_concepts" / "baz.md").write_text(
        "---\ntype: concept\nslug: baz\ntitle: Baz\n"
        "date: 2026-01-01\ntags: [concept]\n---\n\nBaz content foo.\n",
        encoding="utf-8",
    )
    repo2 = SQLiteRepository(db)
    reindex_full(repo2, VAULT_ID)
    repo2.close()

    call_count: dict[str, int] = {"n": 0}
    from scripts.wiki_index import sqlite_repository as _sr

    original_get_vault = _sr.SQLiteRepository.get_vault

    def counting_get_vault(self: _sr.SQLiteRepository, vault_id: str) -> Vault | None:
        call_count["n"] += 1
        return original_get_vault(self, vault_id)

    with patch.object(_sr.SQLiteRepository, "get_vault", counting_get_vault):
        rc = wiki_search.main(["foo", "--vaults", VAULT_ID, "--db-path", str(db)])

    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["count"] >= 1  # at least the "foo" hit
    # Both hits belong to the same vault — get_vault must be called exactly once
    assert call_count["n"] == 1, (
        f"Expected 1 get_vault call (vault cache), got {call_count['n']}"
    )


# ---------------------------------------------------------------------------
# Markdown format tests (R-4, R-5)
# ---------------------------------------------------------------------------


def test_search_markdown_tty_osc8_link(
    vault_db: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--format markdown on TTY appends OSC 8 hyperlink with open + close sequence (R-4)."""
    _vault_root, db = vault_db
    with patch("sys.stdout.isatty", return_value=True):
        rc = wiki_search.main(
            ["foo", "--vaults", VAULT_ID, "--db-path", str(db), "--format", "markdown"]
        )
    assert rc == 0
    out = capsys.readouterr().out
    # OSC 8 open sequence must be present
    assert "\033]8;;obsidian://" in out, f"Missing OSC 8 start in: {out!r}"
    # OSC 8 close terminator must be present (prevents bleed into subsequent output)
    assert "\033]8;;\033\\" in out, f"Missing OSC 8 terminator in: {out!r}"
    # In OSC 8 mode the URL is the escape payload — the plain "  →  obsidian://..."
    # suffix form (used in pipe mode) must NOT appear as bare text (R-5 / L-4).
    assert "  →  obsidian://" not in out, f"Plain URL leaked in TTY mode: {out!r}"


def test_search_markdown_pipe_plain_url(
    vault_db: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--format markdown when piped appends plain obsidian:// URL, no ANSI escapes (R-5)."""
    _vault_root, db = vault_db
    with patch("sys.stdout.isatty", return_value=False):
        rc = wiki_search.main(
            ["foo", "--vaults", VAULT_ID, "--db-path", str(db), "--format", "markdown"]
        )
    assert rc == 0
    out = capsys.readouterr().out
    assert "obsidian://open?vault=" in out, f"Missing plain URL in: {out!r}"
    assert "\033]8;;" not in out, f"Unexpected ANSI escape in pipe output: {out!r}"


def test_search_markdown_apple_terminal_plain_url(
    vault_db: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Apple Terminal (TERM_PROGRAM=Apple_Terminal) falls back to plain URL (not OSC 8).

    Apple Terminal silently strips OSC 8 escape sequences, leaving only the [↗]
    glyph as plain text with no visible URL — useless. We detect TERM_PROGRAM and
    fall back to the same plain-URL branch used for pipe output.
    """
    _vault_root, db = vault_db
    with patch("sys.stdout.isatty", return_value=True), \
         patch.dict("os.environ", {"TERM_PROGRAM": "Apple_Terminal"}):
        rc = wiki_search.main(
            ["foo", "--vaults", VAULT_ID, "--db-path", str(db), "--format", "markdown"]
        )
    assert rc == 0
    out = capsys.readouterr().out
    assert "obsidian://open?vault=" in out, f"Missing plain URL for Apple_Terminal: {out!r}"
    assert "\033]8;;" not in out, f"OSC 8 must not be emitted for Apple_Terminal: {out!r}"


# ---------------------------------------------------------------------------
# Security / encoding tests (S-1, L-3)
# ---------------------------------------------------------------------------


def test_search_markdown_tty_title_esc_stripped(
    vault_db: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """ESC bytes in a DB-sourced title are stripped before TTY output (H-6 / CWE-150).

    The attacker vector: wiki-import from a hostile URL seeds a page whose
    frontmatter title contains ANSI/OSC escape sequences. Running wiki-search
    --format markdown must not relay those bytes to the terminal.
    """
    _vault_root, db = vault_db
    # Directly patch the indexed title — this is the actual threat model: an
    # attacker controls what the indexer stores, not just the markdown source.
    evil_title = "evil\x1b]8;;file:///etc/passwd\x1b\\inject"
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE pages SET title = ? WHERE slug = 'foo'", (evil_title,))
        conn.commit()

    with patch("sys.stdout.isatty", return_value=True):
        rc = wiki_search.main(
            ["foo", "--vaults", VAULT_ID, "--db-path", str(db), "--format", "markdown"]
        )
    assert rc == 0
    out = capsys.readouterr().out
    # The attacker's forged OSC 8 payload must not appear raw in output
    assert "\x1b]8;;file://" not in out, f"ESC injection from title reached output: {out!r}"
    # The printable portion of the title IS present (control chars stripped, not the whole title)
    assert "evil" in out
    assert "inject" in out


def test_search_json_file_path_spaces_encoded(
    vault_db: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spaces (and special chars) in file_path are percent-encoded in obsidian_url (R-6 / UC-6).

    safe='/-_.~' keeps slashes literal but encodes spaces, Cyrillic, and other
    non-unreserved characters.  We patch file_path in the DB directly — the same
    way an imported page with a spaced filename would appear after indexing.
    """
    _vault_root, db = vault_db
    spaced_path = "_concepts/My Foo.md"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE pages SET file_path = ? WHERE slug = 'foo'", (spaced_path,)
        )
        conn.commit()

    rc = wiki_search.main(["foo", "--vaults", VAULT_ID, "--db-path", str(db)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip())
    assert out["count"] >= 1
    hit = next(h for h in out["hits"] if h["slug"] == "foo")
    # Space must be percent-encoded (%20); slash kept literal (safe="/-_.~")
    assert hit["file_path"] == "_concepts/My Foo.md"
    assert hit["obsidian_url"] == "obsidian://open?vault=MyVault&file=_concepts/My%20Foo.md"
