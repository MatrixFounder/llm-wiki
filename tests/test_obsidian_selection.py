"""Contract test for the obsidian-selection wrapper (TASK 068).

Deterministic — no live Obsidian, no live plugin. Mirrors
``tests/test_obsidian_active_note.py``: the wrapper's single obsidian-invocation seam
(``_run_obsidian``) is monkeypatched with canned output, and the plugin's own output is
simulated via committed fixture JSON files pre-seeded into a ``tmp_path``'s ``.obsidian/``
directory (real filesystem reads, deterministic content — no live app, no live plugin).

Phase 0 (this file, as committed by task 068-03): the FULL roster below is RED against
the 068-02 stub (``do_read``/``do_apply`` return ``{"ok": False, "reason":
"not-implemented"}`` + the out-of-band sentinel exit code 1). Phase 1 (068-04/05/06) turns
it GREEN without changing this file.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import re
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Optional

import pytest

_REPO = Path(__file__).resolve().parents[1]
_MOD_PATH = _REPO / "skills" / "obsidian-cli" / "scripts" / "obsidian_selection.py"
_FIX = _REPO / "skills" / "obsidian-cli" / "evals" / "fixtures" / "selection"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("obsidian_selection", _MOD_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


osel = _load()


def _fix(name: str) -> str:
    return (_FIX / name).read_text(encoding="utf-8")


def _fix_json(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_fix(name))
    return data


NONCE = "0123456789abcdef0123456789abcdef"
STALE_NONCE = "fedcba9876543210fedcba9876543210"
VAULT_NAME = "TestVault"


# ── the fake obsidian-invocation seam (prefix-keyed, sibling style) ──────────────────
def _runner(
    mapping: dict[tuple[str, ...], tuple[str, int]],
    calls: Optional[list[list[str]]] = None,
) -> Callable[..., "subprocess.CompletedProcess[str]"]:
    """Build a fake ``_run_obsidian`` keyed on a tuple-prefix of the obsidian args.

    ``calls`` (if given) records every invocation's args list — the seam the
    no-raw-argument and never-dispatches-eval assertions inspect.
    """

    def fake(args: list[str], *, timeout: float = 30.0) -> "subprocess.CompletedProcess[str]":
        if calls is not None:
            calls.append(list(args))
        # `vault=<name>` is a GLOBAL flag the wrapper prepends to every call once a vault is
        # resolved (explicit --vault or CWD auto-detect); strip it before prefix-matching so
        # mappings keyed on the bare subcommand still match.
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
        ("command", "id=agent-bridge:export-selection"): ("", 0),
        ("command", "id=agent-bridge:apply-edit"): ("", 0),
    }


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    mapping: dict[tuple[str, ...], tuple[str, int]],
    *,
    calls: Optional[list[list[str]]] = None,
    mint: Optional[str] = NONCE,
    cli_present: bool = True,
) -> None:
    monkeypatch.setattr(osel.shutil, "which", lambda _: ("/usr/local/bin/obsidian" if cli_present else None))
    monkeypatch.setattr(osel, "_run_obsidian", _runner(mapping, calls))
    if mint is not None:
        monkeypatch.setattr(osel, "_mint_nonce", lambda: mint)


def _instant_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``_await_result``'s deadline poll resolve on the first check — no real sleep."""
    monkeypatch.setattr(osel, "_RESULT_DEADLINE_S", 0.0)
    monkeypatch.setattr(osel.time, "sleep", lambda _: None)


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


# ── per-subcommand happy path ─────────────────────────────────────────────────────
def test_read_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")
    _seed(tmp_path, "agent-selection.json", "read-ok.selection.json")
    assert osel.main(["read"]) == osel.EXIT_OK
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["mode"] == "read"
    assert out["path"] == "Notes/Weekly Review.md"
    assert out["text"] == "Hello world"
    assert out["fromOffset"] == 42 and out["toOffset"] == 53
    assert out["from"] == {"line": 3, "ch": 0} and out["to"] == {"line": 3, "ch": 11}
    # How the plugin resolved the editor is surfaced, so a `recent-editor` fallback (the active
    # leaf was the agent's integrated terminal, where activeEditor is null) is never silent.
    assert out["source"] == "active"


