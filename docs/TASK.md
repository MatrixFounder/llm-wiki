# TASK 030 — reindex-perf-hardening: rename-aware `--delta` (DF-029-1) + chunked-tx `--full` (P-1) + single-pass pruned walk (R-X1-OBS-WALK)

## 0. Meta
- **Task ID:** 030 · **Slug:** `task-030-reindex-perf-hardening`
- **Mode:** VDD (full pipeline). Code task (Python under `scripts/`), Stub-First,
  green-throughout, mypy `--strict`.
- **Source:** operator request 2026-06-12 — "проработай качественно DF-029-1, P-1 (OPEN),
  R-X1-OBS-WALK"; Class-A sources
  `docs/issues/{df-029-1-reindex-delta-misses-mtime-preserved-rename,
  p-1-reindex-full-per-page-transactions,r-x1-obsidian-multiglob-rewalk}.md`;
  ROADMAP P2 table (P-1 row).
- **Review status:** v3 — two adversarial gates folded in: (1) the 3-perspective
  task review (fact-check / req-quality / arch-consistency — 2 HIGH predicate
  holes, 3 HIGH arch conflicts); (2) the arch+plan gate (arch-review /
  plan-review / spec-validator — A6 non-convergence HIGH, chunk lock-hold HIGH,
  symlink+overlap alive-set HIGH, AC-4.1 multiline-grep HIGH, RecursionError
  MED). See `docs/reviews/task-030-review.md`.
- **Precedent:** TASK 017 bundled P-2 + P-3 + R-X1-REDOS-RT as one bounded hardening
  task — same shape: three orthogonal indexer issues, one cycle, shared regression
  surface (`reindex.py` + `layout_config.py`). **Ship-separability:** R-030-3/6 (the
  walk rewrite — the riskiest piece) is independent of R-030-1/2 and can be dropped
  mid-cycle without stranding them; R-030-1 and R-030-2 are mutually independent.
- **YAGNI-gate note:** §3.5 pinned the walk rewrite "YAGNI-gated, not built now"
  with trigger "a real obsidian-personal vault exceeds ~2k files". This task is an
  **explicit operator override of that gate** (operator request, on record) — the
  synthetic ≥2k fixture in AC-3.4 is the measurement rig, NOT the gate trigger.
- **Constraints (binding, inherited):**
  - **Zero DDL** — `PRAGMA user_version` stays **5**; no new tables/columns/indexes/
    triggers, **no runtime DDL** (incl. no trigger drop/recreate — see F-5).
  - **No new deps**; no `import anthropic` (grep-guarded).
  - **Karpathy byte-identity** — golden anchor (`tests/test_karpathy_byte_identity.py`
    GOLDEN_DISCOVER/PAGES/REFS) green bead-by-bead (ADR-002 §D8 L295-300), **including
    the §3.5 walk-scoping property: "for Karpathy-shaped layouts the root tree is
    never walked"** (`system-architecture.md:523-526`) — preserved via R-030-6.
  - **M-4 contract** — `INSERT … ON CONFLICT(vault_id, slug, project) DO UPDATE`,
    never `INSERT OR REPLACE`. Untouched.
  - **M-1 / delta-symmetry** — exactly ONE `replace_refs` per page per run; derivation
    changes apply to full AND delta via the shared `derive_indexed_page` (TASK 024 R-1).
  - **Measured, not projected** (§8.4 / P-5 lesson) — every perf claim is a
    `scripts/benchmark.py` before/after delta at `--n 1000` (and `--n 10000` where
    feasible), recorded in `docs/architectures/scalability-and-performance.md`.
  - **P-2 preserved** — one `stat()` per file; delta consumes `DiscoveredPage.mtime`
    (double-stat detector `tests/test_task017_hardening.py:225-262` stays green).

## 1. Verified recon facts (2026-06-12; line numbers at HEAD, re-verified by the fact-check reviewer)

