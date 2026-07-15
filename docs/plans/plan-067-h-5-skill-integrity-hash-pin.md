# PLAN 067 — H-5 skill-contract integrity (stub-first)

Traces `docs/TASK.md` (TASK 067). Stub-First: **Phase 0** lands every test RED (structure + failing
assertions), **Phase 1** turns them green with the real mechanism, **Phase 2** closes docs + ledger.
Each checklist item names the `R-067-N` it discharges (spec-validator contract).

**Baseline to preserve:** `1 failed (pre-existing, carved §8), 2904 passed, 14 skipped`. Success =
**0 NEW failures**, the pre-existing `test_the_artifact_is_not_STALE` **unchanged**, `mypy --strict scripts/` clean.

---

## Phase 0 — Stub-First: structure + RED tests

- [ ] **067-00a** (R-067-1, R-067-2, R-067-3, R-067-5, R-067-6, R-067-7, R-067-8) Create `tests/test_h5_skill_integrity.py` with the FULL test roster, all RED against stubs:
      `test_every_pinned_hash_matches_the_live_file`, `test_every_marked_contract_is_pinned_or_exempted`,
      `test_verify_skill_integrity_detects_drift` + `test_result_never_echoes_the_body`,
      `test_all_four_prepare_rails_emit_ok_integrity`, `test_default_warns_strict_refuses`,
      `test_repin_script_roundtrips`, `test_every_roster_contract_carries_the_marker` +
      `test_edited_banners_cite_the_manifest`.
- [ ] **067-00b** Stub `verify_skill_integrity()` + result type in `_common.py` (returns a fixed `unpinned`);
      stub `scripts/pin_skill_integrity.py` (`argparse` skeleton, `--write`, exits 0). Importable, mypy-clean.
- [ ] **067-00c** (R-067-2) Confirm the roster is **grep-derived, never hand-listed** in the test — the marker scan
      drives the assertion so a future banner'd contract auto-enrolls (the unenumerated-surface guard).

## Phase 1 — Implement the mechanism (RED → GREEN)

- [ ] **067-01** (R-067-3) `_common.py`: add `_REPO_ROOT` (the `layout_config` idiom), `SKILL_INTEGRITY_MANIFEST`,
      `load_integrity_manifest()`, and the real `verify_skill_integrity()` → value-free `{status, skill, expected,
      actual}`, `status ∈ {ok,drift,unpinned,manifest_unavailable}`, **no body substring ever**.
- [ ] **067-02** (R-067-1, R-067-7) Implement `scripts/pin_skill_integrity.py`: derive the roster by marker-grep
      minus the exempt set, hash each, write `config/skill-integrity.sha256` in `sha256sum` format under `--write`;
      without `--write` print the diff and exit non-zero on drift. Run it to **generate the real manifest** so the
      hash-match test goes green; assert it pins EXACTLY the roster.
- [ ] **067-03** (R-067-2) Land the population + exemption logic: `_INTEGRITY_EXEMPT = {wiki-verify-multi: reason}`;
      every `SECURITY-SENSITIVE` file must be pinned or exempt.
- [ ] **067-04** (R-067-5, R-067-6) Wire the FOUR `prepare` rails (`wiki_extract_concepts`, `wiki_extract_decisions`,
      `wiki_query`, `wiki_verify_multi`) to compute their contract's integrity and add an `integrity` block to the
      envelope; on non-`ok` → `warnings` + exit unchanged (default), or exit 2 `SKILL_INTEGRITY_DRIFT` under
      `--strict-integrity` / `WIKI_STRICT_SKILL_INTEGRITY=1`. Clean tree ⇒ all four emit `status:"ok"`. Fix any
      existing envelope-key-set assertions the new block trips.
- [ ] **067-05** (R-067-4) ★ Execute the MUTATION: append one byte to a pinned `SKILL.md` (NOT re-pinned) ⇒
      `test_every_pinned_hash_matches_the_live_file` RED; revert ⇒ green. Record the run.
- [ ] **067-06** (R-067-8) Add the M-4 banner to `decision-extraction/SKILL.md`; re-point the `wiki-query-synthesis`
      + `wiki-verify` banners at the manifest/mechanism (both coupling-free); leave `concept-extraction` byte-stable.
      All four still carry the marker.

## Phase 2 — Docs, invariants, ledger

- [ ] **067-07a** (R-067-9) Amend the "Load skill" step of all four workflows (`wiki-extract-concepts`,
      `wiki-extract-decisions`, `wiki-query`, `wiki-verify-multi`) to **STOP** when `prepare …
      integrity.status != "ok"` before loading the contract.
- [ ] **067-07b** (R-067-10) Confirm **Decision-17 survives**: no `anthropic` import added; each rail still one JSON
      envelope + stable exit code; run the existing absence gates. Assert **zero DDL** (`git diff sql/` empty).
- [ ] **067-07c** (R-067-8) Docs: `docs/ARCHITECTURE.md` (durable-invariant note on skill-contract integrity) +
      relevant `.AGENTS.md` (`scripts/wiki_skills/`, `config/`); the edited banners cite the mechanism.
- [ ] **067-07d** Update `docs/issues/h-5-*.md` → `status: mitigated` with the honest residual (§3), then
      regenerate `docs/KNOWN_ISSUES.md` via **`wiki-reindex --full --vault obsidian-llm-wiki --vault-root docs`**
      (NOT a bare render — the docs-ledger-regen gotcha).

## Phase 3 — Gates (caller-side)

- [ ] **G1** `pytest tests/ -q` — 0 NEW failures, pre-existing red unchanged; new count + skips stated.
- [ ] **G2** `mypy --strict scripts/` clean.
- [ ] **G3** `python3 .agent/skills/skill-spec-validator/scripts/validate.py --mode plan docs/PLAN.md docs/TASK.md`.
- [ ] **G4** Adversarial review (Phase 4) converges: 0 CRITICAL, no legit logic/security/slop finding.
- [ ] **G5** `sha256sum -c config/skill-integrity.sha256` (from repo root) passes — the out-of-band verifier agrees.

---

### Stub-First rationale

The mechanism is a **gate**, so its defining property is *"it can go RED."* Phase 0 writes the RED tests before
the manifest exists (the primitive returns `unpinned`); Phase 1's very first green is R-067-1 the moment the real
manifest is generated — proving the gate was actually failing and the fix actually closed it. R-067-4 then proves
it can fail AGAIN on a fresh mutation, so the green is not a green-forever accident.