def test_apply_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "apply-ok.result.json")
    assert osel.main([
        "apply", "--path", "Notes/Weekly Review.md",
        "--expect-b64", _b64("Hello world"), "--replacement-b64", _b64("Goodbye world"),
        "--expect-from-offset", "42", "--expect-to-offset", "53",
    ]) == osel.EXIT_OK
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["mode"] == "apply" and out["newLen"] == 15


# ── per exit code (R-068-4), each also asserting the envelope `reason` ───────────────
def test_cli_usage_missing_subcommand_is_argparse_exit_2() -> None:
    # the genuine argparse usage error (no envelope) — kept distinct from the
    # application-level exit-2 (`payload-too-large`) so the two are never conflated.
    with pytest.raises(SystemExit) as ei:
        osel.main([])
    assert ei.value.code == osel.EXIT_USAGE


def test_apply_payload_too_large_is_exit_2(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    huge = "A" * (osel._MAX_B64_LEN + 10)
    assert osel.main(["apply", "--path", "N.md", "--expect-b64", huge, "--replacement-b64", "eA==", "--expect-from-offset", "42", "--expect-to-offset", "53"]) == osel.EXIT_USAGE
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "payload-too-large"


def test_apply_malformed_base64_is_exit_2_usage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # wrapper-side fail-fast: never forward a non-base64 payload to the plugin.
    _patch(monkeypatch, _base_mapping(tmp_path))
    assert osel.main(["apply", "--path", "N.md", "--expect-b64", "not-valid-b64!!", "--replacement-b64", "eQ==", "--expect-from-offset", "42", "--expect-to-offset", "53"]) == osel.EXIT_USAGE
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "usage"


def test_apply_from_json_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # The ARG_MAX escape valve: apply reads path/expect/replacement from a FILE.
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "apply-ok.result.json")
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps({
        "path": "Notes/Weekly Review.md",
        "expectB64": _b64("Hello world"),
        "replacementB64": _b64("Goodbye world"),
        "fromOffset": 42,
        "toOffset": 53,
    }), encoding="utf-8")
    assert osel.main(["apply", "--from-json", str(payload_file)]) == osel.EXIT_OK
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["mode"] == "apply" and out["path"] == "Notes/Weekly Review.md"


def test_apply_from_json_bypasses_512kib_cap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # --from-json is a FILE (no ARG_MAX limit) — it must NOT be rejected by the inline cap,
    # otherwise the documented escape valve doesn't actually escape.
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "apply-ok.result.json")
    big = _b64("x" * (osel._MAX_B64_LEN))  # base64 well over the 512 KiB inline threshold
    assert len(big) > osel._MAX_B64_LEN
    payload_file = tmp_path / "payload.json"
    payload_file.write_text(json.dumps({
        "path": "Notes/Weekly Review.md", "expectB64": _b64("Hello world"), "replacementB64": big,
        "fromOffset": 42, "toOffset": 53,
    }), encoding="utf-8")
    assert osel.main(["apply", "--from-json", str(payload_file)]) == osel.EXIT_OK


def test_read_unknown_plugin_reason_fails_closed_exit_4(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A buggy/tampered plugin that reports an ok:false reason NOT in the ladder must fail
    # CLOSED (exit 4 app-not-running), never be treated as a success or a known rung.
    _patch(monkeypatch, _base_mapping(tmp_path))
    (tmp_path / ".obsidian").mkdir(exist_ok=True)
    (tmp_path / ".obsidian" / "agent-result.json").write_text(
        json.dumps({"ok": False, "mode": "read", "reason": "some-unknown-reason", "nonce": NONCE}), encoding="utf-8")
    assert osel.main(["read"]) == osel.EXIT_APP_NOT_RUNNING
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "some-unknown-reason"


def test_read_no_editor_is_exit_3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "read-no-editor.result.json")
    assert osel.main(["read"]) == osel.EXIT_NO_SELECTION
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "no-editor"


def test_read_preview_is_exit_3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "read-preview.result.json")
    assert osel.main(["read"]) == osel.EXIT_NO_SELECTION
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "preview"


def test_read_empty_selection_is_exit_3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "read-empty-selection.result.json")
    assert osel.main(["read"]) == osel.EXIT_NO_SELECTION
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "empty-selection"


