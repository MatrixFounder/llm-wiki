# PLAN 072 — R-7 re-scoped in place, and the three fixes it uncovered

**Spec**: [TASK.md](TASK.md) (TASK 072). **Scope of THIS plan: P0 · P1a · P1b · P2 only.**
P3/P4/P5 are **CONDITIONAL and out of this plan** — named as follow-on in §7.

**Strategy**: Stub-First per `tdd-stub-first`. Each code phase lands its **failing test first**, and
every bead names the **mutation that is EXECUTED** to prove RED — `tests/.AGENTS.md`: an assertion
that a test *would* be red is not a test.

**Baseline — MEASURED on this working tree, not quoted:**

```
pytest tests/ -q        →  3024 passed, 14 skipped
mypy --strict scripts/  →  Success: no issues found in 97 source files
python3 scripts/pin_skill_integrity.py  →  exit 0, "in sync: 7 contracts pinned; nothing to do."
```

A bead that leaves the tree red is not done.

---

## 0. The six rules that govern EVERY bead

1. **GREEN AT EVERY BOUNDARY.** `pytest tests/` ≥ 3024 passed / 0 failed and `mypy --strict scripts/`
   clean after **each** bead. One bead = one commit.
2. **A PINNED-FILE EDIT AND ITS RE-PIN ARE ONE COMMIT.** `skills/wiki-query-synthesis/SKILL.md` is
   line 12 of `config/skill-integrity.sha256`. This plan touches it **twice** (072-01, 072-03b) ⇒
   **exactly two re-pin commits**, each running `python3 scripts/pin_skill_integrity.py --write`, each
   leaving `git diff config/skill-integrity.sha256` **exactly one changed line (line 12's digest)**.
   A changed header or a second changed hash means something else moved. **Never hand-edit a hash.**
3. **EVERY POPULATION CLAIM CARRIES A GREP THAT WAS *RUN*.** The unenumerated-surface lens is this
   repo's signature failure. Counts here are a **floor, never a ceiling** — re-grep at implementation
   time. Beads carrying such a claim: **00, 01, 03c, 06, 07, 09, 11**.
4. **NO GATE MAY BE SATISFIABLE BY EXAMINING NOTHING** (TASK 061). Concretely: P1a's tests assert
   `retrieved_count >= 1` *before* exercising the floor; P1b's refusal tests carry a **positive
   control** that must NOT be refused; P2's control rule asserts `matched > 0`, not just `gaps == 0`;
   072-01's promise-site gate ships a **synthetic fixture it must flag RED**.
5. **ZERO DDL.** `PRAGMA user_version` stays **7**. No `ALTER`, no new index, no new `ref_type`, no
   new `event_type`. Eight test files hardcode `== 7`; none moves. `git diff sql/` stays empty.
6. **Decision-17 intact.** No `import anthropic` **and** no `from anthropic`. One JSON envelope + a
   stable exit code per CLI.

---

## 1. Corrections carried forward (recon → plan → gates)

Recorded because a fix whose reason is not recorded is a fix that gets reverted.

| # | Claim | Measured truth | Consequence |
|---|---|---|---|
| **K-1** | "5 tests patch `_download_raw_html`; leave them unchanged" | **8 tests / 8 sites** (`tests/test_import_video.py:351,361,372,394,461,473,489,528`), every double a **single-positional** lambda | Threading a new arg breaks all 8 with `TypeError` — and `_append_embedded_videos` wraps the call in `except Exception` (`_fetch.py:958-960`), so 4 go loudly RED while **`test_embedded_off_by_default_no_discovery` stays VACUOUSLY GREEN** (`called["download"] == 0` is satisfied by never calling). Handled in **072-06**. |
| **K-2** | schema uses `anyOf` | It is **`oneOf`** (`config/layout-config.schema.yaml:189-191`) | P2's `dependentRequired` argument **depends on `oneOf`**; under `anyOf` it collapses. Verified — the argument holds. |
| **K-3** | baseline "3019 passed, 19 skipped" | **3024 passed, 14 skipped** | The recon measured in a `.venv`-less tree. Use 3024/14. |
| **K-4** | a per-line `R-8.*deferred` regex catches the stale claims | It **misses** `skills/wiki-query-synthesis/SKILL.md:160-161` (the sentence wraps) | A per-line gate is **vacuous on the pinned file it most needs to cover** — but see **G-2**: the proposed whole-file fix overshoots. |
| ★ **G-1** | the promise-site gate fires on exactly 2 files | It fires on **THREE** — `docs/architectures/verification-map.md:105` ("Scope = R-6 only (R-7/R-8 deferred + gated)") is inside `docs/**/*.md` and matches on **both** R-7 and R-8 | **072-01 could not reach green as originally specified.** Resolved by an explicit, reason-carrying exemption (§3, 072-01). |
| ★ **G-2** | "normalise whitespace over the WHOLE FILE" | `docs/ROADMAP.md` carries the `### R-7.` and `### R-8.` headings and `deferred` on **12** separate lines (`grep -c deferred docs/ROADMAP.md`) | A whole-file match is **RED forever on the one file the closure lives in**. Gate must be **paragraph-scoped with a bounded window** (§3, 072-01). |
| ★ **G-3** | H-5 RED set = `:66, :105, :126, :300` | `:105` compares **PATH SETS**, so a content-only edit cannot make it red; `:224` (the **runtime** gate) *will* go red and was mislabelled as a post-re-pin check | Corrected RED set: **`:66`, `:126`, `:224`, `:300`**. |
| ★ **G-4** | `build_cybos_vault` has "five call sites" | **27 call sites across 5 files** | Drop the enumeration; the parameter is keyword-with-default, so all 27 are unchanged **by construction** — a structural claim needs no census. |

---

## 2. Bead sequence

| # | Bead | Item | Blocked on |
|---|---|---|---|
| 072-00 | ROADMAP R-7 **re-scoped in place** + Epic-6 row + `verification-map.md:105` + 3 false `security.md` claims | P0 | — |
| 072-01 | The two skill promise sites (+ stale **R-8**) · **H-5 re-pin #1** · the promise-site gate | P0 | 072-00 |
| 072-02 | **[RED]** the two `NO_CITATIONS` tests — executed RED on today's `main` | P1a | — |
| 072-03a | **[LOGIC]** the 3-line floor + xfail removal + the executed delete-the-block mutation | P1a | 072-02 |
| 072-03b | The **pinned** synthesis-contract citations table + **H-5 re-pin #2** (one commit, two files) | P1a | 072-03a |
| 072-03c | Doc currency: every exit-code enumeration, the 3-site `--min-hits 0` correction, the phantom code | P1a | 072-03a |
| 072-03d | ★ **[GATE]** the **machine** exit-code census (roster discovered at runtime, static **+** executed, both directions) + the 6 findings that exhausted the roast loop | P1a | 072-03c |
| 072-04 | ★ **[CROSS-REPO]** add the raw-bytes verb to `Universal-skills/skills/html` + record Q-072-1/Q-072-2 | P1b | — |
| 072-05 | **[RED]** hostile-URL tests through **both** actual call sites + the non-skippable resolve test | P1b | — |
| 072-06 | **[LOGIC]** `_download_raw_html` → the guarded ladder (+ the launcher key + the 8 seams) | P1b | 072-05 |
| 072-07 | **[LOGIC]** `_download_pdf` → the new verb + capability probe + `noqa` removal + **file the issue** | P1b | 072-04, 072-05, 072-06 |
| 072-08 | **[STUB]** `forbid_values`: schema + dataclass + build + load gate (finder still ignores it) | P2 | — |
| 072-09 | **[LOGIC]** the SQL OFF/ON split + per-row `field-value` kind + off-equivalence goldens | P2 | 072-08 |
| 072-10 | P2 docs + the `cybos.yaml` **comment-only** `forbid_values` note + `wiki-config validate` finding | P2 | 072-09 |
| 072-10b | ★ **[BUG]** `cybos.yaml` half-support: repo glob fix + two-conjunct regression test + operator override | OQ-4 | — |
| 072-11 | ★ **The doc census** (entirely ungated) + final gates | all | all |

**16 beads.** ★ 072-03d was **added 2026-08-07**, after 072-03c shipped and three adversarial roast rounds
each found the same doc falsehood on one *more* file — the loop bound was exhausted and escalated, and the
operator ruled: re-scope, do not grant a fourth round. Its lesson is written into the bead: *a census
predicate derived from the instances you already found is not a census*. P1a is 4 (not 1) because the review showed the original 072-03 fused a 3-line production
patch, a pinned-file re-pin and an 11-file doc sweep into one commit — which makes the "diff is exactly
line 12" check unverifiable at a glance. P1b is 4 because it is **not homogeneous**: a mechanical
subprocess rewire (HTML) *plus* a **cross-repo prerequisite** (the PDF verb). 072-10b was added by the
OQ-4 ruling and is a standalone bug fix that depends on nothing.

---

## 3. The beads

### Phase 0 — P0 · re-scope and correct (no code; one new gate)

- [ ] **072-00 · Re-scope R-7 in place (OQ-1) and correct the false architecture claims.**
  **Files**: `docs/ROADMAP.md` — addressed BY ANCHOR, never by line number (see (g) below for why):
  the `### R-7. \`wiki-research\` (R-20)` heading's body · the Epic-6 table row whose first cell is
  `\`wiki-source-web\`` · the two-line paragraph ending in the bare token `\`wiki-research\`.`
  — plus `docs/architectures/verification-map.md`
  (:105), `docs/architectures/security.md` (:17, :18, :54), `docs/architectures/system-architecture.md`
  (:275-285).
  **What**: (a) the heading line beginning `### R-7. \`wiki-research\` (R-20)` → `### R-7. \`wiki-research\` (R-20) — ★ RE-SCOPED 2026-08-06
  (TASK 072): external corroboration of OPEN TYPED QUESTIONS`; body = the new scope + a blockquoted
  **non-reopenable** sub-section carrying TASK §2.1 (`CONCEPT_PAGE_EXISTS`, `_pages.py:219`; a
  BEGIN-AUTO block must be a pure function of Class-A/DB state ⇒ web prose breaks §D8), §2.2 **with
  its numbers** (747 entities / 310 = 41.5 % / mean 164.9 / **0** empty; family CLOSED at
  the paragraph beginning `**Phase B is CLOSED as REFUTED.**`; reopening bar ≥30 per class
  **including short-but-good**), §2.4 (6512 orphan
  targets, ~90 % media), §2.5 (`type='query'` and `ref_type='cited'` both **0** on every live DB),
  **both halves** of the discrimination control (SIGNAL 20/20 · CONTROL 0/54), the **OQ-2 named rail
  trigger**, and the **D-9 standing rule** (a web-origin page may never mint `verifies`; use
  `related`). Mirror the R-23 Phase B closure format — the block from the heading
  `### ★ Phase B — RE-SCOPED` down to the `**Phase B is CLOSED as REFUTED.**` paragraph.
  ★ Per TASK §2.3 **name each corpus by ROOT PATH, never `vault_id`**, and ship every census as a
  **re-runnable command**, not a figure in prose.
  (b) `verification-map.md:105` → `Scope = R-6 only (R-8 shipped 2026-05-29, TASK 008; R-7 re-scoped
  2026-08-06, TASK 072)` — it currently calls **both** deferred and R-8 shipped 14 months ago.
  (c) `security.md:18` — «`wiki.research.private_concepts` … schema готова» is **FALSE**
  (`grep -rn 'private_concepts\|private_tags\|wiki\.research' config/` → **0 hits across all 7 files**).
  **CORRECT it, do not extend it**: name the shipped surface (`classification:` + `--audience`,
  ADR-009/TASK 049) and record that it is measured to fire on **0 pages** everywhere — a mechanism
  AVAILABLE, not a mechanism IN USE.
  (d) `security.md:17` — «HTTPS для всех external API calls (Anthropic)» is stale: under Decision-17
  `scripts/` makes **no** LLM-provider call. Name the real in-transit surface (the external
  `html`/`pdf`/`transcript-fetcher` subprocesses).
  (e) `security.md:54` — A10 names `wiki-source-light`, a **never-shipped** surface (`scripts/wiki_source/`
  holds only `__init__/base/manual/parsing.py`; no `bin/` launcher; the only reference is a Phase-3b
  *plan* docstring at `base.py:8`) and asserts "не принимает user-supplied URL", false against
  `_fetch.py:490` and `:898`. Rewrite to the **current** posture — the enumerated 2-site egress
  surface, both unguarded, and the falsified `# noqa: S310 (operator URL)` justification
  (`/wiki-reload` re-fetches a URL out of a note's own frontmatter, i.e. H-6 DATA; and urllib follows
  30x silently, so every hop after hop 0 is attacker-chosen regardless of who typed hop 0).
  ⚠️ Write **today's** truth, not the post-P1b truth — 072-07 owns the final control sentence. An
  architecture record that describes an unbuilt fix is the defect this task exists to remove.
  (f) `system-architecture.md:275-285` still presents `wiki-source-light` as implemented, with an
  `anthropic` SDK dependency that **would violate Decision-17**. Prefix the heading:
  **DESIGNED PHASE-1, NEVER SHIPPED**.
  (g) ~~the R-6 entry's grounding contract states two of three — add `NO_CITATIONS`.~~
  ✅ **DONE in 072-03c** (pulled forward deliberately: leaving a known-stale enumeration behind
  while shipping the census that found it would be the drift this bead exists to stop). It is a
  DIFFERENT block from this bead's two targets, so there is no collision — but re-read it before
  editing and do not re-add.
  ★ **ADDRESS ROADMAP BY ANCHOR TEXT, NEVER BY LINE NUMBER.** This bead's own predecessor cited
  `:293-297` / `:1194-1200` / `:284`, then inserted two lines and falsified all three in the same
  commit. Anchors, which cannot drift:
  · the R-7 entry — the heading line beginning `### R-7. \`wiki-research\` (R-20)`;
  · the Epic-6 row — the table row whose first cell is `\`wiki-source-web\``;
  · the deep-research overlap — the paragraph ending with the bare token `\`wiki-research\`.`
  **RED-first**: n/a (no code). Verification is the **run** census, pasted into the bead's notes.
  ⚠️ That last one holds the bare token **alone on its line**, with the sentence wrapping from the
  line above — a single-line `sed` produces a broken sentence. Match the two lines, not one.
  **Do NOT touch** the TASK-local `R-7` requirement IDs (`config/layout-config.schema.yaml:18`,
  `docs/architectures/open-questions.md:610,:852`, `functional/construct-path.md:536`,
  `tests/test_import_prepare_acquire.py`, `tests/test_import_article_apply.py`,
  `tests/test_import_classification.py`, `docs/tasks/task-047-02-retire-enrich.md:33`) — different
  numbering space.
  **Acceptance**: the census command returns only the re-scoped sites; suite/mypy unchanged.

- [ ] **072-01 · The two skill promise sites + H-5 re-pin #1 + the gate that keeps them current.**
  **Files**: `skills/wiki-query/SKILL.md:175` (**NOT pinned — free edit**),
  `skills/wiki-query-synthesis/SKILL.md:159-161` (**PINNED**), `config/skill-integrity.sha256`
  (generated), **new** `tests/test_r7_promise_sites_are_current.py`.
  **What**: both lines point at the **re-scoped** R-7 instead of "deferred", and both stop calling
  **R-8 `wiki-verify-multi` "deferred"** (shipped 2026-05-29; anchor: the heading line beginning
  `### R-8. \`wiki-verify-multi\` (R-21) ✅ DONE 2026-05-29`).
  ★ **Do NOT touch the banners** in the pinned file: the HTML comment at :13-20 and the prose banner at
  :24-30 must keep the literal `SECURITY-SENSITIVE` (`tests/test_h5_skill_integrity.py:325`) and the
  literals `config/skill-integrity.sha256` + `pin_skill_integrity.py` (:331).
  ★ **Do NOT add a `SECURITY-SENSITIVE` marker to `skills/wiki-query/SKILL.md`** "for consistency" —
  its exclusion is deliberate and written down (`_common.py:262-266`, :279-280: an operator
  CLI-reference SKILL.md is high-churn / low blast-radius). Adding one silently enrols it via the
  marker grep and turns `test_registry_equals_the_grep_roster_both_ways` (:98-102) RED.
  **Then, in the SAME commit**: `pin_skill_integrity.py` (expect exit 1 + `~ would re-pin …`) →
  `--write` (exit 0, `7 contracts pinned`). Roster stays **7**; header bytes unchanged.
  **The new gate** — over an **ENUMERATED, globbed** population (`docs/**/*.md` ∪ `skills/**/*.md` ∪
  `workflows/` ∪ `commands/` ∪ `README.md`, minus `docs/{tasks,plans,archive,reviews}/` and
  `docs/TASK.md` — glob it, never hardcode paths), assert no file claims R-7 **or** R-8 is deferred.
  ★ **G-2 — match PARAGRAPH-scoped, not per line and not whole-file**: split on blank lines, normalise
  whitespace *within* a paragraph, and require `R-7`/`R-8` and `deferred` to co-occur in the same
  paragraph **within a ≤200-char window**. It **must MATCH** the pinned file's wrapped :160-161
  sentence and **must NOT match** `docs/ROADMAP.md` — where the `### R-7.` heading and the nearest
  `deferred` are **hundreds of lines apart** (`deferred` occurs on 12 lines there). ★ Re-derive both
  positions at edit time with `grep -n '^### R-7\.' docs/ROADMAP.md` and `grep -n deferred
  docs/ROADMAP.md`; do **not** transcribe them into this plan as numbers — this very sentence used to,
  and a `+2` insertion elsewhere in the same commit falsified it (finding 5, bead 072-03d).
  ★ **G-1 — one reason-carrying exemption**: `docs/architectures/verification-map.md` is a per-task
  requirement-coverage record scoped to TASK 007 by its own heading (:100) — HISTORY, not a forward
  promise. Exempt it in a **named constant whose comment states that ruling verbatim**, and — mirroring
  `test_exempt_files_actually_carry_the_marker` (:111-118) — assert the exempted path **exists**, so
  the exemption cannot silently rot into a typo that exempts nothing.
  ★ **Rule 4 — non-vacuity**: ship a synthetic fixture carrying the wrapped `R-8 \n deferred` pattern
  that the gate **must flag RED**. A gate that can pass by matching nothing is not a gate.
  **RED-first (EXECUTED, twice)**: (i) run the new gate on the current tree **before any edit** — it
  must fail naming exactly `skills/wiki-query/SKILL.md` and `skills/wiki-query-synthesis/SKILL.md`
  (verification-map.md having been cleared by 072-00, and exempted regardless). (ii) run
  `pytest tests/test_h5_skill_integrity.py` **after** the SKILL.md edit and **before** the re-pin —
  ★ **G-3**: the RED set is **`:66` `test_every_pinned_hash_matches_the_live_file`, `:126`
  `test_designated_contracts_are_all_pinned`, `:224`
  `test_all_designated_contracts_report_ok_via_the_shared_gate` (the RUNTIME gate — its RED is the
  evidence drift reaches the rails, not just the file), `:300`
  `test_repin_reports_in_sync_on_the_committed_tree`.** `:105`, `:77` and `:98` compare PATH SETS and
  **cannot** fire on a content-only edit — do not list them. Paste both outputs.
  **Acceptance**: new gate green; `:224`, `:233`, `:325`, `:331` green;
  `git diff config/skill-integrity.sha256` = exactly one line. Suite **3025 passed**.

### Phase 1 — P1a · the `NO_CITATIONS` floor *(independent of P1b and P2)*

- [x] **072-02 · [RED] Both tests, written and executed RED against unmodified `main`.**
  ✅ **SHIPPED `f0f6b71`** — fused with 072-03a, deliberately and on the record: the repo has **zero**
  `xfail` precedent (`grep -rn 'xfail' tests/` → 0), so introducing that convention for a two-commit
  split was rejected. The RED was **executed and pasted into the commit message** instead, which
  preserves both invariants the split existed to protect (the RED is recorded; the tree is green at
  every boundary). Stated here so the deviation is a decision, not a drift.
  **Files**: `tests/test_wiki_query_apply.py` (append; the `_seed`/`_run`/`_prepare`/`_apply` helpers
  at :20-71 already support the shape).
  **Test 1 `test_empty_citations_refused`**: prepare a real question; **assert
  `retrieved_count >= 1` FIRST** (the rule-4 non-vacuity control — the floor must be exercised over a
  corpus where the grounding gate *can* fire); then `_apply(..., citations=[])` ⇒ exit **4**,
  `error == "NO_CITATIONS"`, `field == "citations"`, **no** `_queries/<slug>.md` on disk, and
  `SELECT COUNT(*) FROM pages WHERE type='query'` **== 0**.
  **Test 2 `test_min_hits_zero_cannot_file_an_ungrounded_page`**: `prepare … --min-hits 0` on a
  no-match question (exit 0, `retrieved_count == 0`), then apply with `[]` ⇒ **4 NO_CITATIONS**, and
  with a non-empty list ⇒ **4 CITATION_NOT_RETRIEVED**. Both branches, no file, no row.
  **The RED is already EXECUTED and recorded** (recon probes, on today's `main`):
  *Probe A* — apply with `[]` ⇒ **exit 0**, envelope `{…,"cites":[],"page_indexed":true,"action":"filed"}`,
  `_queries/hermes-routing.md` written with `cites: []` and **no `## Sources`**, `pages` row created.
  *Probe B* — `--min-hits 0` + `[]` ⇒ **exit 0**, page filed **and indexed** with `retrieved_count 0`.
  The exit-0 path to a zero-grounding filed answer is **real, not theoretical**. Mark both tests
  `xfail(strict=True)` in this bead so the tree stays green at the boundary.
  **Acceptance**: both xfail; suite 3026 passed.

- [x] **072-03a · [LOGIC] The floor.** ✅ **SHIPPED `f0f6b71`** (with 072-02, see above).
  **Files**: `scripts/wiki_skills/wiki_query.py`,
  `tests/test_wiki_query_apply.py` (drop the two xfails).
  **Insertion point**: between the shape gate's closing `emit(...)` and the per-entry `"/" in c`
  grammar check — i.e. **after** `citations` is proven `list[str]` (so a non-list still yields the more
  specific `INVALID_CITATIONS`) and **before** any `all()` that would pass vacuously:
  ```python
  if not citations:
      return emit({"error": "NO_CITATIONS", "field": "citations",
                   "reason": "at least one citation is required"}, 4)
  ```
  **No env bypass, no `--allow-uncited`** — the `FIELD_QUOTE_NOT_IN_BODY` doctrine: the *absence* of an
  escape is what makes it a mechanism. (`--force` is not an override; it is consumed downstream at the
  content-hash skip.) Production diff is **3 lines**, which is what makes the mutation legible.
  **EXECUTED mutation**: delete the block ⇒ both tests RED; restore ⇒ green. Paste both runs.
  **Acceptance**: suite 3026, mypy clean, `git diff sql/` empty.

- [x] **072-03b · The pinned synthesis contract + H-5 re-pin #2 — ONE commit, exactly two files.**
  ✅ **SHIPPED `2173902`** (`git show 2173902 -- config/skill-integrity.sha256` = exactly line 12).
  **Files**: `skills/wiki-query-synthesis/SKILL.md` (the citations output-contract table :125-130 gains
  a `≥1 entry → NO_CITATIONS` row), `config/skill-integrity.sha256` (generated).
  Kept separate from 072-03c precisely so `git diff config/skill-integrity.sha256` being exactly line
  12 is verifiable at a glance. Same RED-then-re-pin protocol as 072-01.

- [x] **072-03c · Doc currency for the new code — every enumeration, not the remembered ones.**
  ✅ **SHIPPED `d6f2702`** + roast fix-ups `fd16627`. ⚠️ **Its eradication claim did not hold** — see
  **072-03d**, which owns the residue and the check that terminates the class.
  **Files**: `skills/wiki-query/SKILL.md` (exit table **:155-164** + the `--citations-*` bullet
  :135-138 + the "universal envelope invariant" line :166-167), `workflows/wiki-query.md` (apply error
  table :127-131 **and the `--min-hits 0` advice at :45**),
  `docs/manuals/obsidian-llm-wiki_manual.md` (**:1690** the `--min-hits 0` advice **and :1700** the
  apply-error enumeration), `docs/manuals/obsidian-llm-wiki_manual.ru.md` (**:1735** and **:1746**),
  `docs/architectures/functional/components.md` (:461 citations bullet · :495-497 exit table · **:503
  the grounding invariant** · :453 the `--min-hits` sentence), `docs/architectures/interfaces.md:38`,
  `docs/ARCHITECTURE.md:236`, `scripts/wiki_skills/.AGENTS.md:186`,
  `docs/architectures/verification-map.md:116` (the R-6.7 row).
  **What**: (a) add `NO_CITATIONS` **everywhere the grounding gate is enumerated** — the contract is a
  **triple**: `NO_CONTEXT` (exit 2, prepare: nothing retrieved) · `NO_CITATIONS` (exit 4, apply:
  grounding not claimed) · `CITATION_NOT_RETRIEVED` (exit 4, apply: grounding claimed *outside* the
  recomputed hit set). (b) **Three sites actively INSTRUCT the operator to retry with `--min-hits 0`**
  to request a "no sources found" answer — a path this bead makes un-appliable. Rewrite all three;
  `--min-hits` is **prepare-only** (verified: the apply subparser has no such option), so it is now
  diagnostic-only and cannot reach a filed page. (c) **Delete the phantom `ANSWER_PARSE_ERROR`** from
  `interfaces.md:38` and `components.md:495` — it exists in **zero** lines of `scripts/`. (d) Add the
  four verified table omissions to `skills/wiki-query/SKILL.md` (`INVALID_AUDIENCE`, `INVALID_POLICY`,
  `INVALID_ARGS`, `SKILL_INTEGRITY_DRIFT` — each executed and confirmed reachable).
  **Ruling, recorded so it is a decision not an omission**: `components.md:485-497` is missing **seven**
  codes, but it self-declares as illustrative (:499); `skills/wiki-query/SKILL.md` is the single
  **normative** roster and is where the four-omission fix lands. Write that sentence into the bead.

- [x] **072-03d · ★ [GATE] The machine census — end the class, don't patch its fourth instance.**
  ✅ **SHIPPED `f0e926e`** (gate + all 6 findings + 4 the machine found that three adversarial
  rounds did not) **+ `f54f0fe`** (DF-072-2…5, the repo-wide falsehoods filed per the operator
  ruling of 2026-08-07: *file, do not fix* — three of them touch an Accepted ADR or the
  Decision-17 paragraph, which is an architecture call, not a doc pass).
  Executed RED (5 failed) and executed mutation (2 shapes) are pasted in `f0e926e`'s message.
  Gates at that commit: **3049 passed / 22 skipped** (was 3026/14), `mypy --strict` clean,
  H-5 25/25 with **no pinned contract in the diff**, `git diff sql/` empty.
  **Why this bead exists.** 072-03c ran a doc-currency pass and declared the class closed. Three
  adversarial roast rounds then found the **same two falsehoods on one more file each time**, and the
  loop bound (3) was **exhausted and escalated 2026-08-07**. The mechanism of the non-convergence is the
  finding, and it is new:

  > Each round proved eradication with **`grep -F` for the literal string the previous round had
  > found**. That grep returns 0 *precisely because* the auditor already fixed every place that string
  > occurs. `skills/wiki-extract-concepts/SKILL.md:139` carries the identical falsehood worded as
  > `| 1 | argparse / usage error | — |` and is **invisible** to it.
  >
  > ★ **A census predicate derived from the instances you already found is not a census.** It is the
  > unenumerated-surface lens with extra steps: the search was defined by the answer. The predicate must
  > be derived from the **POPULATION** — walk `skills/*/SKILL.md` and `bin/` and discover the roster at
  > runtime — so a CLI or contract added tomorrow is in scope **without editing the test**.

  **(A) The six confirmed findings** (each reproduced by execution in round 3, then re-confirmed by an
  independent verify agent; 3 further findings were **refuted** and are deliberately not here):
  1. `skills/wiki-verify-multi/SKILL.md:116` — the exit-6 row asserts `VERDICT_FAIL`, "**the verdict page
     IS still filed**", "a SUCCESS envelope (no `error` key)". **All three false**: `build_repo_config`
     raises `SystemExit(6)` with an `INVALID_INDEX_DB` **error** envelope, from **both** subcommands,
     before any work, filing nothing. Exit 6 is **ambiguous in this CLI** — strictly worse than the
     `wiki-query` case, because a caller doing `[ $? -eq 6 ] && treat_as_fail_verdict` reports
     "verification FAILED" when nothing was examined. Same table also omits `SKILL_INTEGRITY_DRIFT`
     (exit 2, prepare-only) — the omission round 1 forced into `wiki-query`'s roster.
  2. `skills/wiki-verify-multi/SKILL.md:118-119` — the `{error, field?, reason}` **only** invariant,
     falsified for this CLI by two captured envelopes (`+hint`; and `{error, integrity}` with neither
     `field` nor `reason`). Port the corrected wording from `skills/wiki-query/SKILL.md:207-211` verbatim.
  3. `docs/architectures/functional/components.md:632` **and** `:634` — the same two falsehoods, in the
     **same file** `fd16627` edited, 9 and 11 lines below its own hunk. `:634` is the identical sentence
     already corrected 133 lines earlier at `:501`.
  4. `skills/wiki-extract-concepts/SKILL.md:139` — `| 1 | argparse / usage error | — |`. **False on both
     axes** (RUN: bare invocation and `prepare --bogus` both exit **2**); the package's single `return 1`
     at `wiki_extract_concepts/__init__.py:1505` carries its own comment saying argparse makes it
     *unreachable*, while the real exit-1 cause — an unhandled traceback with **no envelope** — is
     undocumented. ⚠️ Out of the previous bead's stated `wiki-query` scope; that scope was the defect.
  5. `docs/PLAN.md:101, :106, :110, :161` — **4 of 6** `ROADMAP:NNN` references still stale by exactly the
     `+2` that `d6f2702` itself inserted; `fd16627`'s message claims "both places that referenced it".
     `:101` is the **operative instruction of the unshipped bead 072-00**. Convert all four to anchors
     per this plan's own rule at :141, and correct the claim in the fix-up commit body (it was 2 of 6).
  6. `skills/wiki-query/SKILL.md:161` (MINOR) — the exit-0 row of the table `d6f2702` **promoted to
     "normative"** lists `manifest`; `wiki-query` has no manifest mode (the only two hits in
     `wiki_query.py:556,558` are comments saying the manifest machinery is deliberately bypassed).
     Promoting a table to normative means auditing **every cell**, not the ones a roast named.

  **(B) The gate** — **new** `tests/test_exit_code_doc_truth.py`. Two assertions, both over a roster
  **discovered at runtime**:
  - **Static**: for each enrolled CLI, the set of `(exit_code, error_token)` pairs its `SKILL.md` table
    documents == the set reachable in its module — including **inherited** pairs the CLI does not raise
    itself (`build_repo_config` → `(6, INVALID_INDEX_DB)`, the integrity gate → `(2,
    SKILL_INTEGRITY_DRIFT)`). Those two are what rounds 1 **and** 3 both missed; a census that cannot see
    them is the same vacuous green in a new costume.
  - **Executed**: run each enrolled `bin/` CLI with no args and with a bogus flag, and assert the
    **observed** status matches what its table claims for the usage/argparse row. This is the assertion
    finding 4 fails, and it is derived from the population, not from the string.
  ★ **Both directions** — documented ⊄ reachable is a phantom (finding 6's `manifest`,
  072-03c's `ANSWER_PARSE_ERROR`); reachable ⊄ documented is a blind spot (findings 1, 3). Round 1
  already got burnt asserting one direction of a "must AGREE"; see [[the-unenumerated-surface-lens]] §067.

  **(C) Controls — the test must be able to FAIL** (rule 4: no gate satisfiable by examining nothing):
  - **non-vacuity**: the discovered roster is non-empty, every enrolled member yields ≥1 documented and
    ≥1 reachable pair, and a parser returning `[]` is an ERROR, never a pass;
  - **mutation, EXECUTED and pasted**: inject one false row into one table ⇒ RED; revert ⇒ green;
  - **enrolment completeness**: every `skills/*/SKILL.md` that *has* an exit table is automatically
    enrolled (cross-checked against a walk of `bin/`), and **every exclusion is listed with a reason in
    the test file**. The 3-way partition (CLI with table · CLI with SKILL.md but no table · CLI with no
    SKILL.md) must be asserted, so a new CLI cannot join the silent third bucket.
  ⚠️ Do **not** hardcode `19`. Derive the count; assert the partition sums to the walk.

  **(D) Honest scope.** Free-prose semantic claims ("one JSON envelope per CLI", the no-echo guarantee)
  are **NOT** mechanically assertable by this gate. Say so in the test's module docstring and name the
  fallback — an overclaiming gate is precisely the failure this bead exists to remove.
  **RED-first**: write the gate, watch it go RED on findings 1/3/4/6 **before** fixing them; paste the run.
  **Acceptance**: gate RED pre-fix (pasted) → all six fixed → gate green; suite ≥3026 + the new tests;
  `mypy --strict scripts/` clean; `git diff sql/` empty; H-5 25/25 (this bead touches **no** pinned file —
  if that changes, it takes the re-pin protocol and the two-re-pin count in §0 rule 2 is amended, not
  silently exceeded).

### Phase 2 — P1b · SSRF *(independent of P1a and P2 — do NOT serialise behind them)*

- [ ] **072-04 · ★ [CROSS-REPO PREREQUISITE] The raw-bytes verb in `Universal-skills`.**
  **⚠️ This bead does not touch this repository.** Its work lands in
  `~/dev-projects/Universal-skills/skills/html` (`github.com/MatrixFounder/Universal-skills`) — the
  operator's own repo, symlinked into every harness skills dir. It is therefore **outside this repo's
  pytest / mypy / H-5 gates** and needs its own verification and its own commit there.
  **Why it exists (the deadlock Q-072-1 resolves)**: the html skill **deliberately refuses PDF bytes at
  its CLI** — `acquire.py:688` raises `FetchFailed(details={"kind": "pdf"})` on the `%PDF-` magic — and
  the pdf skill makes **zero** network calls. So the guarded ladder exists
  (`_resolve_validated_addrs:436` · `_pin_host_addrs:479` · `_assert_public_http:516` ·
  `_http_get_bytes:531`) but **the door to it is closed for exactly the file type we need**.
  **RULED — Q-072-1 = B** (operator, 2026-08-06): add a raw-bytes verb (e.g.
  `html get <URL> <OUT> --allow-binary`) that returns the bytes `_http_get_bytes` already fetched,
  **without** the `%PDF-` refusal. Verbs already dispatch at `cli.py:661-663` (`fetch`, `md`), so this
  is a third branch, not a new architecture.
  **Why B and not the others** (record it, or it gets re-litigated): **A2** (import `html2md.acquire`
  in-process and call `_http_get_bytes`) was rejected — its relative imports (`from ._env import env`)
  break the `spec_from_file_location` precedent, it binds us to a **private** API, and `httpx` is
  imported lazily at `acquire.py:556` and is **absent from our `requirements.txt`**, so A2 would either
  add a runtime dep (falsifying TASK 044's NF-2(e) and the A06 roster at `security.md:55-57`) or
  re-exec into the skill's venv — which is B wearing a disguise. **C** (preflight then `urlopen`) is
  rejected on record: `urlopen` re-resolves DNS unpinned and still follows redirects — **porting trust,
  not importing a guard**. **D** (drop PDF-URL support) would remove three live dispatch branches
  (`_fetch.py:1074` arxiv fallback, `:1079` html-reported-pdf, `:1083` `.pdf` suffix) and a real
  workflow. **B keeps the guard at its owner and adds no dependency here.**
  **Bonus, free with B**: the `scripts/html` launcher **re-execs into the skill's own `scripts/.venv`**,
  where `httpx` already lives — so the dependency problem that sank A2 does not exist on this path.
  **Also record here**: **Q-072-2 = (a)** (below, implemented in 072-06) and **Q-072-1 = B**, written
  into `docs/architectures/open-questions.md`.
  ⚠️ **Sequencing risk (R-7 below)**: until this verb ships **and is installed**, 072-07 cannot go
  green. That is what makes OQ-5's capability probe load-bearing rather than cosmetic.

  ### ✅ DONE 2026-08-06 — shipped in `Universal-skills` (uncommitted). What 072-06/072-07 inherit:
  - **The verb**: `html get URL (OUTPUT_PATH | --stdout)` with `--max-bytes` (default 64 MiB,
    finite) · `--timeout` (default 60, bounded `(0,300]`) · `--retries` (0..10) ·
    `--header 'KEY: VALUE'` (repeatable) · `--browser-ua` · `--json-errors`.
    It calls `_assert_safe_target` **then** `_http_get_bytes` — the same two the text path uses.
  - ★ **THE CAPABILITY PROBE IS `grep -q 'html get URL'` — NOT `grep -q -- get`.** The bare form
    **always succeeds** (it matches `--target-selector`), so the fail-CLOSED probe would be
    fail-OPEN. And `html get --help` is **also** invalid: on a build without the verb, argparse
    reads `get` as INPUT, prints the top-level help and exits **0**. The verb roster was added to
    `html --help` for exactly this reason. Use the documented string verbatim.
  - ★ **EXIT MAP CHANGED FROM THE ORIGINAL SKETCH**: a non-http(s) URL is now **exit 2 (usage)**,
    not exit 10. Exit 10 is reserved for a genuine security refusal, so 072-07 can tell a caller
    typo from an SSRF block in its logs. Over-cap carries `details.max_bytes`.
  - **On failure nothing is written; a pre-existing `OUTPUT_PATH` is left UNTOUCHED, not removed.**
    `_download_pdf` pre-creates its path with `mkstemp`, so it must key on the **exit code**, never
    on `out.exists()`, and unlink its own temp on any non-zero return.
  - ★ **072-06 RULING — use `get --stdout`, NOT `fetch --stdout`.** Three verified reasons:
    `fetch --stdout` emits `sanitize_untrusted_html` + `_absolutize_*` (a regex over `<iframe src>`
    would scan a **transformed** document); it runs the full `acquire()` tier ladder, whose
    `--engine auto` can escalate to Chrome (exit 3 if Playwright is absent) and then to the
    **remote reader tier, which sends the URL to a third party** — an egress a best-effort embed
    scan must not silently acquire; and it can raise `Usage` if the reader returns markdown.
    `get --stdout` is byte-verbatim, local-only, single-tier, and needs no temp-file lifecycle.
  - ★ **072-06 REGRESSION TO DECIDE**: today `_download_raw_html` **truncates** at
    `_EMBED_FETCH_MAX_BYTES` (2 MiB) and still scans the prefix — deliberate, since iframe
    discovery is a regex. `get` **aborts** (exit 10). Since the call site wraps discovery in
    `except Exception` → `{"reason": "discovery-failed"}`, a naive port makes **every page over
    2 MiB silently lose all embed discovery**. Choose explicitly: (a) raise the cap to the 64 MiB
    default, or (b) keep 2 MiB and treat `exit 10 + details.max_bytes` as "too large for embed
    scan" rather than a generic failure. **Do not** ask for a `--truncate` flag — undetectable
    truncation is the hazard the verb was designed to exclude.
  - **072-07 parity**: `_download_pdf` sends `Accept: application/pdf,*/*` + a browser UA — pass
    `--header 'Accept: application/pdf,*/*'` (and `--browser-ua` if the old UA mattered), or accept
    a content-negotiation behaviour change on URLs that serve either HTML or PDF.
  - ★ **072-07 timeout — size the subprocess against `--deadline`, NOT `--timeout`.**
    `--timeout` is **per operation** and bounds nothing in total: a redirect chain multiplies it by
    `max_redirects + 1` inside *every* retry pass, and a slow-drip body resets the read timeout on
    each chunk while `--max-bytes` caps only SIZE. Measured: a 5-hop chain stalling *below* the
    timeout ran 2.4× the per-op budget; a body dripping one byte per 1.6 s returned OK after
    12.85 s against a 2 s timeout. At the shipped defaults the redirect case alone is
    `60 × 6 × 4 = 1440 s` — the earlier "~243 s" written here was **wrong by ~6×**.
    `--deadline` (default 300 s) is enforced *inside* the ladder at every hop and every chunk, so
    it is a real bound. Exceeding it is exit 10 with `details.kind == "deadline"`.
  - ★ **072-07 must branch on `details.kind`, never on the bare exit code.** Every FetchFailed maps
    to 10, so `refused` (SSRF / scheme / control chars), `deadline` and a plain transport error are
    indistinguishable by code alone — that exact gap made the skill's own refusal tests **vacuous**
    (with the SSRF blocklist disabled they still passed, having egressed to RFC-1918 and received a
    real `HTTP 404`). `details.max_bytes` marks the over-cap case.
  - **072-06 `--stdout` broken pipe** is exit **141**, not 0: the consumer holds a PREFIX, and
    reporting success would be the undetectable truncation the file path exists to exclude.
  - **Memory**: the body is buffered, so `--max-bytes` is also the memory bound (~2× at the join).
    The old `_download_pdf` streamed at constant memory. Pass a cap sized to the actual need.
  - ✅ **The proxy caveat was FIXED, not just documented** (operator ruling, 2026-08-06, option 3).
    The ladder was building `httpx.Client` with the default `trust_env=True`, so an ambient proxy —
    including a macOS System Configuration proxy invisible to `env | grep -i proxy`; this machine
    has one at `127.0.0.1:1082` — connected to the PROXY, which resolved the target itself, leaving
    `_pin_host_addrs` **decorative**. Measured: pinning `example.com` to a blackholed `192.0.2.1`
    returned **HTTP 200** proxied vs `ConnectTimeout` direct. Now `trust_env=False` + an explicit
    `$HTML_PROXY` opt-in with a one-time stderr notice. **This is a whole-skill change, not just
    `get`** — the text path gains the same guarantee.
    ⚠️ **072-07 still must not claim rebinding is universally closed**: it re-opens by construction
    whenever `HTML_PROXY` is set, and under a **fake-IP resolver** (which this machine runs — real
    hosts resolve into `198.18.x.x`, the reason `HTML_SSRF_ALLOW_NETS=198.18.0.0/15` is the shipped
    default) the pin binds the *synthetic* address, with the synthetic→real mapping owned by the
    proxy tool. Both residuals are in the skill's SKILL.md §5.

- [ ] **072-05 · [RED] Hostile-URL tests through BOTH actual call sites.**
  **Population that matters is provider-returned URLs**, not operator-typed ones: private IP
  (`10.0.0.1`, `127.0.0.1`, `169.254.169.254`), **redirect-to-private**, non-http scheme (`file://`),
  IPv4-mapped/translated forms. Feed each through the **ACTUAL** call site.
  ★ **Rule 4**: every refusal test carries a **positive control** — a public URL that must NOT be
  refused. A guard suite that only ever sees hostile input cannot prove it fails open.
  ★ Add a **non-skippable** resolve test: if the external skill is absent the suite must report a
  *dependency* failure, never a silent skip — a skipped guard test is a vacuous green.
  **Executed RED**: on today's tree `grep -n '_assert_public_http\|is_private\|ssrf' _fetch.py` → **0
  hits**; both call sites accept every hostile case.

- [ ] **072-06 · [LOGIC] `_download_raw_html` → the guarded ladder, via a new launcher key.**
  **RULED — Q-072-2 = (a)** (operator, 2026-08-06). The problem: `_SKILL_BIN_SPEC['html']`
  (`_fetch.py:48`) resolves `scripts/html2md.py`, a 27-line shim that calls `combined_main()` and has
  **no verb routing**; the `fetch` / `md` verbs live on the extensionless `scripts/html` launcher
  (`cli.py:661-663`). So add a **second** spec entry:
  ```python
  "html_launcher": ("WIKI_HTML_LAUNCHER_BIN", ("html", "html2md"), "scripts/html"),
  ```
  ★ **In the SAME commit** add the new var to `config/skills.env.example`, or
  `tests/test_skill_bin_resolve.py::test_env_example_documents_every_var` goes RED — that test is the
  mechanism that stops a new `WIKI_*` var from becoming undocumented. Then add the operator-facing line
  to `docs/architectures/deployment.md` (a new env var is a deployment surface).
  ★ **K-1**: the 8 single-positional monkeypatch doubles in `tests/test_import_video.py`
  (`:351,361,372,394,461,473,489,528`) must be updated **in this bead**, and
  `test_embedded_off_by_default_no_discovery` must be given a real assertion — as written it is
  satisfied by *never calling*, so it would stay **vacuously green** through a total breakage
  (`_append_embedded_videos` swallows the `TypeError` into `embed_log=[{"reason":"discovery-failed"}]`
  at `_fetch.py:958-960`). Fixing that is part of the bead, not a follow-up.

- [ ] **072-07 · [LOGIC] `_download_pdf` → the new verb + the capability probe + docs + the issue.**
  Blocked on **072-04** (the verb must exist and be installed) and 072-06 (the launcher key).
  **What**: replace the `urlopen` at `_fetch.py:490` with a subprocess call to the raw-bytes verb
  through `html_launcher`, and remove the now-false `# noqa: S310 (operator URL)` from **both** sites.
  ★ **OQ-5 ruling applies HERE, not only at P4** (operator, 2026-08-06): `resolve_skill_bin` proves the
  entry **file** exists, never that it supports a verb — and B's verb is **new**, so every install that
  has not been updated will fail. **Probe once per run** (`"$HTML_LAUNCHER" --help | grep -q -- <verb>`)
  and **stop legibly** with a `DEPENDENCY_MISSING`-shaped envelope naming the three remediations —
  never let it surface as a generic `FETCH_FAILED` (exit 10), which is the confusing failure a weak
  model cannot recover from. The probe must **fail CLOSED**: no verb ⇒ refuse, never fall back to
  `urlopen`.
  **Docs**: write the **final** A10 control sentence in `security.md:54` (072-00 wrote the interim
  truth) and correct the residual pointer at `construct-path.md:238-239` — drop "operator-trusted",
  falsified by `/wiki-reload` re-fetching a frontmatter URL and by silent 30x following. ★ Also correct
  `construct-path.md:217-227`, whose central claim ("composing with the html skill's output is
  therefore impossible for embed discovery") is true only of the skill's **Markdown** output —
  `serialize.sanitize_untrusted_html` writes the HTML artifact **without** stripping tags, so iframes
  survive. Left as-is, the architecture argues against the design that just shipped.
  ✅ **Dropped by the B ruling**: `security.md:55-57` (A06 runtime-dep roster), `README.md`'s
  external-dependencies section and `technology-stack.md` §6.1 are **NOT touched** — B adds no runtime
  dependency, so `requirements.txt` is unchanged and the recorded "external binary, **not** a Python
  runtime import" shape (`construct-path.md:194-200`) stays **true as written**.
  **File `docs/issues/<slug>.md`** (Class A) and regenerate the ledger with
  **`wiki-reindex --full --vault obsidian-llm-wiki --vault-root docs`** — never a bare
  `wiki-index-render` off a stale `.wiki/index.db`.

### Phase 3 — P2 · `forbid_values` on `CoverageRule` *(independent of P1a and P1b)*

- [ ] **072-08 · [STUB] Schema + dataclass + build + load gate; the finder still ignores the key.**
  **Files**: `config/layout-config.schema.yaml` (:177-191 properties · **and the block comment at
  :174-175 + the `requires_field` description at :187**, both of which become false the moment the key
  lands), `scripts/wiki_index/models.py` (the frozen `CoverageRule` + its exactly-one-of docstring),
  `scripts/wiki_index/layout_config.py` (`_build` comprehension + `_validate_health_rules`),
  **`scripts/wiki_index/repository.py:397-406`** (the abstract `find_coverage_gaps` docstring — the
  API-level definition of the vocabulary being extended) and
  **`scripts/wiki_index/sqlite_repository/_health_rules.py:19`** (the module-header summary).
  `forbid_values` is bound to `requires_field` via `dependentRequired` (valid **because** the block
  uses `oneOf`, K-2). **Load gate must reject an empty list and a non-string member** — a dead rule is
  **exit 6**, never a silently never-firing one.
  ★ **G-4**: `build_cybos_vault` gains a keyword-with-default parameter, so **all 27 existing call
  sites across 5 files are unchanged by construction** — a structural claim; do not enumerate them.

- [ ] **072-09 · [LOGIC] The SQL third disjunct + the `field-value` gap kind + off-equivalence.**
  The predicate joins the SAME parenthesised gap condition as a third disjunct —
  `OR CAST(json_extract(frontmatter_json, ?) AS TEXT) IN (?,?,…)` — every sentinel **BOUND** via
  `params`, only the placeholder **count** string-composed; the `$.<field>` path is
  `validate_filter_field`-checked and then bound, never interpolated. This is the identical idiom the
  drift `forbid_status` predicate already uses (`_health_rules.py:318-323`).
  **Off-equivalence (ADR-005-D2 style)**: with the key absent, the emitted SQL and every envelope are
  **byte-identical** to today. Ship that as a golden.
  ★ **Rule 4**: the control rule asserts `matched > 0`, not merely `gaps == 0`.

- [ ] **072-10 · P2 docs + the merge gate.**
  **Files**: `docs/adr/ADR-006-derived-knowledge-health.md` (**D-036-3 at :45** — the ADR is the
  authority on what a rule may EXPRESS — **and the denominator table row at :84**),
  `docs/architectures/open-questions.md` (Q-036-3's security sentence; + the Q-072-1/Q-072-2 rulings),
  `skills/wiki-health/SKILL.md`, **`README.md:465`** (the wiki-health row documents the coverage
  vocabulary), `config/.AGENTS.md`, `scripts/wiki_index/.AGENTS.md`.
  ADR-006 must record **why it is a FIELD predicate and not an EDGE one**, because a future reader will
  otherwise re-derive it: `valid_edges = set(_INVERSE_REF_TYPE)` (`layout_config.py:783`), and
  `_INVERSE_REF_TYPE` (15 keys) contains **neither `verifies` nor `cited`** — even though both are
  legal `ref_type` values in the DB CHECK — so `{class: hypothesis, requires_edge: verifies}` is
  **rejected at load, exit 6**.
  ★ **The sentinel strings stay OUT of every built-in layout.** `scripts/wiki_index/layouts/cybos.yaml`
  gets a **comment only** for `forbid_values`, pointing at the vault-override home. Shipping one
  importer's Russian authoring convention in a built-in layout is the thing this bead exists to avoid.
  **Correct refs**: `wiki-config validate` emits `LAYOUT_CONFIG_INVALID` at
  `scripts/wiki_skills/wiki_config/_lint.py:766` (not `scripts/wiki_config/`); the "UNREPRESENTABLE
  rather than merely unreached" doctrine is `scripts/wiki_index/lint.py:660`; the neighbouring test is
  `tests/test_wiki_config_validate.py:367-377`.

- [ ] **072-10b · ★ [BUG — its own issue] The `cybos.yaml` half-support.**
  **RULED — OQ-4 = both** (operator, 2026-08-06): fix the repository **and** ship the operator
  override, because the trap is someone else's future pain and the dogfood needs to run now.
  **The defect, verified programmatically (not by eye)**: `cybos.yaml` declares **`summary`,
  `article-summary`, `meeting-summary`, `lesson-summary`** in `type_mapping`, and its `paths:` list is
  **18 class dirs + `_queries` + `_verifications`** — **zero globs that can see any of them**. An
  import into a cybos vault is written, exits 0, and is then **pruned by the next reindex**. This is
  the TASK-063 conjunction trap (*the layout must map the class AND its read globs must SEE the write
  dir*), live on `main`. `elma-kb` — which holds all 20 hypothesis pages — is a cybos vault, so this
  blocks the P5 §D8 step.
  **(a) Repo fix**: add the missing source-note glob to `scripts/wiki_index/layouts/cybos.yaml`.
  ★ **Verify with `glob_covers` / `resolve_typed_write_dir`, never by eye** — that is the whole lesson
  of the trap. Add a regression test asserting the two-conjunct property for **every** class in
  `type_mapping`, so the next added class cannot re-open the hole silently.
  **(b) Operator override**: the same glob in `<vault>/.wiki/layout.yaml`. ⚠️ That file's `paths`
  **REPLACES** the built-in list entirely (its own header says so), so the override must carry the
  full list, not just the addition.
  **File `docs/issues/<slug>.md`** (Class A) + regenerate with
  `wiki-reindex --full --vault obsidian-llm-wiki --vault-root docs`.
  ⚠️ **Do NOT bundle this with the `forbid_values` edits** — same file, unrelated defect. Separate
  commit, separate issue record.

### Phase 4 — acceptance

- [ ] **072-11 · ★ The doc census (entirely ungated) + final gates.**
  This is the weakest link **by construction** — commit `bc0875a` had to repair both manual appendices,
  stuck at 17 rows with two shipped CLIs never added. One slice (R-7/R-8 currency) is now a real test
  (072-01); the rest are checklist items a hurried developer can tick without running.
  **Mitigation**: each census item is a **command whose output is pasted**, not a checkbox — and the
  `NO_CITATIONS` census is an **expected-file-list diff**, never a presence grep (a presence grep
  reports what is there and is silent about what is missing).
  **Final gates**: `pytest tests/` green · `mypy --strict scripts/` clean ·
  `pin_skill_integrity.py` exit 0, roster 7 · `git diff sql/` empty ·
  `PRAGMA user_version` == 7 · Decision-17 grep clean · both installers run
  (`bin/install-globally.sh`, `bin/install-project-symlinks.sh`).
  **Housekeeping found en route**: `.claude/skills/` is missing `wiki-config`,
  `wiki-extract-decisions`, `wiki-import-article`; `.pi/skills/wiki-enrich` is a **dangling** symlink
  to a directory TASK 047 deleted; `commands/.AGENTS.md` says 18 commands (dir holds 19);
  `workflows/.AGENTS.md` lists 6 (dir holds 8). Only the **global** installer is census-gated — the
  in-repo trees are gated by nothing, which is why both drifts persisted.

---

## 4. RTM — no orphans in either direction

| TASK 072 item | Bead(s) |
|---|---|
| P0 · re-scope R-7 in place (OQ-1) | 072-00 |
| P0 · the promise sites + H-5 re-pin | 072-01 |
| P0 · false `security.md` / `system-architecture.md` claims | 072-00 (interim), 072-07 (final A10) |
| P1a · the `NO_CITATIONS` floor | 072-02 (RED), 072-03a (logic) |
| P1a · doc currency + the pinned contract | 072-03b, 072-03c |
| ★ P1a · **doc-truth made MECHANICAL** (the class 072-03c could not close by hand) | 072-03d |
| P1b · SSRF-guard both call sites | 072-04 (decision), 072-05 (RED), 072-06, 072-07 |
| P1b · the issue record | 072-07 |
| P2 · `forbid_values` mechanism | 072-08 (stub), 072-09 (logic) |
| P2 · docs + no built-in sentinels | 072-10 |
| all · census + gates | 072-11 |

---

## 5. Dependency order — and what is deliberately NOT serialised

```
072-00 ──► 072-01                                        (P0 chain)

072-02 ──► 072-03a ──► 072-03b
                   └─► 072-03c ──► 072-03d               (P1a chain)

072-04 (CROSS-REPO: Universal-skills) ──┐
072-05 ──► 072-06 ─────────────────────►┴──► 072-07      (P1b chain)

072-08 ──► 072-09 ──► 072-10                             (P2 chain)

072-10b (independent bug — any time)
    all ──► 072-11
```

The four chains are **independent** — do not serialise P1b behind P1a, and 072-10b depends on nothing.

⚠️ **Two real couplings.** (1) 072-01 and 072-03b both rewrite `config/skill-integrity.sha256`
**line 12**, so concurrent chains conflict on that line every time — land them in sequence or expect a
trivial rebase. (2) ★ **072-04 is in another repository and must be committed AND installed before
072-07 can go green.** Start it first; it is the only bead whose lead time is not under this repo's
control.

---

## 6. Risk register

| # | Risk | Mitigation |
|---|---|---|
| R-1 | The census bead is ticked without running the commands | Every item is a command whose **output is pasted**; the R-7/R-8 slice is a real test |
| R-2 | ~~072-04 rubber-stamped~~ — **RULED B** | The rejected options and their reasons are recorded in 072-04 so they are not re-litigated |
| ★ R-7 | **072-04 is cross-repo**: the verb must ship in `Universal-skills` **and be installed** before 072-07 can go green — lead time outside this repo's control, and outside its pytest/mypy/H-5 gates | Start 072-04 **first**; the OQ-5 capability probe in 072-07 must **fail CLOSED** so a not-yet-updated install refuses legibly instead of falling back to `urlopen` |
| ★ R-8 | The new verb weakens the html skill's own posture if written carelessly — it exists to bypass a **deliberate** refusal (`acquire.py:688`) | The verb must bypass **only** the `%PDF-` content check, never the ladder (`_assert_public_http` / `_pin_host_addrs` / the byte cap). Verify in the Universal-skills repo, with its own hostile-URL test |
| R-3 | `test_embedded_off_by_default_no_discovery` stays vacuously green through a real breakage | 072-06 gives it a real assertion — named as in-scope, not a follow-up |
| R-4 | 072-05's redirect-to-private test needs a fake `httpx` injected before a **lazily**-imported call in an external module | Verified lazy (`acquire.py:556`); if the seam proves unworkable, escalate rather than weaken the test |
| R-5 | P1b effort under-estimated | Split into 4 beads; re-estimate after 072-04 rules |
| R-6 | The new promise-site gate rots into an exemption that exempts nothing | The exemption asserts the path **exists** and still carries the string |

---

## 7. FOLLOW-ON — explicitly OUT OF THIS PLAN

- **P3** — the operator hand-runs `html --search` → `wiki-import` → `wiki-query` against two real
  `elma-kb` hypotheses. **~1 hour, and it can cancel P4/P5 entirely.** The pre-registered falsification
  criterion (TASK §6) is non-renegotiable.
- **P4/P5** — CONDITIONAL on P3. Per **OQ-2**: ship as a **workflow** (3 markdown files, zero new
  Python); build the rail **only** if the workflow is used **≥ 10 times** (operator, 2026-08-06)
  **AND** an actual egress mistake appears in the recorded `query:` history. Both conjuncts, not
  either. 072-00 writes that number into the ROADMAP entry — a trigger without a number is an
  intention. The workflow's contract must carry the **H-6 nonce-sentinel fence INLINE** — the SELECT
  step reads raw fetched bodies **before** the pinned wiki-import contract loads.
- **P4 write posture — OQ-3 RULED: frontmatter mutation is ALLOWED** (operator, 2026-08-06). The
  workflow may write the target page's frontmatter directly rather than only printing a suggested edit.
  **Guardrails that are not optional, because there is no safety net here:**
  (a) **frontmatter only — the body stays byte-untouched** (`frontmatter.load` → mutate metadata →
  `atomic_write_text`, the sanctioned `wiki_confirm` pattern);
  (b) ★ **re-index the page in the SAME step** (`upsert_one`), or `wiki-lint` reports `hash-mismatch` —
  and note there is **no PW-Q coverage to lean on**: `check_auto_generated_unchanged` iterates
  `config.auto_indexes`, which is `[]` on karpathy / obsidian-personal / cybos;
  (c) a `--dry-run` printing the **exact frontmatter diff** before the first write;
  (d) ★ a `status:` value must be a member of the layout's declared **R-19 ontology enum** for that
  class (`hypothesis` → `[proposed, testing, confirmed, refuted]`), refusing otherwise — this turns an
  advisory declaration into a **write gate on this one surface**, deliberately.
  ⚠️ This **relaxes scope-fence item 11** in `docs/TASK.md` (previously: "prints a suggested edit, a
  human moves the status"). Recorded as a decision, not a drift.
- **Not in scope, recorded**: `_validate_health_rules` never checks `coverage_rules[].class ∈
  type_mapping`, so a typo'd class loads, examines nothing, reports `matched: 0` and does **not** fire
  `NOTE_COVERAGE_VACUOUS`. An ADR-006 D-036-4 honest-denominator hole that **predates** P2 and that P2
  makes easier to hit. ~5 lines, moves nothing in the built-ins. **Do not smuggle it in** — it widens a
  load gate.

---

## 8. Operator rulings — ALL DECIDED 2026-08-06. Nothing blocks.

| ID | Ruling | Lands in |
|---|---|---|
| **Q-072-1** | **B** — add a raw-bytes verb to `Universal-skills/skills/html`. A2 rejected (private API · relative imports break `spec_from_file_location` · `httpx` not in our `requirements.txt`); C rejected on record (porting trust, not importing a guard); D rejected (removes 3 live dispatch branches and a real workflow). | 072-04, 072-07 |
| **Q-072-2** | **(a)** — a second `_SKILL_BIN_SPEC` key `html_launcher` → `scripts/html`, **plus** `config/skills.env.example` in the same commit and a `deployment.md` line. | 072-06 |
| **N** | **10** — and both conjuncts must hold (≥10 uses **AND** a recorded egress mistake). | 072-00 |
| **OQ-3** | **Frontmatter mutation ALLOWED**, under the four guardrails in §7. Relaxes scope-fence item 11. | P4 (follow-on) |
| **OQ-4** | **Both** — repo glob fix + two-conjunct regression test, **and** the operator override so the dogfood can run now. Separate issue, separate commit from the `forbid_values` edits. | 072-10b |
| **OQ-5** | **Probe once per run** (`--help \| grep -q -- <verb>`), stop legibly with a `DEPENDENCY_MISSING`-shaped envelope naming the remediations. **Fail CLOSED** — never fall back to `urlopen`. Operator accepts that a version-pinning contract may be needed later once precedents accumulate. | 072-07 (P1b), then P4 |

**Start order**: **072-04 first** — it is the only bead whose lead time is not under this repo's
control. The other three chains can run in parallel behind it.
