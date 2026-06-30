"""TASK 046 P3 — `.wiki/sync.yaml` `summarize:` block: schema + loader cascade + delegate wiring.

R-10 schema accept/reject (strict, no value echo) · R-11 per-folder deep-merge (deepest-wins,
partial override inherits) · R-12 absent block ≡ P2 defaults. Plus a scan-level test that the
resolved summarize drives `entry.delegate`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_index.sync_config import (
    SummarizeConfig,
    SyncConfigError,
    load_sync_config,
)
from scripts.wiki_skills._resummarize import Caches, resolve_summarize

_VAULT = "summ-test-vault"


def _write(vault_root: Path, rel: str, text: str) -> None:
    p = vault_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# --- R-10: schema accept / reject ------------------------------------------

def test_sync_config_summarize_accept(tmp_path):
    _write(tmp_path, ".wiki/sync.yaml",
           "summarize:\n  profile: meeting\n  diagrams: true\n  extract_concepts: false\n  target_subdir: _summary\n")
    cfg = load_sync_config(tmp_path)
    assert cfg.summarize == SummarizeConfig(
        profile="meeting", diagrams=True, extract_concepts=False, target_subdir="_summary")


def test_sync_config_summarize_reject_unknown_key(tmp_path):
    _write(tmp_path, ".wiki/sync.yaml", "summarize:\n  profil: meeting\n")  # typo
    with pytest.raises(SyncConfigError) as ei:
        load_sync_config(tmp_path)
    assert ei.value.code == "INVALID_SYNC_CONFIG"
    assert "meeting" not in str(ei.value)   # CWE-209/CWE-117: never echo the offending value


def test_sync_config_summarize_bad_profile(tmp_path):
    _write(tmp_path, ".wiki/sync.yaml", "summarize:\n  profile: pyramid\n")  # not in enum
    with pytest.raises(SyncConfigError) as ei:
        load_sync_config(tmp_path)
    assert ei.value.code == "INVALID_SYNC_CONFIG"
    assert "pyramid" not in str(ei.value)   # no-echo symmetry with the unknown-key test


@pytest.mark.parametrize("bad", ["/abs/path", "../escape", "a/../../etc", "a\b"])
def test_sync_config_summarize_target_subdir_rejects_unsafe(tmp_path, bad):
    # target_subdir traversal/escape/control → refused at the exit-6 validating layer (H-6),
    # not surfaced late as INVALID_FOLDER from wiki-import; the value is never echoed.
    _write(tmp_path, ".wiki/sync.yaml", f"summarize:\n  profile: lesson\n  target_subdir: {bad!r}\n")
    with pytest.raises(SyncConfigError) as ei:
        load_sync_config(tmp_path)
    assert ei.value.code == "INVALID_SYNC_CONFIG"
    assert bad not in str(ei.value)


def test_sync_config_summarize_target_subdir_normalized(tmp_path):
    # trailing slash + surrounding whitespace are normalised; whitespace-only → "" (no subdir).
    _write(tmp_path, ".wiki/sync.yaml", "summarize:\n  target_subdir: \"  _summary/  \"\n")
    assert load_sync_config(tmp_path).summarize.target_subdir == "_summary"
    _write(tmp_path, ".wiki/sync.yaml", "summarize:\n  target_subdir: \"   \"\n")
    assert load_sync_config(tmp_path).summarize.target_subdir == ""


# --- R-11: per-folder deep-merge (deepest-wins, partial override inherits) --

def test_sync_config_summarize_deepmerge(tmp_path):
    # root sets profile+diagrams; a subfolder overrides ONLY diagrams → inherits profile.
    _write(tmp_path, ".wiki/sync.yaml", "summarize:\n  profile: lesson\n  diagrams: false\n")
    _write(tmp_path, "courses/.wiki/sync.yaml", "summarize:\n  diagrams: true\n")
    caches = Caches()
    sm = resolve_summarize(tmp_path / "courses" / "lec.vtt", vault_root=tmp_path, caches=caches)
    assert sm.profile == "lesson"        # inherited from root
    assert sm.diagrams is True           # overridden by the folder
    assert sm.extract_concepts is True   # default (neither level set it)
    # a file at the root resolves to the root block only
    root_sm = resolve_summarize(tmp_path / "x.vtt", vault_root=tmp_path, caches=caches)
    assert root_sm.profile == "lesson" and root_sm.diagrams is False


# --- R-12: absent block ≡ P2 defaults --------------------------------------

def test_sync_config_summarize_default_backcompat(tmp_path):
    cfg = load_sync_config(tmp_path)
    assert cfg.summarize is None                      # no block on the merged config
    sm = resolve_summarize(tmp_path / "x.vtt", vault_root=tmp_path)
    assert sm == SummarizeConfig()                    # = auto / no diagrams / concepts ON / no subdir
    assert (sm.profile, sm.diagrams, sm.extract_concepts, sm.target_subdir) == ("auto", False, True, "")


# --- scan-level: the resolved summarize drives entry.delegate --------------

def _register(db: Path, vault: Path) -> None:
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(vault_id=_VAULT, name=_VAULT, root_path=vault,
                              schema_version="5.0", registered_at=datetime(2026, 6, 30)))
    repo.close()


def test_sync_scan_summarize_drives_delegate(tmp_path):
    vault = tmp_path / "vault"
    z = vault / "courses"
    (z / "_raw").mkdir(parents=True)
    (z / "_raw" / "lec.vtt").write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi\n", encoding="utf-8")
    _write(vault, "courses/.wiki/sync.yaml",
           "summarize:\n  profile: lesson\n  diagrams: true\n  extract_concepts: false\n  target_subdir: _summary\n")
    db = tmp_path / "g.db"
    _register(db, vault)
    res = subprocess.run(
        [sys.executable, "-m", "scripts.wiki_skills.wiki_sync", "scan", str(z),
         "--vault", _VAULT, "--vault-root", str(vault), "--db-path", str(db)],
        capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr
    by_path = {e["path"]: e for e in json.loads(res.stdout)["entries"]}
    deleg = by_path["courses/_raw/lec.vtt"]["delegate"]
    assert deleg["kind"] == "lesson"          # profile → --kind
    assert deleg["diagrams"] is True
    assert deleg["concepts"] is False         # extract_concepts: false → --no-concepts
    assert deleg["folder"] == "courses/_summary"   # topic folder + target_subdir


def test_sync_scan_summarize_root_target_subdir(tmp_path):
    # folder == "." (vault-root raw source) + target_subdir → "_summary", NOT "./_summary"
    # (pins the folder=="." then-branch; a mutation dropping the special-case is caught).
    vault = tmp_path / "vault"
    (vault / "_raw").mkdir(parents=True)
    (vault / "_raw" / "lec.vtt").write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi\n", encoding="utf-8")
    _write(vault, ".wiki/sync.yaml", "summarize:\n  profile: meeting\n  target_subdir: _summary\n")
    db = tmp_path / "g.db"
    _register(db, vault)
    res = subprocess.run(
        [sys.executable, "-m", "scripts.wiki_skills.wiki_sync", "scan", str(vault),
         "--vault", _VAULT, "--vault-root", str(vault), "--db-path", str(db)],
        capture_output=True, text=True, check=False)
    assert res.returncode == 0, res.stderr
    by_path = {e["path"]: e for e in json.loads(res.stdout)["entries"]}
    assert by_path["_raw/lec.vtt"]["delegate"]["folder"] == "_summary"


def test_sync_config_present_without_summarize_backcompat(tmp_path):
    # a sync.yaml that exists but has NO summarize: block ≡ defaults (R-12, the other path).
    _write(tmp_path, ".wiki/sync.yaml", "resummarize:\n  mode: if-missing\n")
    assert load_sync_config(tmp_path).summarize is None
    assert resolve_summarize(tmp_path / "x.vtt", vault_root=tmp_path) == SummarizeConfig()


def test_resolve_summarize_memoization_hit(tmp_path):
    # two files in the SAME dir resolve once (the cache-hit early return), same Caches.
    _write(tmp_path, ".wiki/sync.yaml", "summarize:\n  profile: article\n")
    caches = Caches()
    a = resolve_summarize(tmp_path / "a.vtt", vault_root=tmp_path, caches=caches)
    b = resolve_summarize(tmp_path / "b.vtt", vault_root=tmp_path, caches=caches)
    assert a is b                              # identical object from the memo (same parent dir)
    assert a.profile == "article"


def test_validated_raw_read_once_per_dir_across_both_cascades(tmp_path, monkeypatch):
    # vdd-multi PERF-046-1: the resummarize AND summarize cascades SHARE one per-dir validated-raw
    # read, so the same .wiki/sync.yaml is parsed ONCE per dir per scan — not twice (once per cascade).
    from collections import Counter

    from scripts.wiki_skills import _resummarize

    _write(tmp_path, ".wiki/sync.yaml", "resummarize:\n  mode: always\nsummarize:\n  profile: lesson\n")
    _write(tmp_path, "courses/.wiki/sync.yaml", "summarize:\n  diagrams: true\n")

    real = _resummarize._load_validated_raw
    calls: list[Path] = []

    def _counting(d: Path):
        calls.append(Path(d))
        return real(d)

    monkeypatch.setattr(_resummarize, "_load_validated_raw", _counting)
    caches = _resummarize.Caches()
    f = tmp_path / "courses" / "lec.vtt"
    _resummarize.resolve_policy(f, vault_root=tmp_path, caches=caches)       # resummarize cascade
    _resummarize.resolve_summarize(f, vault_root=tmp_path, caches=caches)    # summarize cascade
    per_dir = Counter(calls)
    # ancestors = {tmp_path, tmp_path/courses}; each read EXACTLY ONCE despite TWO cascades.
    assert set(per_dir) == {tmp_path, tmp_path / "courses"}
    assert all(n == 1 for n in per_dir.values()), f"a dir was read more than once: {per_dir}"
