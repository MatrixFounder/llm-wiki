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

---

