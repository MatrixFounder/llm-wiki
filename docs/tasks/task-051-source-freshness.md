# TASK 051 — Source freshness: the connector substrate (R-18)

## 0. Meta Information
- **Task ID**: 051
- **Slug**: source-freshness
- **ROADMAP**: R-18 (P2, effort **S** — a+b code, c docs). Enterprise-readiness theme
  (ADR-009 pillar-2 substrate; follows R-16/R-17 = TASK 049/050).
- **Context**: The wiki is a **pull-refreshed knowledge cache**, not a live query proxy
  (Class A/B layering + H-6 forbid query-time fetch-through; freshness SLA = fetcher
  cadence, stated plainly). R-18 makes "keep sources current" cheap and defines the
  connector substrate so Epic 6 becomes "any exporter + a zone config", not "N adapters".
- **Revision**: v2 — reframed after task-review (C-1/M-1/M-2/M-3): the Epic-A gap is
  *plan-layer* (`if-missing` skips a **changed** marker-bearing file), NOT "`always`
  re-LLMs everything"; Epic B is an always-on optimisation with a `--force` escape.

## Problem / Motivation

### The `wiki-sync` two-layer skip model (ground truth — the premise Epic A corrects)
`wiki-sync` skips redundant work at **two** layers:
1. **Plan layer** — `_resummarize.apply_policy` turns an actionable candidate into
   `skip:summary-exists:<detector>` under `mode: if-missing` when `summary_exists` fires
   (`source_state` marker **presence** ∪ provenance ∪ mirror — [_resummarize.py](../scripts/wiki_skills/_resummarize.py) L193-229).
2. **Executor layer** — for any entry the plan did **not** skip, `wiki-sync scan` records
   `source_hash = sha256(file)` and an `is_unchanged = (recorded == current)` flag
   ([wiki_sync.py](../scripts/wiki_skills/wiki_sync.py) L218-232); the executor no-ops
   `is_unchanged` entries ([workflows/wiki-sync.md](../workflows/wiki-sync.md) L105).

Consequence: `mode: always` does **not** re-LLM unchanged files — the executor's
`is_unchanged` no-op already covers them. The genuine bug is at the **plan layer**:

- **Bug — a *changed* marker-bearing file is skipped under `if-missing`.** D1
  (`source_state`) fires on marker **presence**, so `apply_policy` returns
  `skip:summary-exists:source_state` and the executor never even evaluates
  `is_unchanged` (it skips on `action == "skip"`). A source whose raw content **changed**
  since last summarised is therefore silently frozen. The only refreshers are `--force`
  or `mode: always` — and `always` is a blunt instrument (it also re-summarises
  externally-authored summaries that D1's marker doesn't cover, via provenance/mirror).
  **The staleness signal already exists** (`source_state.source_hash`); the plan gate just
  can't act on it.

### The second gap + the missing contract
- **A re-poll of an *unchanged* URL still runs REASON.** `wiki-import prepare` computes
  `source_hash = sha256(converted _raw bytes)` ([__init__.py](../scripts/wiki_skills/wiki_import_article/__init__.py) L299)
  but writes `_raw/<slug>.md` unconditionally (L305) and never compares against the
  pre-existing `_raw`. So a scheduled re-poll of an unchanged source drives a full REASON
  pass for no delta — there is no `is_unchanged` short-circuit (the envelope precedent
  `wiki-extract-concepts` / `wiki-query prepare` already use).
- **"Connector" is undocumented tribal knowledge.** No stated contract for what a source
  connector *is*, so Epic 6 reads as "build N adapters". The substrate already exists
  (zone + stable filename + `.wiki/sync.yaml`); nothing names it.

## Goal

Three orthogonal slices, **additive / zero-DDL**, no new authored frontmatter, no live
fetch-through. (Note the OFF-posture differs per slice — see each Epic.)

- **(a)** a new `resummarize.mode: **if-changed**` = `if-missing`'s D1 gate keyed on hash
  **equality** instead of hash **presence**: skip iff a recorded `source_state` hash
  matches the file; a changed (or never-recorded) file re-summarises (~30 LOC + one enum).
  **OFF by default** (global default stays `if-missing`; a zone opts in).
- **(b)** an `is_unchanged` short-circuit in `wiki-import prepare` so an unchanged re-poll
  costs **one fetch+convert+hash and NO REASON pass** (the write + attachment copy/GC +
  context-build + orchestrator summarise are skipped). **Always-on** optimisation with a
  `--force` escape (see M-2 rationale in Epic B).
