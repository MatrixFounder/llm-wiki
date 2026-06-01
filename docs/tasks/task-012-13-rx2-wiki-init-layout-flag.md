# Task 012-13: R-X2.1 — `wiki-init --layout` flag (5 values)

## Use Case Connection
- UC-31: `wiki-init --layout dev-project …` bootstraps a dev-vault (precondition for 012-14/15).

## Task Goal
Expand `wiki-init`'s `--layout` to accept the five layout names and write the chosen value
into `WIKI_SCHEMA.md` so the engine resolves the matching built-in `layouts/<name>.yaml`
(single CLI surface — §10; no new top-level command).

## Changes Description

### Changes in Existing Files

#### File: `scripts/wiki_skills/wiki_init.py`
- `--layout` `choices` → `["flat", "per-project", "karpathy", "dev-project", "obsidian-personal"]`
  (default resolution stays `per-project` for back-compat — `args.layout or "per-project"`).
- The chosen `layout:` flows into the `WIKI_SCHEMA.md` template substitution (already wired)
  and into `vaults.config_json` at registration (already wired) — verify both carry the new
  values unchanged.
- For `dev-project` / `obsidian-personal`, **do not scaffold the Karpathy `SCAFFOLD_DIRS`**
  (those are `_sources/_concepts/…` — wrong for a dev-vault/personal vault). Either skip
  scaffolding for non-Karpathy layouts (register-only) or scaffold a layout-appropriate
  minimal set. `--register-existing` is the natural path for dev/obsidian vaults (the `docs/`
  tree already exists) — ensure `--scaffold-new` for those layouts does not create stray
  `_sources/` dirs in a real repo.

#### File: `templates/WIKI_SCHEMA.md.tmpl`
- Confirm `layout: ${layout}` passes the new values through verbatim (no enum hardcode).

### Changes in Test Files
#### File: `tests/test_wiki_init_layouts.py` (NEW)
- `wiki-init --register-existing --layout dev-project --vault <tmp-with-WIKI_SCHEMA>` → the
  vault registers; `load_config(<vault>)` + `load_layout_config` resolve `dev-project.yaml`.
- `--scaffold-new --layout dev-project` does NOT create Karpathy `_sources/`/`_concepts/`
  dirs in the target (no stray scaffolding).
- All five `--layout` values accepted; existing `flat`/`per-project` tests pass unchanged.

## Acceptance Criteria
- ✅ All 5 layout values accepted; `WIKI_SCHEMA.md` carries the chosen `layout:`.
- ✅ Engine resolves the matching built-in; no stray Karpathy scaffolding for dev/obsidian.
- ✅ Existing `wiki-init` tests pass; `mypy --strict` clean; suite green.

## Stub-First
Phase 1: add the choices (default unchanged) → existing tests green. Phase 2: the
non-Karpathy scaffolding guard + the dev-project resolution test (RED-first).
