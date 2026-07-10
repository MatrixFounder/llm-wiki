# TASK 057 — wiki-import: video robustness (W1), vendor-independent folder inference (W2), announcement detection (W3)

## 0. Meta Information
- **Task ID**: 057
- **Slug**: wiki-import-video-folder-inference
- **Origin**: `docs/wiki-import-video-folder-inference-spec.md` (committed bd57f21) — three
  friction points from the cyber•Fund *"Building AI-Native Startups [004]"* X-Broadcast import
  (2026-07-09). Counterpart of the transcript-fetcher skill spec in the Universal-skills repo.
- **Type**: Feature + robustness (additive CLI surface; zero-DDL; no schema change)
- **Effort**: M–L (three independent work packages over `wiki_import_article`; offline tests only)
- **Dependency status (verified 2026-07-10)**: the transcript-fetcher flags W1 needs
  (`--concurrent-fragments`, `--media-timeout-sec`) **have landed** in the installed skill
  (`~/.claude/skills/transcript-fetcher/scripts/fetch.py` argparse + env
  `TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS` / `_MEDIA_TIMEOUT_SEC`, both X-media-only,
  skill-side defaults 8 / duration-derived). W1 is **unblocked**.
- **Architecture**: no layering change. Class A/B/C, Decision-17 (no `import anthropic`;
  one JSON envelope + stable exit code per subcommand), `user_version 7`, H-6 egress posture
  all untouched. W2 adds a *read-only* DAL consumer (`search_pages`) inside `prepare`.

## 1. Problem (verified against source)

Line references: `scripts/wiki_skills/wiki_import_article/__init__.py` (facade) and
`_fetch.py` (dispatch) at bd57f21.

1. **W1 — long X Broadcasts/Spaces can't be fetched.** `_fetch_transcript()`
   (`_fetch.py:693–746`) builds the transcript-fetcher argv (`_fetch.py:705`) with `--out`,
   `--json-errors`, `--with-description`, `--lang`, and optionally `--max-duration-min` /
   `--cookies-*` — but has **no way** to forward the new fragment-concurrency / media-timeout
   knobs. Additionally `_transcript_timeout()` (`_fetch.py:640–645`) defaults the subprocess
   wall-clock to **300 s** (`_TRANSCRIPT_TIMEOUT_DEFAULT`, `_fetch.py:165`), which a ≥60-min
   broadcast (parallel download + ASR ≈ 15–35 min) always exceeds → `kind:"timeout"` even when
   the skill itself would succeed. This is why the 004 import had to bypass `wiki-import`.
2. **W2 — `--folder` omitted → the operator/model guesses.** `prepare` hard-requires
   `--folder` (`__init__.py:858`). During the 004 import the guess filed the raw capture under
   `05 - Материалы/Криптовалюты/` when episode 003 already sat in `03 - Learning/Webinars/`.
   The CLAUDE.md remedy (`obsidian-active-note`) is vendor-bound and timing-fragile (returned
   "No active file" at the moment it was needed). The vault index already held the answer:
   a same-series sibling note, derivable from FTS + filesystem alone.
3. **W3 — announcement tweets produce junk.** An `x.com/<user>/status/<id>` that merely
   *announces* a Broadcast stays on the html path (correct default), but the reader capture is
   contentless chrome (nav, replies, trending) + a `x.com/i/broadcasts/<id>` link. `prepare`
   still writes `_raw/<ugly-slug>.md` **plus ~17 avatar/emoji attachments** into the (guessed)
   folder, and `--kind auto` mislabels it `thread`. Manual cleanup was required.
4. **§C — concept compounding**: NOT a code defect (extraction defaults ON on the tool path;
   the 004/003 notes were hand-authored). Resolution is config/practice only — see Non-goals.

## Requirements Traceability