| # | Fact | Consequence |
|---|------|-------------|
| F-1 | The delta skip point is `reindex.py:429-430` — `if mtime <= cutoff: continue`. A rename/move preserves `st_mtime`, so the NEW path is walked but never ingested; if the derived `(slug, project)` changed, the OLD row is then deleted by the orphan pass (`:458-461`) → the page vanishes; if unchanged, the row survives with a stale `file_path`. | DF-029-1 root cause; both sub-cases covered by tests. |
| F-2 | At the skip point ALL detection inputs already exist: `paths_on_disk` (`:391`), `db_pages = SELECT slug, project, file_path` (`:403-406`, TASK-021 coalesced read), `on_disk_keys` (`:392`), `untouched_rels` (`:407-410`). The rel-path string convention is `str(path.relative_to(vault_root))` (as established at `:407-413`) — the new check MUST reuse it verbatim (no `as_posix()` divergence). | The rename fix is a set-membership check, **zero extra I/O**. The seeding comment at `reindex.py:396` ("NOT re-walked this batch (mtime <= cutoff)") becomes stale wording under R-030-1 → listed in files-to-touch. |
| F-3 | `upsert_page` (`sqlite_repository.py:234-281`) and `replace_refs` (`:361-403`) each own `BEGIN IMMEDIATE`/`COMMIT` — 2 commits per page; nesting under an outer BEGIN raises `OperationalError`. Connection is `isolation_level=None` (autocommit, `:100`). | P-1 root cause; the bulk path needs txn-free private DML helpers, not API churn. |
| F-4 | The caller-owned-txn shape already exists in-tree: delta's orphan-delete block (`reindex.py:456-465`) wraps txn-free `delete_page` in one `BEGIN IMMEDIATE`; full's Step-1 wipe (`:534-541`) likewise. The chunk contingency is pre-named at `reindex.py:543-546`. | The refactor follows an established in-repo pattern. |
| F-5 | `pages_fts` is **internal-content** FTS5 (`sql/wiki-index-v2.sql:358-369`). The P-1 issue's "drop+rebuild triggers + bulk INSERT into pages_fts at end" IS mechanically workable for internal-content FTS5 (`INSERT INTO pages_fts(rowid,…) SELECT id,… FROM pages`), but is **rejected for recorded reasons**: it requires runtime DDL (against the zero-DDL posture); a crash in the triggers-dropped window leaves permanent silent FTS desync (violates NFR §5 Integrity); `pages_fts` is shared across vaults — dropping triggers affects concurrent operations on OTHER vaults. Trigger DML inside one outer tx is cheap; the real win is collapsing ~2N WAL commits into ~N/K. | Triggers stay; chunked commits are the mechanism. The refuted "trigger drop" text in the issue file Fix-plan line AND `docs/ROADMAP.md:608` ("temporary FTS5 trigger drop") must be amended at close (UC-30-4). |
| F-6 | `upsert_page`'s per-call hash pre-SELECT (`:238-244`) is N wasted SELECTs in a full rebuild **except** in one corner: a within-batch `(slug,project)` collision where both files are byte-identical — there the second file's pre-SELECT hits "unchanged" and the FIRST file's `file_path` survives, which **misreports** vs the `slug_collisions` record (`kept` = later file, `reindex.py:59-67`). The bulk path (pre-SELECT skipped → ON CONFLICT fires) makes the LAST file's `file_path` win — **aligning the DB with the TASK-021 `kept` record** (correctness-positive, deliberate, tested). | Bulk full-rebuild path skips outcome bookkeeping; the equal-hash collision corner is an explicit, tested behavior delta (AC-2.6), excluded from the row-parity corpus. |
| F-7 | `iter_pages` (`layout_config.py:624-677`) runs one `Path.glob` per `paths[]` entry; obsidian-personal (7 entries) scandirs the vault root 4× and every `NN - <Area>/` dir 2×. `ignore[]` filters per-candidate AFTER traversal (`:654`) — saves stats, not directory I/O. For Karpathy-shaped layouts the current per-glob walk **never touches the root tree** (subdir-anchored globs) — a property §3.5 documents and `karpathy.yaml`'s `ignore: []` comment relies on. | The single-pass walk MUST carry a **pattern-prefix descent predicate** (R-030-6), else it would newly traverse `.obsidian/`/`.git/`/attachment trees on karpathy vaults — a regression on the golden layout. |
| F-8 | First-match-wins dedup = `seen: set[Path]` (`:638,:644,:665`); exactly one overlapping-file case exists in the built-ins (root `NN - Area.md` matches obsidian-personal entries 6 AND 7). **No test pins this** (confirmed: no fixture file matches two globs). | Test gap closed FIRST (red→green): overlap fixture pinning declared-order attribution. |
| F-9 | Pinned walk invariants: output sorted by vault-rel POSIX path (`:676`); filter order ext→SYSTEM_FILES→autoindex/ignore→single-stat (`:644-663`); `paths_operator_supplied` threaded into `_derive_project` (`:669`); karpathy golden set+order. `derive_discovered_page` (`:705-749`) already does per-file ordered `full_match` attribution — the walk converges onto the same matcher (upsert↔reindex parity, TASK 024). | Conformance checklist (a)–(e) for the rewrite. |
| F-10 | Python 3.14 `Path.glob` symlink semantics (**empirically confirmed**): `**` does NOT descend symlinked dirs; a non-`**` wildcard component CAN match+descend a symlinked dir; leaf file symlinks are discovered (stat follows). In-vault symlinks are deliberately tolerated by `assert_no_symlink_escape` (TC-UNIT-02, `tests/test_security.py:71-90`). | The walk must **reproduce these semantics exactly** (Q-030-2 v2) — a blanket no-descend would silently orphan-delete previously-indexed rows (e.g. a symlinked `01 - Projects/` area). |
| F-11 | SLO infra: `scripts/benchmark.py` `SLOS` dict (`:34-41`; full @10k < 180 s, delta-noop @10k < 2 s), `--enforce-slos` (`:310`/`:318`), default `--n 100` (`:305`); **no CI exists in the repo** (no `.github/`); P-4 open. | P-1's "wired into CI" gate is unsatisfiable as written → Q-030-1. |
| F-12 | The `--full`-for-rename guidance lives on **TEN live surfaces** (plan-review found the tenth): `docs/issues/df-029-1-*.md`, `docs/ARCHITECTURE.md` §2.2 (the coherence-invariant block), `docs/ROADMAP.md:314,608`, `skills/obsidian-cli/` (SKILL.md:79-83 + recipes + eval E-07; `command-reference.md` carries only tier rows — verify-only), `README.md:421`, `templates/CLAUDE.md.tmpl:295`, `templates/CLAUDE.layout.md.tmpl:152`, `docs/manuals/obsidian-llm-wiki_manual.md:616`, `docs/manuals/obsidian-llm-wiki_manual.ru.md:626-627`, **`CLAUDE.md:387-388`** (the TASK-029 narrative — LIVE per-session agent instructions, wraps across lines so a line-based grep misses it; gets a superseded-by-TASK-030 annotation). Plus two stale-after-this-task design texts: `karpathy.yaml`'s walk comment (R-030-6 keeps it true — verify wording) and `functional-architecture.md:212-219` (single-tx claim already false at HEAD — F-3). | UC-30-4 enumerates ALL; AC-4.1 uses **multiline** matching (`rg -iU`) repo-wide with a defined adjudication allowlist. |
| F-13 | Delta cutoff = `MAX(log_events.event_ts)` else `vaults.registered_at` (`reindex.py:385-390`). | With R-030-1, the first `--delta` after registration ingests the whole vault (was: only files newer than registration). Correctness-positive; documented (Q-030-3). |
| F-14 | `pages` carries `UNIQUE(vault_id, file_path)` (`sql/wiki-index-v2.sql:176`). Delta's per-file catch list (`reindex.py:445-448`) does NOT include `sqlite3.IntegrityError` — a stale row holding the rename destination under a different `(slug,project)`, or an old path re-created by a new file deriving a different slug, would crash the whole delta run today. | R-030-1 widens the per-file catch to `sqlite3.Error` → `skipped` (TASK-015 per-entry precedent), with order-independence tests. |

