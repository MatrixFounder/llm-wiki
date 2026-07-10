# 057-07 — [W2-1][W2-4] prepare no-`--folder` flow: inference → proposal/unresolved + staging

**Goal:** `prepare` without `--folder` never guesses and never writes into the vault: it emits
`folder_proposed` (exit 0) or `FOLDER_UNRESOLVED` (exit 2) with ranked candidates, always with
a `staged_path` making the confirmed re-run fetch-free.

**Context (read):** `__init__.py::prepare` (:192 — folder validation at :203 currently BEFORE
fetch; `_imgtmp` lifecycle :250; kind detection :386); `_fetch.py::ensure_source_frontmatter`
(:203) + `_fm_safe` (:197); ARCHITECTURE §2.3.5 "No-write + staging" + Q-057-1/3.

**Steps:**
1. Parser: prepare `--folder` → `required=False, default=None` (help text: omitted → inference
   + proposal, nothing written). `apply --folder` stays required.
2. `prepare()`: when `args.folder` is set → EXACTLY today's flow (validation before fetch).
   When None → skip folder validation; run `dispatch_fetch` as today (announcement
   short-circuit from 057-04 still applies); then:
   a. Stage: `_stage_capture(result, source) -> Path` — `tempfile.mkstemp(prefix=
      "wiki-import-staged-", suffix=".md")`; content = `result.raw_text` with frontmatter
      stamped via `ensure_source_frontmatter` + NEW `_stamp_metadata(md, title, author, date)`
      (each scalar through `_fm_safe`, quoted; only fills missing keys — H-6).
   b. Reclaim `_imgtmp` (attachments are NOT staged — Q-057-3 residual).
   c. Kind: run the same `--kind auto` detection as today (report-only).
   d. Inference: `inf = infer_folder(repo, vault, result.title, source_subdir=
      layout.write.source_subdir)`; if `inf.folder is None`: `hint = active_note_folder
      (vault_root)` → basis "active-note", confidence "medium" when it lands.
   e. Emit: resolved → exit 0 `{action: "folder_proposed", vault_id, source, title, kind,
      kind_confidence, folder_inferred, basis, confidence, evidence, candidates, staged_path,
      hint: "confirm/override, then re-run prepare --folder <F> --source <staged_path>
      (fetch-free) or --source <original URL> (re-downloads images)"}`;
      unresolved → exit 2 `{error: "FOLDER_UNRESOLVED", message, candidates, staged_path,
      title, kind}`.
   f. The repo handle for (d) closes in a finally (same discipline as the known_concepts
      block).
3. No `_raw`, no `_attachments`, no `known_concepts`/`existing_page_slugs` on either no-folder
   path (the confirmed re-run provides them).

**Tests** (`tests/test_import_folder_inference.py` + prepare-facade style monkeypatching
`wia.dispatch_fetch` and `_folder.infer_folder`/`active_note_folder`):
- proposal path: envelope fields + exit 0; vault rglob snapshot unchanged; staged file exists
  OUTSIDE vault, frontmatter has source/title/date (hostile title with `"` + newline is
  neutralized — H-6).
- unresolved path: exit 2 + candidates + staged_path; vault unchanged.
- active-note fallback engages only when series inference is inconclusive.
- fetch-free re-run: `prepare --folder F --source <staged_path>` with dispatch_fetch
  UN-monkeypatched (local-md path) → `prepared` envelope keeps title/date; `_raw` written
  under F.
- `--folder` given → legacy path byte-identical (existing prepare tests green unmodified).

**Verification:** `pytest tests/test_import_folder_inference.py
tests/test_import_article_prepare.py -q`; `mypy --strict scripts/`.
