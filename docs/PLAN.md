# PLAN 051 — Source freshness: the connector substrate (R-18)

Phases: **PA (Epic A — `resummarize.mode: if-changed`) → PB (Epic B — `wiki-import
prepare` `is_unchanged`) → PC (Epic C — connector-contract docs)**. Stub-first within
each bead (signature/enum + RED → GREEN); every bead ends with the full suite +
`mypy --strict` green. RTM IDs (R1..R5) from `docs/TASK.md`; design record in
`open-questions.md` §11k (Q-051-1..5). Zero-DDL (`user_version` 7). Beads live inline
(the TASK 049/050 convention this task follows).

## PA — Epic A: `resummarize.mode: if-changed` (R1, R4, R5)

**051-01 [R1] schema enum + validation** — `config/sync-config.schema.yaml`: add
`if-changed` to the `resummarize.mode` `enum` (currently `[if-missing, always, never]`,
L146) + extend the description line. `scripts/wiki_index/sync_config.py`: `ResummarizeConfig`
already stores `mode` as a free string validated against the schema enum — confirm
`if-changed` passes and a bogus mode is still `INVALID_SYNC_CONFIG` (exit 6, value never
echoed). Fold a **currency touch-up**: the `ResummarizeConfig` docstring (`sync_config.py`
L108 "`mode` ∈ {if-missing, always, never}") and the schema comment block (L133-147) both
list the old three modes. **Stub-first**: enum value + RED. Tests (`tests/test_sync_config.py`):
`if-changed` parses to `ResummarizeConfig(mode="if-changed")`; a bogus mode rejected
[R4: exit 6, value never echoed]; **default stays `if-missing`** (back-compat, Q-051-3).

**051-02 [R1] `apply_policy` `if-changed` branch** — `scripts/wiki_skills/_resummarize.py::apply_policy`:
add a `current_hash: str | None = None` kwarg and an **explicit** `if policy.mode ==
"if-changed":` branch placed BEFORE the `# if-missing` fall-through (arch-review M-1 — a
new enum value without its own arm silently runs the marker-**presence** if-missing path).
Logic: `recorded = repo.get_source_state(vault_id, "sync", rel, "source_hash")`; return
`Decision("skip", "summary-unchanged")` **only** when
`current_hash is not None and recorded is not None and recorded == current_hash`; otherwise
return `decision` (re-summarise); `--force` → `replace(decision, reason="forced")`
uniformly (mirrors L256/L268). The `None`-guard mirrors the executor TOCTOU guard
(`wiki_sync.py` L221-230) so a markerless-and-unreadable file (`None == None`) never
silently skips. **Stub-first**: signature + RED matrix. Tests (`tests/test_wiki_sync_resummarize.py`):
no-record→decision; match→`skip:summary-unchanged`; mismatch→decision; `current_hash=None`
→decision (never a `None==None` skip) [R4]; `--force`→`forced`; non-ACTIONABLE→pass-through.

**051-03 [R1] wiki-sync scan: hoist the hash + thread it in** — `scripts/wiki_skills/wiki_sync.py`
scan loop. **RED first** — write the failing `skip:summary-unchanged` + no-`delegate`
assertions AND the `if-missing`/`always`/`never` + `upsert` regressions BEFORE touching the
loop. Then: init `source_hash: str | None = None`; **hoist** `source_hash =
_hash_file(cand.path)` for ACTIONABLE candidates ({ingest, convert+ingest} — `_resummarize.
ACTIONABLE`) AHEAD of the `apply_policy` gate (today the hash is at L219, *after* the gate at
L189, only for `action != "skip"` — Q-051-1) and pass `current_hash=source_hash` into
`apply_policy`. **Do NOT drop the `upsert` hash** (plan-review 🟡-1): `upsert` (`_sync.py`
L364 `Decision("upsert","ready-note")`) is **non-ACTIONABLE and non-skip**, so the L218
record still needs a hash — keep that block but make it a **fallback**: `if source_hash is
None: source_hash = _hash_file(cand.path)`, then record `is_unchanged`/`source_hash` on the
single value (no double read for ACTIONABLE; `upsert` reads once as before). Preserve the
existing `None`-hash / `action == "skip"` handling verbatim. Tests (`tests/test_wiki_sync.py`):
an `if-changed` zone — an unchanged marker-bearing file plans `skip:summary-unchanged` with
**no `delegate` emitted**; a changed file plans an ingest delegate; a markerless file plans
ingest; **an `upsert`/ready-note entry still carries a 64-hex `source_hash` + correct
`is_unchanged`** (the hoist-fallback guard); `if-missing`/`always`/`never` plans unchanged
(regression) [R5].

