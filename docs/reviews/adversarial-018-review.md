# VDD Critique: TASK 018 `wiki-sync` (spec + architecture)

> Adversarial design review (`/vdd-adversarial`, adapted to pre-implementation
> artifacts). Multi-agent fan-out: 6 lenses × critic → **per-finding refutation**
> (default-refuted) → completeness meta-pass. Run `wf_2b38a52f-59f` — 45 agents,
> ~3.9M tokens. **38 raw findings → 33 survived refutation** + 4 meta dimensions.
> Full per-finding detail (claim/evidence/refuter rationale): the run result JSON.

## 1. Executive Summary
- **Verdict:** **FAIL → AMENDED** (the design as gated had a CRITICAL idempotency
  flaw + 2 HIGH feasibility errors; all corrected inline — see §4).
- **Confidence:** High (findings are code-grounded; the CRITICAL cluster was hit
  independently by 5 of 6 lenses).
- **Summary:** The adversary broke the architecture exactly where I patched it: the
  **AM-1 idempotency "fix" is factually wrong against the code**, the **`iter_pages`
  reuse can't even discover the raw drops**, and **`wiki-index-upsert` is not a free
  "as-is" upsert**. None were caught by the task/arch reviews. Fixed by a unified
  **`wiki-sync`-owned `source_state` partition** + an **own bounded walk** + an
  **unmappable-type branch** + security/edge/meta tightenings. Zero DDL preserved.

## 2. Root-cause cluster (CRITICAL) — the idempotency story was wrong

Eleven findings (**ID-1, RC-3, EC-3, SEC-A2, F2, F3, ID-2, CONS-1, CONS-2, CONS-4,
ID-4**) share ONE root, verified against code:

- `wiki-enrich` / vendored `ingest()` write **NO `source_state` row** — raw
  idempotency is a `source_hash:` **frontmatter footer** in `_sources/<slug>.md`
  (`ingest.py::_record_source_hash_footer`), keyed by the *summary slug*.
- The only `source_state` writer in the chain is `wiki-extract-concepts`
  (`source_kind='extract-concepts'`, scope = *source-page slug*).
