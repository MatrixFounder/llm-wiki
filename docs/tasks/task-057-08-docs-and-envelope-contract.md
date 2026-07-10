# 057-08 — [W2-5][NF-2] docs + envelope/exit-code contract sync

**Goal:** the prompt layer teaches the new flow; the CLI contract docs stay the single source
of truth for the additive envelope actions.

**Context (read):** `templates/CLAUDE.md.tmpl` (§ "Ingest a new source" ~:120 + the
obsidian-cli active-note paragraph ~:338); `skills/wiki-import/SKILL.md` (flags + exit-code
sections); `workflows/wiki-import.md`; ARCHITECTURE §2.3.5 companion-rule paragraph;
ARCH review MINOR-4.

**Steps:**
1. `skills/wiki-import/SKILL.md`:
   - new prepare flags `--transcript-concurrency` / `--transcript-media-timeout` (forwarded to
     the skill; omitted → skill env/derived defaults) + the scoped wall-clock note
     (`WIKI_TRANSCRIPT_TIMEOUT_S` overrides both roles; defaults 3600 primary / 300 embeds —
     an embed fetch clips a large `--transcript-media-timeout` at 300 s unless the env knob is
     raised — MINOR-4).
   - `--folder` now optional on prepare: inference chain, `folder_proposed` (exit 0) /
     `FOLDER_UNRESOLVED` (exit 2 — NO_CONTEXT-family, typed error disambiguates) /
     `announcement_only` (exit 0) rows in the actions/exit-codes table; `staged_path`
     re-run recipe.
2. `workflows/wiki-import.md`: the confirm/override loop — no-folder run → read proposal →
   confirm (or ask user on FOLDER_UNRESOLVED) → re-run `--folder <F> --source <staged_path>`.
3. `templates/CLAUDE.md.tmpl`: in the ingest recipe, state the FIRST move on a missing folder
   is to omit `--folder` (series-sibling inference, vendor-independent); demote
   `obsidian-active-note` to the secondary hint in that flow (leave §obsidian-cli's own
   active-note protocol text untouched — it reorders import guidance, not the resolver).
4. Cross-check `commands/wiki-import.md` (if it duplicates flags) — sync or confirm it defers
   to SKILL.md.

**Verification:** grep-level: the three files mention `folder_proposed`, `FOLDER_UNRESOLVED`,
`announcement_only`, `--transcript-concurrency`; no stale "required --folder" claim on the
prepare examples; `pytest tests/ -k evals -q` if the wiki-import evals assert SKILL text.
