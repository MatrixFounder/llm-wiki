# task-015-05 — Implement `slugs-only` path in `prepare`

**Parent:** TASK 015. **Depends on:** 015-04. **RTM:** R-015-3, AC-015-3, AC-015-4.

## Goal
Implement the `slugs-only` branch in `prepare()`: when `args.known_concepts_format ==
'slugs-only'`, emit `known_concepts` as a plain list of slug strings instead of the full
list of dicts.

## Steps

1. In `prepare(args)` in `scripts/wiki_skills/wiki_extract_concepts.py`, after:
   ```python
   known = load_known_entities(repo, args.vault)
   ```
   Add:
   ```python
   if args.known_concepts_format == "slugs-only":
       known_out: list[dict[str, Any]] | list[str] = [e["slug"] for e in known]
   else:
       known_out = known
   ```
   Replace `"known_concepts": known` with `"known_concepts": known_out` in the `emit` call.

2. `test_prepare_slugs_only_format` → GREEN:
   - Asserts `all(isinstance(item, str) for item in result["known_concepts"])`.

3. Add regression `test_prepare_full_default` (AC-015-4):
   ```python
   def test_prepare_full_default(minimal_vault_with_entity: Path) -> None:
       """prepare without flag emits full dicts (backward-compat, AC-015-4)."""
       result = run_prepare(minimal_vault_with_entity)
       known = result["known_concepts"]
       assert isinstance(known, list)
       if known:  # skip if no entities
           assert isinstance(known[0], dict)
           assert "slug" in known[0]
           assert "name" in known[0]
           assert "type" in known[0]
           assert "aliases" in known[0]
   ```

4. `pytest -q` all green. `mypy --strict scripts/` clean.

## Acceptance
- ✅ `test_prepare_slugs_only_format` GREEN (AC-015-3): `known_concepts` = `list[str]`.
- ✅ `test_prepare_full_default` GREEN (AC-015-4): `known_concepts` = `list[dict]` with required keys.
- ✅ Existing `test_wiki_extract_concepts.py` prepare tests pass unchanged.
- ✅ mypy strict clean (union type annotation on `known_out` resolves).

## Notes
- The `--known-concepts-format` flag is on the `prepare` subparser only; `apply` and
  `--batch-candidates` are unaffected by this flag.
- The type annotation `list[dict[str, Any]] | list[str]` may need `from __future__ import annotations`
  (already present in the file) or a `Union` alias for mypy compat.

## Files
- `scripts/wiki_skills/wiki_extract_concepts.py` (implement `slugs-only` branch in `prepare`)
- `tests/test_perf_hardening.py` (`test_prepare_slugs_only_format` GREEN + `test_prepare_full_default`)
