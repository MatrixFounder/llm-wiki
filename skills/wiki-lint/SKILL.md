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
- **lifecycle-drift** — a page whose authored `status` *contradicts* its event-graph
  state (R-15; a decision carrying `superseded-by` but still `status: accepted`).
  Config-driven (`drift_rules`; cybos only). Advisory; **gates `--strict`**.
- **ontology-violation** — a page that *contradicts* the declared ontology contract
  (R-19; TASK 054): an edge whose source/target class is outside the declared
  `from`/`to` (`kind: domain`/`range`), or a `status`-style property value outside its
  enum (`kind: property`). Config-driven (the `ontology:` block; cybos only → other
  layouts no-op). Advisory; **gates `--strict`** (a contradiction, ADR-006 D-036).
  The always-exit-0 report view is `wiki-health ontology`.
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
 "by_category": {"orphan-link": 40, "hash-mismatch": 2},
 "denominators": {"<id>": {
   "lifecycle-drift":    {"pages_examined": 11,
                          "by_rule": [{"class": "decision", "kind": "drift",
                                       "ref": "superseded-by", "matched": 4,
                                       "findings": {"drift": 2}}]},
   "ontology-violation": {"edges_examined": 6, "property_pages_examined": 17,
                          "by_rule": [{"class": "", "kind": "edge", "ref": "implements",
                                       "matched": 2,
                                       "findings": {"domain": 0, "range": 1}}]}}}}
```

### `denominators` — a `0` is not a green until you know what was examined (TASK 061)
`by_category` omitting `ontology-violation` means **either** "no contradictions" **or**
"the check examined nothing". On the real vault it was the latter — 8836
`page_entity_refs` rows, every one a `mentioned` wikilink, **zero** declared edges — and
that read as a clean bill of health on the surface that **gates CI**. So both
config-driven semantic checks (`lifecycle-drift` and `ontology-violation` — the two that
gate `--strict`) now report their population:

- **`lifecycle-drift`** — `pages_examined` = pages whose authored `$.type` ∈ ⋃
  `drift_rules[].class`; per-rule `matched` = pages of that class **that already carry the
  edge**. Both, because `matched: 0` alone cannot tell *"no `decision` pages at all"* from
  *"50 decisions, none carrying a `superseded-by` edge"*.
- **`ontology-violation`** — **two** denominators, because one check spans two populations:
  `edges_examined` (refs whose `ref_type` is in the declared edge vocabulary) and
  `property_pages_examined` (pages whose `$.type` ∈ ⋃ `properties[].class`).
- **An absent check key** = "this check does not apply to this layout" (no `drift_rules` /
  no `ontology:` block ⇒ its no-op fired, no DAL call). That is **not** "examined 0".
- The other two checks carry no denominator, and that boundary is deliberate:
  `auto-generated-drift` is a render-hash comparison (no rule population), and the
  `classification-*` checks ride a `policy:` block that is declared-but-OFF.

Denominators **never gate**: `total_issues`, `by_category` and the `--strict` exit code
are unaffected by them.

There is no `issues` key and no file paths in stdout — only counts. To **act on
individual issues** (which file orphaned, which page drifted, which target is
dangling) you MUST request the detail sidecar with `--json-sidecar <abs.json>`.

**⚠️ SHAPE CHANGE (TASK 061 fix-loop).** The sidecar was a **bare array** through TASK 060;
it is now an **OBJECT**. A bare array is *structurally incapable* of carrying a denominator,
so an empty one (`[]`) was indistinguishable from "the checks examined nothing" — the same
false green the markdown report printed, in a file that travels **alone** as a CI artifact,
without the stdout envelope beside it. The pre-061 array survives **verbatim** under `issues`:

```json
{"issues": [{"category": "orphan-link", "severity": "warning", "vault_id": "<id>",
             "page_slug": "<slug>", "details": {"target": "<slug>", "project": "<proj>",
                                                "line": 12}}],
 "denominators": {"<vault>": {"lifecycle-drift": {"pages_examined": 0, "by_rule": []}}},
 "vacuous_checks": [{"vault": "<id>", "check": "ontology-violation",
                     "population": "edges_examined"}]}
```

- **`issues`** — the pre-061 array, unchanged. Migration is one key: `data` → `data["issues"]`.
- **`denominators`** — the same payload as the stdout envelope (above).
- **`vacuous_checks`** — **derived**: every check population that examined **0**. `[]` means
  every config-driven check that ran examined a real population. A **non-empty**
  `vacuous_checks` with `"issues": []` is **NOT a clean bill of health** — it is the check
  telling you it had nothing to look at. Read this key **before** trusting an empty `issues`.

`--report <abs.md>` writes the same issues as a human-readable markdown report — and for the
same reason it now prints `✅ Healthy. No issues found.` **only when every config-driven
check that ran examined a non-empty population**; otherwise it names each empty population
and appends a *"What was examined"* table. Pick the surface by intent: stdout for the
count/health signal (CI gate via `total_issues` + `--strict`), the sidecar/report for
per-issue remediation.

> Gotcha (do not assume by analogy): unlike `wiki-search` (`hits`) /
> `wiki-query` result envelopes, wiki-lint's stdout carries NO item list — the
> per-issue data lives ONLY in the `--json-sidecar` object's `issues` key.

## Related

- `scripts/wiki_index/lint.py`
- KNOWN_ISSUES D-2 (R-26 enforcement on output paths — pending)
