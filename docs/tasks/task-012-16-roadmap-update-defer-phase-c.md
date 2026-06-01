# Task 012-16: ROADMAP update — mark R-X1/R-X2(A-B)/R-X3 done + record deferred R-X2 Phase C

## Use Case Connection
- R-X2.roadmap: keep `docs/ROADMAP.md` truthful; ensure the deferred archive hook isn't forgotten (D-012-4).

## Task Goal
Close out the Epic in `docs/ROADMAP.md`: mark R-X1, R-X2 (Phases A-B), and R-X3 as DONE, and
**split R-X2 Phase C (the agentic-development `archive_protocol.py` indexing hook) into a
distinct, explicitly-deferred follow-up entry** so the deferred cross-repo work is tracked
(operator decision: stabilise the wiki first, then extend to the framework).

## Changes Description

### Changes in Existing Files

#### File: `docs/ROADMAP.md`
- **R-X1** → `✅ DONE <date> (TASK 012)` with a one-line summary (config-driven engine, 3
  built-in layouts, byte-identical Karpathy, zero DDL).
- **R-X2** → split:
  - `R-X2 (Phases A-B)` → `✅ DONE (TASK 012)` — `wiki-init --layout` + dev-vault bootstrap
    (self + one peer) + cross-project search.
  - **NEW entry `R-X2c` (or restated R-X2 Phase C)** → status **DEFERRED**: the
    `agentic-development/.agent/tools/archive_protocol.py` feature-detected shell-out to
    `wiki-index-upsert` + `pending.log` observability (§12 Option C sketch). Trigger: after
    the wiki is stable + dogfooded in daily use. Cross-repo; separate branch/commit in the
    peer repo; its tests live there. **Reason recorded:** D-012-4 — debug/stabilise the wiki
    first, then extend to the framework.
- **R-X3** → `✅ DONE (TASK 012)` — KNOWN_ISSUES migrated to per-file Class-A + Class-B
  auto-rendered ledger (ADR-002 §D8 amendment); reference the dogfood.
- Add a `## Done since …` summary line for TASK 012 (mirroring the existing entries):
  beads count, gates (task/architecture/plan reviews + per-bead vdd-multi/code-review),
  final pytest/mypy numbers, `user_version` 5 (zero DDL).
- Update `CLAUDE.md` status header + Pointers (TASK 012 shipped; new `layout_config.py` +
  `layouts/` + `config/layout-config.schema.yaml` pointers) — orthogonal doc sync.

### Changes in Test Files
#### File: `tests/test_roadmap_rx_status.py` (NEW, optional/light)
- Assert `docs/ROADMAP.md` marks R-X1/R-X2(A-B)/R-X3 done AND contains a DEFERRED Phase-C /
  archive-hook entry (so the deferral can't silently vanish in a future edit).

## Acceptance Criteria
- ✅ ROADMAP marks R-X1 + R-X2(A-B) + R-X3 DONE; the archive-hook (Phase C) is a distinct
  DEFERRED entry with the D-012-4 reason.
- ✅ `CLAUDE.md` status/Pointers synced. Final full regression + `mypy --strict` green.

## Stub-First
Docs-only closeout bead. The optional status test guards the deferral record.