- ⇒ There is **no `source_state` key representing "this raw `.vtt`/`.docx` was
  already ingested"**, and the durable slug is **not knowable at `scan` time**
  (it's derived post-summarisation). So `is_unchanged` for `ingest`/`convert+ingest`
  as written (AM-1) **cannot be computed**, and the "no new DAL surface" claim is
  false. AC-5 "re-run is a no-op" was unmeetable on the expensive LLM step.

**Resolution (consensus across critics) — adopted in §4:** a **`wiki-sync`-owned
idempotency partition** on the existing `source_state` table: `source_kind='sync'`,
`scope=<vault-relative source path>`, `key='source_hash'`, `value=sha256(bytes)`
(original binary bytes for `convert+ingest`). `scan` hashes the discovered file and
reads the row (new generic read-only DAL getter); the **executor writes the row only
after the per-file chain fully succeeds** (commit marker → partial-failure resumes;
downstream tools' own idempotency makes re-runs cheap). **Zero DDL** (`source_state`
has no `source_kind` CHECK — `'sync'` is just data). Uniform across all non-skip
actions (also dissolves the `pages.file_hash`/file_path/rename complications of ID-3).

## 3. Findings by severity (33 confirmed + 4 meta)

| Sev | IDs | Theme |
|---|---|---|
| **CRITICAL** | ID-1 | Idempotency: no raw-keyed `source_state` row exists → `is_unchanged` uncomputable (cluster, §2). |
| **HIGH** | RC-3, EC-3, SEC-A2, F3, ID-2 *(idempotency cluster)* · **EC-1, ID-5** (`iter_pages` can't discover non-`.md`/raw drops — scan needs its OWN walk) · **EC-2** (`wiki-index-upsert`→`UnmappedTypeError` on type-less prose `.md`) · **ID-3** (upsert fast-path needs path-lookup + slug re-derive; rename orphans) · **SEC-A1** (no H-6 armor at the *first* LLM stage `summarizing-meetings`) · **META-1** (plan-entry ordering/determinism unspecified vs AC-1). |
| **MED** | RC-1 (`.vtt`/`.srt` de-timestamp E1.3b has no design surface) · RC-4 (only-a-view matcher under-specified) · RC-5 (Q-018-2 reuse: drop `_detect_grouping`) · EC-5/SEC-A4 (staging `_raw/<stem>.md` collision/clobber) · EC-6 (extension case-fold + `.excalidraw.md`/`.canvas`) · EC-7 (degenerate inputs: empty file, frontmatter parse-fail) · SEC-A3 (`validate_inside_vault(strict)` can't validate a not-yet-existing target) · SEC-A5 (`.wiki/sync.yaml` size-cap/anchor-bomb) · F2/CONS-2 (drop "no new DAL surface") · ID-4 (partial-failure resume) · CONS-3 (`#wiki/keep` missing from mermaid + walk-ordering) · CONS-4 (convert+ingest hashes original binary) · META-2 (concurrency/lock) · META-3 (report format) · META-4 (name `config/sync-config.schema.yaml`). |
| **LOW** | RC-6 (UC-4 CLI `wiki-sync --dry-run` → `scan … --dry-run`) · RC-7 / F5 (fast-path read-cost wording) · EC-9 (folder-note that is real content) · SEC-A6 (refuse symlinked *dir* in walk) · ID-6 (dry-run opens repo — read-only, clarify). |
| **BIKESHED** | CONS-5 (mermaid evaluates view-branch before `#wiki/skip`; skip wins regardless — reorder for clarity). |

## 4. Resolution — design amendments applied

1. **Idempotency redesign (CRITICAL cluster)** — `wiki-sync` `source_state`
   partition (`source_kind='sync'`, scope=path, `source_hash`); new read-only
   `get_source_state` + `set_source_state` DAL (zero DDL); executor writes on
   success; AM-1 wording corrected in `functional-architecture.md` + `interfaces.md`
   §5.4 (drop "no new DAL surface" → "zero DDL + one generic source_state get/set");
   `convert+ingest` hashes the original binary; partial-failure = no row → resume.
   (TASK AC-12; ARCH Q-018-8.)
2. **Own bounded walk (EC-1/ID-5)** — `wiki-sync scan` does NOT reuse `iter_pages`;
   it implements its own zone walk over the wiki-sync extension set, *mirroring*
   `iter_pages`' single-stat + early-extension-skip discipline. Corrected in TASK
   E3.1e, `functional-architecture.md` bounded-walk, `interfaces.md` §5.4.
   (ARCH Q-018-9.)
3. **Upsert feasibility (EC-2)** — a no-tag `.md` routes to `upsert` ONLY if it
   carries a layout-mapped frontmatter `type:` (or sits under a `path_type_fallback`
   subdir); else → `skip` reason `unmappable-type` (flagged, never `UnmappedTypeError`
   crash). TASK E2.3 + mermaid + AC-4b.
4. **Security (SEC-A1/A3/A4/A5, SEC-A6)** — `security.md` §7.5: H-6 fence applied at
   the **first** LLM stage (executor fences raw/converted bodies before
   `summarizing-meetings`); `validate_inside_vault` on the existing `_raw/` parent +
   `O_NOFOLLOW` symlink refusal (target *and* dirs); collision-safe staging name
   `_raw/<slug(stem)>-<ext>.md` + refuse-overwrite-different-content; `.wiki/sync.yaml`
   size-cap (256 KiB) + `safe_load` (no anchor expansion).
5. **Edge/consistency (EC-5/6/7, EC-9, CONS-3/5, RC-1/4/5/6)** — case-insensitive
   extension; `.excalidraw.md`/`.canvas` skip; empty-file + unparseable-frontmatter
   rules (never raise); folder-note skipped only if *also* only-a-view; `#wiki/keep`
   node + exclude-zone gate added to the mermaid (skip-check ordered first);
   `.vtt`/`.srt` de-timestamp pre-step (reuse transcript-fetcher `_vtt_to_text.py`);
   Q-018-2 drops `_detect_grouping`; UC-4 CLI corrected.
6. **Meta (META-1/2/3/4)** — plan `entries[]` sorted by vault-relative POSIX path
   (+ determinism AC-13); per-vault advisory `flock` during execute (single-actor
   precondition stated); report contract (Plan `summary{}` + per-entry `result`);
   `config/sync-config.schema.yaml` named (strict; `exclude`×`keep` precedence pinned
   at the loader).

## 5. Convergence
Not yet zero-slop: the CRITICAL + 6 HIGH were legitimate and are now amended at the
**design** level (this is pre-implementation, so "fix" = correct the spec/arch, not
code). After the amendments the residual set is MED-and-below, each with a concrete
Planning-phase resolution. **Recommendation: re-gate the amended architecture, then
PROCEED to `/vdd-plan`** — Planning must carry the operationalized matchers
(only-a-view body-ratio, the de-timestamp step, the sync-config schema) into beads.

## 6. Hallucination Check
- [x] Files cited by critics confirmed to exist (TASK.md, ARCHITECTURE.md + 4 chunks, the two review files, `wiki_enrich.py`, `wiki_ingest/commands/ingest.py`, `wiki_extract_concepts/_db.py`, `karpathy.yaml`, `sqlite_repository.py`).
- [x] Code claims (footer vs table idempotency; `_SOURCE_KIND='extract-concepts'`; `UnmappedTypeError` in `upsert_one`→`normalize_frontmatter`; `iter_pages` `.md`-only) were quoted by the refuters against the real files.

```json
{ "review_file": "docs/reviews/adversarial-018-review.md", "verdict": "FAIL_AMENDED", "confirmed": 33, "meta": 4, "critical": 1, "high": 6 }
```
