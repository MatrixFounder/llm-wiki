# task-018-16 — Docs + close

**Parent:** TASK 018. **Depends on:** 018-15. **RTM:** AC-9 (docs), NF.

## Goal
Land the docs surface and close R-11; final gate.

## Steps
1. `scripts/wiki_skills/.AGENTS.md` — add the `wiki_sync.py` + `_sync.py` + `sync_config.py`
   entries; `scripts/wiki_index/.AGENTS.md` — note the new `source_state` `sync` partition +
   `get/set_source_state`.
2. `README.md` — add `wiki-sync` to the CLI reference (Knowledge-construction group) + a pointer
   from the *Mixed vault* manual section ("per-note tag-routing is now `wiki-sync`, not just
   ROADMAP R-11"); update the install table counts (15 CLIs / wrappers / commands).
3. `docs/ROADMAP.md` — **R-11 → ✅ SHIPPED** (move to Done-since block; summarize the 2-gate
   hardening: adversarial CRITICAL idempotency + re-gate SEC-N3/RG-1 corrections).
4. `CLAUDE.md` — status header += TASK 018 ship line; `docs/manuals/obsidian-llm-wiki_manual.md`
   *Mixed vault* forward-pointer flipped from "planned" to "shipped".
5. Residual: RC-4/RC-5/SEC-N1 were closed in beads 08/14 → confirm none remain open; if any, file
   a `docs/issues/*.md` + re-render the ledger (`wiki-index-render --auto-indexes`), `wiki-lint`
   PW-Q clean.

## Verification
- Full `pytest -q` (≥ baseline + new) + `mypy --strict scripts/` clean; `user_version` still 5;
  `grep -rL anthropic` on `wiki_sync.py`; `wiki-lint` PW-Q drift-clean; README/ROADMAP/CLAUDE updated.
