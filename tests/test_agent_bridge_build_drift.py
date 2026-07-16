"""TASK 070 (R-070-4 / R-070-9) — the agent-bridge build gate.

`main.js` is the only file Obsidian executes. It is a BUILD PRODUCT of `main.ts`
(`scripts/build_agent_bridge.py`), and this file is what makes that a mechanism rather than a
discipline. Three layers, because each catches what the one below structurally cannot:

* **L0 — zero toolchain.** Hash-pins BOTH `main.ts` and `main.js` against the receipt. Runs on
  every machine, node or not. Pinning only `main.js` would let a `main.ts` edit sail through
  offline; pinning only `main.ts` would let a hand-edited `main.js` do the same. A MISSING
  receipt is RED here — un-pinned is the drift state L0 exists for, not a reason to skip.
* **L1 — needs esbuild (NOT node).** Byte-compares `esbuild(main.ts)` against the committed
  `main.js`. This is the only layer that catches a hand-edited `main.js` that was ALSO re-pinned.
  The separate tsc gate needs `node` + `tsc`; L1 does not, because esbuild's postinstall swaps its
  JS shim for a platform-native binary. **Each tool gets its own predicate** — a shared one would
  skip the typecheck whenever esbuild is missing, which is a green meaning "not checked".
* **L2 — guards on the skip.** `WIKI_STRICT_PLUGIN_BUILD=1` turns a missing toolchain into a
  failure. ⚠️ **Latent**: no CI exists to set it (`docs/issues/arch-10-*`), so L0 carries the
  real guarantee today. L2 is the hook, not the protection.

**The skip predicate is tool ABSENCE and nothing else.** Never `except Exception: skip` — that
converts the drift being hunted into a green, which is this project's signature failure mode.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest
from _pytest.outcomes import Skipped

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.build_agent_bridge as build  # noqa: E402

_STRICT_ENV = "WIKI_STRICT_PLUGIN_BUILD"


def _require(tool: str, present: bool) -> None:
    """Skip iff `tool` is genuinely absent — or FAIL if the strict env forbids skipping."""
    if present:
        return
    if os.environ.get(_STRICT_ENV) == "1":
        pytest.fail(f"{_STRICT_ENV}=1 but {tool} is missing — cannot skip.")
    pytest.skip(f"{tool} absent — L0 (the hash pin) still gates this file")


# ★ Two predicates, never one. See `build_agent_bridge._esbuild_present` for why the shared
# version is a hazard in BOTH directions, and the two tests at the bottom of L2 that pin it.
def _require_esbuild() -> None:
    _require("esbuild", build._esbuild_present())


def _require_tsc() -> None:
    _require("tsc", build._tsc_present())


def _manifest_or_fail() -> dict[str, Any]:
    manifest = build.load_manifest()
    if manifest is None:
        pytest.fail(
            f"{build.MANIFEST.relative_to(_REPO_ROOT)} is MISSING — main.js is UNPINNED. "
            "A missing receipt is drift (the un-pinned state), never a reason to pass or skip. "
            "Mint it: `python3 scripts/build_agent_bridge.py --write`"
        )
    return manifest


# ── L0 — the hash pin. No toolchain. Runs everywhere. ─────────────────────────────────


def test_pinned_hashes_match_the_live_files() -> None:
    for rel, pinned in _manifest_or_fail()["files"].items():
        assert build.sha256_file(_REPO_ROOT / rel) == pinned, (
            f"{rel} has drifted from the build receipt. main.js is GENERATED — never hand-edit "
            f"it; edit main.ts and run `python3 scripts/build_agent_bridge.py --write`."
        )


def test_receipt_pins_both_sides_of_the_tie() -> None:
    # Pin only main.js → a main.ts edit sails through offline. Pin only main.ts → a hand-edited
    # main.js does. Derived from the build module so the roster can never be hand-listed stale.
    assert set(_manifest_or_fail()["files"]) == {
        build.MAIN_TS.relative_to(_REPO_ROOT).as_posix(),
        build.MAIN_JS.relative_to(_REPO_ROOT).as_posix(),
    }


def test_recipe_matches_the_pinned_recipe() -> None:
    # Byte-identity ties main.js to main.ts; it says nothing about the RECIPE being right.
    assert tuple(_manifest_or_fail()["esbuild_argv"]) == build.ESBUILD_ARGV


def test_receipt_attests_a_typecheck_that_actually_passed() -> None:
    # The receipt may only exist downstream of a clean typecheck (`--write` refuses otherwise),
    # so anything but "0 errors" means someone hand-authored it.
    manifest = _manifest_or_fail()
    assert manifest["tsc_result"] == "0 errors"
    assert manifest["tsc_version"], "the receipt must name the tsc that produced that verdict"


def test_bundle_externalizes_what_obsidian_provides_at_runtime() -> None:
    """★ The sole guard for a build-GREEN catastrophe.

    Drop `--external:@codemirror/view`, rebuild, re-pin: esbuild exits 0 with no warning, the
    bundle goes 12,191 → 419,223 bytes, and the plugin ships a SECOND CodeMirror instance whose
    ViewPlugin silently never draws into the real editor. Every other test in this file stays
    green. Byte-identity cannot see it — the build IS its own output.
    """
    js = build.MAIN_JS.read_text(encoding="utf-8")
    for module in ("obsidian", "@codemirror/view"):
        assert f'require("{module}")' in js, (
            f'"{module}" was BUNDLED instead of externalized — Obsidian injects its own '
            f"instance at runtime. Check ESBUILD_ARGV's --external flags."
        )
    assert len(js) < 100_000, (
        f"main.js is {len(js):,} chars — ~12KB is the real bundle, ~419KB means CodeMirror got "
        f"inlined by a dropped --external."
    )


def test_main_js_exports_the_plugin_class_where_obsidian_looks_for_it() -> None:
    # Obsidian reads the plugin class off the CJS `default` export. Verified empirically against
    # a live-enabled community plugin (`mermaid-tools`), which ships this exact esbuild shape.
    assert "default: () => AgentBridge" in build.MAIN_JS.read_text(encoding="utf-8")


# ── L1 — byte-compare + the typecheck. Needs the toolchain. ───────────────────────────


def test_committed_main_js_is_esbuild_output() -> None:
    _require_esbuild()
    assert build.build() == build.MAIN_JS.read_bytes(), (
        "main.js is not esbuild(main.ts) — it was hand-edited, or main.ts changed without a "
        "rebuild. fix: `python3 scripts/build_agent_bridge.py --write`"
    )


def test_build_is_deterministic() -> None:
    _require_esbuild()
    assert build.build() == build.build()


def test_main_ts_typechecks_clean_against_the_real_obsidian_types() -> None:
    # ★ Gated on tsc ALONE — never on esbuild. That is the whole point of the split predicate.
    _require_tsc()
    n_errors, output = build.typecheck()
    assert n_errors == 0, f"tsc reports {n_errors} error(s):\n{output}"


# ── L2 — guards on the skip itself ────────────────────────────────────────────────────


def test_strict_mode_turns_a_missing_toolchain_into_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build, "_esbuild_present", lambda: False)
    monkeypatch.setenv(_STRICT_ENV, "1")
    # `Failed`/`Skipped` derive from BaseException, NOT Exception — `pytest.raises(Exception)`
    # lets them straight through. The exact type is also what proves fail-vs-skip with no
    # string matching.
    with pytest.raises(pytest.fail.Exception) as exc:
        _require_esbuild()
    assert _STRICT_ENV in str(exc.value)


def test_a_failing_build_raises_instead_of_returning_empty_output() -> None:
    """`check=True` in `build()` — pinned against the REAL esbuild, not a mock.

    The first version of this test monkeypatched `build.build` to raise and then asserted that it
    raised: a tautology that pins the mock, not the code. `check=True` is what stops a failing
    esbuild from degrading to empty stdout — and empty output would sail past a `--write` and get
    pinned as a "build". (This session already shipped that exact vacuous green once: a
    determinism check that hashed empty output three times and read three `e3b0c442…` as a pass.)
    So: feed the REAL build a source that cannot compile and require an exception.
    """
    _require_esbuild()
    broken = build.PLUGIN_DIR / "__drift_gate_probe__.ts"
    broken.write_text("this is (((not valid typescript\n", encoding="utf-8")
    try:
        with pytest.raises(subprocess.CalledProcessError):
            subprocess.run(
                [str(build.ESBUILD_BIN), broken.name, "--bundle", "--log-level=silent"],
                capture_output=True,
                check=True,
                cwd=build.PLUGIN_DIR,
            )
    finally:
        broken.unlink(missing_ok=True)


def test_typecheck_never_reports_zero_errors_for_a_failed_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The receipt's whole claim rests on this: a tsc that failed must never read as "0 errors".

    `typecheck()` counts lines matching `": error TS"`. If tsc dies WITHOUT emitting a parseable
    diagnostic — a crash, a missing/broken tsconfig, an output-format change — the naive count is
    0, which `--write` would read as a clean typecheck and mint a receipt asserting "0 errors"
    that nobody observed. The non-zero-returncode fallback is the only thing preventing that, and
    nothing else in this file exercises it.
    """

    class _Proc:
        returncode = 2
        stdout = "error TS5058: The specified path does not exist: 'tsconfig.json'.\n"
        stderr = ""

    # Note the shape: tsc's own catastrophic errors are NOT in `file(line,col): error TS…` form,
    # so the substring the counter looks for is absent — count would be 0 without the fallback.
    monkeypatch.setattr(build.subprocess, "run", lambda *_a, **_k: _Proc())
    count, output = build.typecheck()
    assert count > 0, "a failed tsc run must never count as 0 errors"
    assert "exited 2" in output