## 2. Goal

Make the indexer correct under mtime-preserving renames **to previously-unindexed
paths** (the DF-029-1 class, incl. `cp -p`/archive/sync-client imports), fast at
scale (chunked-commit full rebuild), and walk-cost-independent of layout glob
overlap (single-pass pruned walk) — zero DDL, no new deps, Karpathy golden anchor
intact. The path-present-but-content-moved class (swap/rotation/overwrite renames)
is explicitly OUT of the detection predicate's reach — documented residual,
detectable by `wiki-lint`'s hash-drift check, remedy `--full` (see UC-30-1 A5).

## 3. Use cases

### UC-30-1 — Rename/move absorbed by a plain `--delta` (MODIFIED: `wiki-reindex --delta`)
- **Actors:** operator / any LLM agent (obsidian-cli skill), `wiki-reindex --delta`.
- **Precondition:** registered, indexed vault; a note with ≥1 inbound wikilink is
  renamed/moved app-side (`obsidian rename`) or via `mv` — mtime preserved; its
  link-rewritten neighbours have fresh mtimes; **the destination path is not
  currently held by any `pages.file_path` row**.
- **Main:** 1) `wiki-reindex --delta`; 2) walk lists the new path; 3) delta detects
  the rel (string convention per F-2) absent from the vault's `pages.file_path`
  set → ingests despite `mtime <= cutoff`; 4) neighbours re-ingest as today;
  5) orphan pass deletes the old row iff `(slug, project)` changed; 6) `wiki-lint`
  → `orphan-link: 0, missing-in-db: 0`.
