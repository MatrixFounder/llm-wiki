# Task 012-15: R-X2.3 (Phase B) — bootstrap one peer dev-vault + cross-project search

## Use Case Connection
- UC-33: `wiki-search "M-4" --vaults all` returns hits spanning ≥2 dev-vaults.

## Task Goal
Bootstrap a second project (a peer repo) as a dev-vault and prove the killer feature:
cross-project FTS5 search across vaults. Confirms the multi-vault promise on real data.

## Changes Description

### Operator-run bootstrap (peer repo)
1. Peer = **`Universal-skills`** by default (operator may pick `trade-agents` — Q-012-g;
   confirm at this bead). `wiki-init --register-existing --layout dev-project --vault <peer>
   --vault-id <peer-slug>` → writes the peer's `docs/WIKI_SCHEMA.md`, registers it.
2. `wiki-reindex --full --vault <peer-slug>`.
3. `wiki-search "M-4" --vaults all` → ranked hits from BOTH `obsidian-llm-wiki` and the peer,
   each tagged with its `vault_id` + snippet.

> **Cross-repo note:** this writes a `docs/WIKI_SCHEMA.md` into a *peer* repo (a small,
> additive, gitignored-DB-safe change there). It does NOT touch agentic-development
> (R-X2 Phase C is deferred — D-012-4). Coordinate the peer-repo file as its own commit there.

### Changes in Test Files
#### File: `tests/test_cross_project_search.py` (NEW)
- Two `dev-project` fixtures (each with a doc mentioning a shared token, e.g. `M-4`); register
  both; `search_pages("M-4", vaults=["all"])` (or the multi-vault API) → hits from both
  vault_ids; the private-vault-exclusion default does not regress (proposal §7.3 — assert the
  existing default behaviour unchanged, not a new feature).

## Acceptance Criteria
- ✅ `wiki-search "M-4" --vaults all` returns cross-project hits spanning ≥2 vault_ids.
- ✅ Private-vault default not regressed.
- ✅ `mypy --strict` clean; suite green.

## Stub-First
Integration/dogfood bead. Test uses two fixtures; the peer-repo `WIKI_SCHEMA.md` registration
is the (peer-repo) deliverable.
