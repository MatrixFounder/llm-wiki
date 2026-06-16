# PLAN 033 — list-membership metadata filter

Plan for `docs/TASK.md` (TASK 033). Stub-First (RED→GREEN), green-throughout, mypy
`--strict`. **Zero DDL** (`user_version` 6), additive, backward-compatible. Three beads,
strictly ordered (DAL → CLI → docs). Binding constraint **B-1** (arch-review) threaded into
033-00.

## Binding constraints (from the gates)
- **B-1 (arch-review):** the per-`--where`-field predicate binds **four** params in
  `(path, value, path, value)` order, mirroring `find_pages_citing_source`
  (sqlite_repository.py:1364). A swapped order is the only realistic silent bug → an
  explicit param-order / paired positive+back-compat test is mandatory.
- **M-1 (arch-review, minor):** the membership branch compares `value = ?` with **no CAST**
  (faithful to the reference). Do NOT promise numeric-*list*-member matching; the `tags[]`-of-
  strings use case is text-only. Tests/docstrings must not over-claim CAST symmetry.
- **M-3 (arch-review, minor):** update BOTH DAL docstrings (`repository.py` `search_pages`
  ~180-192 + `sqlite_repository.py` ~616-625) — they currently describe scalar-only.
- **A2/A5 (task-review):** bind-twice is expected; add a `--tag`/`--where tags=` eval case to
  the wiki-search SKILL eval set.

## Bead order

### 033-00 — DAL: list-membership predicate in `search_pages` (R-1, R-3a/b)
**Files:** `scripts/wiki_index/sqlite_repository.py` (`search_pages` predicate ~628),
`scripts/wiki_index/repository.py` (ABC `search_pages` docstring), `tests/test_wiki_search_metadata_filter.py`.
- **RED:** add tests — (1) `--where tags=decision` matches a page whose `tags:[a,decision]`
  and excludes a `tags:[risk]` page (list membership); (2) scalar `--where status=open`
  unchanged (back-compat) in the SAME assertion block (B-1 paired test); (3) a page where the
  field is ABSENT matches neither branch; (4) the `=`-branch CAST still matches a numeric
  scalar (`priority=1`) — guards M-1 (scalar CAST retained, membership branch additive).
- **GREEN:** change the predicate from
  `AND CAST(json_extract(p.frontmatter_json, ?) AS TEXT) = ?`
  to
  `AND (CAST(json_extract(p.frontmatter_json, ?) AS TEXT) = ? OR EXISTS (SELECT 1 FROM json_each(p.frontmatter_json, ?) WHERE value = ?))`,
  appending params `(path, value, path, value)` per field (B-1). Re-validate field (allowlist,
  unchanged). Update the ABC + impl docstrings (M-3).
- **Done:** new tests green; ALL existing `test_wiki_search_metadata_filter.py` green; mypy strict.

### 033-01 — CLI: `--tag <value>` sugar (R-2, R-3c)
**Files:** `scripts/wiki_skills/wiki_search.py` (parser + where-assembly), `tests/test_wiki_search_metadata_filter.py`.
- **RED:** tests — (1) `--tag decision` ≡ `--where tags=decision` (same hits, via the CLI
  `main`); (2) `--tag x --where tags=y` → `INVALID_FILTER` exit 2 (one-predicate-per-field dup
  guard fires), value NOT echoed; (3) `--tag` combines with a FTS `query` + `--types` (AND-ed);
  (4) `--tag` with no query → pure-listing path.
- **GREEN:** add `--tag` argparse flag (mirror `--status`/`--severity` help/shape); in the
  where-assembly append `("tags", args.tag)` when set (after the `--where` list, before the dup
  check so the guard covers it). No other logic.
- **Done:** tests green; mypy strict; injection/echo posture unchanged.

### 033-02 — Docs + ROADMAP currency (R-4)
**Files:** `skills/wiki-search/SKILL.md` (+ version bump + `evals.json` `--tag` case),
`docs/manuals/obsidian-llm-wiki_manual.md` + `.ru.md` (wiki-search section),
`docs/layouts/cybos.md` + `scripts/wiki_index/layouts/cybos.yaml` (flip the "NOT `--where tag=`"
note → "now `--where tags=` / `--tag`"), `docs/ROADMAP.md` (R-13 residual → closed/shipped).
- **Done:** docs describe the membership filter + `--tag`; the cybos gap-note is flipped; ROADMAP
  R-13 residual marked shipped; eval case added; no stale "only via --types" claim remains.
  (Opportunistic: correct the manuals' stale "15 CLIs"/"user_version = 5" overview lines to
  16 / 6 while in-file — TASK 032 currency, trivially in-scope here.)

## Verification (end-to-end)
```bash
source .venv/bin/activate
pytest tests/test_wiki_search_metadata_filter.py -q   # bead-local
pytest tests/                                          # full green
mypy --strict scripts/                                 # clean
# manual smoke on the real dogfood vault (already has eg- typed pages + tags):
python -m scripts.wiki_skills.wiki_search --tag decision --vaults personal \
    --vault-root /Users/sergey/Downloads/TestVault/ObsidianNotes-Test --format json
#  → expect eg-decision-rabbitmq + eg-decision-kafka
```

## Review (post-development)
`/vdd-multi` (logic/security/performance) + `code-review`. Adversarial focus: B-1 param-order
correctness, the scalar back-compat superset claim, injection/echo non-regression, the
`json_each`-over-scalar/absent semantics.

## Out of scope
`IN`/`~=` operator syntax; indexing `tags[]` (R-X3-MF-SCAN stays); `--types` semantics.