- **(c)** the **connector contract** written down (docs + one template): connector = any
  executable materialising one file per business object into a `wiki-sync` zone with a
  **stable filename = stable external key**, plus a zone-local `.wiki/sync.yaml`.

---

## Epic A (R-18-a) — `resummarize.mode: if-changed`

**Delta.** Add `if-changed` to the `resummarize.mode` enum + a fourth `apply_policy`
branch: consult **only** the D1 `source_state` detector — if a `source_hash` is recorded
for this rel AND equals the current file's `sha256`, return `skip:summary-unchanged`;
otherwise (hash differs, or **no record at all**) return the decision unchanged
(→ re-summarise). `--force` re-arms uniformly (reason `forced`, as the other modes do —
`apply_policy` L256/L268). Provenance/mirror are deliberately NOT consulted (they prove
*existence*, not *content sameness*; "no recorded hash" ⇒ re-summarise is the safe choice
— at worst one extra pass, never a silent stale skip).

- **Files**: [_resummarize.py](../scripts/wiki_skills/_resummarize.py) (`apply_policy`),
  [sync_config.py](../scripts/wiki_index/sync_config.py) (`ResummarizeConfig` validation),
  [config/sync-config.schema.yaml](../config/sync-config.schema.yaml) (enum + docs).
- **Hash source (Q-051-1).** The current-file hash MUST be **passed into** `apply_policy`
  by the scan caller, not re-read inside — but today `scan` computes `_hash_file` **after**
  the gate and only for `action != "skip"` ([wiki_sync.py](../scripts/wiki_skills/wiki_sync.py) L218).
  So Epic A must **hoist** the hash of ACTIONABLE candidates ahead of the gate and thread
  it in (avoids a second read of a large raw). Architecture to spec the reorder + signature.
- **Relation to `always` + executor `is_unchanged` (Q-051-5).** `always` + the executor
  no-op and `if-changed` make **identical re-summarise decisions** for every file class
  (both re-summarise a changed marker file AND a markerless file; both no-op/skip an
  unchanged marker file) — so the value of `if-changed` is NOT a behavioural difference but:
  (i) an **explicit plan-layer** `skip:summary-unchanged` (observable in `scan` output, not
  a silent executor no-op); (ii) **no delegate entry** emitted for unchanged files (cleaner
  plan, no wasted `resolve_summarize`); (iii) it fixes the `if-missing`-changed-file
  plan-skip (the real bug); (iv) a semantically clear connector-zone default (whose sources
  are machine-materialised, not hand-authored summaries, so the D1-markerless concern does
  not arise there). Architecture must rule between the three designs in Q-051-5.

## Epic B (R-18-b) — `is_unchanged` short-circuit in `wiki-import prepare`

**Delta.** After the existing symlink refusals ([__init__.py](../scripts/wiki_skills/wiki_import_article/__init__.py)
L276/L284) and **before** the unconditional write (L305): if `raw_path` exists as a
regular file, read+hash it; if that hash equals the freshly-computed `source_hash`, emit
`is_unchanged: true` in the envelope and **return without writing** (no `_raw` rewrite, no
attachment copy, no `_attachments` GC, no `known_concepts`/`existing_page_slugs`
context-build) — the orchestrator STOPs (no REASON, no `apply`). On any mismatch (or no
existing `_raw`), behaviour is byte-identical to today.

- **Not "default-OFF" — always-on (M-1).** Epic B has no gating config; it changes the
  unchanged-**re-import** path unconditionally (today: rewrite + full envelope → REASON →
  `apply` overwrites the note; after: STOP). This is a strict, delta-free optimisation, so
  it is safe as always-on — but it is NOT byte-identical for that case, so the byte-identity
  invariant is scoped to *first import / changed raw*.
- **`--force` escape (M-2).** `wiki-import prepare` exposes **no** force flag today. Add
  `--force` (skip the `is_unchanged` short-circuit; always rewrite + full envelope) so an
  operator can regenerate after a REASON-harness change or a corrupt prior summary without
  hand-deleting `_raw`. Mirrors `wiki-sync`'s `--force` precedent.
- **Envelope precedent, not detection mechanism (m-2).** Epic B reuses the STOP-on-
  `is_unchanged` **envelope** contract of extract-concepts/query; the **detection** here is
  file-vs-file (`_raw` on disk), not file-vs-DB-marker.
