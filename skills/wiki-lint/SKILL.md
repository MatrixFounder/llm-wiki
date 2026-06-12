---
name: wiki-lint
description: >-
  SQL-level health-check across one vault or all vaults. Detects orphan
  links, dangling references, missing-on-disk pages, hash drift, type
  mismatches, cross-vault concept duplicates.
  Triggers: "lint vault", "wiki health", "wiki-lint".
tier: 2
version: 1.1
---

# wiki-lint

Read-only consistency check between the SQLite index and the filesystem.

## When to use

- Before publishing or merging changes to the vault.
- Periodic health-check (CI / cron).
- After a `wiki-reindex --delta` to spot files that drifted between mtime
  cutoffs.
- Investigating mysterious `[[wiki-link]]` failures.

## Categories detected

- **orphan-link** — wiki-link target has no page on disk and no entity row.
- **missing-in-db** — markdown file under `_sources/_concepts/_entities`
  but no row in `pages`.
- **missing-on-disk** — DB has a page row but the file is gone (R-26
  cleanup trigger).
- **hash-mismatch** — `pages.file_hash` differs from on-disk sha256.
- **type-mismatch** — frontmatter `type:` doesn't match DB `pages.type`.
- **cross-vault-duplicate** — same concept slug exists in 2+ vaults
  (R-29; informational, suggests promotion).

## Invocation

```bash
wiki-lint \
    [--vault <vault_id> | omit for all-vaults] \
    [--report <abs-path.md>] \
    [--json-sidecar <abs-path.json>] \
    [--strict] [--db-path <override>]
```

Or `/wiki-lint [...]`.

## Contract

- Omitting `--vault` runs across every registered vault (cross-vault
  duplicates section enabled).
- `--strict` upgrades warning-level issues to error severity.
- Always returns success exit `0`; the envelope's `total_issues` count is
  the signal (use `--strict` + grep to fail CI on issues).

## Output

**stdout is a SUMMARY only** — a histogram, NOT a per-issue list. The envelope is:

```json
{"action": "linted", "vault": "<id>", "total_issues": 42,
 "by_category": {"orphan-link": 40, "hash-mismatch": 2}}
```

There is no `issues` key and no file paths in stdout — only counts. To **act on
individual issues** (which file orphaned, which page drifted, which target is
dangling) you MUST request the detail sidecar with `--json-sidecar <abs.json>`:
its content is a **bare JSON array** (NOT wrapped in any object) of issue
objects, each:

```json
[{"category": "orphan-link", "severity": "warning", "vault_id": "<id>",
  "page_slug": "<slug>", "details": {"target": "<slug>", "project": "<proj>",
  "line": 12}}]
```

`--report <abs.md>` writes the same issues as a human-readable markdown report.
Pick the surface by intent: stdout for the count/health signal (CI gate via
`total_issues` + `--strict`), the sidecar/report for per-issue remediation.

> Gotcha (do not assume by analogy): unlike `wiki-search` (`hits`) /
> `wiki-query` result envelopes, wiki-lint's stdout carries NO item list — the
> per-issue data lives ONLY in the `--json-sidecar` array.

## Related

- `scripts/wiki_index/lint.py`
- KNOWN_ISSUES D-2 (R-26 enforcement on output paths — pending)