- **Alternatives:**
  - **A1 — same-`(slug,project)` move** (dir move, stem unchanged): upsert updates
    the row in place; `file_path` refreshed (the old path's row IS this row).
  - **A2 — collision with a prior-batch row:** TASK-021 cross-batch
    `slug_collisions` record fires (kept = renamed file). Invariant stated and
    pinned: **`seen_keys`-seeded rows ∩ ingest batch = ∅** (a seeded row's
    `file_path` is in the DB set by definition, hence never "new-to-DB"); composite
    test = mtime-preserved rename + collision in one batch.
  - **A3 — new file imported with an old mtime** (`cp -p`, archive extraction,
    sync client): same mechanism — the fix covers the stale-mtime
    **new-path** class.
  - **A4 — old path re-created by a NEW file in the same batch** (and the stale-DB
    cross-row case): if the new file derives a different `(slug,project)` while a
    row still holds that `file_path`, the upsert raises `IntegrityError` on
    `UNIQUE(vault_id, file_path)` — caught **per-file** (`sqlite3.Error` →
    `skipped`, run continues), order-independent (both walk orders tested), one
    WARN.
  - **A5 — RESIDUAL (documented, out of predicate reach): swap/rotation/
    overwrite-rename** — every on-disk path remains present in `pages.file_path` →
    not detected; rows go content-stale. NOT a regression vs today; detectable by
    `wiki-lint`'s always-hash drift check; remedy `wiki-reindex --full`. Recorded
    in the DF-029-1 issue resolution note + §2.2.
  - **A6 — case-only rename (APFS) / NFC↔NFD / path-only move with unchanged
    content (v2, arch-review HIGH-1):** membership is a byte-level string test; a
    divergent path reads as "new" → re-ingest hits the `upsert_page` hash
    short-circuit ("unchanged") — which **returns BEFORE the UPDATE**, so
    `file_path` would stay stale and every future delta would re-detect the file
    (a non-convergent loop, not a wave). **Mechanism:** when `is_new_path` and the
    upsert outcome is `"unchanged"`, delta issues ONE targeted
    `UPDATE pages SET file_path=?, last_modified=? WHERE vault_id=? AND slug=?
    AND project=?` (zero-DDL, single statement) → exactly one re-ingest wave,
    then steady state. The same mechanism is what makes A1/AC-1.2 satisfiable
    (a path-only move with unchanged content is precisely this case). Posture:
    FS-vs-DB-of-FS self-consistent per-OS (Q-024-4); cross-OS DB relocation →
    one cheap wave. Layout note: case-only rename keeps `(slug,project)` only
    under lowercasing slug strategies (obsidian-personal `preserve-unicode`);
    under `identity` it is an ordinary rename (new slug) — tests name their layout.
  - **A7 — rename + content edit in same batch** (stale-mtime edit, `cp -p`
    scenario — the fresh-mtime case is green today): both predicates fire for one
    file → exactly ONE ingest, ONE `replace_refs` (M-1), pinned by test.
  - **A8 — persistently-failing new-path file:** a file that fails ingestion
    stays absent from `pages.file_path` → retried + re-reported in `skipped` on
    EVERY delta until fixed or removed (today: only when touched). Deliberate —
    a broken file should stay visible; cost bounded to one derivation attempt
    per run. Stated, tested. Corollary (on record): with the per-file
    `sqlite3.Error` catch, a SYSTEMIC DB failure degrades to N per-file
    `sqlite:<Type>` skips with batch status "success" — a consecutive-failure
    circuit breaker was weighed and DECLINED (TASK-015 isolation precedent;
    the `skipped` count is the operator signal).
  - **A9 — persistent duplicate-key copy (Sarcasmotron 030-01 MED, empirically
    reproduced):** a RETAINED `cp -p` copy sharing the derived `(slug,project)`
    with its original (both on disk, e.g. an in-vault backup) OSCILLATES: each
    delta re-ingests whichever path the row does not currently hold — 1 ingest +
    1 collision WARN per run, `file_path` flips, and with diverged content the
    indexed body alternates. Pre-030 this state was SILENTLY stable-wrong;
    post-030 it is NOISILY oscillating-wrong — deliberate under the TASK-020
    detection-only posture. Operator signal = the recurring `slug_collisions`
    WARN; remedy = remove/rename the copy or split keys via a per-folder
    `project`. AC-1.9 convergence is scoped to A1/A6/main-flow (single-owner
    paths), NOT to this state. Named residual alongside A5.
- **Postcondition:** **page/link** index coherent after any rename/move **to a
  previously-unindexed path** + `--delta`; `--full` no longer required for that
  class (remains the universal fallback and the swap-class remedy). Boundary
  (arch-review): `entities.file_path` registration rows refresh on `--full` only
  (pre-existing asymmetry, NOT widened here) — pinned by a concept-page e2e
  sibling test and stated in the UC-30-4 doc wording.
- **Acceptance:**
  - ✅ AC-1.1: e2e — rename with 2 inbound links → `--delta` → lint 0/0 (the 029-06
    live repro as a committed regression test).
  - ✅ AC-1.2: A1 path-only move → row count stable, `file_path` updated, refs intact.
  - ✅ AC-1.3: A2 composite (rename + cross-batch collision) → exactly one
    correctly-directed `slug_collisions` record; all TASK-021 delta tests green
    unmodified; the seeded∩ingested=∅ invariant asserted directly **at the PATH
    level** (spec correction, Sarcasmotron 030-01 MED: the original key-level
    phrasing is unsatisfiable in the A2 scenario itself — the seeded KEY is the
    ingested file's key; the by-construction disjointness is over `file_path`s).
  - ✅ AC-1.4: delta envelope gains **additive** field `new_path_ingested:
    [rel,...]` (TASK-020/021 visibility precedent; empty list on no-op); all other
    fields unchanged; no-op delta `touched == 0` unchanged. **`--all-vaults`
    aggregate (spec-validator M-1):** adds summed `new_path_ingested_total`;
    per-vault lists stay inside `results[]` (a flat cross-vault rel list would
    lose vault attribution — deliberate); `scripts/wiki_skills/wiki_reindex.py`
    added to files-to-touch.
  - ✅ AC-1.5: P-2 double-stat detector green (030-01 leg); no-op delta p95 within
    **±5%** of pre-change baseline at `--n 1000` (030-06 leg — split declared).
  - ✅ AC-1.6: A4 IntegrityError isolation — per-file skip + WARN + run completes,
    both walk orders.
  - ✅ AC-1.7: A6 — case-only rename (lowercasing layout) → ONE wave: re-ingest +
    targeted `file_path` refresh, no row churn; A7 single-ingest pin; A8
    persistent-skip retry pin.
  - ✅ AC-1.8: empty vault + fresh-vault first-delta (F-13/Q-030-3) behavior pinned.
  - ✅ AC-1.9 (**convergence, arch-review HIGH-1**): after ANY covered scenario
    (A1/A6/main flow), the SECOND `--delta` is a true no-op — `touched == 0`,
    `new_path_ingested == []`. The steady-state signal is load-bearing.

### UC-30-2 — Full rebuild commits in chunks (MODIFIED: `wiki-reindex --full`)
- **Main (v2 — stage-then-flush, arch-review HIGH-2):** 1) Step-1 wipe unchanged
  (own tx); 2) the per-page loop **STAGES** each chunk OUTSIDE any transaction —
  all file I/O (`derive_indexed_page`: read, parse, normalize, hash) fills a
  buffer of prepared `(page, refs, entity_row, alias_rows)` tuples, bounded by
  `K = 500` pages AND a byte cap (`REINDEX_TX_CHUNK_BYTES = 32 MiB` — full-body
  pages since TASK 024) — whichever fills first; 3) the chunk **FLUSHES** under
  ONE caller-owned `BEGIN IMMEDIATE`: DML-only via **private txn-free helpers**
  (`_upsert_page_in_txn`, `_replace_refs_in_txn`) + the entity/alias INSERTs →
  `COMMIT`. **The write lock is held for DML only (ms-scale), never across file
  I/O** — no writer-starvation regression on a shared `global.db` (multi-vault)
  or a cold iCloud vault (TASK 022 OQ-5); 4) public `upsert_page`/`replace_refs`
  keep own-tx semantics by delegating; 5) the bulk path skips the per-page hash
  pre-SELECT (F-6, chosen for the `kept`-alignment, not the perf — Q-030-5);
  6) Steps 2.5/3/4/5 unchanged.