## PB — Epic B: `is_unchanged` short-circuit in `wiki-import prepare` (R2, R4, R5)

**051-04 [R2] `--force` flag on prepare** — `scripts/wiki_skills/wiki_import_article/__init__.py`
prepare arg parser: add `--force` (store_true; bypass the is_unchanged short-circuit →
always rewrite + full envelope). Confirmed net-new (no force flag exists today). **Stub**:
flag + RED (parser accepts `--force`; default `False`).

**051-05 [R2] prepare `is_unchanged` short-circuit** — same file, `prepare`: after the
symlink guards (L276 `raw_path`, L284 `att_dst`) and after `source_hash` is computed
(L299), BEFORE `raw_path.write_bytes` (L305): if `not args.force` and `raw_path.is_file()`,
read+`sha256` the existing `_raw`; if it equals `source_hash`, reclaim `_imgtmp` (the
`_bad` cleanup path) and `emit({"action":"unchanged","is_unchanged":true, "raw_path":…,
"source_hash":…, "slug":…}, 0)` — skipping the write, the attachment copy/GC, and the
`known_concepts`/`existing_page_slugs` context-build. Any mismatch / absent `_raw` / `--force`
→ byte-identical to today. Placement AFTER the symlink guards keeps the H-6 write posture
(never hash through a swapped symlink). **Stub-first**: envelope shape + RED. Tests
(`tests/test_import_is_unchanged.py`, new): unchanged re-poll → `is_unchanged` envelope +
`_raw` mtime unchanged + no REASON fields; changed source → rewrite + normal envelope;
`--force` on unchanged → rewrite; a symlinked `_raw` still `REFUSED_SYMLINK`; `_imgtmp`
reclaimed on the short-circuit (no temp-dir leak).

## PC — Epic C: connector contract (docs + one template) (R3)

**051-06 [R3] template zone `sync.yaml`** — add a `templates/connector-zone.sync.yaml`
example: `resummarize.mode: if-changed` + a `summarize:` profile + comments naming the
**stable filename = stable external key** discipline. Verification: the example **parses
clean** under `config/sync-config.schema.yaml` (a tiny load-smoke test, not a behavioural
one).

**051-07 [R2][R3] connector-contract docs + currency** — (1) a **connector-contract** section
in `docs/architectures/functional-architecture.md` (connector = PATH-executable exporter,
one file per business object, stable filename, zone + `.wiki/sync.yaml`, in-place refresh,
MCP-*may-wrap-not-the-contract*, `supersedes` reserved for knowledge classes); (2)
`skills/wiki-import/SKILL.md` documents the `is_unchanged` STOP + `--force`; (3)
`config/sync-config.schema.yaml` `if-changed` doc (folded from 051-01); (4) `docs/ROADMAP.md`
R-18 → **SHIPPED**; (5) workflow cross-links (`workflows/wiki-sync.md` / `wiki-import`).
Verification: `grep` cross-refs resolve; no behavioural test.

## Order & risk

Serial: **01 → 02 → 03 → 04 → 05 → 06 → 07**. Riskiest beads:
- **051-03** (scan hoist) — a reorder of live code; the executor's `is_unchanged`/
  `source_hash` record MUST keep reading the *same* hash value, and the `None`/`action==skip`
  handling MUST stay verbatim. Guard: regression tests for `if-missing`/`always`/`never`
  plans + the existing `is_unchanged` executor path.
- **051-05** (prepare short-circuit) — must sit exactly after the two symlink guards and
  before the write, and skip *every* downstream side-effect (write, attachment copy, GC,
  context-build) while still reclaiming `_imgtmp`. Guard: the symlink-still-refused +
  no-temp-leak tests.

Cross-cutting (every bead): **R4** invariants — zero-DDL (`user_version` 7; no new
column/method), Decision-17 (no `import anthropic`; envelope + exit codes), Epic A OFF by
default / Epic B byte-identical for first-import+changed-raw, vendor-agnostic — and **R5** —
each bead ends with the **full `pytest` + `mypy --strict` green**; Karpathy byte-identity
untouched (no layout/schema change).
