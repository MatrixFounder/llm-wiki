"""TASK 049 (R-3) — `wiki-search --audience` e2e: profile resolution
(flag > vault default_audience > OFF), SQL-side filtering, envelope echo
only-when-active, INVALID_AUDIENCE, vault-ladder override, UC-7 cross-vault.
"""

from __future__ import annotations

import contextlib
import io
import json
from datetime import datetime
from pathlib import Path

from scripts.wiki_index.models import Vault
from scripts.wiki_index.reindex import reindex_full
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_skills import wiki_search

VID = "aud-vault"


def _write(vault: Path, rel: str, fm: str, body: str) -> None:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def _seed(tmp_path: Path, *, policy: str = "") -> tuple[Path, Path]:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "WIKI_SCHEMA.md").write_text(
        "---\nname: WIKI_SCHEMA\nvault_id: " + VID + "\n"
        "schema_version: '2.0'\nlanguage: en\nlayout: karpathy\n"
        + policy + "---\n\n# schema\n")
    _write(vault, "_sources/open-note.md",
           "type: summary\ntitle: Open Note\ndate: 2026-07-01\ntags: [t]",
           "Hermes routes public messages.")
    _write(vault, "_sources/secret-note.md",
           "type: summary\ntitle: Secret Note\ndate: 2026-07-01\ntags: [t]\n"
           "classification: restricted",
           "Hermes routes secret messages.")
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=VID, name="v", root_path=vault,
        schema_version="7.0", registered_at=datetime(2026, 7, 1)))
    reindex_full(repo, VID)
    repo.close()
    return vault, db


def _run(vault: Path, db: Path, *argv: str) -> tuple[int, dict]:
    buf = io.StringIO()
    full = ["hermes", "--vaults", VID, "--vault-root", str(vault),
            "--db-path", str(db), *argv]
    with contextlib.redirect_stdout(buf):
        code = wiki_search.main(full)
    return code, json.loads(buf.getvalue())


def _slugs(env: dict) -> set[str]:
    return {h["slug"] for h in env["hits"]}


def test_off_returns_everything_no_audience_key(tmp_path):
    vault, db = _seed(tmp_path)
    code, env = _run(vault, db)
    assert code == 0
    assert _slugs(env) == {"open-note", "secret-note"}
    assert "audience" not in env          # NFR-1: OFF envelope unchanged


def test_audience_filters_and_echoes(tmp_path):
    vault, db = _seed(tmp_path)
    code, env = _run(vault, db, "--audience", "internal")
    assert code == 0
    assert _slugs(env) == {"open-note"}
    assert env["audience"] == "internal"


def test_audience_top_level_sees_all(tmp_path):
    vault, db = _seed(tmp_path)
    code, env = _run(vault, db, "--audience", "restricted")
    assert code == 0
    assert _slugs(env) == {"open-note", "secret-note"}


def test_declared_default_audience_activates_without_flag(tmp_path):
    vault, db = _seed(
        tmp_path,
        policy=("policy:\n  levels: [public, internal, restricted]\n"
                "  default_audience: internal\n"))
    code, env = _run(vault, db)
    assert code == 0
    assert _slugs(env) == {"open-note"}
    assert env["audience"] == "internal"


def test_vault_ladder_overrides_builtin(tmp_path):
    vault, db = _seed(
        tmp_path, policy="policy:\n  levels: [lo, restricted]\n")
    # 'internal' is not in THIS vault's ladder → INVALID_AUDIENCE, no value echo.
    code, env = _run(vault, db, "--audience", "internal")
    assert code == 2
    assert env["error"] == "INVALID_AUDIENCE"
    assert "internal" not in env["reason"]
    # the vault's own level works; restricted page visible at its ladder top.
    code, env = _run(vault, db, "--audience", "restricted")
    assert code == 0
    assert _slugs(env) == {"open-note", "secret-note"}


def test_bad_flag_shape_rejected_without_echo(tmp_path):
    vault, db = _seed(tmp_path)
    code, env = _run(vault, db, "--audience", "NOT!VALID")
    assert code == 2
    assert env["error"] == "INVALID_AUDIENCE"
    assert "NOT!VALID" not in json.dumps(env)


def test_malformed_policy_block_fails_loud(tmp_path):
    vault, db = _seed(
        tmp_path, policy="policy:\n  levels: [public, public]\n")
    code, env = _run(vault, db, "--audience", "public")
    assert code == 2
    assert env["error"] == "INVALID_POLICY"


