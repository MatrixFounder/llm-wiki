# 8. Scalability and Performance

> Part of [docs/ARCHITECTURE.md](../ARCHITECTURE.md).


### 8.1. Scaling Strategy

**Vertical only** для MVP — single-machine, single-user.

- **Корпус ≤ 100K документов**: SQLite FTS5 + WAL. Все SLOs из TASK §5.1 hold.
- **Корпус > 100K**: trigger Postgres backend (opt-in через config). См. [SQLITE-VS-POSTGRES.md §7](./SQLITE-VS-POSTGRES.md).
- **Future horizontal scaling**: multi-user — out of scope, future Epic.

### 8.2. Caching

- **No application-level cache в MVP**.
- **OS-level**: SQLite mmap (256MB) — file-content cached в page-cache.
- **WAL mode** даёт snapshot-isolation для readers без блокировок writers.

### 8.3. DB Optimization

- **Indexes**: 9 indexes на `pages` / `entities` / `page_entity_refs` (см. [SCHEMA-DRAFT.sql](./SCHEMA-DRAFT.sql)).
- **FTS5 BM25 ranking** — out-of-the-box, sub-50ms на 100K rows.
- **JSON computed columns**: `idx_pages_frontmatter` ON `json_extract(frontmatter_json, '$.tags')` — fast tag queries.
- **Partial indexes**: `idx_inter_pending` WHERE `extracted_at IS NULL` (для future LLM-extraction work-queue).
- **WAL checkpoint** — SQLite handles automatically; никаких manual `PRAGMA wal_checkpoint(...)`.

**Performance budget** — см. [TASK §5.1](./TASK.md). Verification — benchmark suite (R-14, I-5.3).

### 8.4. Maintenance-path hardening (TASK 017 — P-2, P-3, R-X1-REDOS-RT)

Scale-readiness for the operator's stated trajectory (*"1k pages soon, 10k is the wall"*).
All **zero-DDL** (`user_version` stays 5; reuses the existing `pages.last_modified`). No
blind index/algorithm changes (P-5 lesson): wins are demonstrated by `scripts/benchmark.py`
before/after deltas at `--n 1000` (and `--n 10000` where feasible), not by projection.

- **P-2 — `reindex_delta` single-stat.** The discovery walk already stats each file once
  (`is_file()`); the redundant second `path.stat()` for mtime (`reindex.py:299`) is removed
  by carrying `DiscoveredPage.mtime` from that one stat (see §3.5 "Single-stat walk"). Target:
  no-op delta well under the 500 ms (n=1000) delta SLO; one stat/file.
- **P-3 — `check_drift` fast-paths (integrity-first default).** Per operator decision
  D-017-B, the **default stays full-`sha256`** (drift is an integrity check — a preserved-
  mtime tamper must not slip). Two changes: (a) replace PyYAML `safe_load` in
  `_extract_frontmatter_type` with a regex fast-path for `^type:\s*(\S+)` + a PyYAML fallback
  for quoted/folded values (byte-identical type extraction on the corpus); (b) an **opt-in**
  `wiki-lint --mtime-skip` flag → when stored `last_modified` == disk mtime, skip the
  read+hash (still hashes on mismatch). **Measured (A/B, n=1000):** the per-file PyYAML
  `safe_load` *dominated* drift cost — the regex `type:` fast-path alone cut `wiki-lint`
  **155 ms → 34 ms (4.6×)** in the **default** always-hash mode (no `--mtime-skip` needed).
  `--mtime-skip` cuts further by also skipping the read+hash on a no-op (integrity-relaxed).
- **R-X1-REDOS-RT — per-file regex deadline** (security; see §3.5 "Runtime ReDoS deadline"
  and §7.3 A06). Operator-custom patterns run under `regex` with a per-file `timeout=`
  budget (`WIKI_REDOS_BUDGET_S`, default 2.0 s) → a catastrophic pattern on a long body
  degrades to skip-file-with-WARN instead of hanging the reindex; built-ins keep stdlib `re`
  (zero overhead).

---

