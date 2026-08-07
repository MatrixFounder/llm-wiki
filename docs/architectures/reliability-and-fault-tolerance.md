# 9. Reliability and Fault Tolerance

> Part of [docs/ARCHITECTURE.md](../ARCHITECTURE.md).


### 9.1. Error Handling

- **Fail-fast philosophy**: invalid input/config → immediate non-zero exit с structured error envelope.
- **No silent corruption**: каждый failure path emits:
  ```json
  {"error": "ERROR_CODE", "message": "...", "context": {...}}
  ```
- **Atomic writes** для всех state-mutation: `tempfile.NamedTemporaryFile + os.replace` (POSIX-atomic).
- **SQLite locked** retry: 3 attempts с 50ms backoff. На 4-й — fail-fast.
- **Subprocess errors** (`wiki-source-transcript` → `summarizing-meetings`): non-zero exit code → log + fail-fast workflow.
- ~~**API rate-limits** (`wiki-source-light` → Anthropic): exponential backoff (1s, 2s, 4s) up to 3 retries.~~ ⚠️ **МЕХАНИЗМА НЕТ (исправлено 2026-08-06, TASK 072)** — `wiki-source-light` никогда не отгружался, и под Decision-17 `scripts/` не вызывает LLM-провайдера. Никакого backoff'а по этому пути не существует. Retry-поведение внешних `html`/`pdf` subprocess'ов принадлежит им, а не этому дереву.

### 9.2. Backup

- **Markdown vault**: пользователь должен иметь git/iCloud backup. Скиллы не делают.
- **SQLite**: derivative, rebuildable из markdown. Backup — file copy `<db>.db` + `<db>.db-wal` (atomic при `journal_mode=WAL`). Restore — replace files. Если corrupt → `PRAGMA integrity_check` + если bad → drop + `wiki-reindex --full`.

### 9.3. Monitoring and Alerting

- **Local-only.** Никаких внешних monitoring tools.
- **Metrics на `batch_runs`**: last reindex time, errors, items processed.
- **SessionStart hook** (опц., в Claude Code): warn если last `batch_runs` > 24h.
- **Lint health**: `wiki-lint --strict` weekly cron — emits report; пользователь reviews.

---

