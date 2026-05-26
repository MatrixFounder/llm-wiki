# Plan Review — Phase 3a (2026-05-26)

**Reviewer**: Plan Reviewer subagent (fresh context, post-Planner output)
**Subject**: `docs/PLAN.md` (294 lines, Stub-First two-stage) + 34 task files `docs/tasks/task-001-{01..34}-*.md`
**Plan target**: gate Planning→Execution boundary for Phase 3a (E1 Foundation → E6 Benchmark)

## 1. Verdict

**APPROVED WITH COMMENTS** (confidence: high).

Plan материально execution-ready. Stub-First discipline rigorously applied across 34 atomic tasks; RTM coverage complete for Phase 3a; out-of-scope items (R-06.3, R-12, R-24) correctly deferred. Архитектурные enforcement points из ADR-001/002 wired в конкретные task bodies с file paths и method signatures. **5 important issues** для pre-Execution cleanup pass (не redesign-level), **0 critical**. Никто не блокирует kickoff task-001-01.

`has_critical_issues: false`

## 2. Critical issues

**None.**

## 3. Important issues (fix before Execution)

### I-1. `PRAGMA user_version = 2` не wired в task

Architecture review M-5 требует `PRAGMA user_version = 2` для migration gating. SCHEMA-v2.sql упоминает только в комментариях, не в DDL. Ни одна task не применяет.

**Fix**: task-001-01 + добавить TC-UNIT в task-001-15 или task-001-20.

### I-2. M-6 (drop indexes на out-of-MVP tables) never addressed

Architecture review M-6: keep `interactions` / `extracted_items` tables, но drop их indexes до Epic 6. Plan не имеет task для этого.

**Fix**: либо acceptance criterion в task-001-01, либо `KNOWN_ISSUES.md` entry. "address opportunistically" в PLAN.md §5 — не verifiable.

### I-3. PLAN.md §5 mis-maps M-IDs vs original architecture-review

PLAN.md §5 переименовывает architecture-review M-IDs неправильно (M-3 vs M-5 vs M-6 mixed up). Создаёт ambiguity для Execution-phase developers.

**Fix**: realign table к original IDs из architecture-review-pre-phase3a-2026-05-26.md.

### I-4. L-1..L-7 minor cleanups без concrete owner

PLAN.md §5: "L-1..L-7 tracked в docs/KNOWN_ISSUES.md; address opportunistically." KNOWN_ISSUES.md содержит 0 entries (stub).

**Fix**: либо task-001-35-minor-cleanups.md, либо populate KNOWN_ISSUES.md с 7 entries сразу.

### I-5. `entities.mentions_count` drift undermines rebuildability invariant

Architecture review §5 flag'нул `mentions_count` как stored field который должен быть view. Class B (computed) — если reindex не recomputes, reindex не idempotent. Ни task-001-30 ни task-001-34 этого не адресуют.

**Fix**: explicit acceptance criterion в task-001-30: после reindex `mentions_count == COUNT(*) FROM page_entity_refs`. Иначе rebuildability gate test даст false-positive.

## 4. Minor / nits

- **N-1**: PLAN.md line 65 batches 5 RTM IDs в один checklist item (task-001-08). Acceptable, но per-skill split cleaner.
- **N-2**: task-001-25 TC-E2E-06 не имеет verbatim AC text для unclosed mermaid fence per TASK.md.
- **N-3**: task-001-27 step 3 использует `repo._connect()` (private accessor) — DAL boundary leak. Use public `repo.update_log_event_offset(event_id, byte_offset)`.
- **N-4**: task-001-30 step 4 explicit `DELETE FROM ...` per table. Correct (vs CASCADE which would drop vault row).
- **N-5**: task-001-34 BM25 tolerance ±0.001 tight; widen к ±0.01 или assert result-set ordering.
- **N-6**: Document full exit-code taxonomy в task-001-08 Notes.
- **N-7**: task-001-33 benchmark не explicitly включает `wiki-reindex --delta` SLO в table.
- **N-8**: PLAN.md §0 "Architectural foundation" table — cosmetic, consider move в ARCHITECTURE.md.

