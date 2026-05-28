# 5. Interfaces

> Part of [docs/ARCHITECTURE.md](../ARCHITECTURE.md).


### 5.1. External APIs

**No exposed APIs.** Вся система — local CLI (Claude Code skills). Внешние API только потребляются:
- **Anthropic API** (Claude Haiku/Sonnet) — для `wiki-source-light`. HTTPS, JSON, key-auth via `ANTHROPIC_API_KEY` env.
- **Future** (Epic 6): Gmail-MCP (OAuth), Telegram MTProto (session keys via GramJS), Exa/Perplexity/Firecrawl MCPs.

### 5.2. Internal Interfaces

**Skill ↔ Skill**: через subprocess + stdout JSON contract. Каждый skill эмиттит:

```json
{
  "action": "added" | "updated" | "unchanged" | "skipped",
  "slug": "...",
  "details": { ... }
}
```

или error envelope:

```json
{
  "error": "ERROR_CODE",
  "message": "...",
  "file": "..."
}
```

**Skill ↔ DAL**: через Python imports. `make_repo(config)` factory.

**DAL ↔ SQLite**: через stdlib `sqlite3` module. Все queries — parameterized statements. Никакого f-string concatenation.

**Adapter ↔ External Skill (transcript)**: Subprocess. Capture stdout, проверить exit code, расковырять JSON envelope.

### 5.3. Integrations with External Systems

| System | Purpose | Protocol | Error Handling |
|---|---|---|---|
| `summarizing-meetings` skill | Generate full pyramid transcript summary | Subprocess, JSON via stdout | Exit code != 0 → fail-fast с user-friendly message |
| Anthropic API (Claude) | LLM call для `wiki-light-summary` | HTTPS POST `/v1/messages` | Rate-limit → exponential backoff (3 retries); auth error → fail-fast |
| Filesystem (markdown vault) | Source-of-truth для контента | POSIX | Atomic writes (`tempfile + os.replace`); read-only on `_raw/` |
| SQLite | Index storage | Library API | WAL retry on `database is locked`; corruption → `PRAGMA integrity_check` + restore from markdown |

---

