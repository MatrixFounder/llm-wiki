"""TASK 022 / beads 02-04, 02-05, 02-08 — end-to-end proof that CLIs resolve a
vault-local `index_db` (declared in WIKI_SCHEMA.md) WITHOUT `--db-path`.

Each test registers + populates a LOCAL `<root>/.wiki/index.db` and a UNIQUE vault_id/
term that exists ONLY there. If a CLI opened the platform global DB instead, the unique
vault/term would be absent — so a successful local hit proves the resolution chain
(`--db-path > index_db > global`) + the ordering inversion (vault_root resolved BEFORE
make_repo). The island contract is exercised via `--all-vaults`/`--vaults all`.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_lint, wiki_reindex, wiki_search


def _local_vault(tmp_path: Path, vid: str, term: str) -> tuple[Path, Path]:
    """A vault whose WIKI_SCHEMA.md declares `index_db: .wiki/index.db`, registered +
    reindexed into that LOCAL db (NOT the global). Returns (vault_root, local_db_path)."""
    root = tmp_path / vid
    (root / "_sources").mkdir(parents=True)
    (root / "WIKI_SCHEMA.md").write_text(
        f"---\nvault_id: {vid}\nschema_version: '2.0'\nlanguage: en\n"
        f"layout: karpathy\nindex_db: .wiki/index.db\n---\n\n# schema\n",
        encoding="utf-8")
    (root / "_sources" / "alpha.md").write_text(
        f"---\ntype: summary\ntitle: Alpha\n---\n\nThe {term} marker lives here.\n",
        encoding="utf-8")
    local_db = root / ".wiki" / "index.db"
    local_db.parent.mkdir(parents=True, exist_ok=True)
    r = SQLiteRepository(local_db)
    r.apply_schema()
    r.register_vault(Vault(vault_id=vid, name=vid, root_path=root,
                           schema_version="2.0", registered_at=datetime(2026, 6, 8)))
    reindex_full(r, vid)
    r.close()
    return root, local_db


def _run(mod, argv) -> tuple[int, dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(argv)
    out = buf.getvalue().strip()
    return rc, (json.loads(out) if out.startswith(("{", "[")) else {"_raw": out})


def test_search_local_flag(tmp_path):
    """`wiki-search` (uses --vaults) with --vault-root finds a term that lives ONLY in
    the local DB → proves local resolution (global has no such vault)."""
    vid = "loc-search-vault"
    root, _ = _local_vault(tmp_path, vid, "ztermzz")
    rc, env = _run(wiki_search, ["ztermzz", "--vaults", vid, "--vault-root", str(root)])
    assert rc == 0
    hits = env.get("results") or env.get("hits") or []
    assert any("alpha" in json.dumps(h).lower() for h in hits), env


def test_search_local_cwd_walkup(tmp_path, monkeypatch):
    """No --vault-root: walk up from CWD to WIKI_SCHEMA.md → resolves the local DB."""
    vid = "loc-cwd-vault"
    root, _ = _local_vault(tmp_path, vid, "ycwdmarkery")
    monkeypatch.chdir(root / "_sources")  # inside the vault
    rc, env = _run(wiki_search, ["ycwdmarkery", "--vaults", vid])
    assert rc == 0
    hits = env.get("results") or env.get("hits") or []
    assert any("alpha" in json.dumps(h).lower() for h in hits), env


def test_reindex_local(tmp_path):
    """`wiki-reindex --full --vault-root` rebuilds the LOCAL db (the vault is registered
    only there) → exit 0 + pages indexed; a global open would fail to find the vault."""
    vid = "loc-reindex-vault"
    root, local_db = _local_vault(tmp_path, vid, "qmark")
    rc, env = _run(wiki_reindex, ["--full", "--vault", vid, "--vault-root", str(root)])
    assert rc == 0 and env.get("action") == "reindexed" and env.get("pages", 0) >= 1
    # the row count lives in the LOCAL db
    n = SQLiteRepository(local_db)._connect().execute(
        "SELECT COUNT(*) FROM pages WHERE vault_id=?", (vid,)).fetchone()[0]
    assert n >= 1


def test_init_register_local(tmp_path):
    """TASK 022 (02-07): `wiki-init --register-existing --local` writes index_db into
    WIKI_SCHEMA.md and registers the `vaults` row into the LOCAL db (not global)."""
    from scripts.wiki_skills import wiki_init
    vid = "init-loc-vault"
    root = tmp_path / vid
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        f"---\nname: WIKI_SCHEMA\nvault_id: {vid}\nschema_version: '2.0'\n"
        f"language: en\nlayout: karpathy\n---\n\n# schema\n", encoding="utf-8")
    rc, env = _run(wiki_init, ["--register-existing", "--vault", str(root), "--local"])
    assert rc == 0
    assert "index_db: .wiki/index.db" in (root / "WIKI_SCHEMA.md").read_text()
    local_db = root / ".wiki" / "index.db"
    assert local_db.is_file()
    n = SQLiteRepository(local_db)._connect().execute(
        "SELECT COUNT(*) FROM vaults WHERE vault_id=?", (vid,)).fetchone()[0]
    assert n == 1


def test_validate_index_db_rel_blocks_yaml_injection():
    """vdd-multi MED-S1 round-2: the index_db validator rejects ALL YAML line breaks —
    `\\n`/`\\r` AND the Unicode separators U+0085/U+2028/U+2029 — plus NUL/`---`/edge ws."""
    from scripts.wiki_skills.wiki_init import _validate_index_db_rel
    assert _validate_index_db_rel(".wiki/index.db")
    assert _validate_index_db_rel("My Vault/index.db")   # internal space is fine
    # YAML line-break codepoints that must be rejected (inject a sibling key):
    for cp in (0x0A, 0x0D, 0x85, 0x2028, 0x2029, 0x0B, 0x0C):
        assert not _validate_index_db_rel("x" + chr(cp) + "vault_id: e"), hex(cp)
    for bad in ["x\x00y", "a---b", " x", "x ", "", "a: b"]:  # "a: b" = YAML map token
        assert not _validate_index_db_rel(bad), repr(bad)


def test_init_rejects_injecting_index_db(tmp_path):
    """End-to-end: `--index-db` carrying a U+0085 line break is rejected (exit 2) and the
    WIKI_SCHEMA.md is left UNTOUCHED (no injected vault_id)."""
    from scripts.wiki_skills import wiki_init
    vid = "inj-vault"
    root = tmp_path / vid
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        f"---\nvault_id: {vid}\nschema_version: '2.0'\nlanguage: en\n"
        f"layout: karpathy\n---\n", encoding="utf-8")
    rc, env = _run(wiki_init, ["--register-existing", "--vault", str(root),
                               "--index-db", "xvault_id: attacker"])
    assert rc == 2 and env.get("error") == "INVALID_INDEX_DB"
    assert "attacker" not in (root / "WIKI_SCHEMA.md").read_text()


def test_enrich_threads_local_db_path(tmp_path, monkeypatch):
    """TASK 022 (M-2): wiki-enrich passes the RESOLVED local index_db down to
    index_from_manifest (not args.db_path=None) → no split-brain (ingest writes local)."""
    import scripts.wiki_skills.wiki_enrich as we
    vid = "enrich-loc-vault"
    root = tmp_path / vid
    root.mkdir()
    (root / "WIKI_SCHEMA.md").write_text(
        f"---\nvault_id: {vid}\nschema_version: '2.0'\nlanguage: en\n"
        f"layout: karpathy\nindex_db: .wiki/index.db\n---\n", encoding="utf-8")
    src = root / "note.txt"
    src.write_text("hello", encoding="utf-8")
    captured: dict = {}
    monkeypatch.setattr(we, "_VENDORED_AVAILABLE", True)
    monkeypatch.setattr(we, "_vendored_ingest",
                        lambda **k: {"manifest_version": "1.1", "pages": []})
    monkeypatch.setattr(we, "validate_manifest", lambda *a, **k: None)

    def _fake_ifm(manifest, vault, vault_root, *, db_path):
        captured["db_path"] = db_path
        return {"failed": [], "indexed": []}
    monkeypatch.setattr(we, "index_from_manifest", _fake_ifm)

    we.main(["--source", str(src), "--vault", vid, "--vault-root", str(root)])
    assert captured["db_path"] == str(root / ".wiki" / "index.db")


def test_all_vaults_island(tmp_path):
    """Island: `wiki-reindex --all-vaults --vault-root <root>` iterates `list_vaults()`
    over ONLY the connected local DB → exactly the 1 local vault (no cross-DB federation).
    A global open would return the platform registry's vaults instead."""
    vid = "loc-island-vault"
    root, _ = _local_vault(tmp_path, vid, "imark")
    rc, env = _run(wiki_reindex, ["--full", "--all-vaults", "--vault-root", str(root)])
    assert rc == 0
    assert env.get("scope") == "all-vaults" and env.get("vaults_processed") == 1
    assert any(r.get("vault_id") == vid for r in env.get("results", []))