- **Alternatives:**
  - A1 — derivation-time per-file error (the common class): caught during
    STAGING, OUTSIDE any tx → `skipped`; the file contributes no DML —
    **strictly better isolation than today**.
  - A2 — **mid-flush DML error** (upsert ok, refs/entity/alias raises):
    statement-level atomicity; the file's partial DML stays in the chunk and
    commits with it while the file lands in `skipped` — equivalent end-state to
    today's committed-partial; pinned by an error-path test (injection:
    monkeypatched `_replace_refs_in_txn` raising for one slug).
  - A3 — fatal mid-flush error (injection: monkeypatched `COMMIT` failure —
    the per-file catch never sees it): chunk rolls back,
    `finish_batch_run("failed")`, FTS stays in sync with `pages` (row counts
    equal) — no worse than today's documented non-atomic rebuild
    (`reindex.py:510`).
- **Postcondition:** DB rows identical to the per-page path **modulo** (i) volatile
  timestamp columns (`entities.first_seen/last_updated`, `batch_runs`) — excluded
  or clock-frozen in the parity test; (ii) the F-6 equal-hash collision corner
  (deliberate delta, AC-2.6). **Per-page commits** drop from ~2N to ~N/K + C
  (other commit sources — per-log-event `append_log_event`, step-2.5 autocommits —
  are fixture-dependent and stay; wording "per-page commits", not "commits").
- **Acceptance:**
  - ✅ AC-2.1: row-parity test — chunked rebuild == a test-local **public-DAL
    replay loop** over the same fixture (`upsert_page` + `replace_refs` per page —
    the public methods ARE the old per-page path post-030-02; no test seam in
    production code, no golden dump): pages, refs, entities, aliases, FTS hits
    equal; timestamps excluded/frozen; karpathy golden green.
  - ✅ AC-2.2: every public DAL caller unchanged (ABC signatures untouched);
    mechanical oracle: public `upsert_page` inside an externally-opened tx still
    raises `OperationalError` (own-tx semantics preserved), while the private
    helpers operate inside the open tx.
  - ✅ AC-2.3 (split declared — PLAN review step + mechanical part):
    grep-enumerated `BEGIN IMMEDIATE` call sites audited; helpers private
    (`_`-prefixed, absent from the ABC).
  - ✅ AC-2.4: commit-count assertion via `sqlite3.Connection.set_trace_callback`
    counting BOTH `BEGIN` forms + `COMMIT`: `commits == ceil(N/K) + C` on a
    **constrained fixture** (zero log.md events, fixed entity/alias counts; C's
    composition documented in-test), asserted at N<K and N%K==0 (K monkeypatched
    small); plus a lock-hold guard: no file I/O between `BEGIN IMMEDIATE` and
    `COMMIT` (staging buffer asserted full before flush).
  - ✅ AC-2.5 (split declared): measured `--n 1000` + `--n 10000` before/after in
    §8.4 + Q-030-1 gate (030-06); P-1 issue acceptance line amended (030-07).
    Full @10k p95 < 180 s with explicit headroom.
  - ✅ AC-2.6: F-6 equal-hash within-batch collision → DB `file_path` == the
    collision record's `kept` (the corrected, aligned behavior), tested.
  - ✅ AC-2.7: chunk boundaries N=0, N<K, N%K==0, and the byte-cap early flush.