- **Files**: [wiki_import_article/__init__.py](../scripts/wiki_skills/wiki_import_article/__init__.py)
  (`prepare` + arg parser `--force`), [skills/wiki-import/SKILL.md](../skills/wiki-import/SKILL.md)
  (document the `is_unchanged` STOP + `--force`), `workflows/` recipe note.

## Epic C (R-18-c) — the connector contract (docs + one template)

**Delta.** Write the contract down; ship no adapters (Epic 6 trigger stands). A connector
= any operator-owned PATH executable that materialises **one file per business object**
into a `wiki-sync` zone with a **stable filename = stable external key** (`PROJ-123.md`
→ stable slug → in-place updates + stable wikilinks), paired with a zone-local
`.wiki/sync.yaml` (`resummarize.mode: if-changed` + a per-zone `summarize:` profile).
Fetchers stay PATH executables (the `resolve_skill_bin` discovery pattern); an MCP tool
MAY wrap one, but **MCP is not the contract**. Source notes refresh **in place**;
`supersedes` chains stay reserved for knowledge-class pages (a refreshed source is "the
current snapshot", not a new event).

- **Files**: a `templates/` zone-`sync.yaml` example (`if-changed` + `summarize:`),
  a **connector-contract** section in
  [docs/architectures/functional-architecture.md](../docs/architectures/functional-architecture.md),
  ROADMAP R-18 → SHIPPED, SKILL/workflow cross-links.

## Out of scope (YAGNI — recorded verbatim from R-18)

- Live SQL federation / fetch-through (Class A/B + H-6 forbid query-time fetch).
- An MCP **server** surface (an MCP tool may *wrap* a fetcher; not the contract).
- Building IMAP / GramJS / Jira adapters now (Epic 6 trigger: first real recurring source).
- Authored `freshness` frontmatter (git + `source_state` already own history).
- A webhook / push daemon (second writer to single-writer SQLite → Postgres trigger).
- `supersedes` chains for refreshed sources (reserved for knowledge-class `--as-of`).
- Changing `if-missing`'s D1 to hash-equality in place (a back-compat break — rejected in
  favour of a new opt-in `if-changed` mode; see Q-051-5).

---

## Requirements (RTM)

| ID | Requirement | MVP? | Sub-features |
|---|---|---|---|
| **R1** | `resummarize.mode: if-changed` gate (Epic A) | ✅ | (1) `if-changed` in schema enum + `sync_config` validation (typo → `INVALID_SYNC_CONFIG` exit 6, value never echoed); (2) `apply_policy` branch: recorded D1 `source_hash` == current sha256 ⇒ `skip:summary-unchanged`, else pass through; **no record ⇒ re-summarise**; (3) hoist the ACTIONABLE-candidate hash ahead of the gate + thread it in (no double read); D1-only keying; (4) `--force` re-arms uniformly (`forced`) |
| **R2** | `is_unchanged` short-circuit in `wiki-import prepare` (Epic B) | ✅ | (1) after the symlink guards, before write: hash the pre-existing `_raw/<slug>.md`; (2) equal ⇒ `is_unchanged: true`, **skip write + attachment copy/GC + context-build**, orchestrator STOPs; (3) mismatch/absent ⇒ current behaviour (byte-identical); (4) `--force` bypasses the short-circuit; (5) SKILL.md documents the STOP + `--force` |
| **R3** | Connector contract as docs + template (Epic C) | ✅ | (1) `templates/` zone `sync.yaml` example (`if-changed` + `summarize:`); (2) connector-contract section in `functional-architecture.md` (zone + stable-filename key + PATH-executable fetcher + in-place refresh); (3) ROADMAP R-18 → SHIPPED; (4) SKILL/workflow cross-links |
| **R4** | Invariants preserved (all epics) | ✅ | (1) zero-DDL (`user_version` 7 — rides existing `source_state`); (2) Decision-17 (no `import anthropic`; envelope + exit codes); (3) Epic A OFF by default (global default stays `if-missing`) + Epic B byte-identical for first-import/changed-raw; (4) vendor-agnostic (flags/env/config only) |
| **R5** | Test coverage (all epics) | ✅ | (1) `if-changed` matrix: no-record→re-summarise, match→`skip:summary-unchanged`, mismatch→re-summarise, `--force`→forced; (2) prepare `is_unchanged`: unchanged re-poll→STOP envelope, changed→rewrite, `--force`→rewrite; (3) schema rejects a bad `mode`; (4) full `pytest` + `mypy --strict` green |

