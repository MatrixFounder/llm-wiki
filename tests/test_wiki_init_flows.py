"""Tests for wiki-init flows (tasks-001-21/22/23)."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from scripts.wiki_skills.wiki_init import main


def _run(argv: list[str]) -> tuple[int, dict]:
    """Invoke wiki_init.main(argv); capture stdout JSON + exit code."""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = main(argv)
    finally:
        sys.stdout = old
    return code, json.loads(buf.getvalue())


# =============================================================================
# scaffold-new (task-001-21)
# =============================================================================


def test_scaffold_new_creates_layout(tmp_path):
    vault = tmp_path / "newvault"
    db = tmp_path / "g.db"
    code, out = _run([
        "--scaffold-new", "--vault", str(vault),
        "--vault-id", "test-vault", "--db-path", str(db),
    ])
    assert code == 0
    assert out["action"] == "scaffolded"
    assert (vault / "WIKI_SCHEMA.md").exists()
    assert (vault / "CLAUDE.md").exists()
    # default: ONE agent file (CLAUDE.md); GEMINI.md only with --vendor
    assert not (vault / "GEMINI.md").exists()
    assert out["agent_files"] == {"CLAUDE.md": "written",
                                   ".claude/settings.json": "written"}  # TASK 026
    for sub in ["_sources", "_concepts", "_entities", "_raw/.locks",
                "_raw/failed", "00-Vault-Index/log"]:
        assert (vault / sub).is_dir(), f"missing {sub}"
    # Schema content
    schema = (vault / "WIKI_SCHEMA.md").read_text()
    assert "vault_id: test-vault" in schema


def test_scaffold_new_invalid_vault_id(tmp_path):
    code, out = _run([
        "--scaffold-new", "--vault", str(tmp_path / "v"),
        "--vault-id", "1bad",
        "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 6
    assert out["error"] == "INVALID_VAULT_ID"


def test_scaffold_new_requires_vault_arg(tmp_path):
    """--vault is mandatory: no silent cwd default (prevents accidental
    scaffolds in the project repo root)."""
    code, out = _run(["--scaffold-new", "--db-path", str(tmp_path / "g.db")])
    assert code == 1
    assert out["error"] == "MISSING_VAULT_ARG"


# =============================================================================
# register-existing (task-001-22)
# =============================================================================


def test_register_existing_minimal_vault(minimal_vault: Path, tmp_path):
    """Register the minimal_vault fixture; vault_id from frontmatter."""
    db = tmp_path / "g.db"
    code, out = _run([
        "--register-existing", "--vault", str(minimal_vault),
        "--db-path", str(db),
    ])
    assert code == 0
    assert out["action"] == "registered"
    assert out["vault_id"] == "minimal-test"
    assert out["is_two_tier"] is False


def _schema(vault: Path, vault_id: str, layout: str = "obsidian-personal") -> Path:
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "WIKI_SCHEMA.md").write_text(
        f'---\nvault_id: {vault_id}\nlayout: {layout}\nlanguage: ru\n'
        'description: "My vault"\n---\n# schema\n', encoding="utf-8")
    return vault


def test_register_existing_writes_default_agent_file(tmp_path):
    """A registered vault with no agent file gets exactly ONE by default
    (CLAUDE.md) so an agent launched at its root has wiki operating instructions
    (DF-018-INIT-1). GEMINI.md is NOT written without --vendor."""
    vault = _schema(tmp_path / "personal-x", "personal-x")
    code, out = _run([
        "--register-existing", "--vault", str(vault), "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0 and out["action"] == "registered"
    assert out["agent_files"] == {"CLAUDE.md": "written",
                                   ".claude/settings.json": "written"}  # TASK 026
    body = (vault / "CLAUDE.md").read_text()
    assert "personal-x" in body and "wiki-sync" in body   # rendered + substituted
    assert not (vault / "GEMINI.md").exists()


def test_register_existing_vendor_gemini(tmp_path):
    """`--vendor gemini` writes ONLY GEMINI.md (an exact copy of the Claude base)."""
    vault = _schema(tmp_path / "gem-x", "gem-x")
    code, out = _run([
        "--register-existing", "--vault", str(vault),
        "--vendor", "gemini", "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0
    assert out["agent_files"] == {"GEMINI.md": "written"}
    assert (vault / "GEMINI.md").exists() and not (vault / "CLAUDE.md").exists()


def test_register_existing_vendor_all(tmp_path):
    """`--vendor all` writes every vendor's file; the instruction bodies are identical
    (all reuse CLAUDE.md.tmpl for now). TASK 043: also AGENTS.md (cross-vendor, written
    ONCE despite both `agents` and `pi` selecting it) + pi's permissions.json."""
    vault = _schema(tmp_path / "both-x", "both-x")
    code, out = _run([
        "--register-existing", "--vault", str(vault),
        "--vendor", "all", "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0
    assert out["agent_files"] == {
        "CLAUDE.md": "written", "GEMINI.md": "written", "AGENTS.md": "written",
        ".claude/settings.json": "written",            # TASK 026 (claude)
        ".pi/extensions/permissions.json": "written",  # TASK 043 (pi)
    }
    assert (vault / "GEMINI.md").read_text() == (vault / "CLAUDE.md").read_text()
    assert (vault / "AGENTS.md").read_text() == (vault / "CLAUDE.md").read_text()


def test_register_existing_vendor_agents(tmp_path):
    """TASK 043: `--vendor agents` writes ONLY the cross-vendor AGENTS.md (no settings)."""
    vault = _schema(tmp_path / "ag-x", "ag-x")
    code, out = _run([
        "--register-existing", "--vault", str(vault),
        "--vendor", "agents", "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0
    assert out["agent_files"] == {"AGENTS.md": "written"}
    assert (vault / "AGENTS.md").exists()
    assert not (vault / "CLAUDE.md").exists() and not (vault / ".pi").exists()


def test_register_existing_vendor_pi(tmp_path):
    """TASK 043: `--vendor pi` writes AGENTS.md + a valid `.pi/extensions/permissions.json`
    (parent dirs created, vault-contained, no allow-list — mode + danger patterns)."""
    vault = _schema(tmp_path / "pi-x", "pi-x")
    code, out = _run([
        "--register-existing", "--vault", str(vault),
        "--vendor", "pi", "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0
    assert out["agent_files"] == {"AGENTS.md": "written",
                                  ".pi/extensions/permissions.json": "written"}
    perms = vault / ".pi" / "extensions" / "permissions.json"
    assert perms.is_file()                                     # nested parents created
    cfg = json.loads(perms.read_text(encoding="utf-8"))        # valid JSON
    assert cfg["mode"] in {"default", "acceptEdits", "fullAuto", "bypassPermissions"}
    pats = {p["pattern"] for p in cfg["dangerousPatterns"]}
    assert "rm -rf" in pats
    # security backstop (TASK 043 audit): fullAuto auto-runs safe bash, so the destructive /
    # eval-adjacent obsidian surfaces the obsidian-cli skill flags T2/T3 MUST be gated here.
    # `obsidian-selection apply` (TASK 068) is a T2 note mutation — gated like move/rename/delete.
    assert {"obsidian eval", "obsidian command", "obsidian delete", "obsidian-selection apply"} <= pats
    # VERBATIM copy of the shipped template (JSON, not Template-substituted)
    tmpl = Path(__file__).resolve().parent.parent / "templates" / "vault.pi-permissions.json"
    assert perms.read_text(encoding="utf-8") == tmpl.read_text(encoding="utf-8")


def test_register_existing_pi_dedup_second_pass(tmp_path):
    """TASK 043 dedup: `--vendor pi` on a vault that ALREADY has AGENTS.md (e.g. a prior
    `--vendor agents` run) must NOT re-render it (→ "exists") yet STILL write pi's own
    settings — the `if filename in out` branch must not skip the settings block."""
    vault = _schema(tmp_path / "pi-2nd", "pi-2nd")
    (vault / "AGENTS.md").write_text("# operator's own AGENTS\n", encoding="utf-8")
    code, out = _run([
        "--register-existing", "--vault", str(vault),
        "--vendor", "pi", "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0
    assert out["agent_files"] == {"AGENTS.md": "exists",
                                  ".pi/extensions/permissions.json": "written"}
    assert (vault / "AGENTS.md").read_text() == "# operator's own AGENTS\n"  # not clobbered
    assert (vault / ".pi" / "extensions" / "permissions.json").is_file()      # settings still landed


def test_register_existing_pi_preserves_operator_permissions(tmp_path):
    """TASK 043: a pre-existing `.pi/extensions/permissions.json` is NEVER clobbered
    without --force (mirrors the .claude/settings.json non-destructive contract)."""
    vault = _schema(tmp_path / "pi-keep", "pi-keep")
    pdir = vault / ".pi" / "extensions"
    pdir.mkdir(parents=True)
    (pdir / "permissions.json").write_text('{"mode": "default"}\n', encoding="utf-8")
    code, out = _run([
        "--register-existing", "--vault", str(vault),
        "--vendor", "pi", "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0 and out["agent_files"][".pi/extensions/permissions.json"] == "exists"
    assert (pdir / "permissions.json").read_text() == '{"mode": "default"}\n'  # untouched


def test_register_existing_invalid_vendor(tmp_path):
    """An unknown --vendor → INVALID_VENDOR (exit 2), names the known set."""
    vault = _schema(tmp_path / "bad-x", "bad-x")
    code, out = _run([
        "--register-existing", "--vault", str(vault),
        "--vendor", "copilot", "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 2 and out["error"] == "INVALID_VENDOR"
    assert "copilot" in out["unknown"] and "claude" in out["known"]


def test_register_existing_preserves_operator_agent_file(tmp_path):
    """An operator's own CLAUDE.md is NEVER clobbered without --force; the OTHER
    selected vendor (GEMINI.md, via --vendor all) is still created (per-file)."""
    vault = tmp_path / "has-claude"
    vault.mkdir()
    (vault / "WIKI_SCHEMA.md").write_text(
        '---\nvault_id: has-claude\nlayout: karpathy\n---\n# schema\n', encoding="utf-8")
    (vault / "CLAUDE.md").write_text("# MY OWN INSTRUCTIONS\n", encoding="utf-8")
    code, out = _run([
        "--register-existing", "--vault", str(vault),
        "--vendor", "all", "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0
    assert out["agent_files"]["CLAUDE.md"] == "exists"
    assert (vault / "CLAUDE.md").read_text() == "# MY OWN INSTRUCTIONS\n"
    assert out["agent_files"]["GEMINI.md"] == "written"   # other selected vendor still scaffolded


# =============================================================================
# .claude/settings.json (TASK 026)
# =============================================================================


def test_register_existing_writes_claude_settings(tmp_path):
    """TASK 026: registering with the (default) claude vendor also drops
    `.claude/settings.json` — byte-identical to the shipped template, in a created
    `.claude/` dir — so the vault stops re-confirming wiki-* commands."""
    vault = _schema(tmp_path / "set-x", "set-x")
    code, out = _run([
        "--register-existing", "--vault", str(vault), "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0
    assert out["agent_files"][".claude/settings.json"] == "written"
    settings = vault / ".claude" / "settings.json"
    assert settings.is_file()
    # VERBATIM copy (not Template-substituted — the JSON carries `$schema`)
    tmpl = Path(__file__).resolve().parent.parent / "templates" / "vault.claude-settings.json"
    assert settings.read_text(encoding="utf-8") == tmpl.read_text(encoding="utf-8")
    assert json.loads(settings.read_text())["defaultMode"] == "acceptEdits"  # valid JSON


def test_register_existing_preserves_operator_settings(tmp_path):
    """TASK 026: a pre-existing `.claude/settings.json` (the operator's accumulated
    rules) is NEVER clobbered without --force; --force overwrites it; the personal
    `settings.local.json` is NEVER touched either way."""
    vault = _schema(tmp_path / "keep-set", "keep-set")
    cdir = vault / ".claude"
    cdir.mkdir()
    (cdir / "settings.json").write_text('{"MINE": true}\n', encoding="utf-8")
    (cdir / "settings.local.json").write_text('{"LOCAL": true}\n', encoding="utf-8")
    code, out = _run([
        "--register-existing", "--vault", str(vault), "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0 and out["agent_files"][".claude/settings.json"] == "exists"
    assert (cdir / "settings.json").read_text() == '{"MINE": true}\n'        # untouched
    assert (cdir / "settings.local.json").read_text() == '{"LOCAL": true}\n'  # never touched
    # --force overwrites settings.json with the template, but still NOT settings.local.json
    _code2, out2 = _run([
        "--register-existing", "--vault", str(vault), "--db-path", str(tmp_path / "g2.db"),
        "--force",
    ])
    assert out2["agent_files"][".claude/settings.json"] == "written"
    assert '"defaultMode"' in (cdir / "settings.json").read_text()
    assert (cdir / "settings.local.json").read_text() == '{"LOCAL": true}\n'


def test_register_existing_gemini_writes_no_settings(tmp_path):
    """TASK 026: a vendor that declares no `settings_file` (gemini) writes none, and
    does not create `.claude/`."""
    vault = _schema(tmp_path / "gem-set", "gem-set")
    code, out = _run([
        "--register-existing", "--vault", str(vault), "--vendor", "gemini",
        "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0
    assert ".claude/settings.json" not in out["agent_files"]
    assert not (vault / ".claude").exists()


def test_write_agent_files_resilient_to_missing_template(tmp_path):
    """vdd-adversarial: a vendor pointing at a missing/misconfigured template must
    NOT crash init — the working vendors still get written, the broken one is
    reported as 'error' (best-effort, never a partial-state crash)."""
    from scripts.wiki_skills import wiki_init as wi
    vendors = {"claude": ("CLAUDE.md", "CLAUDE.md.tmpl"),
               "gemini": ("GEMINI.md", "MISSING.tmpl")}
    ph = {"vault_id": "x-vault", "language": "en", "layout": "karpathy", "description": "y"}
    res = wi._write_agent_files(tmp_path, ph, vendors, ["claude", "gemini"], force=False)
    assert res == {"CLAUDE.md": "written", "GEMINI.md": "error"}   # must not raise
    assert (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "GEMINI.md").exists()


def test_register_existing_two_tier_detected(multi_vault: dict[str, Path], tmp_path):
    """vault-alpha has Lessons/Course-A/_concepts — is_two_tier=True."""
    db = tmp_path / "g.db"
    code, out = _run([
        "--register-existing", "--vault", str(multi_vault["vault-alpha"]),
        "--db-path", str(db),
    ])
    assert code == 0
    assert out["is_two_tier"] is True


def test_register_existing_missing_schema(tmp_path):
    bare = tmp_path / "no-schema"
    bare.mkdir()
    code, out = _run([
        "--register-existing", "--vault", str(bare),
        "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 6
    assert out["error"] == "MISSING_WIKI_SCHEMA"


def test_register_existing_missing_vault_id(tmp_path):
    """WIKI_SCHEMA.md without vault_id → fail-fast with suggestion."""
    vault = tmp_path / "no-vid"
    vault.mkdir()
    (vault / "WIKI_SCHEMA.md").write_text(
        "---\nname: WIKI_SCHEMA\nschema_version: '2.0'\n---\n"
    )
    code, out = _run([
        "--register-existing", "--vault", str(vault),
        "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 6
    assert out["error"] == "MISSING_VAULT_ID"
    assert out["suggested_vault_id"] == "no-vid"


def test_register_existing_idempotent(minimal_vault: Path, tmp_path):
    """Re-registering the same vault returns 'already-registered'."""
    db = tmp_path / "g.db"
    args = ["--register-existing", "--vault", str(minimal_vault),
            "--db-path", str(db)]
    _run(args)
    code, out = _run(args)
    assert code == 0
    assert out["action"] == "already-registered"


# =============================================================================
# reconcile (task-001-23)
# =============================================================================


def test_reconcile_no_change(minimal_vault: Path, tmp_path):
    db = tmp_path / "g.db"
    _run(["--register-existing", "--vault", str(minimal_vault),
          "--db-path", str(db)])
    code, out = _run(["--reconcile", "--vault", str(minimal_vault),
                      "--db-path", str(db)])
    assert code == 0
    assert out["action"] == "no-change"


def test_reconcile_unregistered(minimal_vault: Path, tmp_path):
    code, out = _run(["--reconcile", "--vault", str(minimal_vault),
                      "--db-path", str(tmp_path / "g.db")])
    assert code == 6
    assert out["error"] == "VAULT_NOT_REGISTERED"


def test_reconcile_rename_requires_confirm(minimal_vault: Path, tmp_path):
    db = tmp_path / "g.db"
    _run(["--register-existing", "--vault", str(minimal_vault),
          "--db-path", str(db)])
    # Mutate the WIKI_SCHEMA.md vault_id
    schema = (minimal_vault / "WIKI_SCHEMA.md").read_text()
    schema = schema.replace("vault_id: minimal-test", "vault_id: renamed-vault")
    (minimal_vault / "WIKI_SCHEMA.md").write_text(schema)
    # Without --confirm: warning + exit 7
    code, out = _run(["--reconcile", "--vault", str(minimal_vault),
                      "--db-path", str(db)])
    assert code == 7
    assert out["warning"] == "VAULT_RENAMED"
    # With --confirm: rename succeeds
    code, out = _run(["--reconcile", "--vault", str(minimal_vault),
                      "--db-path", str(db), "--confirm"])
    assert code == 0
    assert out["action"] == "renamed"
    assert out["old_vault_id"] == "minimal-test"
    assert out["new_vault_id"] == "renamed-vault"


# =============================================================================
# Page-type templates copied into the vault (existing-tree layouts)
# =============================================================================


def test_register_existing_copies_page_types_non_two_tier(tmp_path):
    """An existing-tree layout (obsidian-personal) gets the 13 page-type scaffolds
    copied into <vault>/.wiki/page-types/ so a vault-launched agent has them locally;
    re-run is non-destructive (→ 'exists')."""
    vault = _schema(tmp_path / "pt-x", "pt-x")  # obsidian-personal
    code, out = _run([
        "--register-existing", "--vault", str(vault), "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0
    ptt = out["page_type_templates"]
    assert len(ptt) == 13 and all(v == "written" for v in ptt.values())
    assert {".wiki/page-types/decision.md", ".wiki/page-types/agent.md"} <= set(ptt)
    assert (vault / ".wiki" / "page-types" / "decision.md").exists()
    # idempotent / non-destructive on re-run
    code2, out2 = _run([
        "--register-existing", "--vault", str(vault), "--db-path", str(tmp_path / "g.db"),
    ])
    assert all(v == "exists" for v in out2["page_type_templates"].values())


def test_page_types_not_copied_for_karpathy(tmp_path):
    """The Karpathy family (two-tier scaffold) uses the concept/entity model, not
    typed classes → no page-type copy."""
    vault = tmp_path / "kv"
    code, out = _run([
        "--scaffold-new", "--vault", str(vault), "--vault-id", "karp-x",
        "--layout", "karpathy", "--db-path", str(tmp_path / "g.db"),
    ])
    assert code == 0
    assert out["page_type_templates"] == {}
    assert not (vault / ".wiki" / "page-types").exists()


def test_copied_page_types_are_never_indexed(tmp_path):
    """SAFETY INVARIANT: the copied .wiki/page-types/*.md carry `type: decision` with
    placeholder titles — they must NEVER be indexed as junk pages. The walk prunes
    dot-directories, so .wiki/ is never descended (obsidian-personal does not even
    list `.wiki/**` in `ignore`, yet the dot-prune keeps it out)."""
    from scripts.wiki_index.reindex import reindex_full
    from scripts.wiki_index.sqlite_repository import SQLiteRepository

    vault = _schema(tmp_path / "pt-idx", "pt-idx")  # obsidian-personal
    (vault / "05 - Notes").mkdir(parents=True)
    (vault / "05 - Notes" / "real.md").write_text(
        "---\ntype: note\ntitle: Real\n---\nbody\n", encoding="utf-8")
    db = tmp_path / "g.db"
    code, out = _run(["--register-existing", "--vault", str(vault), "--db-path", str(db)])
    assert code == 0
    assert (vault / ".wiki" / "page-types" / "decision.md").exists()  # copied

    repo = SQLiteRepository(db)
    try:
        reindex_full(repo, "pt-idx")
        rows = repo._connect().execute(
            "SELECT slug, type, file_path FROM pages WHERE vault_id='pt-idx'").fetchall()
    finally:
        repo.close()
    assert all(".wiki" not in (r[2] or "") for r in rows)   # no scaffold indexed
    assert not any(r[1] == "decision" for r in rows)         # no junk decision page
    assert any(r[0] == "real" for r in rows)                 # the real note IS indexed