def test_apply_empty_selection_is_exit_3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # apply's guard order checks somethingSelected() before the path/range guards too
    # (068-04) — the wrapper-side reason->exit map is shared, exercised here via `apply`.
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "read-empty-selection.result.json")
    assert osel.main(["apply", "--path", "N.md", "--expect-b64", "eA==", "--replacement-b64", "eQ==", "--expect-from-offset", "42", "--expect-to-offset", "53"]) == osel.EXIT_NO_SELECTION
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "empty-selection"


def test_read_app_not_running_timeout_is_exit_4(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # no agent-result.json ever appears -> the poll must time out, not hang or crash.
    _patch(monkeypatch, _base_mapping(tmp_path))
    _instant_timeout(monkeypatch)
    (tmp_path / ".obsidian").mkdir()
    assert osel.main(["read"]) == osel.EXIT_APP_NOT_RUNNING
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "app-not-running"


def test_read_rejects_stale_result_is_exit_4(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # THE headline read-back-race guard (PLAN decision 2): a LEFTOVER agent-result.json
    # from a prior invocation (ok:true!) carries the WRONG nonce — must be rejected, never
    # accepted as a false success.
    #
    # MUTATION-PINNED: we ALSO seed a stale agent-selection.json so the guard is genuinely
    # exercised. Without this, a hypothetical nonce-IGNORING wrapper would read the stale
    # ok:true result, then fail on the *missing* selection file and return exit 4 anyway —
    # passing this test for the WRONG reason (verified: a nonce-ignore mutation slips through
    # the un-seeded variant). With a stale selection present, a nonce-ignoring wrapper would
    # instead succeed (exit 0 with stale text), so asserting exit 4 truly pins the guard.
    _patch(monkeypatch, _base_mapping(tmp_path), mint=NONCE)
    _instant_timeout(monkeypatch)
    _seed(tmp_path, "agent-result.json", "read-stale-nonce.result.json")
    _seed(tmp_path, "agent-selection.json", "read-ok.selection.json")  # a stale selection is on disk too
    assert STALE_NONCE != NONCE
    assert osel.main(["read"]) == osel.EXIT_APP_NOT_RUNNING
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "app-not-running"


def test_read_rejects_foreign_selection_payload_is_exit_4(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # THE CONCURRENT-DISPATCH GUARD, and the one the result-envelope check above does NOT cover.
    # `agent-result.json` carries OUR nonce (so `_await_result` matches and we proceed) but
    # `agent-selection.json` — read afterwards, as a separate file — carries a DIFFERENT one:
    # exactly what a second dispatch landing in that window leaves behind. The wrapper must not
    # hand us that other request's note under ok:true.
    #
    # MUTATION-PINNED (same discipline as the stale-result test above): the seeded foreign
    # selection is well-formed and complete, so a wrapper WITHOUT the payload nonce check reads it
    # happily and returns EXIT_OK — this test cannot pass for the wrong reason (a missing/corrupt
    # file would exit 4 regardless and prove nothing). Verified by mutation: deleting the check
    # flips this to exit 0 and leaks the foreign path + text into stdout.
    _patch(monkeypatch, _base_mapping(tmp_path), mint=NONCE)
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")          # OUR nonce -> result matches
    _seed(tmp_path, "agent-selection.json", "read-foreign-nonce.selection.json")  # someone else's
    assert osel.main(["read"]) == osel.EXIT_APP_NOT_RUNNING
    out_raw = capsys.readouterr().out
    out = json.loads(out_raw)
    assert out["ok"] is False and out["reason"] == "selection-nonce-mismatch"
    # Pin the HARM, not just the exit code: none of the other dispatch's data may reach the caller
    # (it would otherwise become the baseline for an apply the plugin's guards would PASS).
    assert "Secrets/Private Journal.md" not in out_raw
    assert "ANOTHER-AGENTS-NOTE-TEXT" not in out_raw


def test_read_rejects_unstamped_selection_payload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Fail-CLOSED on an absent nonce: an unattributable payload is refused, never accepted because
    # "there was nothing to compare". Pins the check against a fail-OPEN rewrite of the form
    # `if "nonce" in selection and selection["nonce"] != nonce`, which this test turns RED.
    _patch(monkeypatch, _base_mapping(tmp_path), mint=NONCE)
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")
    unstamped = _fix_json("read-ok.selection.json")
    del unstamped["nonce"]
    (tmp_path / ".obsidian" / "agent-selection.json").write_text(json.dumps(unstamped), encoding="utf-8")
    assert osel.main(["read"]) == osel.EXIT_APP_NOT_RUNNING
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "selection-nonce-mismatch"


def test_read_cli_absent_is_exit_5(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path), cli_present=False)
    assert osel.main(["read"]) == osel.EXIT_CLI_ABSENT
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "cli-absent"


def test_read_vault_mismatch_is_exit_6(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path, vault_name=VAULT_NAME))
    assert osel.main(["--expect-vault", "some-other-vault", "read"]) == osel.EXIT_VAULT_MISMATCH
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "vault-mismatch"


def test_apply_path_mismatch_is_exit_7(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "apply-path-mismatch.result.json")
    assert osel.main(["apply", "--path", "N.md", "--expect-b64", "eA==", "--replacement-b64", "eQ==", "--expect-from-offset", "42", "--expect-to-offset", "53"]) == osel.EXIT_GUARD_REFUSED
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "path-mismatch"


def test_apply_stale_range_is_exit_7(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "apply-stale-range.result.json")
    assert osel.main(["apply", "--path", "N.md", "--expect-b64", "eA==", "--replacement-b64", "eQ==", "--expect-from-offset", "42", "--expect-to-offset", "53"]) == osel.EXIT_GUARD_REFUSED
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "stale-range"


def test_apply_position_mismatch_is_exit_7(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # The wrong-occurrence guard: the plugin refuses when the LIVE selection sits at different
    # document offsets than the ones captured at read time (e.g. the human re-selected an
    # identical string elsewhere in the same file — content alone would have matched).
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "apply-position-mismatch.result.json")
    assert osel.main([
        "apply", "--path", "N.md", "--expect-b64", "eA==", "--replacement-b64", "eQ==",
        "--expect-from-offset", "42", "--expect-to-offset", "53",
    ]) == osel.EXIT_GUARD_REFUSED
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "position-mismatch"


def test_apply_requires_position_offsets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # The position guard must not be skippable — omitting the offsets is a usage error, never a
    # silent downgrade to the content-only check.
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "apply-ok.result.json")
    assert osel.main(["apply", "--path", "N.md", "--expect-b64", "eA==", "--replacement-b64", "eQ=="]) == osel.EXIT_USAGE
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "usage"


