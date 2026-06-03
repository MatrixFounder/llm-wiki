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


## 7.5. Sync Dispatcher (`wiki-sync`, TASK 018 / R-11)

`wiki-sync` widens the *input surface* (it discovers heterogeneous files and drives
conversion), so its security posture is explicit:

- **Path-traversal (SEC-A3/A6 refinement):** discovered paths are validated inside
  the vault; the symlink refusal covers both the **target file AND its directories**
  (`O_NOFOLLOW`, not just the leaf). The converted markdown is written atomically
  (`tempfile + os.replace`) inside the vault — note `validate_inside_vault(strict=True)`
  cannot resolve a *not-yet-existing* target, so the containment guard is on the
  **existing `_raw/` parent dir** (+ symlink refusal), not the unborn target path.
- **Staging-name collision (SEC-A4/EC-5; + RG-5/SEC-N1):** the staged target is the
  **collision-safe** `_raw/.staging/<slug(stem)>-<ext>.md` — in the **non-walked**
  `.staging/` subdir (so it is never re-ingested, RG-1/W-3) and disambiguated by
  extension (same-stem `.docx`/`.pdf` never share a target). Before writing, if a
  target exists with **different** content the executor **refuses to overwrite** and
  emits a `staging-collision` reason — never a silent `os.replace`. (Modelled on
  `register_summary`'s refuse-overwrite posture, which refuses on *existence* absent
  `--force`; here refined to compare **content** so an identical re-stage is
  idempotent.) Planning must define the **empty-slug fallback** (a punctuation-/
  whitespace-only stem slugifies to `''`): substitute a path-derived disambiguator
  `_raw/.staging/sync-<sha8(vault-relative-source-path)>-<ext>.md` (SEC-N1).
- **Untrusted content (H-6 — binding; SEC-A1 fix):** raw sources and converted
  markdown are **data, not instructions**. The deterministic `scan` never interprets
  file *content* as directives. ⚠️ The **first** LLM stage on the ingest chain is
  `summarizing-meetings`, which has **no** built-in H-6 banner (the existing banners
  are on the second-stage `wiki-extract-concepts`/`wiki-query` only) — so the executor
  MUST fence each raw/converted body with a sentinel **before** `summarizing-meetings`,
  not only at the extractor. File content is **never executed**.
- **Resource bounds + YAML anchor-bomb (SEC-A5 corrected — SEC-N3, the binding fix):**
  binaries are skipped by extension *before* any read; text/converted reads are
  size-bounded. ⚠️ **`yaml.safe_load` does NOT defang a billion-laughs/anchor-bomb** —
  it only blocks arbitrary-object construction (`!!python/object`), and **still
  expands aliases/anchors** (a 232-byte bomb expands to ~531 k nodes; a sub-256 KiB
  bomb reaches 10⁸). So the `.wiki/sync.yaml` defense is: (1) a **256 KiB input
  size-cap** (`stat().st_size` before read) — necessary but **not sufficient alone**;
  (2) **forbid YAML anchors/aliases entirely** via a custom `SafeLoader` subclass that
  raises on an anchor/alias node (the sync config is a flat dict of glob strings —
  anchors have no legitimate use), which is the actual anchor-bomb bound. One
  oversize/unconvertible/`needs-ocr`/`unmappable-type` file is flagged, never crashes
  the batch (per-file isolation).
- **Config injection:** `.wiki/sync.yaml` is strict-schema-validated against
  `config/sync-config.schema.yaml` (a misspelled key is a load error, not a silent
  skip); `zones`/`exclude` are **path globs**, not regexes — no
  operator-supplied-regex ReDoS surface is introduced (unlike the layout engine's
  `ref_extraction`/`project_pattern`, which keep their TASK-012/017 ReDoS guards).
- **Concurrency (META-2 specified — SEC-N4):** the executor takes a **per-vault
  advisory `flock` on `<vault>/.wiki/sync.lock`** with **`LOCK_EX | LOCK_NB`** — if
  already held, `wiki-sync` exits `2` `SYNC_IN_PROGRESS` (it does **not** block for
  the multi-minute run). The lock is held on an open fd for the executor's lifetime
  and auto-released on process exit (no stale-file recovery needed — `flock` is
  fd-scoped, unlike the short-lived per-append `wiki-append-log` lock, which is a
  *different* profile and is **not** cited as the precedent for lifetime). It guards
  `wiki-sync` runs **against each other only**; unrelated writers (`wiki-append-log`,
  `wiki-query`) take their own short locks and are unaffected (they never acquire
  `sync.lock`). Operator edits *during* a run remain the documented single-actor
  precondition (a file changed mid-walk is detected by the next run's hash).
- **No new authZ surface:** single-user, file-permission trust scope unchanged;
  `wiki-sync` adds no network or credential surface (no `import anthropic`).

---
