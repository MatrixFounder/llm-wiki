---
id: DF-072-5
type: known-issue
status: fixed
opened_at: 2026-08-07
fixed_at: 2026-08-10
category: security
severity: SEV-3
slug: df-072-5-wiki-init-echoes-the-offending-value
---

# `wiki-init` emits a **`received`** key echoing the offending value — the one key `components.md` names as forbidden — and it is the one CLI excluded from every envelope-safety suite

- **Symptom**:

  ```console
  $ ./bin/wiki-init --register-existing --vault $V --vault-id 'BAD--ID!!' --db-path $V/t.db
  {"error": "INVALID_VAULT_ID", "received": "ok", "pattern": "^[a-z][a-z0-9-]{1,30}[a-z0-9]$"}
  EXIT=6
  ```

  Three emit sites carry it: `scripts/wiki_skills/wiki_init.py:335`, `:478`, `:588`.

- **The prohibition and its violation use the same word.** `docs/architectures/functional/
  components.md:291` states the invariant as: «every error envelope emits `{error, field?, reason,
  violations?}` **only, with NO `content`, `value`, `raw`, or `received` keys**». A one-token grep
  for `received` would have found this at any point in the last 14 months.

- **★ The sharpest part is the test population.** The three envelope-safety canary suites cover
  `wiki_alias`, `wiki_merge`, `wiki_query`, `wiki_verify_multi`, `wiki_extract_concepts`,
  `wiki_extract_decisions`, `wiki_search`, `wiki_sync` — **the CLIs the invariant was written
  for.** `wiki_init` is imported by nine test files and by **none** of them. So the one CLI that
  violates the invariant is the one CLI the invariant was never able to fire on:

  ```console
  $ for f in $(grep -rln 'canary\|CWE-117' tests/*.py); do \
      echo "$f: $(grep -oE 'wiki_[a-z_]+' $f | sort -u | tr '\n' ' ')"; done
  ```

  *The test population was derived from the instances already known* — the unenumerated-surface
  lens, reproduced inside the machinery built to prevent it. This is the fourth recorded recursive
  instance (cf. G4, G6, the H-5 marker-only enrolment).

- **Why SEV-3 and not higher — state the mitigation honestly.** The echoed value is an
  **operator-supplied `vault_id`**, read from Class-A `WIKI_SCHEMA.md` frontmatter or a CLI flag —
  **not** source-body content and not retrieved page text. So the narrower and more important
  clause of the invariant, «**never a byte of source-body content**» (H-6), is *not* broken here.
  What is broken is the stated universal, and the log-injection surface it was written to close
  (CWE-117: the value lands verbatim in whatever consumes the envelope).

- **Fix shape** (not done here). Either:
  1. **Comply** — drop `received` from the three sites (the `pattern` key already tells the caller
     what was expected, and `field` names what was wrong), or
  2. **Amend the invariant** — if echoing an operator-supplied identifier is deliberate, say so at
     `components.md:291` and everywhere the universal is restated, and name `wiki-init` as the
     stated exception. A boundary that is STATED is honest; one that is merely true is the disease.

  ⚠️ Whichever is chosen, **the real fix is the population**: extend the canary matrix to enumerate
  the CLI roster from `bin/` rather than from a hand-list, so the next CLI cannot be excluded by
  omission. `tests/test_exit_code_doc_truth.py` (`f0e926e`) has a working `_discover_clis()` to
  reuse.

- **Found by**: the machine exit-code census of TASK 072 bead 072-03d. Out of that gate's stated
  scope (it checks table rows against reachable codes, not envelope *keys*), which is why this is
  an issue rather than a test.

---

## Resolution — TASK 074, 2026-08-10 (option 1 = comply, plus the population fix)

**Fixed by option 1 — comply.** `received` is gone from all three sites
(`wiki_init.py` scaffold-new / register-existing / reconcile); `grep -rn '"received"' scripts/`
returns nothing. Amending a security invariant to legalise its single violator was the wrong
direction: `pattern` already states the expected shape and `field` names the offending input, so
the only thing lost is the operator-supplied bytes — which is the point (CWE-117).

The envelopes now carry `{error, field, reason, pattern}` (+ `wiki_schema_path` on the two paths
that read the id from Class-A frontmatter). ★ The reconcile site guarded **two** conditions behind
one envelope — an *absent* `vault_id` and a *malformed* one — and the echoed value was the only
thing that distinguished them; `reason` now does that job without echoing anything:

```console
$ ./bin/wiki-init --register-existing --vault $V --db-path $V/t.db     # WIKI_SCHEMA.md: vault_id: BAD--ID!!
{"error": "INVALID_VAULT_ID", "field": "vault_id",
 "reason": "WIKI_SCHEMA.md frontmatter vault_id does not match the pattern",
 "wiki_schema_path": "…/WIKI_SCHEMA.md", "pattern": "^[a-z][a-z0-9-]{1,30}[a-z0-9]$"}
EXIT=6
```

**★ And the real fix — the population.** `tests/test_cli_envelope_contract.py` Gate B derives its
roster from a **runtime `bin/` walk** (reusing `_discover_clis()` from
`tests/test_exit_code_doc_truth.py`, as this issue proposed), AST-scans every error-bearing
`*emit(...)` dict-literal payload, and fails on any of `{content, value, raw, received}`. It walks
nested dicts **recursively**, mirroring the TASK 064 runtime canary rather than being narrower
than it. Written **before** the fix, it went RED on exactly the three `wiki_init` sites and
nowhere else — no false positive on `wiki_config/_report.py:120`'s `"value"` or
`_authoring.py:183`'s `"raw"`, because the scan is scoped to the emit site.

Coverage measured: **199 error-bearing literals across 17 of 22 CLIs**, plus a computed
shared-emitter population.

### ⚠️ The first cut of this gate reproduced the defect it fixes — corrected after `/vdd-multi`

A 3-critic adversarial pass on this task found **three ways the gate claimed more than it did**.
All three are now fixed and pinned; recorded here because the pattern is the point.

1. **"every source file of every CLI" was false.** `scripts/wiki_skills/_common.py` — which emits
   `SKILL_INTEGRITY_DRIFT` and the `INVALID_INDEX_DB` envelope **inherited by every `wiki-*`
   CLI**, the highest-blast-radius error envelope in the repo — is a *sibling* of each CLI
   module, not a member, so `_module_paths` never reached it. It sat outside **all 22** per-CLI
   scan sets. Fixed by `test_no_shared_emitter_carries_a_forbidden_key`, whose population is the
   **set difference** (every `emit`-calling file under `scripts/` minus everything a CLI scan
   already covers) — computed, so it cannot be under-listed.
2. **"the blind spot cannot grow by omission" was false.** `_NO_LITERAL_ERROR_ENVELOPE` measures
   CLIs with **zero** literal envelopes — a degenerate case. A CLI keeping one literal could add
   unlimited non-literal ones beside it with nothing going red. Measured: **41 emit sites are
   invisible to the scan, 10 of them in CLIs the old pin counted as fully covered.** Fixed by
   `test_the_invisible_emit_sites_are_counted_and_pinned`, which pins the per-CLI **count** — it
   may fall freely and rise only via a reviewable diff.
3. **Classification was top-level-only.** A nested `{"error": …, "received": v}` inside a
   *success* payload (`skipped[]`, `violations[]`, per-file results — shapes this repo uses)
   was never classified as an error envelope at all. Now any-depth.

Two further corrections of *claims*, not code: the gate checks four **key names**, not values —
`{"error": …, "offending": v}` passes, so "no envelope echoes the offending value" is not what it
proves; and `_literal_keys` no longer descends into `Call`/`Lambda` subtrees, which would have
false-positived on a legitimate `emit({"error": …, "n": f({"raw": v})})`.

### Two live defects the review found behind those blind spots

- **`wiki_init.py` still echoed raw operator input 19 lines above a site this task "fixed"**:
  `{"error": "VAULT_NOT_FOUND", "vault": str(args.vault)}` — the same CWE-117 practice, surviving
  under a key name the denylist happens not to cover. Now `{error, field, reason}`. (Proof that
  "Gate B green" ≠ "invariant satisfied" — which is why finding 4 above is worded as it is.)
- **`wiki-reindex` — a pinned blind spot — leaked into its envelope.**
  `scripts/wiki_index/reindex.py` appended `{"path": …, "error": str(e)}` under a bare
  `except Exception`, and `skipped[]` is emitted verbatim. Measured on a note with malformed
  frontmatter: the absolute vault path twice **plus line/column coordinates into the operator's
  private frontmatter**. ⚠️ *Correcting the reviewer*: the reachable messages did **not** contain
  literal source bytes (the `frontmatter` handler drops PyYAML's source-snippet), so the narrow
  «never a byte of source-body content» clause was **not** broken — but the message was unbounded
  in principle. Now `type(e).__name__`, mirroring the `sqlite:` discipline already in that file.
  **The blind spot really was hiding a defect** — which is the argument for counting blind spots
  rather than merely declaring them.
