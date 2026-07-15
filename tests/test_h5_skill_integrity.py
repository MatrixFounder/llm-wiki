"""TASK 067 (H-5) — skill-contract integrity is a MECHANISM, not a comment.

The population + mutation + wiring gate for the SHA-256 hash-pin of every `SKILL.md` loaded
VERBATIM into the orchestrator's LLM context (`config/skill-integrity.sha256`). Its defining
property is that it can go RED: an un-re-pinned prompt edit fails
`test_every_pinned_hash_matches_the_live_file`; a new banner'd contract that is neither pinned
nor exempt fails `test_every_marked_contract_is_pinned_or_exempted`. Both are grep-derived — the
roster is never hand-listed (the unenumerated-surface guard). See docs/tasks/task-067-*,
docs/issues/h-5-*.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

import scripts.pin_skill_integrity as pin
from scripts.wiki_skills import _common
from scripts.wiki_skills._common import (
    _DESIGNATED_VERBATIM_CONTRACTS,
    _INTEGRITY_EXEMPT,
    _INTEGRITY_MARKER,
    _REPO_ROOT,
    _sha256_file,
    discover_integrity_roster,
    emit_prepare_with_integrity,
    load_integrity_manifest,
    skill_integrity_block,
    verify_skill_integrity,
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")

# The complete pinned surface, as repo-relative PATHS, DERIVED from the positive allow-list (which
# is asserted == the grep roster — no second hand-list). Includes SKILL.md contracts AND the
# references/*.md contracts (the H-6 fence, the tier table) the cycle-2 review found uncovered.
_DESIGNATED_PATHS = sorted(_DESIGNATED_VERBATIM_CONTRACTS)
# The subset addressable BY skill-name (`skills/<name>/SKILL.md`) — what `verify_skill_integrity
# (name)` and the rails resolve. references/*.md are pinned + verified by PATH, not by name.
_RAIL_CONTRACT_NAMES = sorted(
    p.split("/")[1] for p in _DESIGNATED_VERBATIM_CONTRACTS if p.endswith("/SKILL.md"))

# (rail source file → the contract name it must pass to the shared gate). obsidian-cli is NOT a
# rail (invoked directly), so its coverage is the manifest + population/registry tests, not a
# per-invocation prepare check — see test_designated_contracts_are_all_pinned.
_RAIL_WIRING = {
    "scripts/wiki_skills/wiki_extract_concepts/__init__.py": "concept-extraction",
    "scripts/wiki_skills/wiki_extract_decisions/__init__.py": "decision-extraction",
    "scripts/wiki_skills/wiki_query.py": "wiki-query-synthesis",
    "scripts/wiki_skills/wiki_verify_multi.py": "wiki-verify",
}


def _bad_manifest(tmp_path: Any, skill: str = "concept-extraction") -> Any:
    """A manifest pinning a deliberately-wrong hash for one contract ⇒ induces `drift` without
    touching any real file."""
    p = tmp_path / "bad.sha256"
    p.write_text("0" * 64 + f"  skills/{skill}/SKILL.md\n", encoding="utf-8")
    return p


# ── R-067-1 — every pin matches the live file (the mechanical supply-chain gate) ──────────────
def test_every_pinned_hash_matches_the_live_file() -> None:
    manifest = load_integrity_manifest()
    assert manifest, "config/skill-integrity.sha256 is missing or empty"
    for rel, pinned in manifest.items():
        actual = _sha256_file(_REPO_ROOT / rel)
        assert actual == pinned, (
            f"{rel}: live bytes ({actual}) != pinned ({pinned}). An approved edit must be "
            f"re-pinned: `python3 scripts/pin_skill_integrity.py --write`.")


# ── R-067-2 — the surface is grep-derived; every marker file is pinned or exempt ──────────────
def test_every_marked_contract_is_pinned_or_exempted() -> None:
    # ★ The broad completeness guard: grep EVERY markdown under skills/ (recursive — SKILL.md,
    # references/, anywhere), NOT just the two contract shapes the roster pins. So a marker'd file
    # in an UNPINNED location (the cycle-2 file-shape blind spot) fails here even though the precise
    # roster glob would never have looked at it. This is the "don't scope enrolment to a filename
    # shape" fix, as a test.
    manifest = load_integrity_manifest() or {}
    for p in sorted((_REPO_ROOT / "skills").glob("**/*.md")):
        rel = p.relative_to(_REPO_ROOT).as_posix()
        try:
            body = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _INTEGRITY_MARKER not in body:
            continue
        assert rel in manifest or rel in _INTEGRITY_EXEMPT, (
            f"{rel} carries the {_INTEGRITY_MARKER!r} marker but is neither pinned nor exempt — "
            f"pin it (`scripts/pin_skill_integrity.py --write`) or add it to _INTEGRITY_EXEMPT "
            f"with a reason.")


def test_registry_equals_the_grep_roster_both_ways() -> None:
    # ★ cycle-2 MINOR-B: "two independent enrolments that must AGREE" is now a MECHANISM, not prose.
    # marker-grep roster == positive allow-list, BOTH directions. A marker'd+pinned file missing
    # from the registry (or vice-versa) fails here — the cross-check can't silently degrade.
    assert set(discover_integrity_roster()) == set(_DESIGNATED_VERBATIM_CONTRACTS)


def test_manifest_pins_exactly_the_grep_derived_roster() -> None:
    manifest = load_integrity_manifest() or {}
    assert set(manifest) == set(discover_integrity_roster()), (
        "the committed manifest and the grep-derived roster disagree — re-pin.")


def test_exempt_files_actually_carry_the_marker() -> None:
    # A stale exemption (for a file that no longer carries the marker) hides intent and could
    # mask a future real contract that reuses the path.
    for rel in _INTEGRITY_EXEMPT:
        p = _REPO_ROOT / rel
        assert p.exists(), f"exempt path does not exist: {rel}"
        assert _INTEGRITY_MARKER in p.read_text(encoding="utf-8"), (
            f"{rel} is exempt but no longer carries {_INTEGRITY_MARKER!r} — drop the exemption.")


# ── R-067-2 (MAJOR-1 closure) — the SECOND, independent enrolment cross-check ──────────────────
# The v1 gate enrolled ONLY via the marker grep, so a designated contract that never got the
# marker (obsidian-cli) was silently uncovered while every gate stayed green. These two tests are
# the positive allow-list + the load-site derivation the adversarial review asked for: a gap in
# the marker enrolment is now caught by a DIFFERENT signal.
def test_designated_contracts_are_all_pinned() -> None:
    # The positive allow-list: every contract PATH the orchestrator loads verbatim (SKILL.md AND
    # references/*.md) must be pinned with a matching hash. Catches a designated contract losing its
    # marker (→ dropped from the marker-roster) — this fails independently of the grep.
    manifest = load_integrity_manifest() or {}
    for rel, why in _DESIGNATED_VERBATIM_CONTRACTS.items():
        assert rel in manifest, f"designated verbatim contract {rel!r} ({why}) is not pinned"
        assert _sha256_file(_REPO_ROOT / rel) == manifest[rel], f"{rel} pin does not match live bytes"


def test_every_skill_load_site_is_pinned_or_exempt() -> None:
    # Load-site derivation: every `Skill({skill: "X"})` load written into a workflow/command must
    # resolve to a pinned-or-exempt contract. A future rail that ships a Skill-load without the
    # marker fails HERE (the enrolment blind spot, closed for the Skill({}) convention). Regex is
    # tolerant of interior whitespace and single/double quotes (cycle-2 M-1).
    manifest = load_integrity_manifest() or {}
    load_re = re.compile(r'Skill\(\{\s*skill\s*:\s*["\']([a-z0-9-]+)')
    loaded: set[str] = set()
    for d in ("workflows", "commands"):
        for f in (_REPO_ROOT / d).glob("*.md"):
            loaded.update(load_re.findall(f.read_text(encoding="utf-8")))
    assert loaded, "no Skill({skill:...}) load sites found — the derivation regex likely broke"
    for name in sorted(loaded):
        rel = f"skills/{name}/SKILL.md"
        assert rel in manifest or rel in _INTEGRITY_EXEMPT, (
            f"{rel} is loaded via Skill({{skill:{name!r}}}) but is neither pinned nor exempt.")


# ── R-067-3 — the primitive detects drift and is value-free (CWE-117/209) ─────────────────────
def test_verify_skill_integrity_ok_on_clean_tree() -> None:
    for name in _RAIL_CONTRACT_NAMES:
        assert verify_skill_integrity(name).status == "ok", name


def test_verify_skill_integrity_detects_drift(tmp_path: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(_common, "SKILL_INTEGRITY_MANIFEST", _bad_manifest(tmp_path))
    r = verify_skill_integrity("concept-extraction")
    assert r.status == "drift"
    assert r.expected == "0" * 64
    assert r.actual is not None and _HEX64.match(r.actual)


def test_unpinned_and_manifest_unavailable_are_distinct(tmp_path: Any, monkeypatch: Any) -> None:
    empty = tmp_path / "empty.sha256"
    empty.write_text("# header only, no pins\n", encoding="utf-8")
    monkeypatch.setattr(_common, "SKILL_INTEGRITY_MANIFEST", empty)
    assert verify_skill_integrity("concept-extraction").status == "unpinned"

    monkeypatch.setattr(_common, "SKILL_INTEGRITY_MANIFEST", tmp_path / "does-not-exist.sha256")
    assert verify_skill_integrity("concept-extraction").status == "manifest_unavailable"


def test_bom_pin_survives_and_malformed_digest_is_rejected(
    tmp_path: Any, monkeypatch: Any,
) -> None:
    # cycle-2 MINOR-1 (corrected): the BOM goes on the FIRST line, which is a REAL pin (no comment
    # header). Under plain `utf-8` the BOM prepends to the hash (65 chars) → hex guard rejects → the
    # pin is DROPPED (reads `unpinned`); `utf-8-sig` prevents that. This test FAILS under `utf-8` and
    # PASSES under `utf-8-sig`, so it actually exercises the fix (the old test did not). The
    # malformed-digest line is still rejected — a bad token never becomes a pin.
    real = _sha256_file(_REPO_ROOT / "skills/concept-extraction/SKILL.md")
    m = tmp_path / "m.sha256"
    m.write_text(
        f"﻿{real}  skills/concept-extraction/SKILL.md\n"
        "not-a-hash  skills/bogus/SKILL.md\n",
        encoding="utf-8")
    monkeypatch.setattr(_common, "SKILL_INTEGRITY_MANIFEST", m)
    parsed = load_integrity_manifest() or {}
    assert parsed == {"skills/concept-extraction/SKILL.md": real}, (
        "the BOM'd real pin must survive (utf-8-sig) and the malformed line must be rejected")
    assert verify_skill_integrity("concept-extraction").status == "ok"


def test_discover_roster_is_fail_loud_on_an_unreadable_contract(
    tmp_path: Any, monkeypatch: Any,
) -> None:
    # MINOR-2: an unreadable marker-candidate must RAISE, not silently shrink the protected set.
    fake_repo = tmp_path / "repo"
    (fake_repo / "skills" / "broken").mkdir(parents=True)
    # a broken symlink → read_text raises FileNotFoundError (an OSError)
    (fake_repo / "skills" / "broken" / "SKILL.md").symlink_to(tmp_path / "nowhere")
    monkeypatch.setattr(_common, "_REPO_ROOT", fake_repo)
    with pytest.raises(RuntimeError):
        discover_integrity_roster()


def test_result_never_echoes_the_body() -> None:
    # Value-free BY CONSTRUCTION: exactly {status, skill, expected, actual}; skill is the
    # repo-relative path; hashes are hex or None — never a byte of the contract body.
    for name in _RAIL_CONTRACT_NAMES:
        block = skill_integrity_block(name)
        assert set(block) == {"status", "skill", "expected", "actual"}
        assert block["skill"] == f"skills/{name}/SKILL.md"
        for h in (block["expected"], block["actual"]):
            assert h is None or _HEX64.match(h)


# ── R-067-5 — every pinned contract reports ok; every rail is wired ───────────────────────────
def test_all_designated_contracts_report_ok_via_the_shared_gate(capsys: Any) -> None:
    for name in _RAIL_CONTRACT_NAMES:
        code = emit_prepare_with_integrity({}, name)
        out = json.loads(capsys.readouterr().out)
        assert code == 0
        assert out["integrity"]["status"] == "ok", name
        assert out["integrity"]["skill"] == f"skills/{name}/SKILL.md"


def test_every_prepare_rail_is_wired_to_the_gate() -> None:
    # The wiring, RUN over the source: each rail calls the shared gate with ITS contract name —
    # catches a rail that forgot to wire it, or wired the WRONG contract name.
    for rel, name in _RAIL_WIRING.items():
        src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "emit_prepare_with_integrity" in src, f"{rel} is not wired to the integrity gate"
        assert f'"{name}"' in src, f"{rel} does not pass its contract name {name!r}"


def test_decision_prepare_end_to_end_carries_ok_integrity(
    tmp_path: Any, capsys: Any,
) -> None:
    from scripts.wiki_skills.wiki_extract_decisions import main

    vault = tmp_path / "v"
    vault.mkdir()
    (vault / "WIKI_SCHEMA.md").write_text(
        "---\nvault_id: test-vault\nlanguage: en\nlayout: cybos\n---\n", encoding="utf-8")
    src = vault / "meetings" / "m1.md"
    src.parent.mkdir(parents=True)
    src.write_text("# Protocol\n\nWe decided X.\n", encoding="utf-8")

    code = main(["prepare", "--vault", "test-vault", "--vault-root", str(vault),
                 "--source-page", "meetings/m1.md", "--db-path", str(tmp_path / "x.db")])
    env = json.loads(capsys.readouterr().out.strip())
    assert code == 0
    assert env["integrity"]["status"] == "ok"
    assert env["integrity"]["skill"] == "skills/decision-extraction/SKILL.md"


# ── R-067-6 — default warns (exit unchanged); strict refuses (exit 2) ─────────────────────────
def test_default_warns_on_drift(tmp_path: Any, monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(_common, "SKILL_INTEGRITY_MANIFEST", _bad_manifest(tmp_path))
    monkeypatch.delenv("WIKI_STRICT_SKILL_INTEGRITY", raising=False)
    code = emit_prepare_with_integrity({}, "concept-extraction")
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["integrity"]["status"] == "drift"
    assert any("integrity" in w for w in out["warnings"])
    assert "error" not in out


def test_strict_refuses_on_drift(tmp_path: Any, monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(_common, "SKILL_INTEGRITY_MANIFEST", _bad_manifest(tmp_path))
    monkeypatch.setenv("WIKI_STRICT_SKILL_INTEGRITY", "1")
    code = emit_prepare_with_integrity({}, "concept-extraction")
    out = json.loads(capsys.readouterr().out)
    assert code == 2
    assert out["error"] == "SKILL_INTEGRITY_DRIFT"
    assert out["integrity"]["status"] == "drift"
    # value-free: the refusal names the FAMILY, never a file body.
    assert set(out["integrity"]) == {"status", "skill", "expected", "actual"}


def test_strict_on_manifest_unavailable_also_refuses(
    tmp_path: Any, monkeypatch: Any, capsys: Any,
) -> None:
    monkeypatch.setattr(_common, "SKILL_INTEGRITY_MANIFEST", tmp_path / "nope.sha256")
    monkeypatch.setenv("WIKI_STRICT_SKILL_INTEGRITY", "1")
    code = emit_prepare_with_integrity({}, "concept-extraction")
    out = json.loads(capsys.readouterr().out)
    assert code == 2
    assert out["error"] == "SKILL_INTEGRITY_DRIFT"
    assert out["integrity"]["status"] == "manifest_unavailable"


# ── R-067-7 — the re-pin script round-trips ───────────────────────────────────────────────────
def test_repin_reports_in_sync_on_the_committed_tree(capsys: Any) -> None:
    # The committed manifest IS what `--write` would produce (idempotent) — proves it is current.
    assert pin.main([]) == 0


def test_repin_roundtrips_on_a_temp_manifest(
    tmp_path: Any, monkeypatch: Any, capsys: Any,
) -> None:
    tmp_manifest = tmp_path / "skill-integrity.sha256"
    monkeypatch.setattr(_common, "SKILL_INTEGRITY_MANIFEST", tmp_manifest)
    # (1) missing manifest ⇒ drift ⇒ exit 1
    assert pin.main([]) == 1
    # (2) --write creates it ⇒ exit 0
    assert pin.main(["--write"]) == 0
    assert tmp_manifest.exists()
    # (3) now in sync ⇒ exit 0
    assert pin.main([]) == 0
    # (4) it pins EXACTLY the roster, with real hashes
    written = load_integrity_manifest() or {}
    assert set(written) == set(discover_integrity_roster())
    for rel, h in written.items():
        assert h == _sha256_file(_REPO_ROOT / rel)


# ── R-067-8 — every roster contract carries the marker; edited banners cite the mechanism ─────
def test_every_roster_contract_carries_the_marker() -> None:
    for rel in _DESIGNATED_PATHS:
        p = _REPO_ROOT / rel
        assert _INTEGRITY_MARKER in p.read_text(encoding="utf-8"), rel


def test_edited_banners_cite_the_manifest() -> None:
    # The banners this task added/edited point operators at the REAL mechanism. concept-extraction
    # is intentionally byte-stable (its banner already cites H-5; re-pointing is deferred to the
    # TASK-066 harness refresh that owns the next edit to that file — task-067 §8).
    edited = [
        "skills/decision-extraction/SKILL.md", "skills/wiki-query-synthesis/SKILL.md",
        "skills/wiki-verify/SKILL.md", "skills/obsidian-cli/SKILL.md",
        "skills/obsidian-cli/references/command-reference.md",   # cycle-3
        "skills/wiki-import/references/reason-contract.md",       # cycle-3
    ]
    for rel in edited:
        text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "config/skill-integrity.sha256" in text, rel
        assert "pin_skill_integrity.py" in text, rel


# ── R-067-9 — each rail's load-skill workflow STOPs on integrity drift ────────────────────────
# All four rails now have a workflows/ recipe (the missing wiki-extract-decisions.md was created
# by this task — a TASK-063 convention gap). The `commands/` files are thin pointers to these.
_LOAD_RECIPES = [
    "workflows/wiki-extract-concepts.md",
    "workflows/wiki-extract-decisions.md",
    "workflows/wiki-query.md",
    "workflows/wiki-verify-multi.md",
]


def test_load_recipes_document_the_integrity_stop() -> None:
    for rel in _LOAD_RECIPES:
        text = (_REPO_ROOT / rel).read_text(encoding="utf-8").lower()
        assert "integrity" in text, f"{rel} does not document the H-5 integrity STOP"


# ── R-067-10 — Decision-17 survives: no LLM client added on the H-5 surface ───────────────────
def test_no_anthropic_import_on_the_h5_surface() -> None:
    surface = list(_RAIL_WIRING) + [
        "scripts/wiki_skills/_common.py", "scripts/pin_skill_integrity.py"]
    for rel in surface:
        src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        # Line-anchored: `wiki_query.py`'s docstring legitimately says "no `import anthropic`";
        # Decision-17 is about an actual import STATEMENT, not a prose mention.
        for line in src.splitlines():
            s = line.strip()
            assert not s.startswith("import anthropic"), f"{rel}: {line!r}"
            assert not s.startswith("from anthropic"), f"{rel}: {line!r}"
