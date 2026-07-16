# TASK 070-06 — [R-070-2] pin == minAppVersion == 1.12.3

**Goal:** one number; both guards agree. Ordered AFTER 070-05 — until main.js is generated the pin gates a file Obsidian never executes.

**Context:** `skills/obsidian-cli/plugin/agent-bridge/{manifest.json,package.json,package-lock.json}`. Design: `design-version-pin.md`.

**Steps**
1. `manifest.json`: `"minAppVersion": "1.4.0"` → `"1.12.3"`.
2. Tests (fold into `tests/test_agent_bridge_build_drift.py` or a sibling): pin is exact (no caret — `^1.12.3` resolves to 1.13.1 and silently defeats the gate) · `pin == manifest.minAppVersion` · lockfile version == pin.

**Verification** — the 3 tests green. Rationale to preserve in review: pinning to the floor (1.4.0) was **rejected** — Obsidian's types are not purely additive (`CloseableComponent` exists at 1.12.3, **gone** at 1.13.1), so a floor can promise APIs the runtime *removed*.
