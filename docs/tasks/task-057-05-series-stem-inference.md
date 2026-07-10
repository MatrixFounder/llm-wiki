# 057-05 — [W2-2] series-stem inference (primary signal)

**Goal:** given the detected title and a seeded same-series sibling, `infer_folder` proposes
the sibling's folder with evidence; ambiguity/absence yields ranked candidates, never a guess.

**Context (read):** 057-00 scaffold; `_search.py:342 search_pages` (FTS5 `MATCH`, `vaults=`,
`limit=`) — returns `list[PageHit]` (`models.py:168`): the `Page` (`file_path` vault-relative,
`title`) is nested at `hit.page`, the score at `hit.bm25_score` (plan-review F3); ARCHITECTURE
§2.3.5 W2 step 1; layout `write.source_subdir` (`layout_config.py`).

**Steps (all in `_folder.py`):**
1. `series_stem(title)`: strip ONE trailing episode/index marker —
   `re` alternation over `\[\d+\]` / `\(\d+\)` / `#\d+` / `(?:ep(?:isode)?|part|выпуск|серия|урок|занятие)\.?\s*№?\s*\d+` /
   bare `\d{1,4}` — with surrounding `[\s\-–—:.]*` separators, case-insensitive, anchored at
   end. Result floor: ≥ 8 chars AND ≥ 2 whitespace-separated words, else None (over-merge
   guard). Title None/blank → None.
2. `folder_for_hit(file_path, source_subdir)`: vault-relative `PurePosixPath(file_path).parent`;
   machinery exclusion — any segment starting `_` or equal to `00-Vault-Index`, EXCEPT a
   trailing segment equal to `source_subdir`, → None; strip that ONE trailing `source_subdir`
   segment; empty result → `source_subdir` itself (karpathy vault-tier) or None when no subdir.
3. `infer_folder(repo, vault_id, title, *, source_subdir)`:
   - stem = `series_stem(title)`; None → unresolved (empty candidates).
   - FTS phrase: `'"' + stem.replace('"', '""') + '"'` →
     `repo.search_pages(q, vaults=[vault_id], limit=10)` — a raised `ValueError`/empty → unresolved.
   - siblings = hits where casefold+space-collapsed `hit.page.title` OR filename stem
     startswith the normalized stem, and `folder_for_hit(hit.page.file_path, ...)` is not None.
   - distinct folders: exactly 1 → `FolderInference(folder, "series-sibling", "high",
     evidence=[top 3 sibling file_paths], candidates=[folder])`; ≥ 2 → unresolved with
     candidates ranked (sibling count desc, then best bm25); 0 → unresolved empty.

**Tests** (`tests/test_import_folder_inference.py`):
- `series_stem`: `"Building AI-Native Startups [004]"` → `"Building AI-Native Startups"`;
  `"Урок 12"` → None (floor); `"Standup #42"` → None (floor: 1 word); plain title → itself
  (no marker) — and a no-marker title shorter than the floor → None.
- `folder_for_hit`: `"03 - Learning/Webinars/x.md"`, subdir "" → `"03 - Learning/Webinars"`;
  `"Lessons/AI/_sources/x.md"`, `_sources` → `"Lessons/AI"`; `"_sources/x.md"` → `"_sources"`;
  `"_concepts/x.md"` → None; `"00-Vault-Index/index.md"` → None.
- `infer_folder` with a FAKE repo (duck-typed `search_pages`):
  seeded 003 sibling in `03 - Learning/Webinars/` + 004 title → high-confidence proposal with
  the 003 path as evidence; same-stem hits across two folders → unresolved + 2 ranked
  candidates; body-only FTS match (title/filename don't start with stem) → NOT a sibling.

**Verification:** `pytest tests/test_import_folder_inference.py -q`; `mypy --strict scripts/`.
