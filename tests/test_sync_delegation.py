"""TASK 046 P2 — wiki-sync delegates per-source distil to wiki-import.

R-8 the scan plan emits a `delegate` (tool=wiki-import + kind/diagrams/concepts/folder) for each
ingest/convert+ingest entry. R-9 the executor delegates rather than inlining summarise/enrich/
extract — pinned here at the plan level: every distil entry carries a wiki-import delegation and
non-distil entries (upsert/skip) carry none. (The recipe-side "no inline distil" is in
workflows/wiki-sync.md.) `_delegate_folder` resolves the topic folder (parent-of-_raw).
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_sync

_VAULT = "deleg-test-vault"


def _register_vault(db: Path, vault: Path) -> None:
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=_VAULT, name=_VAULT, root_path=vault,
        schema_version="5.0", registered_at=datetime(2026, 6, 30)))
    repo.close()


def _md(path: Path, fm: str | None, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((f"---\n{fm}\n---\n{body}" if fm is not None else body), encoding="utf-8")


def _run_scan(zone: Path, vault: Path, db: Path):
    return subprocess.run(
        [sys.executable, "-m", "scripts.wiki_skills.wiki_sync", "scan", str(zone),
         "--vault", _VAULT, "--vault-root", str(vault), "--db-path", str(db)],
        capture_output=True, text=True, check=False)


def _scan_zone(tmp_path: Path):
    vault = tmp_path / "vault"
    z = vault / "courses"
    (z / "_raw").mkdir(parents=True)
    (z / "_raw" / "lec.vtt").write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi\n", encoding="utf-8")
    (z / "deck.docx").write_bytes(b"PK\x03\x04deck")
    _md(z / "ready.md", "type: lesson-summary", "a real summary body with content here")
    _md(z / "draft.md", "tags: [wiki/skip]", "draft body")
    db = tmp_path / "g.db"
    _register_vault(db, vault)
    res = _run_scan(z, vault, db)
    assert res.returncode == 0, res.stderr
    return {e["path"]: e for e in json.loads(res.stdout)["entries"]}


def test_sync_scan_delegates_to_import(tmp_path):
    by_path = _scan_zone(tmp_path)
    # a .vtt under _raw/ → ingest, delegated to wiki-import, folder = parent-of-_raw
    deleg = by_path["courses/_raw/lec.vtt"]["delegate"]
    assert deleg["tool"] == "wiki-import"
    assert deleg["concepts"] is True          # default ON (back-compat; P3 toggles)
    assert deleg["diagrams"] is False
    assert deleg["kind"] == "auto"            # wiki-import prepare auto-detects (P3 profile overrides)
    assert deleg["folder"] == "courses"       # _raw stripped → topic folder
    assert deleg["source"] == "courses/_raw/lec.vtt"


def test_sync_plan_delegates_not_inline(tmp_path):
    by_path = _scan_zone(tmp_path)
    for path, e in by_path.items():
        if e["action"] in ("ingest", "convert+ingest"):
            assert e.get("delegate", {}).get("tool") == "wiki-import", f"{path} not delegated"
        else:  # upsert / skip never delegate
            assert "delegate" not in e, f"{path} ({e['action']}) should not delegate"
    # the office file also delegates (conversion now lives in wiki-import prepare, P1b) — assert
    # the FULL knob set, not just tool+folder (a convert+ingest-special-casing mutation must fail)
    deck = by_path["courses/deck.docx"]
    assert deck["action"] == "convert+ingest"
    assert deck["delegate"] == {
        "tool": "wiki-import", "source": "courses/deck.docx", "folder": "courses",
        "kind": "auto", "diagrams": False, "concepts": True,
    }


def test_delegate_folder_resolution():
    f = wiki_sync._delegate_folder
    assert f("03 - Learning/Webinars/_raw/x.vtt") == "03 - Learning/Webinars"
    assert f("03 - Learning/Webinars/lecture.docx") == "03 - Learning/Webinars"
    assert f("courses/.staging/deck-docx.md") == "courses"
    # nested _raw grouping subdir → trim from the FIRST _raw onward (the re-ingest-loop fix);
    # only stripping the immediate parent would yield "a/b/_raw/sub" → capture back inside _raw.
    assert f("a/b/_raw/sub/x.vtt") == "a/b"
    assert f("_raw/x.vtt") == "."          # zone == vault root
    assert f("x.vtt") == "."               # bare vault-root file
