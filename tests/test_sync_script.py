"""Tests for scripts/sync_wiki_ingest.sh (bead 004-02 / I-V.2 / R-49).

Invokes the bash script via subprocess; assertions on exit code, stdout/stderr,
and filesystem mtime snapshots. Tests use the REAL vendored directory and the
REAL upstream path — integration-leaning but bounded (no LLM, no network, no
upstream mutations).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "sync_wiki_ingest.sh"
VENDORED = REPO_ROOT / "scripts" / "wiki_ingest"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )


def _mtime_snapshot() -> dict[str, float]:
    return {
        str(p.relative_to(VENDORED)): p.stat().st_mtime
        for p in VENDORED.rglob("*")
        if p.is_file()
    }


def test_help_exits_zero() -> None:
    """R-49(e): script has --help that prints usage and exits 0."""
    result = _run(["--help"])
    assert result.returncode == 0, result.stderr
    assert "Usage:" in result.stdout
    assert "--dry-run" in result.stdout
    assert "--accept-local-divergence" in result.stdout


def test_dry_run_no_mutations() -> None:
    """R-49(f): --dry-run leaves every vendored file untouched (mtime check)."""
    before = _mtime_snapshot()
    result = _run(["--dry-run"])
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    after = _mtime_snapshot()
    assert before == after, f"mtimes changed under --dry-run: {set(before) ^ set(after)}"


def test_dry_run_prints_completion_marker() -> None:
    """--dry-run prints a recognisable completion line on stdout."""
    result = _run(["--dry-run"])
    assert result.returncode == 0
    assert "Dry run complete" in result.stdout


def test_source_not_found_exits_one() -> None:
    """R-49(a): --source pointing nowhere → exit 1 with clear error message."""
    result = _run(["--source", "/nonexistent/path/that/does/not/exist"])
    assert result.returncode == 1
    assert "upstream source directory not found" in result.stderr


def test_divergence_check_blocks_overwrite(tmp_path: Path) -> None:
    """R-49(b): mutate a vendored file (not in local_patches), run sync without
    --accept-local-divergence → exit 1, stderr has per-file diff entry.
    Reverts the mutation on test teardown."""
    target = VENDORED / "_safety.py"
    backup = tmp_path / "_safety.py.backup"
    shutil.copy2(target, backup)
    try:
        with open(target, "ab") as f:
            f.write(b"\n# test-only mutation\n")

        result = _run(["--dry-run"])
        assert result.returncode == 1, (
            f"expected exit 1 on divergence, got {result.returncode}"
            f"\nstdout={result.stdout!r}\nstderr={result.stderr!r}"
        )
        assert "local divergence detected" in result.stderr
        assert "_safety.py" in result.stderr
    finally:
        shutil.copy2(backup, target)


def test_accept_local_divergence_escape_hatch(tmp_path: Path) -> None:
    """--accept-local-divergence bypasses the hash guard (dry-run leaves files
    untouched but exits 0 with a warning)."""
    target = VENDORED / "_safety.py"
    backup = tmp_path / "_safety.py.backup"
    shutil.copy2(target, backup)
    try:
        with open(target, "ab") as f:
            f.write(b"\n# test-only mutation\n")

        result = _run(["--dry-run", "--accept-local-divergence"])
        assert result.returncode == 0, (
            f"expected exit 0 with escape hatch, got {result.returncode}"
            f"\nstderr={result.stderr!r}"
        )
        assert "diverged from recorded hashes" in result.stderr
        assert "REMINDER: add local_patches[]" in result.stderr
    finally:
        shutil.copy2(backup, target)


def test_unknown_argument_exits_two() -> None:
    """Usage-error: unknown flag → exit 2."""
    result = _run(["--no-such-flag"])
    assert result.returncode == 2
    assert "unknown argument" in result.stderr
