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
  The non-gating report view is `wiki-health ontology` (exit 0 on success).
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
  duplicates section enabled). **A bare `wiki-lint` therefore does real work** — it opens
  the global DB and lints every registered vault. That is intended (this is the one CLI
  with no argparse-required argument), not an accident of the parser.
- `--strict` upgrades warning-level issues to error severity **and turns the run into a
  gate**: a gating issue makes the process exit **1**. Without `--strict` the exit is
  always `0` and `total_issues` is the signal.
- ⚠️ **Exit `1` means two different things in this CLI — read the envelope, not just `$?`.**
  See [Exit codes](#exit-codes) below. This is a **deliberate divergence** from the family
  convention (`1` = unhandled exception), kept because exit-1-on-findings is the universal
  linter convention (ruff / eslint / shellcheck) and because moving the signal to the
  family's `6` would collide with this CLI's inherited `INVALID_INDEX_DB` (DF-072-4).

## Exit codes

This table is the **normative roster** for this CLI — every reachable code is listed,
including the one it inherits rather than raises itself.

| Code | `error` | Cause |
|---|---|---|
| 0 | — (success envelope) | the run completed. Either no gating issue was found, or `--strict` was not passed. **Findings can be present at 0** — read `total_issues`. |
| **1** | — (a **SUCCESS** envelope: `action:"linted"`, **no `error` key**) | **`--strict` gate tripped** — at least one gating issue. `wiki_lint.py:99`. **Deliberate divergence** from the family's `1 = crash` convention. ⚠️ see the box below. |
| **1** | — (**no envelope at all**) | an **uncaught exception**: stdout is EMPTY and a raw traceback goes to stderr. Mostly bug/environment faults (corrupt `--db-path`, unwritable `--report` path) — but ⚠️ **two plain user-input paths land here too**: a malformed `--vault` raises `ConfigValidationError` and an iCloud `--db-path` raises `ICloudRejectionError`, both from `factory.py`, neither caught in `wiki_lint.main`. So "1 with no envelope" does **not** reliably mean "file a bug"; check your `--vault`/`--db-path` first. (Closing this properly = catching both and emitting at 6; tracked, not done here.) |
| **2** | — (argparse, **no envelope**) | unrecognised argument / bad flag value. argparse writes usage to **stderr** and its own status is **2**, always. This CLI has no required argument, so there is no "missing flag" path. |
| **6** | `INVALID_INDEX_DB` | **inherited from `build_repo_config`** (`wiki_lint.py:73`), raised before any check runs: the vault's `index_db:` escapes the vault / is a symlink / is an unsafe absolute path. **Nothing is linted.** Envelope carries an extra `hint` key. |

> ⚠️ **EXIT 1 IS AMBIGUOUS IN THIS CLI — never treat `$? == 1` as a crash.** It means *either*
> a tripped `--strict` gate (success envelope, findings in `by_category`) *or* an unhandled
> exception (no envelope). **Branch on stdout:** empty ⇒ crash, re-run and read stderr;
> parseable JSON without an `error` key ⇒ the gate did its job, read `total_issues` /
> `by_category`. A caller applying the family's «`1` = unhandled exception, raw traceback»
> convention (see `skills/wiki-query/SKILL.md`) reads a perfectly successful gate run as a
> crash — that was DF-072-4, and this table is its fix.
>
> Pinned by `tests/test_cli_envelope_contract.py::test_wiki_lint_strict_gate_is_a_success_envelope_at_exit_1`,
> which asserts the **envelope shape** alongside the code — an `rc == 1`-only assertion
> structurally cannot tell the two apart.

> **Why not move the gate signal off `1`?** Because the obvious target is already taken. The
> family's `6` is this CLI's inherited `INVALID_INDEX_DB` (an *error* envelope, nothing linted),
> so putting the gate there would reproduce `wiki-verify-multi`'s exit-6 ambiguity rather than
> remove it. Exit 1 also *is* the linter convention everywhere else (ruff, eslint, shellcheck,
> flake8). Recorded as TASK 074 D-074-2.

## Output

**stdout is a SUMMARY only** — a histogram, NOT a per-issue list. The envelope is:

```json
{"action": "linted", "vault": "<id>", "total_issues": 42,
 "by_category": {"orphan-link": 40, "hash-mismatch": 2},
 "denominators": {"<id>": {
   "lifecycle-drift":    {"pages_examined": 11,
                          "by_rule": [{"class": "decision", "kind": "drift",
                                       "ref": "superseded-by", "matched": 4,
                                       "matched_by_kind": {"drift": 4},
                                       "findings": {"drift": 2}}]},
   "ontology-violation": {"edges_examined": 6, "property_pages_examined": 17,
                          "by_rule": [{"class": "", "kind": "edge", "ref": "implements",
                                       "matched": 2,
                                       "matched_by_kind": {"domain": 2, "range": 1},
                                       "findings": {"domain": 0, "range": 1}}]}}},
 "vacuous_checks": [], "vacuous_kinds": []}
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
- **`by_rule[].matched_by_kind`** — ⚠️ **the number you must actually read.** `matched`
  counts rows the check **cannot judge**: an edge rule's `domain` fires only on a **typed
  source**, its `range` only on a **resolved + typed target**. A rule whose targets are all
  dangling or untyped reports `{matched: 500, findings: {domain: 0, range: 0}}` — which
  *reads* as "500 examined, all clean" while `range` examined **zero**. Mirrors `findings`
  key for key. The honest invariant, per rule and per kind:
  `findings[k] ≤ matched_by_kind[k] ≤ matched ≤ <family denominator>`.
- **`vacuous_checks`** — every check population that examined **0**.
- **`vacuous_kinds`** — `[{vault, check, class, kind, ref, finding_kind}]`: rules that
  **matched rows but could judge none of them**. A rule with `matched: 0` is *not* listed —
  it is openly empty (visible in its `by_rule` row), not hiding.
- **An absent check key** = "this check does not apply to this layout" (no `drift_rules` /
  no `ontology:` block ⇒ its no-op fired, no DAL call). That is **not** "examined 0".
- The other two checks carry no denominator, and that boundary is deliberate:
  `auto-generated-drift` is a render-hash comparison (no rule population), and the
  `classification-*` checks ride a `policy:` block that is declared-but-OFF.

**`total_issues: 0` is a clean bill of health ONLY when `vacuous_checks == []` and
`vacuous_kinds == []`.** All three sinks (stdout, `--report`, `--json-sidecar`) carry both
keys and already derive the verdict — do not re-derive it from `denominators` yourself.

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
                     "population": "edges_examined"}],
 "vacuous_kinds": [{"vault": "<id>", "check": "ontology-violation", "class": "",
                    "kind": "edge", "ref": "uses", "finding_kind": "range"}]}
```

- **`issues`** — the pre-061 array, unchanged. Migration is one key: `data` → `data["issues"]`.
- **`denominators`** — the same payload as the stdout envelope (above).
- **`vacuous_checks`** — **derived**: every check population that examined **0**. `[]` means
  every config-driven check that ran examined a real population. A **non-empty**
  `vacuous_checks` with `"issues": []` is **NOT a clean bill of health** — it is the check
  telling you it had nothing to look at. Read this key **before** trusting an empty `issues`.
- **`vacuous_kinds`** — **derived**: rules that examined rows but could **judge none of
  them** (see `matched_by_kind` above). `"issues": []` with a non-empty `vacuous_kinds` is
  **not** a green either — the rule's `0` is noise, not a finding. Read it **before**
  trusting an empty `issues`.

`--report <abs.md>` writes the same issues as a human-readable markdown report — and for the
same reason it now prints `✅ Healthy. No issues found.` **only when every config-driven
check that ran examined a non-empty population and every rule that matched rows could judge
them**; otherwise it names each empty population / rule×kind and appends a *"What was
examined"* table plus a *"What each rule could judge"* table (`matched | judgeable | found`,
where a `judgeable` of `0` marks the count beside it as noise). Pick the surface by intent:
stdout for the count/health signal (CI gate via `total_issues` + `--strict`), the
sidecar/report for per-issue remediation.

> Gotcha (do not assume by analogy): unlike `wiki-search` (`hits`) /
> `wiki-query` result envelopes, wiki-lint's stdout carries NO item list — the
> per-issue data lives ONLY in the `--json-sidecar` object's `issues` key.

## Related

- `scripts/wiki_index/lint.py`
- KNOWN_ISSUES D-2 (R-26 enforcement on output paths — pending)