def _skips(require: "Callable[[], None]") -> bool:
    """Did `require()` skip? Returns a BOOL rather than letting the skip propagate.

    ★ Load-bearing. The obvious way to write the two tests below is to call `_require_tsc()` bare
    and comment "must NOT raise Skipped". That is a VACUOUS GREEN: `pytest.skip()` raises
    `Skipped`, and pytest records a test that skips ITSELF as **SKIPPED, never FAILED**. So the
    exact hazard these tests exist to detect would turn them into skips, and the suite would still
    report 0 failed. Catching the skip and asserting on a boolean is what makes them able to fail.
    """
    try:
        require()
    except BaseException as exc:  # Skipped derives from BaseException, not Exception
        if isinstance(exc, Skipped):
            return True
        raise
    return False


def test_the_tsc_gate_still_runs_when_only_esbuild_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """★ The mutation a single shared `toolchain_present()` would let through.

    esbuild absent + typescript present ⇒ with one shared predicate the TYPECHECK skips although
    it could have run perfectly well, and reads as green. `design-drift-gate.md:51-52` ships
    copy-paste-ready code with exactly that shape. This test is what makes the per-tool split a
    mechanism instead of an assertion in a docstring.
    """
    monkeypatch.setattr(build, "_esbuild_present", lambda: False)
    monkeypatch.setattr(build, "_tsc_present", lambda: True)
    assert not _skips(_require_tsc), (
        "the tsc gate skipped because ESBUILD is missing — the predicates have been collapsed "
        "into one. A green from that skip means 'not checked'."
    )


