# Task 019.06: [LOGIC] gate — D1∪D2a union + mode + monotonicity — `skill-tdd-strict`

## Use Case Connection
- UC-1, UC-3, UC-6 · E1.2, E1.3, E2.1, E2.2, E2.4 · AC-1, AC-4, AC-8

## Task Goal
Implement the detector union (D1 ∪ D2a) + `apply_policy` mode handling, and wire the
**monotone gate** into `_build_entries`.

## Changes Description
#### File: `scripts/wiki_skills/_resummarize.py`
- `summary_exists`: per `policy.detect` toggles, short-circuit
  **D1** `repo.get_source_state(vault_id,'sync',rel,'source_hash')` (returns `'source_state'`) →
  **D2a** `repo.find_pages_citing_source(vault_id, rel, policy.detect.provenance_ref.fields)`
  (returns `'provenance'`) → (D2b added in 07). Return matched name or `None`.
- `apply_policy`:
  - `policy is None` → decision unchanged.
  - `decision.action not in {"ingest","convert+ingest"}` → unchanged (**monotonicity**).
  - `force` → unchanged (reason annotate `forced` — set in 08).
  - `mode == "never"` → `Decision("skip","resummarize-never")`.
  - `mode == "always"` → unchanged.
  - `mode == "if-missing"` → `which = summary_exists(...)`; if `which` →
    `Decision("skip", f"summary-exists:{which}")` else unchanged.

#### File: `scripts/wiki_skills/wiki_sync.py`
- `_build_entries(...)`: after `classify_file` → `d = apply_policy(d, path=cand.path,
  rel=cand.rel, vault_root=vault_root, repo=repo, vault_id=vault_id,
  policy=resolve_policy(cand.path, vault_root=vault_root, vault_config=config), force=force)`
  (add `force: bool = False` param; threaded from CLI in 08).

## Test Cases
### Unit (RED-first per `skill-tdd-strict`)
1. **TC-06-1 (monotonicity):** an `upsert`/`skip` decision is NEVER changed by `apply_policy`.
2. **TC-06-2 (D1):** recorded `source_state` → `skip:summary-exists:source_state`.
3. **TC-06-3 (D2a):** a citing page → `skip:summary-exists:provenance`.
4. **TC-06-4 (never):** `mode:never` → `skip:resummarize-never` for raw; `upsert` untouched.
5. **TC-06-5 (always):** `mode:always` → raw stays `ingest`.
6. **TC-06-6:** no detector matches → raw stays `ingest`.

## Acceptance Criteria
- [ ] Gate is monotone; union short-circuits; bead-00 golden green (policy=None path).
- [ ] `mypy --strict` clean; regression green.

## Notes
Strict bead: TC-06-1 (monotonicity) RED first — it is the core safety invariant.
