# TASK 063-01 — per-folder cascade resolver for `extract_decisions`

**Phase**: 0 (config surface) · **RTM**: R-063-3′(d) · **Type**: code · **Effort**: 2h
**Depends on**: 063-00 · **Unblocks**: 063-05, 063-17

## Goal

`resolve_extract_decisions(path, *, vault_root, caches) -> ExtractDecisionsConfig | None` — the
Option-A per-folder cascade, so **two engagements may use different folder names** (R-063-3′(d)) and
a partial override inherits its parent.

## Context — files

- **Edit** `scripts/wiki_skills/_resummarize.py` — the resolver + two `Caches` fields.
- **Read (precedent)** `resolve_summarize` (`_resummarize.py:145-171`) — deep-merge every ancestor's
  **RAW** block deepest-wins, **then** parse once. The RAW-then-parse order is load-bearing: it is
  what makes a folder override that sets only `dirs.risk` inherit the parent's `enabled` and
  `dirs.decision`.
- **Read** `Caches` (`_resummarize.py:60-80`) — reuse the shared `validated` per-dir read
  (PERF-046-1) so this cascade does **not** re-read `sync.yaml` a third time per directory.

## Steps

1. `Caches`: add `extract_decisions_raw: dict[Path, dict[str, Any] | None]` and
   `extract_decisions: dict[Path, ExtractDecisionsConfig | None]`.
2. `resolve_extract_decisions`: clone `resolve_summarize` verbatim in structure — iterate
   `_ancestor_dirs(path, vault_root)` (shallowest-first), source each level's block from the shared
   `_validated_dir(d, c)` read, `deep_merge` deepest-wins, `_parse_extract_decisions(merged)` once.
3. **Return `None` when NO level configures it** — *not* a default-enabled config. This is the
   difference from `resolve_summarize` (which returns `SummarizeConfig()` defaults) and it is
   deliberate: `summarize` has a live default behaviour to preserve; `extract_decisions` absent must
   mean **the rail is never auto-dispatched** (R-063-3′(c)). Note it in the docstring, because the
   asymmetry with its sibling is exactly the kind of thing a future reader "fixes".
4. Memoize on `path.parent` (resolution is a function of the parent dir).

## Tests (RED first)

`tests/test_sync_config_extract_decisions.py` (extend):
- `test_absent_at_every_level_is_none` — no block anywhere ⇒ `None`.
- `test_partial_override_inherits_parent` — root sets `{enabled: true, dirs: {decision: decisions}}`,
  zone sets `{dirs: {risk: риски}}` ⇒ resolved = `enabled: True`, `decision: decisions`,
  `risk: риски`, `requirement: requirements` (the default). **MUT:** parse-then-merge instead of
  merge-then-parse ⇒ the zone's `enabled` reverts to `False` and this test goes RED.
- `test_two_zones_resolve_different_names` — `Zone A/.wiki/sync.yaml` → `dirs.decision: decisions`;
  `Zone B/.wiki/sync.yaml` → `dirs.decision: решения` ⇒ two different resolved configs from ONE
  vault. This is R-063-3′(d) literally.
- `test_caches_read_sync_yaml_once_per_dir` — patch `_validated_dir`, resolve 3 files in one dir,
  assert 1 call (the PERF-046-1 contract survives a third cascade).

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] **GREP:** `grep -n "_ancestor_dirs\|c.validated" scripts/wiki_skills/_resummarize.py` — the new
      resolver appears in **both** populations (it uses the shared ancestor walk AND the shared
      validated-read cache). A resolver that opened its own file read would be a second, divergent
      hardening surface.
- [ ] **MUT:** delete the `caches` memo ⇒ `test_caches_read_sync_yaml_once_per_dir` goes RED.

## Rollback

Delete the resolver + the two `Caches` fields. Nothing else reads them yet.