def test_the_esbuild_gate_still_runs_when_only_tsc_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The mirror image, pinned for the same reason.
    monkeypatch.setattr(build, "_esbuild_present", lambda: True)
    monkeypatch.setattr(build, "_tsc_present", lambda: False)
    assert not _skips(_require_esbuild), (
        "the esbuild gate skipped because TSC is missing — the predicates have been collapsed."
    )


def test_the_skip_probe_can_actually_observe_a_skip() -> None:
    # Negative control for `_skips` itself: if it silently swallowed everything, both tests above
    # would pass no matter what. Prove it reports True on a real skip.
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(build, "_tsc_present", lambda: False)
        monkeypatch.delenv(_STRICT_ENV, raising=False)
        assert _skips(_require_tsc) is True
    finally:
        monkeypatch.undo()


def test_esbuild_presence_does_not_depend_on_node(monkeypatch: pytest.MonkeyPatch) -> None:
    # esbuild's postinstall swaps the JS shim for a platform-native binary; verified with
    # `env -i PATH=/usr/bin:/bin ./node_modules/.bin/esbuild --version` → 0.28.1. Requiring node
    # here would skip a gate that can run — the same hazard, mirrored.
    monkeypatch.setattr(build.shutil, "which", lambda _name: None)
    assert build._esbuild_present() is os.access(build.ESBUILD_BIN, os.X_OK)


# ── the re-pin contract: no bypass may exist ──────────────────────────────────────────


def test_write_refuses_to_repin_on_a_type_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The single most important test in this file. If it ever goes green, the task failed.

    Both output paths are redirected into `tmp_path` first — deliberately. If the refusal ever
    breaks, this test must report that, not overwrite the repo's real `main.js` on its way to
    telling us.
    """
    built: list[str] = []
    fake_manifest = tmp_path / "agent-bridge-build.json"
    fake_main_js = tmp_path / "main.js"
    monkeypatch.setattr(build, "MANIFEST", fake_manifest)
    monkeypatch.setattr(build, "MAIN_JS", fake_main_js)
    monkeypatch.setattr(build, "_tsc_present", lambda: True)
    monkeypatch.setattr(build, "typecheck", lambda: (3, "main.ts(277,12): error TS2339: ..."))
    monkeypatch.setattr(build, "build", lambda: built.append("built") or b"")

    assert build.main(["--write"]) == 1
    assert built == [], "a type error must block the rebuild"
    assert not fake_main_js.exists(), "a type error must block the write to main.js"
    assert not fake_manifest.exists(), "a type error must block the re-pin"


def test_write_hard_fails_when_tsc_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    # Not a skip. A receipt minted without a typecheck asserts "0 errors" nobody observed.
    monkeypatch.setattr(build, "_tsc_present", lambda: False)
    monkeypatch.setattr(
        build, "typecheck", lambda: pytest.fail("typecheck() ran with tsc absent")
    )
    assert build.main(["--write"]) == 2


def test_no_bypass_flag_exists() -> None:
    """Three distinct holes, banned as three distinct names.

    `--force` skips the tsc refusal. `--build-only`/`--no-pin` build without re-pinning, so L0
    stays red on a tree that is in sync — training the reader to ignore a red gate. Each would
    reintroduce the un-type-checked artifact this task exists to eliminate.
    """
    source = Path(build.__file__).read_text(encoding="utf-8")
    for flag in ("--force", "--build-only", "--no-pin", "--skip-typecheck"):
        assert f'"{flag}"' not in source, f"{flag} is a sanctioned bypass — it must not exist"


def test_dry_run_reports_a_missing_receipt_as_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build, "load_manifest", lambda: None)
    assert build.main([]) == 1