def test_apply_payload_carries_position_offsets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # The offsets must actually reach the plugin's payload — otherwise the guard has nothing
    # to compare the live selection against.
    _patch(monkeypatch, _base_mapping(tmp_path))
    monkeypatch.setattr(osel, "_cleanup_exchange", lambda root: None)
    _seed(tmp_path, "agent-result.json", "apply-ok.result.json")
    osel.main([
        "apply", "--path", "N.md", "--expect-b64", "eA==", "--replacement-b64", "eQ==",
        "--expect-from-offset", "387", "--expect-to-offset", "606",
    ])
    payload = json.loads((tmp_path / ".obsidian" / "agent-edit.json").read_text(encoding="utf-8"))
    assert payload["fromOffset"] == 387 and payload["toOffset"] == 606


def test_exchange_files_are_cleaned_up(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # `.obsidian/` is replicated by Obsidian Sync / git / iCloud in many setups, and
    # agent-selection.json holds the note's selected text in PLAINTEXT. Nothing reads the
    # exchange files after the nonce-matched read-back, so they must not linger at rest.
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")
    _seed(tmp_path, "agent-selection.json", "read-ok.selection.json")
    assert osel.main(["read"]) == osel.EXIT_OK
    d = tmp_path / ".obsidian"
    for name in ("agent-request.json", "agent-edit.json", "agent-selection.json", "agent-result.json"):
        assert not (d / name).exists(), f"{name} left at rest after read"


def test_read_headless_is_exit_8(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    monkeypatch.setenv("WIKI_HEADLESS", "1")
    assert osel.main(["read"]) == osel.EXIT_HEADLESS
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "headless"


def test_read_plugin_absent_is_exit_9(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path, commands_fixture="agent-commands-absent.txt"))
    assert osel.main(["read"]) == osel.EXIT_PLUGIN_ABSENT
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "plugin-absent"


def test_apply_plugin_absent_is_exit_9(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # plugin feature-detection is shared logic between read/apply — prove apply also
    # refuses (never a silent eval fallback) when the plugin isn't installed.
    _patch(monkeypatch, _base_mapping(tmp_path, commands_fixture="agent-commands-absent.txt"))
    assert osel.main(["apply", "--path", "N.md", "--expect-b64", "eA==", "--replacement-b64", "eQ==", "--expect-from-offset", "42", "--expect-to-offset", "53"]) == osel.EXIT_PLUGIN_ABSENT
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["reason"] == "plugin-absent"


# ── base64 (R-068-5) ──────────────────────────────────────────────────────────────
def test_b64_roundtrip() -> None:
    for vector in json.loads(_fix("b64-vectors.json")):
        plaintext, expected = vector["plaintext"], vector["expected_b64"]
        assert base64.b64encode(plaintext.encode("utf-8")).decode("ascii") == expected
        assert base64.b64decode(expected).decode("utf-8") == plaintext


def test_no_unencoded_text_reaches_argv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    _patch(monkeypatch, _base_mapping(tmp_path), calls=calls)
    # This test inspects what the wrapper WROTE to agent-edit.json; the real run cleans that file
    # up afterwards (no plaintext/base64 note text left at rest), so disable cleanup here — the
    # assertion is about the write, not about disk residue. `test_exchange_files_are_cleaned_up`
    # covers the removal itself.
    monkeypatch.setattr(osel, "_cleanup_exchange", lambda root: None)
    _seed(tmp_path, "agent-result.json", "apply-ok.result.json")
    replacement = "Привет \"мир\"\nвторая строка"
    expect = "Hello world"
    osel.main([
        "apply", "--path", "Notes/Weekly Review.md",
        "--expect-b64", _b64(expect), "--replacement-b64", _b64(replacement),
        "--expect-from-offset", "42", "--expect-to-offset", "53",
    ])
    for call in calls:
        joined = " ".join(call)
        assert replacement not in joined
        assert expect not in joined
    edit_json = (tmp_path / ".obsidian" / "agent-edit.json").read_text(encoding="utf-8")
    assert replacement not in edit_json
    assert expect not in edit_json
    assert _b64(replacement) in edit_json
    assert _b64(expect) in edit_json


# ── no-eval, ever (R-068-4) ────────────────────────────────────────────────────────
def test_wrapper_never_dispatches_eval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    _patch(monkeypatch, _base_mapping(tmp_path), calls=calls)
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")
    _seed(tmp_path, "agent-selection.json", "read-ok.selection.json")
    osel.main(["read"])
    osel.main(["apply", "--path", "N.md", "--expect-b64", "eA==", "--replacement-b64", "eQ==", "--expect-from-offset", "42", "--expect-to-offset", "53"])
    monkeypatch.setenv("WIKI_HEADLESS", "1")
    osel.main(["read"])
    monkeypatch.delenv("WIKI_HEADLESS", raising=False)
    assert calls, "expected at least one recorded _run_obsidian call"
    # `eval` must never be dispatched, whether as the sole arg or anywhere in the args list
    # (a positional-only check would miss `["command", "eval", …]`-style hiding).
    assert all("eval" not in call for call in calls if call)


def test_wrapper_never_dispatches_eval_when_plugin_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # The highest-risk eval-fallback site: the plugin is missing. The wrapper must refuse
    # (exit 9), NEVER reach for the T3 eval channel to "still get the job done".
    calls: list[list[str]] = []
    _patch(monkeypatch, _base_mapping(tmp_path, commands_fixture="agent-commands-absent.txt"), calls=calls)
    assert osel.main(["read"]) == osel.EXIT_PLUGIN_ABSENT
    assert osel.main(["apply", "--path", "N.md", "--expect-b64", "eA==", "--replacement-b64", "eQ==", "--expect-from-offset", "42", "--expect-to-offset", "53"]) == osel.EXIT_PLUGIN_ABSENT
    assert all("eval" not in call for call in calls if call)


def test_static_source_never_dispatches_eval() -> None:
    src = _MOD_PATH.read_text(encoding="utf-8")
    # the literal dispatch shape this wrapper would use if it (incorrectly) ever routed
    # through eval: a list literal whose first element is the string "eval".
    assert not re.search(r"""\[\s*["']eval["']""", src)


# ── coherence dispatch marker (R-068-7) ───────────────────────────────────────────
def test_apply_coherence_marker_with_wiki_vault(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "apply-ok.result.json")
    assert osel.main([
        "apply", "--path", "Notes/Weekly Review.md",
        "--expect-b64", _b64("Hello world"), "--replacement-b64", _b64("Goodbye world"),
        "--expect-from-offset", "42", "--expect-to-offset", "53",
        "--wiki-vault", "my-vault-id",
    ]) == osel.EXIT_OK
    out = json.loads(capsys.readouterr().out)
    assert out["coherence"] == {
        "action": "wiki-index-upsert",
        "vault": "my-vault-id",
        "source": str(tmp_path / "Notes/Weekly Review.md"),
    }


def test_apply_coherence_marker_without_wiki_vault_self_disables(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "apply-ok.result.json")
    assert osel.main([
        "apply", "--path", "Notes/Weekly Review.md",
        "--expect-b64", _b64("Hello world"), "--replacement-b64", _b64("Goodbye world"),
        "--expect-from-offset", "42", "--expect-to-offset", "53",
    ]) == osel.EXIT_OK
    out = json.loads(capsys.readouterr().out)
    assert out["coherence"] == {"skipped": "vault-not-registered"}


def test_apply_refusal_omits_coherence_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "apply-path-mismatch.result.json")
    assert osel.main([
        "apply", "--path", "N.md", "--expect-b64", "eA==", "--replacement-b64", "eQ==", "--expect-from-offset", "42", "--expect-to-offset", "53", "--wiki-vault", "my-vault-id",
    ]) == osel.EXIT_GUARD_REFUSED
    out = json.loads(capsys.readouterr().out)
    assert "coherence" not in out


# ── CWD → vault auto-detection (bare `obsidian-selection read` targets the terminal's vault) ──
def test_detect_vault_from_cwd_matches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".obsidian").mkdir()  # mark tmp_path as a vault root
    monkeypatch.setattr(osel.shutil, "which", lambda _: "/usr/local/bin/obsidian")
    monkeypatch.setattr(osel, "_run_obsidian", _runner({
        ("vaults", "verbose"): (f"Other\t/somewhere/else\nMyVault\t{tmp_path}\n", 0),
    }))
    assert osel.detect_vault_from_cwd(str(tmp_path)) == "MyVault"
    # a deeper CWD inside the vault walks UP to the .obsidian root and still matches
    assert osel.detect_vault_from_cwd(str(tmp_path / "sub" / "deep")) == "MyVault"


