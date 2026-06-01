# TASK 014 — Fix dogfooding findings (ref-slugify + CLI-UX)

### 0. Meta Information
- **Task ID:** 014
- **Slug:** `dogfood-fixes`
- **Mode:** VDD (compact — the filed issues supply the analysis).
- **Closes:** `docs/issues/r-x1-ref-target-not-slugified.md` (R-X1-REF-SLUGIFY, SEV-2)
  + two SEV-3 CLI-UX gaps surfaced in the 2026-06-01 comprehensive dogfood
  (logged below as F2/F3; tracked here, not separate issue files).

### 1. General Description
The 2026-06-01 comprehensive dogfood (dev-vault + karpathy/obsidian-personal/
dev-project sandbox vaults) surfaced one correctness bug and two UX gaps. Fix all.

### 2. Issues to fix (each an RTM row)

#### R-MF14-1 — Ref targets not slugified (R-X1-REF-SLUGIFY, SEV-2) **[primary]**
- **Problem:** `_body_refs` stores the raw wikilink target as `entity_slug`. Under
  non-`identity` slug strategies (`dev-project`=transliterate, `obsidian-personal`=
  preserve-unicode) the page slug is lowercased/separated, so a `[[Title Case]]` /
  `[[Идеи]]` link never matches its (existing) target page → false `orphan-link` +
  broken link graph.
- **Fix (issue Option 1):** slugify the extracted target via the layout's
  `slug_strategy` (`_apply_slug_strategy`) before persisting it as `entity_slug`,
  so it matches page-slug derivation by construction.
- **Byte-identity invariant:** `identity` (karpathy) → `_apply_slug_strategy` is a
  no-op, so karpathy reindex output stays byte-identical (golden anchor must remain
  green).
- **Acceptance:** under preserve-unicode + transliterate, `[[Идеи]]` / `[[Title Case]]`
  resolve to their slug (no orphan); karpathy unchanged; a layout-matrix
  link-resolution test added; the obs-personal dogfood orphan drops to 0 for
  existing-page links.

#### R-MF14-2 — `wiki-query prepare` requires redundant `--vault-root` (SEV-3 UX)
- **Problem:** `prepare` needs both `--vault` and `--vault-root`; the latter is
  derivable from the registered vault's `root_path`.
- **Fix:** make `--vault-root` optional; when omitted, resolve it from the repo
  (the registered vault's `root_path`). Explicit `--vault-root` still overrides.
- **Acceptance:** `wiki-query prepare "<q>" --vault <id> --db-path <db>` (no
  `--vault-root`) works; explicit `--vault-root` still honored.

#### R-MF14-3 — No vault-wide alias listing (SEV-3 UX)
- **Problem:** `wiki-alias --list` requires a `slug` positional (lists one entity's
  aliases); there is no "list all aliases in the vault" surface.
- **Fix:** make the `slug` positional optional when `--list`; with no slug, list
  every alias in the vault (via a repo `list_all_aliases(vault_id)`-style read).
- **Acceptance:** `wiki-alias --list --vault <id>` (no slug) lists all aliases;
  `wiki-alias <slug> --list` still lists that entity's aliases.

### 3. Non-functional
- **Byte-identity (karpathy):** the golden snapshot + `test_karpathy_byte_identity`
  stay green (R-MF14-1 must be an identity no-op).
- **Zero DDL:** `user_version` stays 5.
- mypy `--strict` + full pytest green.

### 4. Constraints
- R-MF14-1 changes reindex ref output for **non-identity** layouts ONLY (intended).
- Keep `_cites_refs` (RAG citation path — explicit slugs) untouched.

## RTM
| Req | Issue | Fix site | Acceptance test |
|-----|-------|----------|-----------------|
| R-MF14-1 | R-X1-REF-SLUGIFY | `reindex._body_refs` + `_apply_slug_strategy` | layout-matrix link-resolution test; karpathy golden green |
| R-MF14-2 | F2 | `wiki_query.py` prepare | prepare works w/o `--vault-root` |
| R-MF14-3 | F3 | `wiki_alias.py` + repo | `--list` w/o slug lists all |
