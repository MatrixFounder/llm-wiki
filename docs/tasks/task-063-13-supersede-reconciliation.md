# TASK 063-13 — **G3**: supersede reconciliation — **drift-rule-driven, never hardcoded**

**Phase**: 4 (write) · **RTM**: R-063-8 · **Type**: code · **Effort**: 4h
**Depends on**: 063-08, 063-12 · **Unblocks**: 063-14, 063-15

## Goal

A `supersedes` edge **reconciles the target's `status`** — otherwise cybos's drift rule
`{class: decision, edge: superseded-by, expect_status: superseded}` fires and the vault is no longer
`--strict`-clean. **G3 is guaranteed to be needed**, not hypothetical.

## ★ The two bugs this bead exists to NOT repeat

**v2** hardcoded `status: superseded` — and **that VIOLATES G1**: `supersedes` is legal
`requirement → requirement`, and the `requirement` enum is `[draft, approved, implemented, dropped]`
— **there is no `superseded`**. *The fix for G3 authored the exact contradiction G1 exists to prevent.*

**v3** fixed the *value* but left the *precondition* hardcoded as `{proposed, accepted}` — a
**decision-specific** set. `workflow`'s enum is `[draft, active, deprecated, superseded]`, so v3 would
**never patch a workflow** and drift would fire. *v2's bug, one field to the left.*

> **DERIVE BOTH FROM CONFIG.** The value **and** the precondition live in `drift_rules`.

## The rule, read from config

```python
rule = find_drift_rule(config.drift_rules, target_class, "superseded-by")   # may be None
# value:        rule.expect_status
# precondition: the DRIFT RULE'S OWN FIRING CONDITION  (_health_rules.py:312-317)
#   patch  <=>  json_type($.status) == 'text'   AND   status != rule.expect_status
```

- **No rule for that class** (requirement, adr, pattern…) ⇒ **patch NOTHING.** There is no drift to
  prevent, and inventing a status would violate the class's enum.
- ⚠️ **A rule of the `forbid_status` SHAPE ⇒ also patch NOTHING** (plan-review **M-9**). `DriftRule`
  carries **exactly one** of `expect_status` / `forbid_status` (`models.py:384-391`), and an
  operator's `.wiki/layout.yaml` may legitimately declare the `forbid_status` shape for
  `(class, superseded-by)`. Then **`rule.expect_status is None`** and *there is no value to patch to* —
  `forbid_status` says what a status must **not** be, which does not determine what it **should** be.
  Treat it as the same branch as "no rule at all": **`rule is None or rule.expect_status is None ⇒ no
  patch`.** *This is v2's bug and v3's bug one field further left — the shape neither of them caught —
  and it is reachable from config, not from code.*
- **Absent / null / non-scalar status** ⇒ never drifts ⇒ **never patched** (no gratuitous Class-A edit).
- **Already `expect_status`** ⇒ no-op (idempotent).

## The AUTHORITY ENVELOPE — `apply` may modify an existing page ONLY when ALL hold

1. it is the declared target of a `supersedes` edge **in this batch**;
2. a `drift_rule` exists for `(target_class, superseded-by)`;
3. **the precondition is the drift rule's own firing condition, read from config** (above);
4. **(3″) a PROTECTED TERMINAL STATUS REFUSES THE BATCH.** `decision.status: rejected` ⇒ **do NOT
   silently skip** (a skip leaves the `lifecycle-drift` finding standing and **breaks the property**)
   and do **NOT** overwrite ⇒ **`REQUIRES_STATUS_RECONCILIATION`, exit 4, zero writes.** Superseding a
   *rejected* decision is a semantic contradiction the **operator** must resolve — not something the
   rail may paper over;
5. the edit is **a single frontmatter scalar** — body bytes, key order and comments preserved (**the
   comment-preserving ruamel sandwich**, TASK 058);
6. the new value is **∈ the class's ontology enum** — *a G1 self-check on `apply`'s own write*;
7. the patch is reported as an explicit diff (`reconciled: [{slug, field, from, to}]`), the patched
   page **IS IN THE MANIFEST** (G5 — else its DB hash goes stale ⇒ `hash-mismatch`), and a **backup**
   is written (`.wiki/backups/`) so the escalation is reversible.

**NOT flag-gated.** An opt-in flag would make the headline invariant *conditional on a flag* — v1's
disease in a new costume. By authoring `supersedes: [[D1]]` the operator has already asserted D1 is
superseded. **`--no-reconcile` is the opt-OUT and it REFUSES THE WHOLE BATCH** (zero pages,
`REQUIRES_STATUS_RECONCILIATION`) whenever the batch contains a `supersedes` edge — writing the pages
*without* the patch would silently break G3 and turn the opt-out into a footgun.

## Context — files

- **Edit** `_pages.py` (`patch_frontmatter_scalar`), `_db.py` (manifest incl. patched pages),
  `__init__.py`.
- **Read** `scripts/wiki_index/sqlite_repository/_health_rules.py:290-325` — **the precondition, in
  the code that fires it.** Read it; do not paraphrase it.