### UC-30-3 — One pruned traversal per vault (MODIFIED: `iter_pages` engine)
- **Actors:** every `iter_pages` consumer (reindex full/delta, lint, render).
- **Main (v2 — alive-sets, iterative):** 1) ONE **iterative explicit-stack**
  `os.scandir` walk from `vault_root` (NOT Python-recursive — `RecursionError` on
  ~1k-deep trees is a new DoS class the replaced engine doesn't have;
  pathological-depth test required); 2) the walk threads a **per-pattern
  alive-set** down the tree: a pattern is *alive* at a dir iff its segments can
  still match below it (`**` consumes ≥0 segments; "can still consume ≥1 further
  segment" — PROPER prefix, a dir fully matching a file-glob does not descend)
  AND — symlink rule — entering a **symlinked** dir keeps a pattern alive only
  if the pattern consumes that component with an explicit (non-`**`) segment
  (exact per-entry `Path.glob` union semantics, F-10; arch/spec-review HIGH);
  **descend iff alive-set ≠ ∅** and the dir is not covered by a prunable
  `<prefix>/**`-shaped ignore glob (R-030-6); 3) per file: ext → SYSTEM_FILES →
  autoindex/ignore string-filters (order preserved, F-9); 4) **attribution =
  first match in declared order AMONG THE PATTERNS ALIVE at the containing dir**
  (not a symlink-blind global `full_match` — prevents match-set inflation AND
  attribution flips on overlap+symlink operator layouts); 5) single
  `DirEntry.stat()` into `DiscoveredPage.mtime` (P-2; symlinked leaf: `is_dir
  (follow_symlinks=True)` + `is_symlink()` gate per the alive-set rule);
  6) output sorted by rel-POSIX path (unchanged).