def test_detect_vault_from_cwd_outside_any_vault(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(osel.shutil, "which", lambda _: "/usr/local/bin/obsidian")
    monkeypatch.setattr(osel, "_run_obsidian", _runner({("vaults", "verbose"): ("V\t/elsewhere\n", 0)}))
    assert osel.detect_vault_from_cwd(str(tmp_path)) is None  # no .obsidian above tmp_path → None


def test_read_auto_detects_vault_from_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A bare `read` (no --vault) run from inside a vault must target THAT vault, so a calling
    # agent in Obsidian's integrated terminal need not know or pass --vault.
    mapping = _base_mapping(tmp_path)
    mapping[("vaults", "verbose")] = (f"DetectedVault\t{tmp_path}\n", 0)
    _patch(monkeypatch, mapping)
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")
    _seed(tmp_path, "agent-selection.json", "read-ok.selection.json")
    monkeypatch.chdir(tmp_path)
    assert osel.main(["read"]) == osel.EXIT_OK  # no --vault passed
    assert json.loads(capsys.readouterr().out)["ok"] is True


# ── --format path/tsv (envelope emission) ─────────────────────────────────────────
def test_read_format_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "read-ok.result.json")
    _seed(tmp_path, "agent-selection.json", "read-ok.selection.json")
    assert osel.main(["read", "--format", "path"]) == osel.EXIT_OK
    assert capsys.readouterr().out.strip() == "Notes/Weekly Review.md"


def test_apply_format_tsv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _patch(monkeypatch, _base_mapping(tmp_path))
    _seed(tmp_path, "agent-result.json", "apply-ok.result.json")
    assert osel.main([
        "apply", "--path", "N.md", "--expect-b64", "eA==", "--replacement-b64", "eQ==", "--expect-from-offset", "42", "--expect-to-offset", "53", "--format", "tsv",
    ]) == osel.EXIT_OK
    row = capsys.readouterr().out.strip().split("\t")
    assert row[0] == "True" and row[1] == "apply" and row[3] == "N.md"