## Use Cases

- **UC-1 (scheduled re-poll, unchanged).** A cron re-runs `wiki-import prepare <url>` on
  an unchanged article → after fetch+convert the hash matches `_raw` → envelope
  `is_unchanged: true` → orchestrator stops → **zero LLM cost**, `_raw` + note untouched.
- **UC-2 (scheduled re-poll, changed).** Same URL, content changed → hash differs →
  `_raw` rewritten, normal envelope → orchestrator summarises → source note refreshed
  **in place** (same slug, stable wikilinks).
- **UC-3 (`wiki-sync` zone with `if-changed`).** A connector drops `PROJ-123.md` into a
  zone whose `.wiki/sync.yaml` sets `resummarize.mode: if-changed`. `wiki-sync scan`:
  unchanged files → `skip:summary-unchanged` (explicit in the plan); a changed file →
  re-ingested; a new object → ingested. No `--force`, no re-LLM of the untouched majority.
- **UC-4 (write a connector).** An operator points any exporter (one file per object,
  stable filename) at a zone + copies the template `sync.yaml`. No code in this repo.
- **UC-5 (force-regenerate).** After changing the REASON harness, `wiki-import prepare
  <url> --force` rewrites `_raw` and re-summarises even though the bytes are unchanged.

## Invariants that must not break

- **Zero-DDL** — `source_state` already exists (Class C); `if-changed` reads it, writes
  nothing new. Schema stays `user_version 7`.
- **Decision-17** — no `import anthropic`; both code slices are deterministic plumbing
  emitting a JSON envelope + stable exit code; the orchestrator owns REASON.
- **Class A/B/C layering** — `source_state` is Class C (operational); raw + summary are
  Class A; **no query-time fetch-through** (pull cache, not proxy).
- **Scoped byte-identity** — Epic A: absent `mode: if-changed`, the existing
  `if-missing`/`always`/`never` paths are untouched. Epic B: byte-identical for **first
  import / changed raw**; the unchanged-re-import path changes by design (always-on, with
  `--force` to restore old behaviour).
- **Vendor-agnostic** — config/flags/env only; works across every LLM CLI.

## Open Questions

- **Q-051-1 (hash plumbing).** `apply_policy` must receive the current-file hash, but
  `scan` computes `_hash_file` **after** the gate and only for `action != "skip"`
  ([wiki_sync.py](../scripts/wiki_skills/wiki_sync.py) L218). → Architecture: hoist the
  hash of ACTIONABLE candidates ahead of the gate and pass it in (avoid a 2nd large read).
- **Q-051-2 (D1-only keying).** Confirmed: `if-changed` keys on `source_state` only;
  provenance/mirror prove existence, not sameness; "no recorded hash" ⇒ re-summarise.
- **Q-051-3 (default).** Global default stays `if-missing` (back-compat); the template
  connector zone opts into `if-changed`.
- **Q-051-4 (which bytes).** Compare the **converted `_raw` bytes** (the `source_hash`
  already in the envelope) — exact against what is stored; an upstream byte change that
  converts to identical markdown is correctly a no-op. Corollary (m-4): for `convert+ingest`
  in `wiki-sync`, D1's `source_state` hash is the **source binary** hash, so a re-save with
  identical text but new metadata re-summarises (safe, mildly wasteful — consistent with
  the existing `is_unchanged` semantics; documented, not fixed).
- **Q-051-5 (`if-changed` vs `always`+executor `is_unchanged`) — the design decision the
  gate must ratify.** Three options: **(i)** new opt-in `if-changed` enum value [chosen —
  explicit plan-layer skip, no delegate emitted for unchanged, fixes the if-missing-changed
  plan-skip, clean connector-zone default]; **(ii)** change `if-missing`'s D1 to
  hash-equality in place [rejected — back-compat break for every existing `if-missing`
  vault]; **(iii)** tell operators to use `mode: always` + rely on the executor's
  `is_unchanged` no-op [rejected NOT on a behavioural difference — `always` and `if-changed`
  re-summarise the identical file classes — but because `always` hides the skip inside the
  executor (no plan-layer `skip:summary-unchanged`), still emits a delegate for every
  unchanged file, and reads as a blunt "re-summarise everything" intent rather than a
  freshness policy]. Architecture to confirm (i) and record the rejection rationale for
  (ii)/(iii).
