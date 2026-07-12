# Task 061-09 — [DOCS] The `_raw/`-appears-in-retrieval claim, every LIVING surface + Q-061-*

RTM: **R-061-7** (+ the prose half of R-061-3). Depends on: `061-06`, `061-08`.

## Goal

Four (in fact **nine**) LIVING surfaces claim that a `_raw/` capture can appear in retrieval.
**It cannot** in normal operation: **all four built-in layouts ignore `**/_raw/**`** — verified:
`layouts/karpathy.yaml:28`, `dev-project.yaml:20`, `obsidian-personal.yaml:24`, `cybos.yaml:28`
— so no `_raw/` page is ever indexed, and the `_raw/` limb of `_is_external` cannot fire on a
hit. Name the **http(s) frontmatter key** as the operative signal; document `_raw/` as a
**backstop** for direct upserts / custom layouts. **No predicate or SQL change** — the `_raw/`
limb stays (it is correct, just not reachable via the normal index path).

## The census (grep-derived; re-run before editing — the count is a FLOOR)

| # | Surface | Claim to correct |
|---|---|---|
| 1 | `skills/wiki-query/SKILL.md:86-87` | "`external` (a `_raw/` capture or an `http(s)://` `source`/`URL`/`url`)" |
| 2 | `skills/wiki-query-synthesis/SKILL.md:29` | "`external` = an external-origin page (`_raw/` capture or `http(s)://` source)" |
| 3 | `scripts/wiki_skills/wiki_query.py:830-837` | `prepare`'s `--min-trust` argparse help ("_raw/ captures, http(s) sources") |
| 4 | `scripts/wiki_skills/wiki_query.py:877` | **`apply`'s SECOND `--min-trust` argparse help** — the RTM says "the argparse help", singular. It is two. |
| 5 | `docs/architectures/functional/policy-and-trust.md:38` | "Computed from `$.source`/`$.URL`/`$.url` http-prefix, the `_raw/` path segment…" (also an **R-061-3** key-list surface) |
| 6 | `docs/architectures/security.md:198-200` | names `Source:` as an **accepted evasion** — **R-061-3 CLOSES it**, so leaving this makes a LIVING arch doc false |
| 7 | `docs/manuals/obsidian-llm-wiki_manual.md:1811` | key list + "**or** lives under `_raw/`" |
| 8 | `docs/manuals/obsidian-llm-wiki_manual.md:2089` | glossary: "`external` (web capture / `_raw/`)" |
| 9 | `docs/manuals/obsidian-llm-wiki_manual.ru.md:1860` | the RU mirror of #7 (EN/RU lockstep, TASK 059) |

Re-run before starting:

```bash
grep -rn "_raw" skills/ scripts/wiki_skills/wiki_query.py docs/architectures/ docs/manuals/ \
  | grep -iE "trust|external|min-trust|retriev|hit|capture"
```

## FROZEN — do not edit (verify with `git diff --name-only`)

- `docs/tasks/task-050-*.md` (its UC-3 records what was believed at authoring time — rewriting it
  is exactly what the frozen-archive rule prevents; the corrected belief lives in TASK 061)
- `docs/plans/plan-050-*.md`
- the **Q-050 entries** in `docs/architectures/open-questions.md` (new Q-061-* entries are
  *additions*, not edits — that is allowed and required below)

## The corrected wording (reuse verbatim; one claim, nine renderings)

> `external` = the page declares an **`http(s)://` provenance key** in frontmatter (`source` /
> `url` / `URL` and their case variants — see `policy.EXTERNAL_PROVENANCE_KEYS`). A `_raw/` path
> segment is also treated as external, but it is a **backstop**: all built-in layouts exclude
> `**/_raw/**` from the index, so a `_raw/` capture is not retrievable in normal operation — the
> limb exists for direct `wiki-index-upsert` calls and custom layouts.

For #6 (`security.md`), rewrite the third evasion example: `Source:` is now **closed**
(TASK 061 / R-061-3); the remaining accepted imprecision is a **list-valued `source:`** and
**vault-specific provenance keys** (`youtube:`/`teachable:` — **Q-061-4**), plus typo-shaped keys.
Do not overstate: the tier remains **advisory, never an authorization boundary**.

## Open questions — ADD to `docs/architectures/open-questions.md`

New entries (`Q-061-1` … `Q-061-4`), each carrying its **settled decision** from `docs/TASK.md
§4`, so the reasoning is durable and greppable:

- **Q-061-1** — three denominator nouns, because three populations (RESOLVED, TASK 061).
- **Q-061-2** — enumerate the case variants from one shared constant; the binding constraint is
  Q-050-3 alignment, not performance (RESOLVED, TASK 061).
- **Q-061-3** — `zones` advisory: **Option A′ generalize, don't badge**; Option B
  (`x-wiki-advisory` + badge) deferred until a *second* advisory field exists (RESOLVED, TASK 061).
- **Q-061-4** — vault-specific provenance keys (`youtube:` 9, `teachable:` 9) still derive
  `internal`. **OPEN.** Deferred by *mechanism* (needs a per-vault `external_keys:` config
  surface), not by defect. **Raised stakes:** the always-on per-hit `trust` **annotation** — the
  surface operators actually use (the `--min-trust` floor was withdrawn) — mislabels these 18
  pages. Pinned by `tests/test_trust_tier.py::test_vault_specific_provenance_key_still_internal_q0614`.

## Verification

```bash
# 1. no LIVING surface still implies a _raw/ page can be retrieved:
grep -rniE "_raw/.{0,40}(retriev|hit|search|floor)" skills/ scripts/ docs/architectures/ docs/manuals/
# 2. the frozen set is untouched:
git diff --name-only | grep -E "docs/(tasks/task-050|plans/plan-050)" && echo "FROZEN FILE TOUCHED — REVERT"
# 3. the Q-050 entries are byte-identical:
git diff docs/architectures/open-questions.md | grep -E "^[-+].*Q-050" && echo "Q-050 EDITED — REVERT"
# 4. the two argparse helps agree:
python3 -m scripts.wiki_skills.wiki_query prepare --help | grep -A4 min-trust
python3 -m scripts.wiki_skills.wiki_query apply   --help | grep -A4 min-trust
pytest tests/ -q && mypy --strict scripts/
```

## Acceptance criteria

- [ ] All **nine** sites read correctly; the census grep returns no uncorrected claim.
- [ ] **Both** `--min-trust` argparse helps corrected (not just `prepare`'s).
- [ ] `security.md`'s `Source:` evasion updated (it is now closed) — with the *remaining*
      imprecision named honestly.
- [ ] Q-061-1…4 ADDED to `open-questions.md`; **no Q-050 entry modified**; no frozen archive touched.
- [ ] No predicate or SQL change in this bead (`git diff --stat` shows docs/skills/help-strings only).
