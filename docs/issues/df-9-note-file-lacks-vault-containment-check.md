---
id: DF-9
type: known-issue
status: fixed
opened_at: 2026-07-08
resolved_at: 2026-07-08
resolved_by: TASK 053 (R4)
category: security
slug: df-9-note-file-lacks-vault-containment-check
---

# `wiki-import apply --note-file` accepts an absolute path outside `--vault-root`; the sibling `wiki-extract-concepts apply --candidates-file` refuses one

> **Resolution (TASK 053 / R4, fixed 2026-07-08 — as a DELIBERATE divergence).**
> The DF's fix option (a) (add containment to `--note-file`) was **rejected**: the
> note JSON is ephemeral orchestrator scratch (the primary channel is
> `--note-stdin`, and `--note-file` routinely points at a scratchpad tmpfile
> OUTSIDE the vault), so `is_relative_to(vault_root)` would break the documented
> flow — and the existing tests wouldn't catch it (they keep note.json inside
> vault_root). Adopted option (b): documented the asymmetry as intentional at both
> sites (the `--note-file` argparse help + a `_load_note_json` comment; a symmetric
> note by `--candidates-file` in `_sourcing.py`). Added the safe subset of
> hardening that does NOT require containment — a symlink refusal (REFUSED_SYMLINK,
> R-26 posture). Regressions: `tests/test_import_article_apply.py::
> test_apply_note_file_outside_vault_root_succeeds` (locks the divergence in) and
> `::test_apply_note_file_symlink_refused`.

- **Symptom**: `wiki-import apply --note-file /private/tmp/.../note.json` (an absolute path
  well outside the target vault) succeeded with no complaint and no containment check. The
  same session's `wiki-extract-concepts apply --candidates-file /private/tmp/.../
  candidates.json` — structurally the same "read an operator/orchestrator-authored JSON
  payload from a path" operation, one step later in the same pipeline — was **refused**:
  `{"error": "INVALID_CANDIDATES_PATH", "reason": "... is missing or outside --vault-root"}`
  (had to switch to `--candidates-stdin` to proceed).
- **Root cause**: `wiki_import_article/__init__.py`'s note-loading branch
  (`elif args.note_file: nf = Path(args.note_file); ... raw = nf.read_text(...)`, around
  line 491) does a size check but **no** `is_relative_to(vault_root)` containment check.
  Compare `wiki_extract_concepts`'s `--candidates-file` handling, which explicitly resolves
  and validates containment before reading (`INVALID_CANDIDATES_PATH`) — the pattern this
  repo already uses elsewhere (e.g. the `_raw` target-folder containment check at
  `wiki_import_article/__init__.py:424`, `d.resolve().is_relative_to(vault_root.resolve())`).
- **Impact**: low in the current single-operator local-CLI usage model (this is the
  orchestrating agent's own scratch file, not attacker-controlled input) — but it's an
  inconsistency between two CLIs in the same construct-import family that otherwise share a
  fairly careful containment/CWE-117/209 discipline everywhere else in this codebase. If
  `--note-file` is ever driven by a less-trusted caller (a batch/cron path, a different
  orchestrator), the asymmetry becomes a real path-disclosure/arbitrary-file-read surface
  (any file the process can read gets ingested verbatim as the note body).
- **Fix**: either (a) add the same containment check `wiki-extract-concepts apply
  --candidates-file` already does to `wiki-import apply --note-file` for defense-in-depth
  consistency, or (b) if `--note-file` is intentionally meant to accept an orchestrator
  scratch path outside the vault (arguably reasonable — the note JSON is ephemeral
  scaffolding, not vault content), document that divergence explicitly next to both flags so
  it reads as a deliberate choice rather than an oversight, and consider whether
  `--candidates-file`'s restriction is actually the odd one out and should be relaxed to
  match instead.
