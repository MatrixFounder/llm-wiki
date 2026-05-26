# VDD Critique Pass 2: TASK 001 — wiki-mvp (post Pass-1 fixes)

Reviewer: Adversary (fresh context). Target: `/Users/sergey/dev-projects/obsidian-llm-wiki/docs/TASK.md` + `ARCHITECTURE.md` + `SCHEMA-DRAFT.sql` + `KNOWN_ISSUES.md` after Pass-1 fixes applied.

## 1. Executive Summary

- **Verdict**: **PASS** (with one LOW spec-gap worth a one-line tightening, not a re-design).
- **Confidence**: High. Every Pass-1 HIGH/MED was implemented as a concrete, verifiable spec change — not weasel-acknowledged.
- **Summary**: All 4 HIGH and all 4 MED items are resolved with grounded fixes: `source_state` row is real (SCHEMA L293-300, composite PK aligns with UC-07 A4 query), subprocess contract pins `subprocess.run(..., timeout=600)` + `TimeoutExpired` + cleanup, R-11.1 drift-check explicitly applies §6.1 forward-mapping, R-07.5 regex is the exact pattern recommended in Pass 1. Token math computes to the documented numbers. The §6.1 mapping table targets only enum values that exist in `SCHEMA L109` (`summary`/`concept`/`query`/`brief`/`research`/`index`/`log`). KNOWN_ISSUES.md stub exists at `docs/KNOWN_ISSUES.md`.

---

## 2. Pass-1 Issue Verification

| Pass-1 ID | Severity | Verification Status | Evidence |
|:---|:---|:---|:---|
| HIGH-1 (idempotency landing place) | HIGH | **Resolved** | UC-07 A4 step 2 (TASK L536) uses `SELECT value FROM source_state WHERE source_kind='transcript' AND scope = abs(source) AND key='source_hash'`. PK `(source_kind, scope, key)` in SCHEMA L299 allows this row. I-3.3 step (f) (L114) does `INSERT OR REPLACE INTO source_state`. |
| HIGH-2 (subprocess contract) | HIGH | **Resolved** | I-3.3 splits into (a)…(g) at L107-115. (a) discovery with `shutil.which('claude')` + `WIKI_GENSUMMARY_CMD` escape-hatch; (c) `subprocess.run(..., timeout=600, capture_output=True, check=False, env={...'CLAUDE_NONINTERACTIVE': '1'})`; (c.1) `TimeoutExpired` + `proc.kill()` + best-effort `unlink` + move-to-`_raw/failed/`. ARCHITECTURE L399-401 mirrors via dedicated error codes. |
| HIGH-3 (R-11.1 drift mapping) | HIGH | **Resolved** | R-11.1 (L63) explicitly says drift "не флажит case когда `file_frontmatter.type ∈ {lesson-summary, summary-light, meeting-summary}` AND `pages.type='summary'` AND tags-marker present". UC-04 step 3.6 (L338) repeats. AC at L369 ("Type-mapping aware drift") asserts `count(*)=0` for transcript-slug post-ingest. |
| HIGH-4 (R-07.5 regex) | HIGH | **Resolved** | R-07.4/R-07.5 (L59) pins (a) Mermaid `re.compile(r"^```mermaid\s*\n.*?^```\s*$", re.DOTALL\|re.MULTILINE)` with `BodyNormalizationError` on unclosed fence; (b) `re.compile(r"<!--\s*SECTION:[a-z0-9_-]+\s*-->")` whitelist on `SECTION:` prefix. UC-07 AC L574-575 covers both the unclosed-fence path AND generic-comment preservation. |
| MED-Karpathy-Deviation | MED | **Resolved** | §6.1 dedicated bullet "Karpathy-deviation (MVP intentional gap)" at L650, naming Epic 7 as fulfilment, explicitly acknowledging trade-off. |
| MED-Slugify | MED | **Resolved** | R-07.4 (L59) pins `python-slugify` with `lowercase=True, separator='-', regex_pattern=r'[^a-z0-9\-]'`; UC-07 AC L576 names the documented losses (`"OAuth 2.0" → oauth-2-0`, `"C++" → c`); collision policy: original concepts preserved in `frontmatter_json.concepts[]`, slugs in `tags[]`. |
| MED-§6.2 token math | MED | **Resolved** | §6.2 (L656-667) pins Sonnet 4.6 at $3/$15 per M, gives per-language math (30-min EN $0.35, RU $0.42, 90-min chunked $0.98) and ties verification to R-14 `llm_tokens_used` benchmark dimension. **Math check**: 40K × $3/M + 15K × $15/M = $0.12 + $0.225 = $0.345 ≈ $0.35 ✓. 150K × $3/M + 35K × $15/M = $0.45 + $0.525 = $0.975 ≈ $0.98 ✓. |
| MED-A3 UNMAPPED_TYPE | MED | **Resolved** | UC-07 A3 (L530-532) fail-fasts with `{error: 'UNMAPPED_TYPE', received, allowed}`. ARCHITECTURE L403 lists code. §6.1 mapping table (L638-646) covers all four producers (summary / summary-light / lesson-summary / meeting-summary). |
| LOW-Fingerprint placeholder | LOW | **Resolved** | I-3.3 step (d) requires "rendered `Content Fingerprint` block (NOT `{{N}}` placeholders), `Total concepts extracted: N ≥ 1`, `Source files:` non-empty". UC-07 A9 (L557-560) duplicates the check with `WORKFLOW_INCOMPLETE` and moves output to `_raw/failed/`. |
| LOW-Concurrent ingest | LOW | **Partial — see new issue below** | UC-07 A8 (L551-555) adds flock + 60s timeout + post-release A4 short-circuit. Mechanism is sound BUT lock-file location may not exist on first run — see new issue NEW-1. |
| LOW-KNOWN_ISSUES.md missing | LOW | **Resolved** | `docs/KNOWN_ISSUES.md` exists as a stub with template entry-format. |
| Cross-doc drift (ARCHITECTURE L71, L421-425) | LOW | **Resolved** | ARCHITECTURE L71 now says "wraps `/generate-detailed-meeting-summary` workflow (educational overlay поверх `summarizing-meetings` skill) через subprocess". L424-433 (`wiki-source-transcript` component) is fully consistent with TASK R-06.3 / I-3.3 / UC-07. |

