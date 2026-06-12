# 030-01 — Rename-aware `--delta` (R-030-1, closes DF-029-1)

**RTM:** R-030-1. **UC:** UC-30-1. **Depends:** 030-00 (AC-1.5 baseline).
**Mode:** `tdd-strict` (SEV-2 correctness fix — TASK-019 precedent).

## Goal
`reindex_delta` ingests any on-disk page whose vault-rel path is absent from the
vault's `pages.file_path` set, regardless of mtime — zero extra I/O; **targeted
`file_path` refresh when the upsert short-circuits "unchanged"** (A6 convergence
— without it a moved-but-unedited file is re-detected forever); per-file
`sqlite3.Error` isolation; additive `new_path_ingested` envelope field (+
summed `new_path_ingested_total` in the `--all-vaults` aggregate).

## RED first (tests, then code)
1. **e2e repro (AC-1.1)** — the 029-06 scenario as a test: index vault → rename a
   note with 2 inbound links preserving mtime (`os.utime` back-date) → neighbours
   re-linked (fresh mtime) → `reindex_delta` → lint: `orphan-link: 0,
   missing-in-db: 0`; envelope `new_path_ingested == [<new rel>]`. RED today.
2. **A1 (AC-1.2):** same-`(slug,project)` dir-move → row count stable, `file_path`
   refreshed, refs intact. RED today.
3. **A2 composite (AC-1.3):** mtime-preserved rename INTO a `(slug,project)`
   collision with an untouched prior row → exactly ONE correctly-directed
   `slug_collisions` record; assert directly `set(seeded keys) ∩ set(ingested
   keys) == ∅`. RED today (file not ingested at all).
4. **A4 (AC-1.6):** old path re-created by a new file deriving a different slug
   while a row holds that `file_path` → `IntegrityError` caught per-file →
   `skipped` + WARN + run completes; BOTH walk orders (parametrize). RED today
   (crash).
5. **A6/A7 (AC-1.7):** case-only rename on a LOWERCASING layout
   (obsidian-personal `preserve-unicode`) → ONE wave: "unchanged" short-circuit +
   targeted `file_path` refresh, no row churn (under `identity` it's an ordinary
   rename — separate assertion); A7 = rename + STALE-mtime content edit
   (`cp -p` scenario; the fresh-mtime variant is green today) → exactly one
   ingest, one `replace_refs` (M-1).
6. **AC-1.8:** empty vault delta → no error, empty envelope; fresh-vault first
   delta ingests all (Q-030-3), `new_path_ingested` lists them.
7. **AC-1.4:** envelope no-op test asserts `new_path_ingested == []` present;
   existing delta envelope tests green UNMODIFIED; `--all-vaults` test asserts
   `new_path_ingested_total` summed (per-vault lists stay in `results[]`).
8. **AC-1.9 (convergence — arch-review HIGH-1):** after main-flow rename AND
   after A1/A6, the SECOND `--delta` is a true no-op (`touched == 0`,
   `new_path_ingested == []`). RED against a refresh-less implementation.
9. **A8:** persistently-failing new-path file (e.g. `UnmappedTypeError`) →
   re-reported in `skipped` on every delta, never crashes, never ingested.

## GREEN (implementation, minimal)
- In `reindex_delta` pre-loop: `db_file_paths = {r["file_path"] for r in db_pages}`
  (the EXISTING coalesced read — no new query). In the per-file loop replace the
  gate: `is_new_path = rel not in db_file_paths` (rel via the F-2 string
  convention, computed once and reused); `if mtime <= cutoff and not is_new_path:
  continue`; track `new_path_ingested`.
- **Refresh leg:** `if is_new_path and outcome == "unchanged":` one targeted
  `UPDATE pages SET file_path=?, last_modified=? WHERE vault_id=? AND slug=? AND
  project=?` on `repo._connect()` (zero-DDL, single statement; the in-tree
  caller-owned-DML precedent). NOT routed through `_upsert_page_in_txn` — keeps
  030-01 ⊥ 030-02 (ship-separability).
- Widen the per-file catch tuple with `sqlite3.Error` (TASK-015 precedent) → one
  WARN + `skipped` entry (no value echo — CWE-209 posture).
- Envelope: add `new_path_ingested` (sorted rel list);
  `scripts/wiki_skills/wiki_reindex.py` `--all-vaults` block adds
  `new_path_ingested_total`.
- Refresh the stale seeding comment at `reindex.py:396` (F-2).

## Acceptance
- ✅ AC-1.1..1.9 green; ALL TASK-021 delta tests + P-2 double-stat detector green
  UNMODIFIED; full suite + mypy strict green.
- ✅ No new SQL queries on the steady-state delta path (diff review; the refresh
  UPDATE fires only on the `is_new_path ∧ unchanged` corner).
- ✅ Concept-page e2e sibling: renamed `_concepts/` page → pages/refs coherent via
  `--delta`; `entities.file_path` stale until `--full` (boundary pinned, UC-30-1
  postcondition note).
- ✅ Sarcasmotron pass on the bead diff.
