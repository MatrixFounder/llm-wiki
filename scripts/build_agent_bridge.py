"""TASK 070 (R-070-4 / R-070-9) — the sanctioned BUILD + RE-PIN path for the agent-bridge plugin.

`skills/obsidian-cli/plugin/agent-bridge/main.js` is the ONLY file Obsidian executes, and it
used to be hand-authored as a "mirror" of `main.ts` — a discipline, kept by memory, that
demonstrably failed: a fabricated `getMode()` survived to an adversarial review because
`tsc` was checking a hand-vendored `obsidian.d.ts` that had invented it. `main.js` is now a
BUILD PRODUCT of `main.ts`, and this script is the single source of truth for the recipe::

    python3 scripts/build_agent_bridge.py            # dry-run: report drift, exit 1 if any
    python3 scripts/build_agent_bridge.py --write     # typecheck → rebuild → re-pin
    npm run build                                     # the same thing, from the plugin dir

`--write` runs `tsc --noEmit` FIRST and **refuses to re-pin on a type error**, so the receipt
at `config/agent-bridge-build.json` can only ever attest a `main.js` built from a `main.ts`
that type-checked clean against the real pinned `obsidian` package.

Deliberately absent, and each for its own reason (R-070-9):

* **`--force`** — would skip the tsc refusal, i.e. mint a receipt for code nobody type-checked.
* **`--build-only` / `--no-pin`** — would build without re-pinning, leaving the drift gate red
  on a tree that is actually in sync, which trains the reader to ignore a red gate.
* **hand-authoring `"0 errors"`** — a lie in the artifact whose entire job is to not be one.

Mirrors `scripts/pin_skill_integrity.py` (H-5): a script that mints a reviewable receipt, plus
a test that goes RED when the receipt and the tree disagree.

★ Same stated limit as `pin_skill_integrity.py`: this does NOT defend against a maintainer who
edits `main.js` AND re-pins in one commit — that is branch-protection / CODEOWNERS territory.
It turns silent drift into a reviewable diff and a red test; that is the claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Bootstrap: allow `python3 scripts/build_agent_bridge.py` (plain script) as well as
# `python3 -m scripts.build_agent_bridge`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

PLUGIN_DIR = _REPO_ROOT / "skills" / "obsidian-cli" / "plugin" / "agent-bridge"
MAIN_TS = PLUGIN_DIR / "main.ts"
MAIN_JS = PLUGIN_DIR / "main.js"
ESBUILD_BIN = PLUGIN_DIR / "node_modules" / ".bin" / "esbuild"
TSC_BIN = PLUGIN_DIR / "node_modules" / ".bin" / "tsc"
MANIFEST = _REPO_ROOT / "config" / "agent-bridge-build.json"

# The recipe. `--external:*` is load-bearing, not tidiness: Obsidian injects its own `obsidian`
# and CodeMirror instances at runtime. Dropping one is SILENT — the bundle grows 12,191 →
# 419,223 bytes, esbuild exits 0 with no warning, and the plugin ships a SECOND CodeMirror
# instance whose `ViewPlugin` never draws into the real editor. `--external:@codemirror/state`
# is defensive-only today (0 occurrences in the output); it is here so a future `StateField`
# import cannot get bundled. `test_bundle_externalizes_what_obsidian_provides_at_runtime` is
# the only guard that fires on that mutation.
ESBUILD_ARGV: tuple[str, ...] = (
    "main.ts",
    "--bundle",
    "--external:obsidian",
    "--external:@codemirror/view",
    "--external:@codemirror/state",
    "--format=cjs",
    "--target=es2018",
    "--platform=browser",
    "--log-level=warning",
)

TSC_ARGV: tuple[str, ...] = ("--noEmit",)

_PINNED_FILES = (MAIN_TS, MAIN_JS)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


# ── per-tool presence predicates ──────────────────────────────────────────────────────
# ★ NEVER collapse these into one `toolchain_present()`. The hazard is concrete and
# asymmetric: with a single shared predicate, *esbuild absent + typescript present* makes the
# **tsc gate skip although it could have run** — a green that means "not checked". The two
# tools also have genuinely different requirements, verified on this machine (2026-07-16):
#
#   esbuild  node_modules/.bin/esbuild -> ../esbuild/bin/esbuild, a Mach-O arm64 binary
#            (esbuild's `postinstall: node install.js` swaps the JS shim for the platform
#            binary). `env -i PATH=/usr/bin:/bin esbuild --version` → `0.28.1`. Needs NO node.
#   tsc      `#!/usr/bin/env node`. Same probe → `env: node: No such file or directory`.
#
# So requiring `node` for esbuild would ALSO be wrong — it is the same hazard mirrored: a gate
# that could run, skipped on a condition it does not depend on.
#
# Accepted corner: `npm install --ignore-scripts` leaves `bin/esbuild` as the JS shim, which
# then needs node. In that state `_esbuild_present()` says True and the build RAISES rather
# than skips. That is the correct posture — a broken toolchain must be loud (`check=True`), and
# only a genuinely ABSENT tool may skip.


def _esbuild_present() -> bool:
    """Can we run esbuild? The binary is platform-native, so `node` is NOT part of this."""
    return os.access(ESBUILD_BIN, os.X_OK)


def _tsc_present() -> bool:
    """Can we run tsc? It is a `#!/usr/bin/env node` script, so `node` IS part of this — and
    this is the only predicate node belongs to."""
    return shutil.which("node") is not None and TSC_BIN.is_file()


# ── the toolchain ─────────────────────────────────────────────────────────────────────


def build() -> bytes:
    """esbuild(main.ts) → the bundle bytes.

    `cwd=PLUGIN_DIR` + a RELATIVE entry are load-bearing for determinism, not style: esbuild
    stamps the entry path into the output as a comment, so the same source built from a
    different cwd yields a different hash (verified: rel `05d906d4…` vs abs `3b3a3645…`).

    `check=True`: a broken build must RAISE. Degrading it to a skip would convert the exact
    drift this gate hunts into a green.
    """
    proc = subprocess.run(
        [str(ESBUILD_BIN), *ESBUILD_ARGV],
        capture_output=True,
        check=True,
        cwd=PLUGIN_DIR,
    )
    return proc.stdout


def esbuild_version() -> str:
    proc = subprocess.run(
        [str(ESBUILD_BIN), "--version"], capture_output=True, check=True, text=True, cwd=PLUGIN_DIR
    )
    return proc.stdout.strip()


def tsc_version() -> str:
    proc = subprocess.run(
        [str(TSC_BIN), "--version"], capture_output=True, check=True, text=True, cwd=PLUGIN_DIR
    )
    # `tsc --version` prints "Version 5.9.3"; keep just the number.
    return proc.stdout.strip().removeprefix("Version").strip()


def typecheck() -> tuple[int, str]:
    """Run `tsc --noEmit` against the plugin's tsconfig. Returns `(error_count, output)`.

    `check=False` is deliberate: a type error is a REPORTABLE outcome here (the caller refuses
    to re-pin), not an exception. The count is parsed from the diagnostics rather than taken
    from the exit status so the caller can show the reader exactly what blocked the re-pin.
    """
    proc = subprocess.run(
        [str(TSC_BIN), *TSC_ARGV], capture_output=True, text=True, cwd=PLUGIN_DIR
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    count = sum(1 for line in output.splitlines() if ": error TS" in line)
    # A non-zero exit with no parseable diagnostic (a tsc crash, a bad tsconfig) must not read
    # as "0 errors" — that would let `--write` mint a receipt off a typecheck that never ran.
    if proc.returncode != 0 and count == 0:
        count = 1
        output += f"\n(tsc exited {proc.returncode} with no parseable diagnostic)"
    return count, output


# ── the receipt ───────────────────────────────────────────────────────────────────────


def load_manifest() -> dict[str, Any] | None:
    """The pinned receipt, or **None if it does not exist**.

    None is not an error here — it is the UN-PINNED state, which is a form of drift, and the
    caller (the L0 gate) must render it RED. Raising or skipping on a missing receipt would
    hand exactly the un-pinned tree a pass.
    """
    if not MANIFEST.is_file():
        return None
    parsed: dict[str, Any] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return parsed


def _receipt(esbuild_ver: str, tsc_ver: str) -> dict[str, Any]:
    return {
        "_comment": (
            "GENERATED by scripts/build_agent_bridge.py --write (TASK 070 / R-070-4). "
            "Pins BOTH sides of the main.ts -> main.js tie. Do NOT hand-edit: the hashes are "
            "meant to be reviewed, not authored. `tsc` is: 0 errors — asserted only because "
            "--write refuses to re-pin otherwise."
        ),
        "files": {_rel(p): sha256_file(p) for p in _PINNED_FILES},
        "esbuild_version": esbuild_ver,
        "esbuild_argv": list(ESBUILD_ARGV),
        "tsc_version": tsc_ver,
        "tsc_argv": list(TSC_ARGV),
        "tsc_result": "0 errors",
    }


def _drift() -> list[str]:
    """Human-readable drift lines vs the receipt; empty == in sync."""
    manifest = load_manifest()
    if manifest is None:
        return [f"- {_rel(MANIFEST)} is MISSING — main.js is unpinned."]
    problems: list[str] = []
    pinned: dict[str, str] = manifest.get("files", {})
    for path in _PINNED_FILES:
        rel = _rel(path)
        if rel not in pinned:
            problems.append(f"- {rel} is not pinned by the receipt.")
        elif sha256_file(path) != pinned[rel]:
            problems.append(f"- {rel} changed since the last pin.")
    if tuple(manifest.get("esbuild_argv", ())) != ESBUILD_ARGV:
        problems.append("- the pinned esbuild recipe differs from ESBUILD_ARGV.")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Typecheck, rebuild main.js from main.ts, and re-pin config/agent-bridge-build.json.",
    )
    args = parser.parse_args(argv)

    if args.write:
        # 1. tsc FIRST. Absent tsc is a HARD FAIL, never a skip: a receipt minted without a
        #    typecheck would attest "0 errors" that nobody observed — C-1 surviving inside
        #    C-1's own fix.
        if not _tsc_present():
            print(
                "error: tsc is not available (need `node` on PATH and "
                f"{_rel(TSC_BIN)}). Run `npm install` in {_rel(PLUGIN_DIR)}.\n"
                "       Refusing to re-pin: the receipt asserts a clean typecheck, and this "
                "run cannot perform one.",
                file=sys.stderr,
            )
            return 2
        n_errors, output = typecheck()
        if n_errors:
            print(output.rstrip(), file=sys.stderr)
            print(
                f"\nerror: tsc reports {n_errors} error(s) — REFUSING to rebuild or re-pin.\n"
                "       Fix main.ts. There is no --force: a receipt for un-type-checked code "
                "is the exact failure this gate exists to end.",
                file=sys.stderr,
            )
            return 1

        # 2. esbuild.
        if not _esbuild_present():
            print(
                f"error: esbuild is not available ({_rel(ESBUILD_BIN)}). "
                f"Run `npm install` in {_rel(PLUGIN_DIR)}.",
                file=sys.stderr,
            )
            return 2
        bundle = build()
        MAIN_JS.write_bytes(bundle)

        # 3. the receipt — minted only now, downstream of a clean typecheck and a real build.
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(
            json.dumps(_receipt(esbuild_version(), tsc_version()), indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"built:  {_rel(MAIN_JS)} ({len(bundle):,} bytes) from {_rel(MAIN_TS)}")
        print(f"pinned: {_rel(MANIFEST)} (tsc {tsc_version()}: 0 errors)")
        return 0

    problems = _drift()
    if not problems:
        print(f"in sync: {_rel(MAIN_JS)} is esbuild({_rel(MAIN_TS)}) per {_rel(MANIFEST)}.")
        return 0
    print("DRIFT — the agent-bridge build receipt is stale:")
    for line in problems:
        print(f"  {line}")
    print("\nRebuild and re-pin with: python3 scripts/build_agent_bridge.py --write")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