---

## 3. New Issues Introduced By Fixes

| Severity | Category | Issue | Impact | Recommendation |
|:---|:---|:---|:---|:---|
| **LOW** | Logic / Spec-Gap | **UC-07 A8 lock path `<output>/.summary.lock` assumes `<output>` directory exists.** On the very first transcript ingest, `<output>` is the target dir to be created by the workflow's write of `summary.md`. Opening a flock file in a non-existent parent dir raises `FileNotFoundError` before the lock can be acquired. I-3.3 doesn't list `mkdir -p <output>` as a precondition. | First-run ingest crashes before subprocess even spawns. Trivial bug, but the spec currently reads as if the lock will Just Work. | In I-3.3 add a step (a.1) immediately after Discovery: "`Path(<output>).mkdir(parents=True, exist_ok=True)` before any flock attempt." Also alternative: relocate lock to vault-wide path independent of `<output>`, e.g. `<vault>/_raw/.locks/transcript-<sha256(abs(source))[:12]>.lock` (more robust to caller passing weird `--output` paths, and matches the A4 scope which is keyed on `abs(source)`, not on `<output>`). |

That's the only new real issue. Everything else I checked converged on "the spec already covers it":

- "What if `claude` CLI output uses CRLF line endings and breaks `re.MULTILINE` on `^```$`?" — `python-frontmatter` and Python file IO open in text mode with universal newlines by default; not a real failure mode for the spec-level review.
- "What if `python-slugify`'s `regex_pattern` keyword name is different from spec?" — that's an implementation detail; the AC at L576 nails behavior, the implementation can use whatever API knob actually does it.
- "What if `source_state` row insert races with parallel writer?" — SQLite `BEGIN IMMEDIATE` covers it (§5.3 / `pages` upsert uses same lock), and the A8 flock prevents two transcript adapters from racing in the first place.
- "What if `<vault>/_raw/failed/` doesn't exist?" — best-effort move; adapter would `mkdir -p` parent. Not load-bearing; the spec already says "best-effort".

---

## 4. Hallucination Check

Verified each Pass-2 citation against actual file contents:

| Cited | Exists? | Notes |
|:---|:---|:---|
| `docs/TASK.md` L107-115 (I-3.3 steps a-g) | YES | All seven steps present with concrete pseudo-code/contract |
| `docs/TASK.md` L530-532 (UC-07 A3) | YES | `UNMAPPED_TYPE` fail-fast as recommended |
| `docs/TASK.md` L534-538 (UC-07 A4) | YES | `source_state` query + INSERT OR REPLACE |
| `docs/TASK.md` L551-555 (UC-07 A8) | YES | flock + 60s timeout |
| `docs/TASK.md` L557-560 (UC-07 A9) | YES | unrendered-template-placeholder rejection |
| `docs/TASK.md` L637-648 (§6.1 mapping) | YES | 4 frontmatter→DB type rows, all DB types ∈ SCHEMA L109 CHECK enum |
| `docs/TASK.md` L656-667 (§6.2 token math) | YES | Sonnet 4.6 pricing + per-language math + R-14 verification |
| `docs/SCHEMA-DRAFT.sql` L293-300 (source_state) | YES | composite PK `(source_kind, scope, key)` |
| `docs/ARCHITECTURE.md` L71 (transcript adapter purpose) | YES | now references workflow, not base skill |
| `docs/ARCHITECTURE.md` L399-405 (error codes) | YES | full enum including new codes |
| `docs/KNOWN_ISSUES.md` | YES | stub with format |

No fabricated references.

---

## 5. Convergence Signal

I am converging. After scanning every Pass-1 issue and every load-bearing diff, the only real remaining issue is the `<output>` dir mkdir gap for the flock file — a one-line fix in I-3.3, not a re-design. The four candidate adversarial probes I tried (CRLF, slugify API name, source_state race, _raw/failed mkdir) all dead-end into "already addressed elsewhere" or "implementation detail outside spec scope". This is the convergence signal the methodology defines as **Zero-Slop achieved**.

**Recommendation**: Apply the LOW NEW-1 fix (mkdir + optional lock-path relocation), then proceed to Architecture-phase ratification and Plan phase. TASK is implementation-ready.
