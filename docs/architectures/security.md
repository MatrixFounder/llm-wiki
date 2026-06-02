# 7. Security

> Part of [docs/ARCHITECTURE.md](../ARCHITECTURE.md).


### 7.1. Authentication and Authorization

**Single-user personal tool. No auth.**

- Skills исполняются под user-account, читают/пишут within vault permissions.
- `ANTHROPIC_API_KEY` хранится в `~/.config/wiki-mcp/keys.env` (env file, **никогда** не commit'ится; `.gitignore`).
- Future Epic 6: Gmail OAuth + Telegram MTProto session keys тоже в `~/.config/wiki-mcp/`.

### 7.2. Data Protection

- **At rest**: Markdown в iCloud Obsidian — encrypted iCloud sync. SQLite — local FS, **не** в iCloud (R-03). No additional encryption (vault уже под user permissions).
- **In transit**: HTTPS для всех external API calls (Anthropic).
- **PII**: `wiki.research.private_concepts` + `private_tags: [confidential]` — fail-fast в research/external-share. MVP не имеет research/external-share, но schema готова.
- **Backups**: Vault уже git-versionable (рекомендация); SQLite — derivative, всегда rebuildable. **Скиллы не делают бэкапы** (per TASK §22 v2).

### 7.3. Attack Protection (OWASP-aligned)

- **A03 Injection**:
  - **SQL Injection**: все queries через parameterized statements (`?` для SQLite, `%s` для Postgres). Test: ingest файла с frontmatter `title: "'; DROP TABLE pages--"` → table остаётся.
  - **Command Injection**: `wiki-source-transcript` использует `subprocess.run([...], shell=False)` — argv list, не shell-string.
- **A01 Broken Access Control**:
  - **Path Traversal**: `wiki-source-manual` validates `os.path.realpath(source).startswith(os.path.realpath(vault_root))`. Test: `--source ../../../etc/passwd` → fail-fast.
- **A04 Insecure Design**:
  - SQLite вне iCloud (R-03) — phys-design защита от sync-corruption.
- **A05 Security Misconfiguration**:
  - JSON Schema validation для config до запуска любого skill (R-01.3).
  - Fail-fast если `wiki:` блок отсутствует в `CLAUDE.md`.
- **ReDoS / Availability (TASK 017 — R-X1-REDOS-RT)**:
  - **Threat**: an operator-custom layout regex (`ref_extraction[].regex` / `project_pattern`)
    that backtracks catastrophically on long file *content* can hang `wiki-reindex` (single-
    user DoS / stuck maintenance). Built-in layout patterns are pre-vetted.
  - **Control (defense-in-depth, two layers)**: (1) load-time `_redos_budget_check` rejects
    obviously-catastrophic operator regex at config-load (exit 6) — a short-payload heuristic;
    (2) a **runtime per-file `timeout=` deadline** via the `regex` engine on operator-custom
    patterns (`WIKI_REDOS_BUDGET_S`, default 2.0 s) → degrades to skip-file-with-WARN, never
    hangs. Verified: builtin `TimeoutError` fires at the deadline even on a 100 KB single line
    (stdlib `re` cannot be interrupted — GIL-held C call). See §3.5 "Runtime ReDoS deadline".
  - **CWE-117/209**: skip/WARN reasons name the file, never echo the offending pattern or body.
- **A06 Vulnerable & Outdated Components**: TASK 017 adds **one** runtime dependency — `regex`
  (PyPI, pinned floor `>=2024.0`) — for the control above: a single, widely-used, actively-
  maintained package, no transitive bloat; `types-regex` for the type gate. (Pre-017 the tool
  was stdlib + frontmatter/yaml/slugify/jsonschema only.)
- **A08 Software & Data Integrity**:
  - `pages.file_hash` (sha256) для change detection.
  - `vault_metadata.schema_version` для migration tracking.
- **A09 Logging Failures**:
  - `log.md` append-only с monthly rotation. Не редактируется автоматически.
- **A10 SSRF**: `wiki-source-light` отправляет только в Anthropic API (hard-coded host). Не принимает user-supplied URL.

**Out-of-scope для MVP** (per TASK):
- Multi-user RBAC.
- Audit logs beyond `log.md`.
- Encryption at rest (vault encryption — responsibility пользователя).

### 7.4. Vendoring Policy

Snapshot-based vendoring is used for the `wiki_ingest` Python module to eliminate the external PATH dependency (Decision-11). Key policy points:

**Rationale for snapshot over live link:** A snapshot copy (vs git-submodule or pip dependency) minimises install friction for end-users (target: single-step `pip install obsidian-llm-wiki`), avoids network fetches at runtime, and gives the repo a stable import surface. The trade-off is manual sync, which is bounded and operator-controlled.

**Sync strategy:** `bash scripts/sync_wiki_ingest.sh` (rsync from configurable upstream path). The script is idempotent: re-running immediately produces "no changes". Supports `--dry-run` (no mutations) and `--accept-local-divergence` (bypass hash abort for documented patches).

**Drift detection mechanism:** `VENDORED_FROM.md::file_hashes` records SHA256 content hashes of all committed `*.py` files at sync time. Pre-sync, the script recomputes hashes and aborts with a per-file diff if any hash diverges from the recorded value and is not covered by a `local_patches` entry. This mechanism works regardless of whether the operator commits between syncs and does not assume the source path is a git checkout. See §1.5.7 for full details.

**Upstream-first fix policy (Decision-12):** All bug fixes go to `Universal-skills/skills/wiki-ingest` first, then sync down. Local divergences in the vendored copy are prohibited except for documented `local_patches` (primarily `mypy --strict` type-annotation fixups — R-50). Each local patch carries a `# VENDORED-PATCH:` comment and is listed in `VENDORED_FROM.md::local_patches` so the sync script can warn before overwriting.

**Third-party notices:** Covered in `THIRD_PARTY_NOTICES.md` (R-55). Both repos are operator-owned; no open-source licensing friction today. The notices file is maintained for clean posture in anticipation of future publication (TASK 005 — PyPI).

---

