"""End-to-end acceptance for `wiki-sync` (TASK 018 / R-11) — AC-1..14.

Runs `wiki-sync scan` (as a subprocess, the real CLI) over the committed
`tests/fixtures/sync/**` tree (incl. a realistic DB Folder `yaml:dbfolder`
sidecar, Bases, Dataview, an embedded-dataview content note, a folder-note, a
`.vtt`, an empty source, office/PDF convert sources, images, excalidraw/canvas)
copied into a tmp vault, and asserts the full classify matrix + determinism +
idempotency + convert-convergence + dry-run + degenerate behaviour.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository

FIXTURES = Path(__file__).parent / "fixtures" / "sync"
_VAULT = "sync-e2e-vault"


def _vault(tmp_path: Path) -> tuple[Path, Path]:
    """Copy the committed fixtures into a tmp vault + register it; return
    (vault_root, db_path)."""
    vault = tmp_path / "vault"
    shutil.copytree(FIXTURES, vault)
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=_VAULT, name=_VAULT, root_path=vault,
        schema_version="5.0", registered_at=datetime(2026, 6, 3),
    ))
    repo.close()
    return vault, db


def _scan(vault: Path, db: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.wiki_skills.wiki_sync", "scan", str(vault),
         "--vault", _VAULT, "--vault-root", str(vault), "--db-path", str(db), *extra],
        capture_output=True, text=True, check=False,
    )


def _plan(vault: Path, db: Path) -> dict[str, dict[str, object]]:
    res = _scan(vault, db)
    assert res.returncode == 0, res.stderr
    return {str(e["path"]): e for e in json.loads(res.stdout)["entries"]}


def test_e2e_classify_matrix(tmp_path: Path) -> None:
    """AC-2/2b/3/4/11/12: the real fixture set classifies as designed."""
    vault, db = _vault(tmp_path)
    by = _plan(vault, db)

    # AC-2 generated views skip
    assert by["courses/My Tasks.md"]["reason"] == "view:dbfolder"
    assert by["courses/AllNotes.md"]["reason"] == "view:base"
    assert by["courses/Dashboard.md"]["reason"] == "view:dataviewjs"
    assert by["Area/Area.md"]["reason"] == "view:folder-note"
    # AC-2b embedded-dataview CONTENT note → upsert (not skipped)
    assert by["courses/lesson-recap.md"]["action"] == "upsert"

    # AC-3 extension routing (incl. uppercase .PDF case-fold)
    assert by["courses/report.docx"]["action"] == "convert+ingest"
    assert by["courses/Slides.PDF"]["action"] == "convert+ingest"
    assert by["courses/Slides.PDF"]["converter"] == "pdf"
    assert by["courses/lecture.vtt"]["action"] == "ingest"
    assert by["courses/lecture.vtt"]["normalize"] == "vtt-detimestamp"
    assert by["courses/sketch.excalidraw.md"]["reason"] == "excalidraw"  # suffix .md → walked
    # `.canvas` + images are pruned at the WALK (extension not in the walk set,
    # W-2 pre-read prune) so they never reach the plan.
    assert "courses/board.canvas" not in by
    assert "courses/diagram.png" not in by

    # AC-4 tag routing + precedence
    assert by["courses/wip.md"]["reason"] == "wiki/skip"
    assert by["courses/notes.md"]["action"] == "ingest"   # #wiki/raw
    assert by["courses/ready-summary.md"]["action"] == "upsert"

    # AC-11/12 degenerate + unmappable
    assert by["courses/empty.txt"]["reason"] == "empty-source"
    assert by["courses/scratch.md"]["reason"] == "unmappable-type"

    # AC-12 same-stem convert sources → DISTINCT staged targets
    assert by["courses/report.docx"]["staged_target"] == "_raw/.staging/report-docx.md"
    assert by["courses/report.pdf"]["staged_target"] == "_raw/.staging/report-pdf.md"


def test_e2e_plan_valid_and_deterministic(tmp_path: Path) -> None:
    """AC-1/10: valid plan JSON; two scans of an untouched zone byte-identical."""
    vault, db = _vault(tmp_path)
    a = _scan(vault, db)
    b = _scan(vault, db)
    assert a.returncode == 0 and b.returncode == 0
    plan = json.loads(a.stdout)
    assert plan["generated_by"] == "wiki-sync/scan"
    assert plan["summary"]["total"] == len(plan["entries"])
    # sorted by vault-relative POSIX path
    paths = [e["path"] for e in plan["entries"]]
    assert paths == sorted(paths)
    assert a.stdout == b.stdout


def test_e2e_idempotency_rerun_noop(tmp_path: Path) -> None:
    """AC-5/AC-8: after the executor `record`s a file, the next scan no-ops it."""
    vault, db = _vault(tmp_path)
    by = _plan(vault, db)
    ready = by["courses/ready-summary.md"]
    assert ready["is_unchanged"] is False
    rec = subprocess.run(
        [sys.executable, "-m", "scripts.wiki_skills.wiki_sync", "record",
         "courses/ready-summary.md", "--source-hash", str(ready["source_hash"]),
         "--vault", _VAULT, "--db-path", str(db)],
        capture_output=True, text=True, check=False,
    )
    assert rec.returncode == 0, rec.stderr
    by2 = _plan(vault, db)
    assert by2["courses/ready-summary.md"]["is_unchanged"] is True


def test_e2e_convert_convergence_staging_not_rediscovered(tmp_path: Path) -> None:
    """AC-14: a staged conversion output in `_raw/.staging/` is NOT re-discovered
    on a later scan (no convert→ingest self-loop)."""
    vault, db = _vault(tmp_path)
    staging = vault / "_raw" / ".staging"
    staging.mkdir(parents=True)
    (staging / "report-docx.md").write_text("# converted\nbody\n", encoding="utf-8")
    by = _plan(vault, db)
    assert not any(p.startswith("_raw/.staging/") for p in by)


def test_e2e_dry_run_writes_nothing(tmp_path: Path) -> None:
    """AC-6: --dry-run mutates neither the vault tree nor the DB; lists skips."""
    vault, db = _vault(tmp_path)
    before = sorted(str(p.relative_to(vault)) for p in vault.rglob("*"))
    db_size = db.stat().st_size
    res = _scan(vault, db, "--dry-run")
    assert res.returncode == 0, res.stderr
    assert sorted(str(p.relative_to(vault)) for p in vault.rglob("*")) == before
    assert db.stat().st_size == db_size
    assert "view:dbfolder" in res.stdout and "unmappable-type" in res.stdout


def test_e2e_unparseable_frontmatter_never_raises(tmp_path: Path) -> None:
    """AC-11: a malformed-frontmatter note does not crash the scan."""
    vault, db = _vault(tmp_path)
    (vault / "courses" / "broken.md").write_text(
        "---\n: : : not: valid\n---\nbody prose content here\n", encoding="utf-8")
    res = _scan(vault, db)
    assert res.returncode == 0, res.stderr
    by = {str(e["path"]): e for e in json.loads(res.stdout)["entries"]}
    assert by["courses/broken.md"]["action"] == "skip"