## 5. RTM coverage audit — COMPLETE

| RTM ID | Required Phase 3a | Covered | Task(s) |
|---|---|---|---|
| R-01 | ✓ | ✓ | task-001-02 (stub), -13 (impl) |
| R-02 | ✓ | ✓ | task-001-01 |
| R-03 | ✓ | ✓ | task-001-14 |
| R-04 | ✓ | ✓ | task-001-03/04/05 (stubs), 15-20 (impl) |
| R-05 | ✓ | ✓ | task-001-08 (stub), 21/22/23 (impl) |
| R-06.1 | ✓ | ✓ | task-001-06 |
| R-06.2 | ✓ | ✓ | task-001-07 (stub), 24 (impl) |
| R-07 (+.1/.2/.3/.4/.5) | ✓ | ✓ | task-001-08 (stub), 25 (impl) |
| R-08 | ✓ | ✓ | task-001-08 (stub), 26 (impl) |
| R-09 | ✓ | ✓ | task-001-08 (stub), 27 (impl) |
| R-10 | ✓ | ✓ | task-001-08, 17, 28 |
| R-11 | ✓ | ✓ | task-001-08, 18, 29 |
| R-13 | ✓ | ✓ | task-001-32 |
| R-14 | ✓ | ✓ | task-001-09, 33, 34 |
| R-15.3 | ✓ | ✓ | task-001-24 |
| R-25 (superseded) | ✓ | ✓ | task-001-15 |
| R-26 | ✓ | ✓ | task-001-12, 24 |
| R-27 (new) | ✓ | ✓ | task-001-01, 15 |
| R-28 (new) | ✓ | ✓ | task-001-19, 27 |
| R-29 (new) | ✓ | ✓ | task-001-17, 18, 28, 29 |

**Out-of-scope correctly deferred**: R-06.3, R-12, R-24 mentioned только в §0 deferral block, не в task bodies. ✓

## 6. Stub-First / Atomicity / Dependencies: PASS

- Stub-First random pairs verified (R-04, R-06.2, R-05, R-07, R-14). E2E harness asserts hardcoded stub values.
- Atomicity: smallest task ~1hr, largest ~3.5hr (task-001-25 R-07.1-.5; task-001-30 reindex). All within 2-4hr ceiling.
- Dependencies form valid DAG. No circularity.

## 7. Architectural enforcement: PASS (except I-5)

| Constraint | Status |
|---|---|
| ADR-002 §D1.1 vault_id REQUIRED (quadruple-validated) | ✓ |
| ADR-002 §D8 Class A→B reconstruction | ✓ (task-001-30/34) |
| M-4 ON CONFLICT contract | ✓ (task-001-16 with grep guard) |
| R-07.4 type-mapping + R-07.5 anti-tail-eat regex | ✓ (task-001-25) |
| R-26 path-traversal | ✓ (task-001-12 utility + 24 call-site) |
| log.md ↔ log_events sync (D2) | ✓ (task-001-19/27/30/34) |
| index_meta UNION custom-section preservation | ✓ (task-001-26) |
| iCloud rejection (R-03) | ✓ (task-001-14/20) |
| `entities.mentions_count` drift | ✗ (see I-5) |

## 8. Hallucination check — clean

All cited file paths, schema lines, ADR sections verified. One outdated hedge in task-001-26 ("`index_meta` may need adding") — view present at SCHEMA-v2.sql line 450.

## 9. Convergence signal

APPROVED WITH COMMENTS — fixable in one cleanup pass. Issues bookkeeping/wiring gaps (I-1..I-4) + one real correctness (I-5 mentions_count drift). After cleanup, Execution may begin без re-review.
