"""Contract test for the obsidian-context wrapper (TASK 070).

Deterministic — no live Obsidian, no live plugin. Mirrors ``tests/test_obsidian_selection.py``:
the sibling's single obsidian-invocation seam (``_run_obsidian``) is monkeypatched with canned
output, and the plugin's own output is simulated via committed fixture JSON files pre-seeded into
a ``tmp_path``'s ``.obsidian/`` directory (real filesystem reads, deterministic content).

``obsidian_context`` IMPORTS ``obsidian_selection`` as ``_sel`` and reuses its plumbing, so the
monkeypatch seams live on that shared module (``octx._sel._run_obsidian`` etc.). Patching the
sibling module is patching the exact functions the context wrapper calls.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Optional

import pytest

_REPO = Path(__file__).resolve().parents[1]
_MOD_PATH = _REPO / "skills" / "obsidian-cli" / "scripts" / "obsidian_context.py"
_FIX = _REPO / "skills" / "obsidian-cli" / "evals" / "fixtures" / "context"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("obsidian_context", _MOD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


octx = _load()
_sel = octx._sel  # the shared sibling module the seams live on

NONCE = "0123456789abcdef0123456789abcdef"
STALE_NONCE = "fedcba9876543210fedcba9876543210"
VAULT_NAME = "TestVault"


def _fix(name: str) -> str:
    return (_FIX / name).read_text(encoding="utf-8")


def _fix_json(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_fix(name))
    return data


# ── the fake obsidian-invocation seam (prefix-keyed, sibling style) ──────────────────
def _runner(
    mapping: dict[tuple[str, ...], tuple[str, int]],
    calls: Optional[list[list[str]]] = None,
) -> Callable[..., "subprocess.CompletedProcess[str]"]:
    def fake(args: list[str], *, timeout: float = 30.0) -> "subprocess.CompletedProcess[str]":
        if calls is not None:
            calls.append(list(args))
        match_args = args[1:] if args and args[0].startswith("vault=") else args
        for key, (out, rc) in mapping.items():
            if tuple(match_args[: len(key)]) == key:
                return subprocess.CompletedProcess(args, rc, stdout=out, stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    return fake


def _seed(tmp_path: Path, dest_name: str, fixture_name: str) -> None:
    d = tmp_path / ".obsidian"
    d.mkdir(exist_ok=True)
    (d / dest_name).write_text(_fix(fixture_name), encoding="utf-8")


def _base_mapping(
    tmp_path: Path,
    *,
    commands_fixture: str = "agent-commands-present.txt",
    vault_name: str = VAULT_NAME,
) -> dict[tuple[str, ...], tuple[str, int]]:
    return {
        ("vault", "info=path"): (str(tmp_path) + "\n", 0),
        ("vault", "info=name"): (vault_name + "\n", 0),
        ("commands",): (_fix(commands_fixture), 0),
        ("command", "id=agent-bridge:export-context"): ("", 0),
    }


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    mapping: dict[tuple[str, ...], tuple[str, int]],
    *,
    calls: Optional[list[list[str]]] = None,
    mint: Optional[str] = NONCE,
    cli_present: bool = True,
) -> None:
    # Seams live on the shared sibling module the context wrapper imports.
    monkeypatch.setattr(_sel.shutil, "which", lambda _: ("/usr/local/bin/obsidian" if cli_present else None))
    monkeypatch.setattr(_sel, "_run_obsidian", _runner(mapping, calls))
    if mint is not None:
        monkeypatch.setattr(_sel, "_mint_nonce", lambda: mint)


def _instant_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_sel, "_RESULT_DEADLINE_S", 0.0)
    monkeypatch.setattr(_sel.time, "sleep", lambda _: None)


# ── happy path ──────────────────────────────────────────────────────────────────────
def test_read_ok_source_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")
    _seed(tmp_path, "agent-context.json", "read-ok.context.json")
    assert octx.main(["read"]) == octx.EXIT_OK
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["mode"] == "context"
    assert out["path"] == "Areas/Health.md" and out["folder"] == "Areas"
    # heading is RAW — no leading '#' (the F-11 bug); tags stripped of '#' (F-10).
    assert out["heading"] == "Exercise" and out["headingLevel"] == 2
    assert out["tags"] == ["health", "habit"]
    assert out["cursor"] == {"line": 12, "ch": 5} and out["cursorOffset"] == 234
    assert out["source"] == "active"
    assert len(out["outline"]) == 3
    # The internal nonce is stripped from the caller-facing envelope.
    assert "nonce" not in out


def test_read_ok_preview_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A read-only context op must SUCCEED while the human is READING the note (preview) — the
    # bug F-12 fixed (the write-path preview gate wrongly rejected it). Cursor/heading absent.
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")
    _seed(tmp_path, "agent-context.json", "read-preview.context.json")
    assert octx.main(["read"]) == octx.EXIT_OK
    out = json.loads(capsys.readouterr().out)
    # `mode` is the OPERATION ("context"); the editor's view mode is `editorMode` (no clash).
    assert out["ok"] is True and out["mode"] == "context" and out["editorMode"] == "preview"
    assert out["path"] == "Areas/Health.md"
    assert "cursor" not in out and "heading" not in out
    assert out["source"] == "recent-editor"


def test_read_request_carries_optin_flags(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # The opt-in flags must actually reach the plugin's request file — else --outline/--frontmatter/
    # --selection are silently ignored (the dead-flag class this rewrite removes).
    _patch(monkeypatch, _base_mapping(tmp_path))
    monkeypatch.setattr(_sel, "_cleanup_exchange", lambda root: None)  # inspect the write
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")
    _seed(tmp_path, "agent-context.json", "read-with-selection.context.json")
    octx.main(["read", "--outline", "--frontmatter", "--selection"])
    req = json.loads((tmp_path / ".obsidian" / "agent-request.json").read_text(encoding="utf-8"))
    assert req["includeOutline"] is True
    assert req["includeFrontmatter"] is True
    assert req["includeSelection"] is True
    assert req["op"] == "context"


def test_read_default_flags_are_off(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Untrusted fields (selection/frontmatter) default OFF — a bare read never opts into them.
    _patch(monkeypatch, _base_mapping(tmp_path))
    monkeypatch.setattr(_sel, "_cleanup_exchange", lambda root: None)
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")
    _seed(tmp_path, "agent-context.json", "read-ok.context.json")
    octx.main(["read"])
    req = json.loads((tmp_path / ".obsidian" / "agent-request.json").read_text(encoding="utf-8"))
    assert req["includeOutline"] is False
    assert req["includeFrontmatter"] is False
    assert req["includeSelection"] is False


# ── the nonce race guards (the M2/F-9 finding) ───────────────────────────────────────
def test_read_rejects_stale_result_is_exit_4(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A LEFTOVER agent-result.json (ok:true!) with the WRONG nonce must be rejected — and a stale
    # context is on disk too, so a nonce-ignoring wrapper would wrongly succeed (mutation-pinned).
    _patch(monkeypatch, _base_mapping(tmp_path), mint=NONCE)
    _instant_timeout(monkeypatch)
    _seed(tmp_path, "agent-result.json", "read-stale-nonce.result.json")
    _seed(tmp_path, "agent-context.json", "read-ok.context.json")
    assert STALE_NONCE != NONCE
    assert octx.main(["read"]) == octx.EXIT_APP_NOT_RUNNING
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "app-not-running"


def test_read_rejects_foreign_context_payload_is_exit_4(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # THE concurrent-dispatch guard the result-envelope check does NOT cover: agent-result.json
    # carries OUR nonce (so _await_result matches) but agent-context.json — read afterwards —
    # carries a DIFFERENT one, exactly what a second dispatch landing in that window leaves. The
    # wrapper must not hand us that other request's note under ok:true.
    # MUTATION-PINNED: the foreign context is well-formed, so a wrapper WITHOUT the payload nonce
    # check reads it happily and returns EXIT_OK — deleting the check flips this to exit 0 and
    # leaks the foreign path into stdout.
    _patch(monkeypatch, _base_mapping(tmp_path), mint=NONCE)
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")           # OUR nonce -> matches
    _seed(tmp_path, "agent-context.json", "read-foreign-nonce.context.json")  # someone else's
    assert octx.main(["read"]) == octx.EXIT_APP_NOT_RUNNING
    out_raw = capsys.readouterr().out
    out = json.loads(out_raw)
    assert out["ok"] is False and out["reason"] == "context-nonce-mismatch"
    # Pin the HARM, not just the exit code: none of the other note's data may reach the caller.
    assert "Secrets/Private Journal.md" not in out_raw
    assert "ANOTHER-AGENTS-NOTE-HEADING" not in out_raw


def test_read_rejects_unstamped_context_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Fail-CLOSED on an absent nonce: an unattributable payload is refused, never accepted because
    # "there was nothing to compare" — pins against a fail-OPEN `if "nonce" in ctx and ...` rewrite.
    _patch(monkeypatch, _base_mapping(tmp_path), mint=NONCE)
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")
    unstamped = _fix_json("read-ok.context.json")
    del unstamped["nonce"]
    (tmp_path / ".obsidian" / "agent-context.json").write_text(json.dumps(unstamped), encoding="utf-8")
    assert octx.main(["read"]) == octx.EXIT_APP_NOT_RUNNING
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "context-nonce-mismatch"


# ── the degradation ladder (each exit code + typed reason) ───────────────────────────
def test_read_unknown_plugin_reason_fails_closed_exit_4(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    (tmp_path / ".obsidian").mkdir(exist_ok=True)
    (tmp_path / ".obsidian" / "agent-result.json").write_text(
        json.dumps({"ok": False, "mode": "context", "reason": "some-unknown-reason", "nonce": NONCE}), encoding="utf-8")
    assert octx.main(["read"]) == octx.EXIT_APP_NOT_RUNNING
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "some-unknown-reason"


def test_read_no_editor_is_exit_3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "read-no-editor.result.json")
    assert octx.main(["read"]) == octx.EXIT_NO_SELECTION
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "no-editor"


def test_read_unsupported_view_is_exit_3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "read-unsupported-view.result.json")
    assert octx.main(["read"]) == octx.EXIT_NO_SELECTION
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "unsupported-view"


def test_read_app_not_running_timeout_is_exit_4(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _instant_timeout(monkeypatch)
    (tmp_path / ".obsidian").mkdir()
    assert octx.main(["read"]) == octx.EXIT_APP_NOT_RUNNING
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "app-not-running"


def test_read_cli_absent_is_exit_5(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # The F-8/L3 bug: CLI-absent used to fall through to exit 6 (vault-mismatch). Now it is 5.
    _patch(monkeypatch, _base_mapping(tmp_path), cli_present=False)
    assert octx.main(["read"]) == octx.EXIT_CLI_ABSENT
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "cli-absent"


def test_read_vault_mismatch_is_exit_6(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # --expect-vault is a REAL guard now (F-16): it compares against the app's reported vault name,
    # not the user's own --vault argument. Here the app says TestVault, we expect another → 6.
    _patch(monkeypatch, _base_mapping(tmp_path, vault_name=VAULT_NAME))
    assert octx.main(["--expect-vault", "some-other-vault", "read"]) == octx.EXIT_VAULT_MISMATCH
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "vault-mismatch"


def test_read_headless_is_exit_8(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    monkeypatch.setenv("WIKI_HEADLESS", "1")
    assert octx.main(["read"]) == octx.EXIT_HEADLESS
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "headless"


def test_read_plugin_absent_is_exit_9(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path, commands_fixture="agent-commands-absent.txt"))
    assert octx.main(["read"]) == octx.EXIT_PLUGIN_ABSENT
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "plugin-absent"


# ── cleanup on EVERY path (the M1/F-18 finding) ──────────────────────────────────────
def test_exchange_files_cleaned_up_on_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")
    _seed(tmp_path, "agent-context.json", "read-ok.context.json")
    assert octx.main(["read"]) == octx.EXIT_OK
    d = tmp_path / ".obsidian"
    for name in ("agent-request.json", "agent-context.json", "agent-result.json"):
        assert not (d / name).exists(), f"{name} left at rest after a successful read"


def test_exchange_files_cleaned_up_on_plugin_refusal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # The leak the rewrite closes: a plaintext context.json must not linger in a synced .obsidian/
    # after a refusal (no-editor here). Even though this refusal writes no context, the request
    # file (and any orphaned context) must be swept.
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "read-no-editor.result.json")
    _seed(tmp_path, "agent-context.json", "read-foreign-nonce.context.json")  # a stale plaintext note
    assert octx.main(["read"]) == octx.EXIT_NO_SELECTION
    d = tmp_path / ".obsidian"
    for name in ("agent-request.json", "agent-context.json", "agent-result.json"):
        assert not (d / name).exists(), f"{name} left at rest after a refusal — plaintext leak"


# ── no-eval, ever ────────────────────────────────────────────────────────────────────
def test_wrapper_never_dispatches_eval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    _patch(monkeypatch, _base_mapping(tmp_path), calls=calls)
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")
    _seed(tmp_path, "agent-context.json", "read-ok.context.json")
    octx.main(["read"])
    _patch(monkeypatch, _base_mapping(tmp_path, commands_fixture="agent-commands-absent.txt"), calls=calls)
    octx.main(["read"])  # plugin-absent — the highest-risk eval-fallback site
    assert calls, "expected at least one recorded _run_obsidian call"
    assert all("eval" not in call for call in calls if call)


def test_static_source_never_dispatches_eval() -> None:
    src = _MOD_PATH.read_text(encoding="utf-8")
    import re
    assert not re.search(r"""\[\s*["']eval["']""", src)
    # And it never dispatches the eval command id in any string form.
    assert "id=eval" not in src and '"eval"' not in src.replace('"never emits `eval`"', "")


# ── tsv output escapes untrusted fields (the L7 finding) ─────────────────────────────
def test_tsv_output_escapes_tabs_and_newlines(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")
    ctx = _fix_json("read-ok.context.json")
    ctx["heading"] = "Ex\ter\ncise"  # a crafted heading with a tab + newline
    (tmp_path / ".obsidian" / "agent-context.json").write_text(json.dumps(ctx), encoding="utf-8")
    assert octx.main(["read", "--format", "tsv"]) == octx.EXIT_OK
    out = capsys.readouterr().out
    # The heading row must be exactly one line with no embedded raw tab/newline breaking structure.
    heading_rows = [ln for ln in out.splitlines() if ln.startswith("heading\t")]
    assert len(heading_rows) == 1
    assert "\ter\n" not in heading_rows[0]