- **Alternatives:**
  - A1 — karpathy vault with fat `.obsidian/`/`.git/`/attachment trees: the
    alive-set (subdir-anchored globs) never enters them — the §3.5 "root tree
    never walked" property holds BY CONSTRUCTION for subtrees (instrumented
    test). Footnote: the rewrite adds exactly ONE root scandir that karpathy's
    literal-anchored globs avoid today — §3.5 wording says "root *subtrees*";
    cost covered by the AC-3.4 lean ±5% check.
  - A2 — symlinked dir reachable via `**` only: no pattern stays alive →
    not descended (today's behavior). Reachable via an explicit segment: those
    patterns stay alive → descended, and `**`-patterns are NOT alive below it →
    no match-set inflation, no attribution flip (the spec-validator H-1
    counterexample is the pinning fixture).
  - A3 — unreadable entry (`OSError`): skipped, parity with `:659-660`.
  - A4 — case-sensitivity: attribution via `full_match` is case-sensitive
    everywhere, where today's FS-glob enumeration is case-insensitive on
    APFS/NTFS for literal components. **Enumerated behavior delta** — RESOLVES
    the Q-024-residual-2 walk↔single-file parity gap; a custom layout relying on
    case-mismatched literal globs breaks consistently instead of
    platform-dependently. Documented in §3.5 + Q-024-residual-2 amended (UC-30-4).
- **Postcondition:** every directory scandir'd ≤1×; ignored/unmatchable subtrees
  0×; obsidian-personal root 1× (was 4×), `NN - Area/` 1× (was 2×). NOTE
  (parity boundary): the single-file twin `derive_discovered_page` stays
  symlink-blind (it sees one rel path, no traversal) — the pre-existing
  upsert-path asymmetry is recorded, not widened.
- **Acceptance:**
  - ✅ AC-3.1: NEW overlap-dedup test (F-8 gap): root `NN - Area.md` → exactly one
    DiscoveredPage, entry-6 attribution (`project=<Area>`, `[moc]`); written RED
    first against the current engine? — no: it must PASS on the current engine and
    the rewrite (it pins semantics, not the bug); RED-first applies to the
    traversal-count tests (AC-3.3) which fail on the per-glob engine.
  - ✅ AC-3.2: conformance (a)–(e) — sort order, first-match attribution, filter
    order, karpathy golden set+order, `paths_operator_supplied` threading — all
    existing engine/e2e/parity/security tests green unmodified.
  - ✅ AC-3.3: instrumented traversal-count tests (monkeypatched `os.scandir`
    counter): (i) obsidian-personal fixture — each dir exactly once; (ii) karpathy
    fixture with planted `.obsidian/`+`.git/` subtrees — those dirs **never**
    scandir'd (A1); (iii) `**/_raw/**`-ignored subtree under a numbered area —
    pruned (R-030-6).
  - ✅ AC-3.4: measured before/after on a synthetic PARA-shaped vault ≥2k files,
    recorded in §8.5; karpathy/dev-project full-walk within **±5%** of baseline
    (lean fixtures — BOTH sides measured at 030-06 via the git-HEAD-
    reconstructed old engine: dev-project 3.19→2.84 ms, karpathy 2.13→1.65 ms;
    the ±5% reading is ONE-SIDED — improvement always satisfies, the bound
    catches regressions; recorded per Sarcasmotron 030-06 LOW) AND strictly
    improved on the fat-fixture (A1).
  - ✅ AC-3.5: symlink parity tests (A2) on 3.14: (i) `**`-only-reachable
    symlinked dir NOT descended; (ii) explicit-segment symlinked dir descended;
    (iii) leaf symlink discovered; **(iv) overlap+symlink attribution** (the H-1
    counterexample: `Areas/**/*.md` + `Areas/*/notes/*.md`, `Areas/link`
    symlinked → file attributed to the explicit entry, as today); **(v)
    `**`-beyond-symlink subtree exclusion** (`Areas/link/other/b.md` NOT
    discovered — no match-set inflation).
  - ✅ AC-3.6: empty vault → empty result, no error.
  - ✅ AC-3.7: `wiki-sync`'s own walk untouched — owned by the 030-05 diff-review
    step (no RTM row; assigned per plan-review).
  - ✅ AC-3.8 (**amended at 030-05, Sarcasmotron MED — deviation recorded
    here, not just in the test**): the spec'd ≥1500-deep fixture is
    UNBUILDABLE on macOS (PATH_MAX 1024 B caps trees at ~330 levels). The
    explicit-stack property is pinned equivalently: a 120-deep tree walked
    under a clamped `sys.recursionlimit` — a Python-recursive walk blows,
    the explicit stack does not (discriminating, environment-honest).

### UC-30-4 — Doc/skill currency at close (NEW)
- **Main:** update in lockstep (the F-12 nine + design texts):
  1) `docs/issues/df-029-1-*.md` → `status: fixed` + resolution note naming the A5
     residual; `p-1-*.md` → `fixed` with the F-5 corrected rationale (recorded
     reasons, not the strawman) + amended acceptance line per Q-030-1;
     `r-x1-obsidian-multiglob-rewalk.md` → `fixed` (+ corrected "Prevention"
     wording — ignore-prune now real); re-render `docs/KNOWN_ISSUES.md`
     (`wiki-index-render --auto-indexes`, PW-Q clean).
  2) `docs/ARCHITECTURE.md` §2.2 coherence invariant → `--delta` suffices for
     rename/move-to-new-path (swap-class caveat + `--full` fallback); §3 summary
     line + `system-architecture.md` §3.5 walk section rewritten (single-pass
     pruned walk; YAGNI-gate wording updated as "operator-overridden, built");
     `functional-architecture.md:213-219` single-tx claim corrected (F-3);
     Q-024-residual-2 amended (A4); §8.4 perf table extended.
  3) `docs/ROADMAP.md` — R-12 wording + P2 row (P-1 mechanism text corrected,
     P-1 closed; P-4 stays open with the Q-030-1 note).
  4) `skills/obsidian-cli/` — SKILL.md coherence rule + recipes + command-reference
     → `--delta`-first for rename/move (+ `--full` universal fallback + swap
     caveat); eval E-07 expectation updated.
  5) `README.md:421`, `templates/CLAUDE.md.tmpl:295`,
     `templates/CLAUDE.layout.md.tmpl:152`, `docs/manuals/…manual.md:616`,
     `…manual.ru.md:626-627` — same rule change, vendor-agnostic wording.
  6) `karpathy.yaml` walk comment verified still-true under R-030-6 (it is — by
     construction); `reindex.py:396` seeding comment refreshed (F-2).
- **Acceptance:**
  - ✅ AC-4.1: repo-wide **multiline** grep (`rg -iU`, patterns incl. the
    wrapped-line form) finds no live `--full`-for-rename prescription. Defined
    adjudication protocol (plan-review HIGH-2): allowlist = archived records
    (`docs/tasks/`, `docs/plans/`, `docs/reviews/`, `.agent/sessions/`,
    `skills/obsidian-cli/evals/reports/` historical transcripts), test
    identifiers (e.g. `reindex_full(r, "renamev")`), and the NEW corrected
    wording itself ("`--full` universal fallback / swap-class remedy"); every
    remaining hit must be individually adjudicated in the close-out notes —
    not vibes.
  - ✅ AC-4.2: KNOWN_ISSUES ledger re-rendered, PW-Q drift guard clean.
  - ✅ AC-4.3: obsidian-cli eval — E-07 + the routing canaries re-run green
    (Q-030-4 scope; not the full 14-suite).
  - ✅ AC-4.4: `CLAUDE.md:387-388` TASK-029 narrative annotated
    (superseded-by-TASK-030); Q-030-3 fresh-vault-delta widening documented in
    §2.2 or the DF-029-1 resolution note (spec-validator L-3).

## 4. Requirements Traceability Matrix

