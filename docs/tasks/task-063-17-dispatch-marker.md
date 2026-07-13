# TASK 063-17 — the config-driven **dispatch marker** (`wiki-sync` + `wiki-import`)

**Phase**: 5 (acceptance) · **RTM**: R-063-3′(a)(c)(d), Q-063-2 · **Type**: code · **Effort**: 3h
**Depends on**: 063-01, 063-05 · **Unblocks**: 063-18

## Goal

**The operator requirement (v6):** the rail must be **invocable from config**, like its sibling
`extract_concepts`.

**And Decision-17 must survive it.** `wiki-sync` / `wiki-import` **do not call an LLM**. They emit a
**dispatch marker**, and the **orchestrator** runs the rail as a second step — *precisely how
`wiki-sync` already delegates to `wiki-import`* (`wiki_sync.py:220-232`, the `delegate` block). The
CLI stays deterministic plumbing.

## The marker

`wiki-import apply`'s envelope gains:

```jsonc
"extract_decisions": {                 // present ONLY when the resolved config enables it
  "tool": "wiki-extract-decisions",
  "source": "<note_rel>",
  "dirs": {"decision": "decisions", "requirement": "requirements", "risk": "risks"}
}
```

`wiki-sync scan`'s per-entry `delegate` block gains `"extract_decisions": true|false`, resolved via
`resolve_extract_decisions(cand.path, …)` (063-01) — the same per-folder cascade `summarize:` uses.

**Absent / `enabled: false` ⇒ the key is OMITTED ⇒ the rail is never auto-dispatched** (R-063-3′(c)).
Omission, not `false`: a marker that is always present invites an orchestrator to act on it.

## Context — files

- **Edit** `scripts/wiki_skills/wiki_import_article/__init__.py` — the `emit()` envelope at line ~999
  (next to `concepts_deferred`, which is the exact precedent for "this downstream step is deferred to
  a separate run").
- **Edit** `scripts/wiki_skills/wiki_sync.py` — the `delegate` dict at line 225.
- **Read** `_resummarize.resolve_extract_decisions` (063-01).
- **Edit** `commands/wiki-import.md`, `commands/wiki-sync.md` — the orchestrator must be *told* to act
  on the marker, or the marker is decoration. This is the step that closes the conveyor.

## ⚠️ Spec inconsistency, resolved here (see PLAN §7)

TASK.md **§7 "Out of scope"** still lists *"Auto-chaining from `wiki-import` (Q-063-2)"* — a **stale
line from v5**. §5 Q-063-2 was **REVERSED by operator requirement in v6**. The operator requirement
governs. **063-18 corrects §7** when TASK.md is finalised on ship, so the shipped spec does not carry
a contradiction into the archive.

## Tests (RED first) — `tests/test_sync_delegation.py` (extend) + `tests/test_extract_decisions_dispatch.py` (new)

- `test_marker_absent_when_not_configured` — no `extract_decisions:` block ⇒ the key is **absent** from
  both envelopes. **Back-compat: every existing `wiki-import`/`wiki-sync` envelope test stays green,
  byte-identical.** **MUT:** always emit the marker ⇒ the existing envelope tests go RED (which is the
  correct, loud way to learn you changed a contract).
- `test_marker_present_when_enabled` — `enabled: true` ⇒ the marker carries the **resolved** dirs.
- `test_marker_respects_the_per_zone_cascade` — Zone A (`decisions`) and Zone B (`решения`, on a
  generic-glob layout) ⇒ two different markers **from one `wiki-sync scan`**. This is R-063-3′(d),
  end-to-end.
- `test_no_llm_call_in_the_dispatch_path` — grep both modules for `import anthropic` ⇒ none.
  Decision-17 survives the feature.
- `test_marker_is_omitted_not_false` — `enabled: false` ⇒ the key is **absent**, not `false`.

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] **GREP-THE-SURFACES — "the CLIs never call an LLM" is the Decision-17 denominator claim.**
      Enumerate the LLM-shaped skills from CLAUDE.md and assert over **all** of them, not just the two
      this bead touched:
      ⚠️ **BOTH import forms** (plan-review **M-8**) — the house gate
      (`tests/test_wiki_sync.py:634-639`) asserts `"import anthropic"` **and** `"from anthropic"`:
      ```bash
      grep -rlE "import anthropic|from anthropic" scripts/wiki_skills/ && echo "VIOLATION"
      ```
      Add it as a **test** that globs `scripts/wiki_skills/` so a *new* skill is covered by default.
      A hand-typed module list is exactly this project's failure mode; so is a one-pattern grep.
- [ ] The `wiki-import` envelope is **byte-identical** when the block is absent (diff the JSON against
      a pre-change golden).

## Rollback

Remove the two envelope keys. The rail stays independently invocable by hand (the
`wiki-extract-concepts` posture is preserved by design — the marker is an *addition*, never the only
door).
