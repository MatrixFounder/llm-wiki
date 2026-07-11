# Task 060: [LIGHT] Recognize Obsidian Bases (.base) files in active-note resolution

## 0. Meta Information
- **Task ID**: 060
- **Slug**: obsidian-cli-bases-active-note-resolution
- **Origin**: operator dogfood report, 2026-07-11 — opened a `.base` file in Obsidian, ran
  `claude` CLI, asked "which folder is open?"; the active-note resolver reported "no active
  note" even though a file was genuinely open.
- **Type**: Bugfix (existing skill script, no new files)
- **Effort**: S

## 1. Problem

`skills/obsidian-cli/scripts/obsidian_active_note.py` (the `obsidian-active-note` resolver,
TASK 041 / ADR-008) hard-codes "open note" to **markdown only**:

- `markdown_tabs()` filters `tabs` output to `view_type == "markdown"` — an open `.base` tab
  has a different view-type and is invisible to `tabs`/`match`.
- `_recents_md()` filters `recents` to `endswith(".md")` — so the `recent-open` MEDIUM
  fallback (used when the focused leaf isn't a markdown editor, e.g. the integrated
  terminal) also never surfaces an open `.base` file.

Repro: user has `.../05 - Материалы/Разработка.base` open and focused in Obsidian, in the
vault's integrated terminal runs `claude` and asks which folder is open. `obsidian file`
reports `Error: No active file`, and the wrapper's own `recent-open` fallback also comes up
empty (the `.base` file is filtered out), so `focused`/`folder` both fail with
`EXIT_NO_ACTIVE_FILE`. The agent then wrongly tells the user nothing is open, when a Base
view genuinely is.

## 2. Scope (files to update)

- [x] `skills/obsidian-cli/scripts/obsidian_active_note.py`:
  - [x] New `open_file_tabs()` / `list_open_files()` — an EXCLUDE-list over known Obsidian UI
        chrome view-types (`_CHROME_VIEW_TYPES`), not a per-extension allow-list, so Bases
        (view-type `bases`, live-verified against the real vault) and any future non-markdown
        content view-type is recognized without another patch.
  - [x] `_recents_md()` → `_recents_files()`, drops the `.md`-only filter (recents also lists
        bare folder entries — harmless, the per-line `path=` probe just skips them).
  - [x] `markdown_tabs()`/`list_open_notes()`/`match`/`resolve_title`/`vault_basename_count`
        (F-1 guard) left **markdown-only, deliberately**: live-verified `obsidian file
        file=<title>` (the wikilink resolve `match` depends on) does NOT find a `.base` by
        bare title — only appending the extension works, which a tab title doesn't carry.
        Documented as a scope boundary in both `markdown_tabs()`'s docstring and SKILL.md.
- [x] `skills/obsidian-cli/evals/fixtures/` — added `obsidian-tabs-with-base.txt` +
      `obsidian-file-base.tsv`, real live captures (2026-07-11) against the operator's actual
      vault (`.base` focused; confirmed `obsidian file` bare still reports "No active file").
- [x] `tests/test_obsidian_active_note.py` — 3 new tests: `open_file_tabs` keeps Bases/excludes
      chrome, `resolve_focused` recent-open fallback for a `.base`, `resolve_folder` deriving
      the containing folder of a `.base` (the user's literal "which folder is open?" case).
- [x] `skills/obsidian-cli/SKILL.md` — v1.3 bump + prose update in "Active-note resolution"
      (no changelog comment block per operator preference — removed the pre-existing one too).
- [x] `tests/.AGENTS.md` — TASK 060 follow-up note on the test surface.

## 3. Acceptance

- `obsidian-active-note focused` / `folder` resolve a genuinely-open `.base` file instead of
  exiting `EXIT_NO_ACTIVE_FILE` (verified via unit test against a fixture, since this
  environment has no live Obsidian+Bases to dogfood against synchronously).
- No regression to the existing all-markdown eval/test paths (E-09/E-10/E-13/E-15 style
  never-relax evals stay green).
- No new dependencies; no architecture change — this is a resolver-internals fix, ADR-008's
  confidence-gating contract (HIGH/MEDIUM/LOW) is unchanged, only the *set of resolvable file
  types* widens.

## 4. Completion

Shipped. Root cause confirmed live against the operator's real vault (`obsidian vault=…
tabs`/`file`/`recents`) rather than guessed: a focused `.base` file shows as `[bases] <title>`
in `tabs`, and `obsidian file` (bare) still reports `Error: No active file` for it — Obsidian's
own active-file pointer doesn't recognize a Bases view, which is exactly why the wrapper's
`recent-open` fallback (not the primary `active` path) is how a focused Base ever resolves.
Fixed by widening the *orientation* paths (`focused`/`recent-open`/`folder`) to any open file
via an exclude-list of known UI chrome, while deliberately leaving the descriptor `match`
HIGH path (feeds note-editing) markdown-only — its wikilink-style `file=<title>` resolve
doesn't work for non-markdown files by bare title (live-verified). Full test suite green
(2251 passed, 5 skipped), `mypy --strict scripts/` clean (script lives outside that tree but
was mypy-checked directly too, clean). No architecture change; ADR-008's confidence-gating
contract is unchanged.
