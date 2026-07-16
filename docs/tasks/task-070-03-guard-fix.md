# TASK 070-03 — [R-070-5] Make the preview fail-open unrepresentable

**Goal:** all 3 tsc errors die with **zero casts**; a non-`MarkdownView` can never be silently retargeted.

**Context:** `skills/obsidian-cli/plugin/agent-bridge/main.ts`, `skills/obsidian-cli/scripts/obsidian_selection.py` (`_REASON_EXIT` :323-343), `skills/obsidian-cli/SKILL.md` (**H-5-pinned**), `references/recipes.md`. Design: `design-preview-guard.md`.

**Steps**
1. `main.ts`: drop `MarkdownFileInfo` from the import — the type that carried the fabrication leaves the plugin. Resolution returns `MarkdownView`.
2. Refuse a non-`MarkdownView` **AT the active editor** → `unsupported-view`. **Never fall through to `lastEditor`** — that silently retargets a *different note* and every apply guard then passes against it.
3. `lastEditor: MarkdownView | null`; `rememberEditor` narrows (`ae instanceof MarkdownView`). Fixes a real bug for free: a non-MarkdownView memory can never pass `isAttached`, so it evicts a good remembered view.
4. `isAttached(view: MarkdownView)` — `leaf.view === view` now genuinely overlaps (TS2367 dies).
5. Wrapper: `"unsupported-view": EXIT_NO_SELECTION` (**3**). **Keep `no-saveable-view`** (legacy alias — the plugin installs by *copying*, so a vault may run an older main.js).
6. Vocabulary: `SKILL.md:394-397`, `recipes.md:309,323` → re-pin: `python3 scripts/pin_skill_integrity.py --write`.
7. **[R-070-7] vocabulary — fold in here** (PLAN's RTM maps it to this bead and nowhere else).
   `SKILL.md:395` still describes exit 4 as *"(result timeout / stale nonce never matched)"* — it
   **omits `selection-nonce-mismatch`, a reason the shipped code already emits**, in a file loaded
   **verbatim** into the orchestrator's context. Verify the gap first:
   `grep -r selection-nonce-mismatch skills/obsidian-cli/ --include='*.md'` → **0 hits today**. Add it;
   the H-5 re-pin in step 6 already covers the cost.

**Verification** — `npx tsc --noEmit` → **0 errors**; `grep -c "as \|any" main.ts` shows no new cast. New tests: `unsupported-view` → exit 3; `no-saveable-view` still maps. `pytest tests/test_h5_skill_integrity.py` green.