| ID | Requirement | MVP? | Acceptance criteria | Affected component |
|---|---|---|---|---|
| W1-1 | `_fetch_transcript()` accepts `concurrent_fragments: int \| None` and `media_timeout_sec: int \| None` and, when non-None, appends `--concurrent-fragments N` / `--media-timeout-sec N` to the fetch.py argv; `None` omits the flags so the skill's own env/`.env`/duration-derived defaults rule. Both callers (`_fetch_x_status_with_video`, `_append_embedded_videos`) and `dispatch_fetch` forward them. | yes | Offline argv assertion: flags present with values when set, absent when None, on all three call paths. | `_fetch.py::_fetch_transcript/_fetch_x_status_with_video/_append_embedded_videos/dispatch_fetch` |
| W1-2 | `wiki-import prepare` exposes `--transcript-concurrency` and `--transcript-media-timeout` (int, default None = skill defaults), plumbed to `dispatch_fetch`. Values ≤ 0 are refused at the argparse layer. | yes | `prepare --transcript-concurrency 8 --transcript-media-timeout 2400` reaches the fetch.py argv verbatim; omitted → absent. | `__init__.py::_build_parser/prepare` |
| W1-3 | The subprocess wall-clock default rises 300 → **3600 s for PRIMARY transcript fetches** (unambiguous video / x-status `--video`) so it covers parallel download + ASR of a ≥60-min broadcast, while best-effort **embedded-video fetches keep 300 s** (ARCH Q-057-2 scoping); `WIKI_TRANSCRIPT_TIMEOUT_S` set overrides BOTH roles (existing env contract unchanged). | yes | `_transcript_timeout(primary=True)` → 3600 / `primary=False` → 300 with no env; env override wins for both; docstring/SKILL.md state the budget rationale. | `_fetch.py::_transcript_timeout` (+ per-role constants) |
| W2-1 | `--folder` becomes **optional** on `prepare`. When omitted: fetch+convert runs as today, then a **folder-inference step** executes and `prepare` emits a proposal/unresolved envelope and **writes nothing into the vault** (no `_raw`, no attachments). When `--folder` is given, behaviour is byte-identical to today. | yes | With `--folder`: existing tests unaffected. Without: no vault write on ANY inference outcome (asserted on a seeded tmp vault). | `__init__.py::prepare/_build_parser` |
| W2-2 | **Series-stem inference (primary, vendor-independent):** derive a series stem from the detected title (strip trailing episode/index markers: `[004]`, `(4)`, `#4`, `Episode/Part/выпуск/урок N`, trailing bare number; conservative — a stem shorter than a floor (≥ 8 chars AND ≥ 2 words) aborts inference). FTS-query the stem (quoted phrase, vault-scoped, via `IndexRepository.search_pages`); keep hits whose title OR filename stem starts with the stem (case-folded); map each to its `--folder`-form folder (parent dir with a trailing layout `source_subdir` segment stripped; empty → the subdir itself). Exactly one distinct folder → proposal `{folder_inferred, basis:"series-sibling", evidence:[paths], confidence:"high"}`. | yes | Unit: 004-title + seeded 003 sibling → proposes `03 - Learning/Webinars` with the 003 path as evidence, no Obsidian involved. Distinct-series titles do NOT merge (stem guard). Multi-folder siblings → unresolved with ranked candidates. | new `_folder.py` (pure) + `__init__.py::prepare` (DAL call) |
| W2-3 | **Active-note hint (secondary):** only when W2-2 is inconclusive, consult `obsidian-active-note folder --format json` (resolved via PATH; ~10 s timeout; **ANY non-zero exit = hint unavailable** — exits 3/4/5 are the illustrative family, never a per-code allowlist; ARCH §2.3.5). A folder is accepted only if it resolves inside `--vault-root` and exists → proposal `basis:"active-note"`, `confidence:"medium"`. Absent binary / any non-zero exit / outside-vault → skip silently (it is a hint, never a contract). | yes | Unit with a stubbed binary on PATH: success → proposal; exit 3 → skipped; outside-vault folder → skipped. No hard dependency: absence of the binary must not error. | new `_folder.py::_active_note_folder` |
| W2-4 | **Ask fallback + staging:** neither signal → typed `FOLDER_UNRESOLVED` envelope (exit 2) carrying ranked `candidates` (may be empty). On BOTH proposal and unresolved paths the converted capture is **staged to a tempfile outside the vault** (frontmatter stamped with `source:` + detected title/author/date) and emitted as `staged_path`, so the confirmed re-run (`--source <staged_path> --folder <F>`) is fetch-free — a 70-min broadcast is never transcribed twice. Envelope also carries detected `kind`/`title` so the orchestrator can confirm intelligently. | yes | Unit: unresolved → exit 2 + candidates + staged file exists outside vault with stamped frontmatter; re-run on staged file with `--folder` imports without network (local-md engine) and keeps title/date. | `__init__.py::prepare`; `_fetch.py::ensure_source_frontmatter` (title stamp helper) |
| W2-5 | **Companion rule:** the vault-template guidance (`templates/CLAUDE.md.tmpl`) makes "omit `--folder` → prepare infers from a same-series sibling (vault search first)" the primary path; `obsidian-active-note` is demoted to the secondary hint. `skills/wiki-import/SKILL.md` + `workflows/wiki-import.md` document the new flags/actions and the confirm/override loop. | yes | Template + SKILL.md + workflow mention series-sibling inference before active-note; new envelope actions documented with exit codes. | `templates/CLAUDE.md.tmpl`, `skills/wiki-import/SKILL.md`, `workflows/wiki-import.md` |
| W3-1 | **Announcement heuristic (pure):** on the html path of an `ambiguous_x_status` URL (no `--video`), after a successful reader extraction: if the normalized prose (same normalization discipline as `_is_x_login_wall`) is below an announcement floor AND the body links a first-party `x.com`/`twitter.com` `/i/broadcasts/<id>` or `/i/spaces/<id>` URL, classify `announcement_only` and surface the broadcast URL. Host-shape allowlisted (no arbitrary egress); a substantive tweet that also links a broadcast is NOT dropped (floor gate). | yes | Unit: 004-shaped fixture (short prose + broadcast link + chrome) → `announcement_only` with the exact broadcast URL; a ≥floor-prose tweet with the same link passes through; a short tweet WITHOUT such a link passes through. | `_fetch.py` (new `_announcement_only` + `dispatch_fetch` hook) |
| W3-2 | On `announcement_only`, `prepare` writes **no `_raw`, no attachments** (the html skill's temp attachment dir is reclaimed), and emits `{action:"announcement_only", broadcast_url, hint}` with **exit 0**. `--kind auto` never labels the junk capture `thread` (the path short-circuits before kind detection). | yes | Unit: prepare on the fixture → exit 0, envelope has `broadcast_url` + re-route hint, vault tree byte-identical before/after (no `_raw/`, no `_attachments/`). | `__init__.py::prepare` |
| W3-3 | Regression: with `--video` the existing `_fetch_x_status_with_video` concat path is used unchanged (announcement heuristic does not run); a normal text tweet (no broadcast link) imports exactly as today. | yes | Existing `test_import_video.py` suite green unmodified; new no-regression unit for a plain tweet. | `_fetch.py::dispatch_fetch` |
| NF-1 | Quality gates: `mypy --strict scripts/` clean; full `pytest tests/` green; all new tests offline (no network, no real Obsidian, no transcript-fetcher install required — subprocess/binary boundaries stubbed). | yes | CI-equivalent local run green. | tests + typing |
| NF-2 | Envelope/exit-code contract stays stable: existing actions (`prepared`, `unchanged`, `fetch-failed`, errors) byte-compatible; new actions (`folder_proposed`, `announcement_only`) and error (`FOLDER_UNRESOLVED`) are additive and documented in SKILL.md §exit codes. | yes | Grep-level doc check + envelope regression tests. | `_errors.py`, SKILL.md |

## 3. Use cases

- **UC-1 (W1) long broadcast end-to-end.** `prepare --source https://x.com/i/broadcasts/<id>
  --kind meeting --folder <F>` on a ~70-min broadcast: argv carries the concurrency/media-timeout
  flags when given; the 3600 s wall-clock no longer clips; transcript `_raw` produced with no
  manual `yt-dlp`/`mw` steps. (Live run is opt-in — gated on cookies/ASR; the committed test is
  the offline argv/timeout assertion.)
- **UC-2 (W2) sibling-resolved folder.** `prepare --source <004-broadcast>` with NO `--folder`:
  title `Building AI-Native Startups [004]` → stem `Building AI-Native Startups` → FTS finds the
  003 note in `03 - Learning/Webinars/` → envelope `action:"folder_proposed"`,
  `folder_inferred:"03 - Learning/Webinars"`, `basis:"series-sibling"`, evidence = 003 path,
  `staged_path` set; nothing written in the vault. Orchestrator confirms → re-runs
  `prepare --folder "03 - Learning/Webinars" --source <staged_path>` → fetch-free import.
- **UC-3 (W2) unresolved.** Same, but no sibling and no active note → exit 2,
  `error:"FOLDER_UNRESOLVED"`, `candidates:[…]` (possibly empty), `staged_path` set; the
  orchestrator asks the user instead of guessing.
- **UC-4 (W3) announcement tweet.** `prepare --source https://x.com/cyberfund/status/<id>` (no
  `--video`) where the tweet only announces a broadcast → exit 0, `action:"announcement_only"`,
  `broadcast_url:"https://x.com/i/broadcasts/<id>"`, hint to re-run on the broadcast URL or pass
  `--video`; vault untouched.
- **UC-5 (W3) announcement + `--video`.** Same tweet with `--video` → existing concat path
  (tweet text + transcript), unchanged.
- **UC-6 (regression) normal tweet / explicit folder.** A substantive text tweet imports as
  today; any `prepare` WITH `--folder` is byte-identical to current behaviour.

## 4. Non-goals / constraints

- **§C (concept compounding)** — explicitly NO code change: extraction already defaults ON via
  the tool path; resolution = file future episodes through `wiki-import`/`wiki-sync` (optionally
  a Webinars-scoped `summarize:` block) + a one-time `wiki-extract-concepts` backfill for
  003/004. Recorded here so the pipeline doesn't reinvent it.
- **No new authored frontmatter fields** (derive-don't-author): inference derives from index +
  filesystem; nothing new is required of note authors.
- **wiki-sync untouched**: it always passes an explicit folder per its zone config; W2 changes
  only the interactive/orchestrator path.
- **Zero DDL**; no new indexes (P-5). W2 reads via the existing `search_pages` ABC surface only.
- **H-6/egress posture unchanged**: W3 detection is string-shape only (no new network); the
  active-note hint shells out to a local resolver binary only, never the network.
- **Vendor-agnostic** (user requirement): W2's primary signal must work with no running
  Obsidian, no specific harness; the secondary hint degrades silently.

## 5. Open questions

None blocking. Four implementation-level decisions taken here (recorded for the architect):
(1) `FOLDER_UNRESOLVED` exits 2 (missing-argument family) while `folder_proposed` /
`announcement_only` exit 0 — proposal and benign stop are successes of the guard, not failures;
(2) staging lives in a persistent tempfile OUTSIDE the vault (never a "guessed" vault folder —
spec W2 hard rule); (3) announcement prose floor is a named constant (initial 600; login-wall
floor 220 stays separate) — tunable, conservative by AND-gating with the broadcast link;
(4) wall-clock default 3600 s is a hang-guard, not a pacing knob — pacing lives in the skill's
duration-derived media timeout.