def test_uc7_cross_vault_home_ladder_fails_closed_foreign_labels(tmp_path):
    """UC-7: --vaults all under the home vault's ladder — a foreign vault's
    label ('geheim') is unknown to the home ladder → excluded, never included."""
    vault, db = _seed(tmp_path)
    other = tmp_path / "other"
    _write(other, "_sources/foreign-note.md",
           "type: summary\ntitle: Foreign\ndate: 2026-07-01\ntags: [t]\n"
           "classification: geheim",
           "Hermes routes foreign messages.")
    repo = SQLiteRepository(db)
    repo.register_vault(Vault(
        vault_id="other-vault", name="o", root_path=other,
        schema_version="7.0", registered_at=datetime(2026, 7, 1)))
    reindex_full(repo, "other-vault")
    repo.close()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_search.main(
            ["hermes", "--vaults", "all", "--vault-root", str(vault),
             "--db-path", str(db), "--audience", "restricted"])
    env = json.loads(buf.getvalue())
    assert code == 0
    # home ladder top sees home pages; the foreign label fails closed.
    assert _slugs(env) == {"open-note", "secret-note"}


# =============================================================================
# vdd-multi review fixes (SEC-1 / SEC-2 / SEC-3)
# =============================================================================

def test_sec1_named_vault_default_audience_applies_from_outside(tmp_path):
    """SEC-1: `--vaults X` run from OUTSIDE X's directory (no --vault-root)
    must still apply X's declared default_audience — the registered root
    supplies the policy."""
    vault, db = _seed(
        tmp_path,
        policy=("policy:\n  levels: [public, internal, restricted]\n"
                "  default_audience: internal\n"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        # NOTE: no --vault-root; CWD (the repo) is outside any vault.
        code = wiki_search.main(
            ["hermes", "--vaults", VID, "--db-path", str(db)])
    env = json.loads(buf.getvalue())
    assert code == 0
    assert _slugs(env) == {"open-note"}          # restricted filtered
    assert env["audience"] == "internal"


def test_sec2_foreign_unclassified_page_fails_closed(tmp_path):
    """SEC-2: a foreign vault's UNCLASSIFIED page must not inherit the home
    vault's default_level under a cross-vault scoped search."""
    vault, db = _seed(tmp_path)
    other = tmp_path / "other"
    _write(other, "_sources/foreign-plain.md",
           "type: summary\ntitle: Foreign Plain\ndate: 2026-07-01\ntags: [t]",
           "Hermes routes foreign plain messages.")
    _write(other, "_sources/foreign-public.md",
           "type: summary\ntitle: Foreign Public\ndate: 2026-07-01\ntags: [t]\n"
           "classification: public",
           "Hermes routes foreign public messages.")
    repo = SQLiteRepository(db)
    repo.register_vault(Vault(
        vault_id="other-vault", name="o", root_path=other,
        schema_version="7.0", registered_at=datetime(2026, 7, 1)))
    reindex_full(repo, "other-vault")
    repo.close()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = wiki_search.main(
            ["hermes", "--vaults", "all", "--vault-root", str(vault),
             "--db-path", str(db), "--audience", "internal"])
    env = json.loads(buf.getvalue())
    assert code == 0
    slugs = _slugs(env)
    assert "foreign-plain" not in slugs      # unclassified foreign: fail closed
    assert "foreign-public" in slugs         # explicit in-ladder label: passes
    assert "open-note" in slugs              # home unclassified: default applies


def test_sec3_broken_yaml_with_declared_policy_fails_loud(tmp_path):
    """SEC-3: unparseable WIKI_SCHEMA.md that visibly declares `policy:` must
    surface INVALID_POLICY — never silent OFF."""
    vault, db = _seed(tmp_path)
    # Corrupt the frontmatter YAML while keeping a visible policy: key.
    (vault / "WIKI_SCHEMA.md").write_text(
        "---\nname: WIKI_SCHEMA\nvault_id: " + VID + "\n"
        "policy:\n  levels: [public, internal\n"   # unclosed list → YAMLError
        "---\n\n# s\n")
    code, env = _run(vault, db)
    assert code == 2
    assert env["error"] == "INVALID_POLICY"


def test_sec3_broken_yaml_without_policy_stays_off(tmp_path):
    """A vault with unrelated config damage and NO policy key keeps pre-049
    behavior (silent OFF, search works)."""
    vault, db = _seed(tmp_path)
    (vault / "WIKI_SCHEMA.md").write_text(
        "---\nname: WIKI_SCHEMA\nvault_id: " + VID + "\n"
        "broken: [unclosed\n"
        "---\n\n# s\n")
    code, env = _run(vault, db)
    assert code == 0
    assert _slugs(env) == {"open-note", "secret-note"}
    assert "audience" not in env
