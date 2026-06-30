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
