# 6. Technology Stack

> Part of [docs/ARCHITECTURE.md](../ARCHITECTURE.md).


### 6.1. Backend

- **Language**: **Python 3.11+** для всех wiki-* скиллов.
  - **Justification**: SQLite stdlib, mature ecosystem (`python-frontmatter`, `pyyaml`, `python-slugify`, `jsonschema`), CLAUDE.md `LOCAL DEVELOPMENT RULES` mandate `pip + .venv`. Python 3.11+ для `match` statements, type hints (`X | None`), and structural pattern matching.
- **Framework**: **None** (per skill-architecture-design TIER 0 «No frameworks if API is easier on lower-level libs»). `argparse` (stdlib) для CLI, `dataclasses` для models, raw `sqlite3` для DB.
- **Future TypeScript**: Future Epic 6 `wiki-source-telegram` — TS/Bun для GramJS MTProto (cybos pattern). MVP — Python only.
- **Libraries (NEW — TASK 017):** **`regex`** (PyPI, pin `>=2024.0`) — used *only* to enforce
  a per-file `timeout=` deadline on **operator-custom** layout regex (R-X1-REDOS-RT); stdlib
  `re` stays the engine for every built-in pattern. Adds **`types-regex`** (dev) for
  `mypy --strict`, consistent with the existing `types-PyYAML` / `types-jsonschema` stub
  pattern (the `regex` wheel ships **no** inline stubs — verified: no `py.typed`/`.pyi`); if
  the stubs prove inadequate, fall back to a per-module `ignore_missing_imports`. This is a
  deliberate, scoped relaxation of TASK 012's stdlib-only ReDoS posture — justified because no
  pure-stdlib mechanism can interrupt a catastrophic stdlib-`re` match (GIL-held C call;
  verified on CPython 3.14.4). **Resolves Q-017-4.**
- **Libraries (NEW — TASK 058):** **`ruamel.yaml`** (pin `>=0.18`) — comment-preserving
  round-trip YAML editing for `wiki-config` writes (`fix`/`set`/`unset`/`init --merge`/serve
  saves). Imported by exactly ONE module (`wiki_skills/wiki_config/_edit.py`) and **never a
  security gate**: every write rides the hardened sandwich — our own `SafeLoader`
  (anchor-ban) + strict schema gate BEFORE, ruamel round-trip, then the same gate AFTER +
  semantic equality vs a plain-dict oracle + a comment-survival check; any failure →
  `EditDowngrade`, nothing written. The read path everywhere else stays `pyyaml SafeLoader`.

### 6.2. Frontend

- **Primary surface: CLI.** Обsidian — внешний viewer markdown (не часть нашей system).
- **`wiki-config` web layer (TASK 058)** — the ONE web surface, deliberately minimal:
  backend = stdlib `http.server` on `127.0.0.1` (token-auth, zero cookies); frontend =
  ONE self-contained vanilla-JS/CSS page inlined in `_app_html.py` + the static HTML
  `report`. **No Node.js, no build step, no JS dependencies** (React/shadcn/Tailwind
  explicitly declined — user-ratified): the UI is a generic renderer over the
  schema-derived UI model, which is what keeps new config fields zero-UI-code (R-058-10).
- **Future**: web UI for `wiki-search` — still an explicit non-goal (TASK §7c).

### 6.3. Database

- **MVP default**: **SQLite 3.38+** (stdlib).
  - **Justification**: см. [SQLITE-VS-POSTGRES.md §1-§2](./SQLITE-VS-POSTGRES.md). Decision matrix 9-4 в favor of SQLite для personal vault use-case. Embedded, zero-config, iOS-compatible, < 50ms FTS5 на 100K rows.
  - **Pragmas**: `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`, `mmap_size=256MB`.
  - **Extensions**: FTS5 (built-in). Опц. `sqlite-vec` для future vector layer (Epic 8).
- **Opt-in**: **PostgreSQL 15+** через DAL — для users у которых корпус > 100K или multi-user team setup. Реализуется в future Epic 8.

### 6.4. Infrastructure

- **Containerization**: **None** в MVP. Personal CLI tool.
- **Orchestration**: **None**. Single-machine.
- **Middleware**: **None**.
- **Observability**: **`log.md`** chronological + JSON sidecar lint reports. SessionStart hook reads `batch_runs`. 
- **CI**: GitHub Actions (если репо public) — pytest + benchmark suite + JSON Schema validation. Stub для Now: `Makefile` с `test`, `bench`, `lint` targets.

---