- **Read** `scripts/wiki_skills/wiki_config/_edit.py` (`_rt()`, `_apply_edits_ruamel`, `rewrite_text`)
  — the ruamel sandwich. Note it operates on a whole YAML file; a markdown page needs a
  frontmatter-block split first (`---\n…\n---\n` + body), then the sandwich on the block, then
  byte-identical body re-attachment.
- **Read** `scripts/wiki_skills/wiki_config/_backups.py` (`write_backup`, `ensure_wiki_writable`).

## Tests (RED first) — `tests/test_extract_decisions_supersede.py` (new)

**The `supersedes.to` range, ENUMERATED from cybos.yaml — not assumed:**
`{decision, requirement, workflow, adr, pattern}`. One test per member; the test **reads the range
from the layout** and asserts it has covered every element (so a future range widening fails here
rather than shipping an unhandled class).

- `test_requirement_target_no_rule_zero_patches` — `REQ-B supersedes REQ-A` ⇒ **zero patches, zero
  violations**, exit 0. **MUT:** hardcode `superseded` ⇒ a G1 `status` violation appears ⇒ RED.
  *This is v2's bug, pinned.*
- `test_decision_target_is_patched` — `DEC-B supersedes DEC-A(accepted)` ⇒ patched to `superseded`,
  **manifested**, **backed up**, diff in `reconciled[]`.
- `test_workflow_target_is_patched` — `DEC-B supersedes WF-A(status: active)` ⇒ **WF-A patched to
  `superseded`** (∈ the workflow enum). **MUT:** hardcode the precondition `{proposed, accepted}` ⇒
  no patch ⇒ drift fires ⇒ RED. *This is v3's bug, pinned.*
- `test_rejected_target_refuses_the_batch` — `DEC-B supersedes DEC-A(status: rejected)` ⇒
  **`REQUIRES_STATUS_RECONCILIATION`, exit 4, ZERO writes** (assert the filesystem).
  **MUT:** silently skip ⇒ the `lifecycle-drift` finding stands ⇒ the delta test (063-15) goes RED.
- `test_target_without_status_is_not_patched` — can't drift ⇒ no gratuitous Class-A edit; assert the
  file's **bytes are unchanged**.
- `test_in_batch_supersede` — D3 supersedes sibling D2 ⇒ D2 is **WRITTEN WITH** the reconciled status;
  a batch where D2 carries `status: accepted` while superseded by a sibling is **rejected**.
- `test_patch_preserves_body_comments_and_key_order` — a target with YAML comments + a hand-written
  body ⇒ after the patch, **only** the `status:` line differs (byte-diff the rest).
- `test_no_reconcile_refuses_the_whole_batch` — `--no-reconcile` + any `supersedes` ⇒ exit 4, zero
  pages. **MUT:** write the pages and skip the patch ⇒ G3 silently broken ⇒ 063-15 RED.
- `test_patched_page_is_in_the_manifest` — G5's positive half; else `hash-mismatch`.
- ★ `test_forbid_status_shaped_rule_patches_nothing` (plan-review **M-9**) — a synthetic
  `.wiki/layout.yaml` declaring `{class: decision, edge: superseded-by, forbid_status: [proposed]}`
  ⇒ `rule.expect_status is None` ⇒ **zero patches, zero violations, exit 0** (and the target's bytes
  are unchanged). **MUT:** read `rule.expect_status` unguarded ⇒ the patch value is `None` ⇒ the rail
  either crashes or writes a null status ⇒ RED. *Reachable from config, not from code — which is why
  it needs a test and not a comment.*

## Exit criteria

- [ ] `pytest tests/ -q` ≥ 2477 passed. `mypy --strict scripts/` clean.
- [ ] **GREP-THE-SURFACES — "every class in `supersedes.to` is handled" is a denominator claim, and it
      is where v2 AND v3 both died.** In the test:
      ```python
      cfg = resolve_layout_config(cybos_vault)
      rng = next(e.to for e in cfg.ontology.edges if e.edge == "supersedes")
      assert set(rng) == COVERED_BY_TESTS      # fails when the layout widens the range
      ```
- [ ] **GREP:** `grep -rn "superseded" scripts/wiki_skills/wiki_extract_decisions/` ⇒ **no literal
      status value** in the patch path. The only source is `rule.expect_status`.
- [ ] **GREP:** `grep -rn "proposed\|accepted" scripts/wiki_skills/wiki_extract_decisions/` ⇒ no
      hardcoded precondition set. The only source is `status != rule.expect_status`.
- [ ] Clause (6) — the self-check — is exercised: force a layout whose `drift_rule.expect_status` is
      **not** in the class's ontology enum ⇒ `apply` **refuses** rather than writing a G1-violating
      value. *A config can be wrong; the rail must not amplify it.*

## Rollback

Reconciliation → no-op ⇒ `lifecycle-drift` fires ⇒ 063-15's delta test RED. Correct signal.