| Req | Statement | Closes | UC | Verification |
|-----|-----------|--------|----|--------------|
| R-030-1 | `reindex_delta` ingests any on-disk page whose vault-rel path (F-2 string convention) is absent from the vault's `pages.file_path` set, regardless of mtime; zero extra I/O; targeted `file_path` refresh on the "unchanged" outcome (A6 convergence); per-file `sqlite3.Error` isolation; additive `new_path_ingested` (+ `--all-vaults` `new_path_ingested_total`); A5 swap-class residual + A8 persistent-retry documented. | DF-029-1 | UC-30-1 | AC-1.1..1.9 |
| R-030-2 | `reindex_full`'s per-page loop = stage-then-flush chunked txns (K=500 ∧ 32 MiB byte cap; lock held for DML only) via private txn-free DML helpers; public DAL semantics unchanged; bulk path skips the hash pre-SELECT with the F-6 corner as a deliberate, tested delta. | P-1 | UC-30-2 | AC-2.1..2.7 |
| R-030-3 | `iter_pages` = single-pass iterative (explicit-stack) scandir walk + per-pattern alive-set threading (symlink rule = per-entry `Path.glob` union parity) + first-match attribution among alive patterns; conformance (a)–(e); case-sensitivity delta enumerated (A4). | R-X1-OBS-WALK | UC-30-3 | AC-3.1, 3.2, 3.4, 3.5, 3.6, 3.8 |
| R-030-6 | Directory **descent predicate**: descend iff the alive-set is non-empty (PROPER-prefix rule: the pattern can still consume ≥1 further segment) AND the dir is not covered by a prunable `<prefix>/**` ignore glob — preserving the §3.5 karpathy "root subtrees never walked" property and adding real ignore-pruning. | R-X1-OBS-WALK (+ §3.5 property) | UC-30-3 | AC-3.3 |
| R-030-4 | All doc/skill/template surfaces (F-12 enumeration, ten + two design texts) updated in lockstep; issue files closed with corrected rationale. | doc-drift | UC-30-4 | AC-4.1..4.4 |
| R-030-5 | Benchmark evidence: before/after JSON for `--n 1000` + `--n 10000` (full, delta-noop) and the ≥2k PARA walk fixture; ±5% tolerances; committed to §8.4. | P-5 lesson | UC-30-1/2/3 | AC-1.5, AC-2.5, AC-3.4 |

## 5. Non-functional requirements
- **Perf SLOs (existing, must hold):** full < 20 s @1k / < 180 s @10k; delta-noop
  < 500 ms @1k / < 2 s @10k; upsert < 100 ms (`SLOS` dict = source of truth);
  regression tolerance ±5% of measured baseline p95 where no SLO headroom number
  is asserted.
- **Integrity:** rebuild stays §D8-rebuildable; FTS never desyncs from `pages`
  (triggers always in place, in-tx); no integrity-relaxed shortcuts on by default
  (D-017-B precedent).
- **Security:** no new input surfaces; symlink posture **byte-for-byte unchanged**
  (Q-030-2 v2); ReDoS posture unchanged (`_derive_project`/`guarded_search`
  reused as-is; the descent predicate runs only on layout globs already past the
  load-gate).
- **Type/test bar:** mypy `--strict`; full pytest green (1204 + new); per-bead
  Sarcasmotron + post-ship `/vdd-multi` convergence.

## 6. Out of scope
- R-X1-CFG-COST (resolve memoization) — separate issue; this task must not ADD
  resolves (and the walk rewrite must not introduce a second resolve).
- P-4 full closure (CI scale gate) — only the Q-030-1 opt-in local gate lands.
- Swap/rotation rename **detection** (UC-30-1 A5) — documented residual.
- P-9, P-11, R-X3-MF-SCAN, wiki-sync `.md`-read-twice; `wiki_query`/
  `wiki_verify_multi` direct-DAL writers keep per-call txns; `wiki_sync`'s own
  walk untouched.

## 7. Open questions (defaults binding unless operator overrides)
- **Q-030-1 (P-1 gate):** "enforce_slos at N=10k wired into CI" predates the no-CI
  reality. **Default:** opt-in `@pytest.mark.slow` + env-gated (`WIKI_BENCH_SLO=1`)
  enforcement at `--n 1000`; documented runbook line for the manual
  `--n 10000 --enforce-slos` run; one-time committed 10k measurement in §8.4.
  P-4 itself stays open.
- **Q-030-2 (walk semantics envelope):** **Default (v2, revised after review):**
  the single-pass walk reproduces `Path.glob` discovery semantics EXACTLY —
  symlink behavior per F-10 (no tightening; a blanket no-descend would silently
  delete indexed rows), filter order per F-9. The only enumerated deltas:
  (i) UC-30-3 A4 case-sensitivity of literal glob components (resolves
  Q-024-residual-2 parity); (ii) traversal cost/pruning (R-030-6) — match-set
  preserved.
- **Q-030-3 (fresh-vault `--delta`):** with R-030-1 the first `--delta` after
  registration ingests the whole vault (F-13). **Default:** accept + document —
  correct reading of "index reflects disk"; cost equals the otherwise-needed
  `--full`; visible via `new_path_ingested`.
- **Q-030-4 (skill update depth):** **Default:** update the obsidian-cli
  rename/move coherence rule to `--delta`-first (+ fallback + A5 caveat); re-run
  E-07 + routing canaries only (text delta confined to the coherence rule).
