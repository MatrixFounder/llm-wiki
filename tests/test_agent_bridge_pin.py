"""TASK 070 (R-070-2) — the agent-bridge type pin must stay sound: `pin <= minAppVersion`.

Types must never promise more than the OLDEST runtime allowed to load the plugin. Two numbers
enforce that from opposite sides, and they only agree if we keep them equal:

* `package.json` `devDependencies.obsidian` — what `tsc` checks `main.ts` against. It REFUSES
  anything the pinned version does not have.
* `manifest.json` `minAppVersion` — Obsidian's own load guard. It REFUSES to load the plugin on
  an older app.

Before TASK 070 the pin was 1.12.3 and the floor 1.4.0, so `1.4.0 … 1.12.2` was an UNGATED
window: an API added in 1.11 type-checked clean AND passed the load guard, then crashed at
runtime. Empty in practice (everything this plugin touches has existed since 1.1.1), but
unsound by construction — an unverified compatibility claim in JSON, which is the same defect
class as the fabricated `getMode()`, just in a different file.

Equality is the tightest sound point: `pin == minAppVersion == 1.12.3`. Adopting a 1.13 API
becomes a deliberate two-number bump rather than an accident.

Rejected, and worth preserving: pinning to the FLOOR (1.4.0) would verify the manifest's claim,
but Obsidian's types are not purely additive — `CloseableComponent` exists at 1.12.3 and is GONE
at 1.13.1 — so a floor far below the runtime can promise APIs the runtime REMOVED. Same
over-promise, arrived at through deprecation instead of addition.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parents[1] / "skills/obsidian-cli/plugin/agent-bridge"
_EXACT = re.compile(r"^\d+\.\d+\.\d+$")


def _package_json() -> dict[str, dict[str, str]]:
    return json.loads((_PLUGIN / "package.json").read_text(encoding="utf-8"))


def _pin() -> str:
    return _package_json()["devDependencies"]["obsidian"]


def test_obsidian_pin_is_exact() -> None:
    # A range defeats the gate silently: `^1.12.3` resolves to 1.13.1 (verified against the
    # registry, 2026-07-16), which exports ~27 symbols a 1.12.7 runtime does not have. Code
    # written against them would type-check clean and crash on the user's app — the fabrication
    # failure with an npm package standing in for a hand-written d.ts.
    assert _EXACT.match(_pin()), f"the obsidian pin must be exact, got {_pin()!r}"


def test_pin_equals_min_app_version() -> None:
    manifest = json.loads((_PLUGIN / "manifest.json").read_text(encoding="utf-8"))
    assert _pin() == manifest["minAppVersion"], (
        "soundness requires pin <= minAppVersion; equality is the tightest sound point. "
        "tsc refuses anything above the pin; Obsidian refuses to load below minAppVersion."
    )


def test_lockfile_matches_pin() -> None:
    lock = json.loads((_PLUGIN / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["packages"]["node_modules/obsidian"]["version"] == _pin()


def test_every_devdependency_is_pinned_exact() -> None:
    """R-070-9(b) — the build's OWN toolchain must not float either.

    The receipt records the esbuild and tsc versions that produced it; a caret would let an
    `npm install` months later mint byte-different output from identical source and read as drift,
    or worse, mint identical-looking output from a compiler with different semantics.

    ★ The roster is DERIVED from package.json, never hand-listed. The first version of this test
    was `@parametrize("tool", ["obsidian", "esbuild", "typescript"])` — it was named "every
    devDependency" and checked three remembered names, so a FOURTH one could float unpinned with
    this file fully green. That was caught by mutation, not by review: adding `"@types/node": "^20"`
    left `pytest tests/test_agent_bridge_pin.py` at 6 passed. An enumeration with a gap exactly
    where the gap is invisible — inside the test whose name promises there is none.
    """
    dev_deps = _package_json()["devDependencies"]
    assert dev_deps, "package.json declares no devDependencies — the roster cannot be empty"
    floating = {name: v for name, v in dev_deps.items() if not _EXACT.match(v)}
    assert not floating, (
        f"these devDependencies are not pinned exact: {floating}. A range floats the build "
        f"toolchain: `^1.12.3` resolves to 1.13.1 (verified 2026-07-16)."
    )
