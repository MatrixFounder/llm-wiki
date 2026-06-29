# TASK 044 — video sources for wiki-import via transcript-fetcher

## 0. Meta
- **Task ID:** 044 · **Slug:** `task-044-wiki-import-video-transcript`
- **Mode:** VDD — construct path fetch layer + skill. Reviewers: `code-reviewer` +
  `critic-security` (SSRF/egress on operator URLs, cookies handling, untrusted media,
  H-6) + `critic-logic`. `mypy --strict scripts/` is the static contract.
- **ADR:** none new — this EXTENDS ADR-001 "Wrap + Index" composition: `transcript-fetcher`
  becomes a third wrapped external skill alongside `html`/`pdf` (composition, not reinvention).
  Record the design rationale in `docs/ARCHITECTURE.md` §2.3 + `docs/architectures/open-questions.md`.
- **Touches:**
  - `scripts/wiki_skills/wiki_import_article/_fetch.py` — primary: `_video_host()`,
    `_fetch_transcript()`, `_transcript_python()`, updated `dispatch_fetch`, typed-error
    mapping, text+video concatenation, "no-media → fall back to html" path.
  - `scripts/wiki_skills/wiki_import_article/__init__.py` — new args: `--video`,
    `--transcript-bin`, `--max-duration-min`, `--cookies-from-browser`, `--cookies-file`,
    `--lang`; passthrough to `dispatch_fetch`.
  - `scripts/wiki_skills/wiki_import_article/_detect.py` — orthogonality verification; no
    functional change expected.
  - `skills/wiki-import/SKILL.md` — prepare dispatch line, exit codes table, dependency
    note, `--video`/host-routing docs.
  - `tests/` — mock the transcript binary exactly as `html`/`pdf` are mocked; four new test
    scenarios (see §5).
  - `docs/ARCHITECTURE.md` + `docs/architectures/open-questions.md`.
- **Branch:** `task-044-wiki-import-video-transcript`
- **Schema:** `user_version` 7, untouched. **Zero DDL. Zero new Python runtime deps.**

---

## 1. Problem / motivation

`wiki-import prepare` routes its source through `dispatch_fetch` which today knows only two
external skill branches: **`html`** (URL / HTML) and **`pdf`** (PDF). A video URL — YouTube,
Vimeo, Skool lesson, X.com Broadcast/Space, or an X status tweet carrying a video — therefore
falls into the `html` branch, which fetches the watch-page chrome (player embed, login wall,
or at best a text-only description) rather than the spoken content. The result is either junk
in `_raw/` or a FETCH_FAILED with no guidance.

The `transcript-fetcher` external skill
(`/Users/sergey/dev-projects/Universal-skills/skills/transcript-fetcher/`) already solves this
end-to-end: captions-first (yt-dlp subtitles/automatic_captions) with automatic ASR fallback
(MacWhisper → Whisper CLI → whisper.cpp → opt-in cloud), covering YouTube, Vimeo, X.com, and
Skool. It is a global skill binary with its own venv (`scripts/.venv/bin/python scripts/fetch.py`),
mirroring the `html`/`pdf` pattern exactly.

Adding it as a **third fetch branch** in `dispatch_fetch` (hybrid auto + flag routing) gives the
operator a clean, deterministic video path with zero LLM involvement in the dispatch decision
(Decision-17), zero schema change, and zero new Python deps — the binary is an external
dependency, failed-fast like `html`/`pdf` when absent.

---

## 2. Scope

### In scope
- A **`_video_host()` classifier** in `_fetch.py` that categorises a URL as one of:
  `unambiguous_video` (YouTube, Vimeo, Skool lesson, X Broadcast/Space),
  `ambiguous_x_status` (x.com|twitter.com `/<user>/status/<id>`), or `not_video`.
- A **`_fetch_transcript()` function** in `_fetch.py` that shells out to the
  `transcript-fetcher` binary, reads the `.txt` + `.stat.json` sidecar, maps the stat into
  `FetchResult` (engine = `transcript:<origin>`), and maps typed exit codes to domain errors.
- A **`_transcript_python()` helper** (mirrors `_pdf_python()`) that prefers the skill's own
  `scripts/.venv/bin/python`.
- A **`dispatch_fetch` update**: new video-dispatch tier inserted BEFORE the html branch,
  implementing Decision 1 + Decision 2 + Decision 3 routing (see §3, R-1 through R-6).
- **New CLI flags** on `prepare`: `--video` (force transcript path for ambiguous x-status),
  `--transcript-bin` (path to `fetch.py`; fail-fast exit 6 if absent and a video URL is hit),
  passthrough flags `--max-duration-min`, `--cookies-from-browser`, `--cookies-file`, `--lang`
  forwarded to the transcript binary.
- **SKILL.md update**: prepare dispatch documentation extended to three branches
  (html / pdf / transcript); exit codes table gains the new dep-error case; dependencies
  section notes yt-dlp (always for captioned video), ffmpeg + a whisper backend (only for
  ASR path on HLS sources — Broadcasts/Spaces); `--video` and host-routing described.
- **Tests**: four new test modules / scenarios mocking the transcript binary (no live network).
- **Architecture docs**: `docs/ARCHITECTURE.md` §2.3 + open-questions entry Q-044-*.

### Out of scope (explicit non-goals)
- New `--kind` values: content-type detection (`_detect.py`) is ORTHOGONAL — a transcript
  body with timestamps/speaker turns detects as `meeting`; the operator may override with
  `--kind`. No new kind is added.
- Any change to the `apply` subcommand logic (note filing, concept extraction, indexing).
- The `summarizing-meetings` harness (external skill, unchanged).
- ASR backend installation in this repo — that is `transcript-fetcher`'s own concern.
- Karpathy layout-specific behavior; `wiki-enrich`; `wiki-reindex`; SQLite schema.
- New Python runtime dependencies in `requirements.txt` (`transcript-fetcher` is an external
  binary, not a library import).
- An `import anthropic` anywhere in the new code (Decision-17 hard constraint).
- A network probe ("does this URL have a video track?") in the default path — routing is
  URL-shape + `--video` flag ONLY.

---

## 3. Requirements (RTM)

| ID | Requirement | MVP? | Sub-features |
|----|-------------|------|--------------|
| **R-1** | **Video-host classifier `_video_host(url)`** — deterministic, URL-shape only, no network. Returns `"unambiguous_video"`, `"ambiguous_x_status"`, or `"not_video"`. | ✅ | (a) `youtube.com`, `youtu.be` (incl. `m.youtube.com`, `music.youtube.com`, `www.` variants) → `unambiguous_video`; (b) `vimeo.com`, `www.vimeo.com`, `player.vimeo.com` → `unambiguous_video`; (c) `skool.com`, `www.skool.com`, `app.skool.com` with a classroom/lesson URL pattern → `unambiguous_video`; (d) `x.com/i/broadcasts/<id>` and `x.com/i/spaces/<id>` (and `twitter.com` equivalents) → `unambiguous_video`; (e) `x.com/<user>/status/<id>` / `twitter.com/<user>/status/<id>` → `ambiguous_x_status`; (f) everything else → `not_video`; (g) classifier is a **pure function** (no I/O, no imports of anthropic, no network call); (h) host matching is label-boundary (prevents `evil-youtube.com` false positive). |
| **R-2** | **`dispatch_fetch` routing — Decision 1 + Decision 2 (MUST NOT regress the text path).** New media-tier BEFORE the html branch. | ✅ | (a) `unambiguous_video` → always try `transcript-fetcher`; (b) `ambiguous_x_status` WITHOUT `--video` → skip to the EXISTING html path (default, zero regression); (c) `ambiguous_x_status` WITH `--video` → Decision 3 (R-5); (d) `not_video` → existing html/pdf dispatch, byte-for-byte unchanged; (e) `--video` on a non-x-status URL that is already `unambiguous_video` → still routes through transcript (flag is harmless/additive); (f) `--video` on a `not_video` URL → **intentional NO-OP**: the existing html/pdf path is taken, **no transcript subprocess is spawned** (preserves NF-2 byte-identity + avoids a wasted subprocess; `--video` only changes behavior on `ambiguous_x_status`). |
| **R-3** | **`_fetch_transcript()` — shell-out to transcript-fetcher binary.** | ✅ | (a) uses `_transcript_python()` to prefer the skill's own venv interpreter (mirrors `_pdf_python()`); (b) invocation: `[python, fetch.py, url, --out, tmp.txt, --json-errors, ...passthrough_flags]`; (c) reads back the `<tmp>.txt.stat.json` sidecar after success; (d) sets `FetchResult.engine = f"transcript:{stat.get('transcript_origin', 'unknown')}"`; (e) `raw_text` is the `.txt` contents (plain text, no frontmatter — `ensure_source_frontmatter` is called by the prepare layer as in the pdf case); (f) `title`, `author`, `date` populated from stat sidecar fields `title`, `uploader`, `upload_date` when present; (g) temp directory cleaned in a `finally` block regardless of success/error (no orphaned temp files). |
| **R-4** | **`--transcript-bin` flag** — path to `transcript-fetcher`'s `fetch.py`; `require_bin()` fail-fast on first video URL if absent. | ✅ | (a) `require_bin(args.transcript_bin, "transcript")` raises `ImportArticleError(exit_code=EXIT_DEP_MISSING)` if the binary is not found; (b) error message says "install transcript-fetcher skill or pass --transcript-bin"; (c) `_TIMEOUT_TRANSCRIPT` constant (suggested 300 s); (d) default value for `--transcript-bin` points to the conventional installed path (e.g. `~/.claude/skills/transcript-fetcher/scripts/fetch.py` or the Universal-skills location). |
| **R-5** | **Decision 3 — `--video` on `ambiguous_x_status`: CONCATENATE html + transcript.** | ✅ | (a) run the **html** skill on the status URL first → captures the tweet's own prose; (b) then run **transcript-fetcher** on the same URL → captures the video audio; (c) if html fetch fails → fall through to transcript-only (do not write junk); (d) if transcript fetch fails for no-media reason (exit 3 from transcript-fetcher: "no transcript producible") → fall back to html-only result (the `--video` flag degrades gracefully — R-6a); (e) if BOTH succeed → concatenate: `_raw/<slug>.md` = `## Tweet\n\n<html_body>\n\n## Video Transcript\n\n<transcript_body>`; (f) `FetchResult.engine = "html+transcript:<origin>"`; (g) `quality_flag` from transcript sidecar is still propagated (R-8). |
| **R-6** | **Edge case: no-media on `--video` status URL** — graceful degradation, no silent junk. | ✅ | (a) transcript exit 3 ("no transcript producible") on an `ambiguous_x_status` with `--video` → fall back to the html path and return that result; (b) `FetchResult` carries no error; the operator gets the tweet prose as if `--video` had not been passed; (c) the fall-back is logged/traceable in the error envelope's details but NOT a hard failure; (d) `_raw` is written only if the html result is ok and non-empty (R-3 invariant); (e) **SCOPE GUARD — exit 3 on an `unambiguous_video` URL (YouTube/Vimeo/Broadcast/Space) maps to `FETCH_FAILED` (exit 10), `_raw` NOT written, NO html fallback** — there is no useful text path (html returns only watch-page chrome). The no-media→html fallback (a–d) is EXCLUSIVE to `ambiguous_x_status` under `--video`. (transcript-fetcher exit 3 conflates genuine no-media with ASR-produced-nothing; on an unambiguous-video host both are a hard fail.) |
| **R-7** | **Edge case: Broadcast/Space with no ASR backend** — typed dep error, `_raw` not written. | ✅ | (a) transcript exit 7 ("MissingDependency") → map to `ImportArticleError` with `exit_code=EXIT_DEP_MISSING`; (b) error envelope `{"error": "DEP_MISSING", "type": "FetchFailed", "details": {"url": …, "kind": "no_asr_backend", "remediation": "install ffmpeg and a whisper backend (whisper-cli, whisper.cpp, or MacWhisper)"}}` or equivalent human-readable hint; (c) `_raw` is NOT written (the prepare layer writes only on `ok` result — R-3 invariant preserved); (d) exit code from `prepare` is 6 (DEP_MISSING); (e) the error surfaces the transcript-fetcher's own `details.remediation` hint if present in its JSON error envelope. |
| **R-8** | **`quality_flag: english_auto_translation` MUST be surfaced.** | ✅ | (a) after a successful `_fetch_transcript`, check `stat.get("quality_flag")`; (b) if set to `"english_auto_translation"` (or any non-null value), include it in `FetchResult` — carried as a field (e.g. `quality_flag: str \| None`) and emitted in the `prepare` envelope's top-level `quality_flag` key; (c) the orchestrator MUST see it before running the REASON harness — the SKILL.md documents that a `quality_flag` in the prepare envelope requires surfacing a warning to the operator before summarization; (d) recorded in frontmatter provenance via the `engine` field (already carries `transcript:<origin>`). |
| **R-9** | **`transcript_origin` as provenance — `FetchResult.engine`.** | ✅ | (a) `FetchResult.engine = f"transcript:{stat['transcript_origin']}"` (e.g. `"transcript:embedded-captions"`, `"transcript:macwhisper"`); (b) `ensure_source_frontmatter` already handles the no-frontmatter case (txt dump) — reuse it; do not duplicate FM injection logic; (c) the `source:` frontmatter link points to the original video URL. |
| **R-10** | **Login-walled video — surface cookies guidance.** | ✅ | (a) transcript exit 5 ("source-auth error" — HTTP 401/403) → map to a `FetchFailed` envelope with a login-wall hint mirroring the existing `_is_x_login_wall` message; (b) hint text: suggest `--cookies-from-browser <browser>` or `--cookies-file <path>` as remediation; (c) `_raw` NOT written; exit code 10 (FETCH_FAILED). |
| **R-11** | **Passthrough flags forwarded to transcript binary.** | ✅ | (a) `--lang <code>` is **ALWAYS** forwarded to the transcript subprocess (NEVER rely on transcript-fetcher's own `ru` default per its SKILL.md §7 — a wrong-language fallback ladder); the value defaults from the vault's `language` config (en fallback) via `_vault_language()`, asserted by a test; (b) `--max-duration-min N`; (c) `--cookies-from-browser <browser>`; (d) `--cookies-file <path>`; (e) flags are passed as argv to the transcript subprocess only when explicitly set (no accidental defaults); (f) `--json-errors` is ALWAYS passed to transcript binary (for parseable error envelopes). |
| **R-12** | **Orthogonality of `_detect.py` / `--kind`** — no change to content-type detection. | ✅ | (a) `_detect.py` is NOT modified for the video path (its heuristics already handle transcript-like bodies via `_looks_like_transcript`); (b) a video transcript body with timestamps/speaker turns naturally detects as `meeting`; (c) operator may always override with `--kind`; (d) the harness is always `summarizing-meetings` (no new kind, no new harness); (e) confirm with a grep/read that `_detect.py` needs no functional change. |
| **NF-1** | **Vendor-agnostic** — identical behavior across claude/codex/gemini/pi/hermes. | ✅ | (a) dispatch is subprocess + flags, no SDK or vendor-specific tool; (b) `--transcript-bin` is a plain path, resolvable on any platform; (c) no `import anthropic` anywhere in new code. |
| **NF-2** | **No regressions** — existing html/pdf dispatch is byte-for-byte unchanged for non-video URLs. | ✅ | (a) a plain article URL that is `not_video` takes exactly the pre-existing code path; (b) `mypy --strict scripts/` clean; (c) `pytest tests/` green (all pre-existing tests pass); (d) zero SQLite DDL; (e) `requirements.txt` unchanged. |
| **NF-3** | **Security + H-6 invariants.** | ✅ | (a) transcript binary invoked via argv array (never a shell string — no injection); (b) `--cookies-file` path is operator-supplied, validated for existence (not content); (c) stat sidecar values (`title`, `uploader`, `transcript_origin`, `quality_flag`) pass through `_fm_safe()` before injection into frontmatter (H-6 guard — same treatment as html/pdf metadata); (d) `_raw` self-containment + `validate_inside_vault` (R-26) unchanged; (e) temp transcript files are cleaned in a `finally` block; (f) SSRF residual documented (operator URL, same as pdf — the operator owns the URL). |
| **R-13** | **Opt-in `--embedded-videos` flag — discover and transcribe videos embedded in a `not_video` HTML page.** Off by default; operator-activated; acts ONLY on the `not_video` html path. Ad-exclusion is **always-on** within this flag (no separate toggle — ads must NEVER be transcribed). | ✅ | **(a) Default-off / orthogonality:** flag has NO effect unless set; with it absent, the `not_video` html path is byte-for-byte unchanged (NF-2). Flag acts ONLY when `_video_host()` returns `not_video`; it is a NO-OP on `unambiguous_video` and `ambiguous_x_status` (those are `--video`'s domain). `--video` and `--embedded-videos` are mutually exclusive on any single invocation — passing both on the same URL is a usage error (exit 2). **(b) Embed discovery — allowlist-bounded, ReDoS-safe, ad-excluded:** the html skill's pipeline strips `<iframe>`/`<video>` before emitting Markdown (html preprocess.py L1079–1116) and its `meta.json` sidecar carries no embed URLs; therefore discovery CANNOT reuse the reader output. Discovery uses a single SIZE-CAPPED raw-HTML GET (reuse the `urllib` + browser-UA + byte-cap pattern of `_download_pdf`; cap constant `_EMBED_FETCH_MAX_BYTES`, default 2 MB) followed by a bounded, anchored, ReDoS-safe regex scan for known video-embed URL patterns only. The regex is anchored and uses a bounded quantifier (no unbounded `.*`), identical posture to the layout-config ReDoS load-gate. The raw HTML is scanned BEFORE the allowlist check — the filtering order is: allowlist → ad-network denylist → ad-context → ad-param → dedup → cap → fetch (see (k)). **(c) Allowlist (H-6 / SSRF):** discovered URLs are filtered against the SAME video-host allowlist as `_video_host()`: `youtube.com/embed`, `youtube-nocookie.com/embed`, `youtu.be`, `player.vimeo.com/video`, `vimeo.com`. Any `<iframe src>` not matching the allowlist is SILENTLY DROPPED — the page cannot trigger a fetch to an arbitrary host. Residual SSRF surface (operator-trusted, known video hosts only) is documented in SKILL.md like the pdf residual. Note: allowlist alone does NOT exclude ad embeds on allowlisted hosts (YouTube IMA ad units appear on `youtube.com`/`googlesyndication.com`); ad-exclusion (k) operates as the second gate after the allowlist passes. **(d) Cap — `--embedded-videos-max N`:** default 5. Cap is applied AFTER allowlist + ad-exclusion filters (so ad embeds never consume cap slots). Embeds surviving filtering beyond N are DROPPED; a note naming the count dropped is appended to the prepare envelope's `details` list — NO silent truncation. **(e) Dedup:** the same embed URL appearing multiple times in the HTML is fetched ONCE (set-based dedup before any subprocess is spawned; applied after ad-exclusion). **(f) Per-embed failure isolation + skip-reason logging:** a transcript failure for one embed (exit 3 no-media / exit 7 dep-missing / exit 5 auth) is SKIPPED with a logged note added to the envelope `details`; it does NOT abort the page import — the article prose remains the primary content and `_raw` is still written (contrast R-6e: on an `unambiguous_video` exit-3 IS a hard `FETCH_FAILED`; here embedded videos are supplementary). **The prepare envelope's `details` MUST log every discovered embed and WHY each was skipped** — skip reason is one of: `ad-denylist` / `ad-context` / `ad-param` / `not-allowlisted` / `dedup` / `cap` / `transcript-failure`. NO silent behavior is permitted at any filtering stage. **(g) `_raw` assembly:** `_raw` = article prose (primary), then each successfully transcribed embed appended under a heading `## Embedded video <k> — <title or url>`. `FetchResult.engine = "html+embedded:<count_transcribed>"` where `count_transcribed` is the number of embeds that produced a transcript. `_raw` is written only if the html result was ok and non-empty (R-3 invariant); embedded transcripts are strictly additive. **(h) Provenance + quality:** each embedded transcript is fetched via `_fetch_transcript()` (reused without modification), preserving its `engine`/`transcript_origin` in the heading. Any `quality_flag` from an embed sidecar is collected and aggregated per R-8 (e.g. `"english_auto_translation"` present on any embed is surfaced in the envelope). Each transcript subprocess ALWAYS receives `--lang` (C-3 / R-11 invariant). **(i) Reuse:** `_fetch_transcript()`, `_video_host()` (for allowlist matching), `require_bin`, `ensure_source_frontmatter`, and `_fm_safe` are all reused without modification; no fetch or parse logic is duplicated. **(j) mypy / Decision-17 / H-6:** `mypy --strict scripts/` clean on all new code; no `import anthropic`; `_fm_safe` applied to any scalar from a discovered embed URL before it reaches frontmatter. **(k) Ad-exclusion — always-on, no off switch (operator hard requirement):** advertising and promotional embeds MUST NEVER be transcribed regardless of operator flags. Implemented as three deterministic, ReDoS-safe filters applied in sequence after the allowlist, before dedup/cap/fetch — no LLM judgment, no network probe (Decision-17). **(k-1) Ad-network host denylist:** drop any embed whose host (or redirect URL) matches a known ad-network domain: `doubleclick.net` (incl. `*.doubleclick.net`, `googleads.g.doubleclick.net`, `g.doubleclick.net`), `googlesyndication.com` (incl. `pagead2.googlesyndication.com`), `imasdk.googleapis.com` (Google IMA SDK), `2mdn.net`, `adnxs.com`, `adservice.google.*`. Most are already outside the youtube/vimeo allowlist (so the allowlist drops them first), but they are listed explicitly here as belt-and-braces to catch youtube-hosted IMA/ad URLs that pass the host allowlist but resolve to an ad endpoint. Logged as skip reason `ad-denylist`. **(k-2) Ad-context exclusion:** skip any allowlisted embed whose ENCLOSING element (inspected within a BOUNDED character window around each matched `<iframe>` — NOT a full DOM parse) carries class/id/data-* attributes that signal an ad or non-content slot. Word-boundary, case-insensitive match on: `ad`, `ads`, `advert`, `advertisement`, `advertising`, `sponsor`, `sponsored`, `promo`, `promoted`, `dfp`, `adsbygoogle`, `googlead`, `outbrain`, `taboola`, `recommend`, `related`, `widget`. Also skipped: embeds inside `<ins class="adsbygoogle">`, inside `<aside>`, inside `[role=complementary]`, and inside `[aria-hidden="true"]`. The contextual scan is bounded (fixed character window, bounded quantifier regex) and ReDoS-safe — identical posture to the layout-config load-gate. Logged as skip reason `ad-context`. **(k-3) YouTube ad-param drop:** drop any youtube/youtube-nocookie embed URL carrying ad marker query parameters: `ad_type`, `adformat`, `ad_companion` (case-insensitive key match on the URL's query string). Logged as skip reason `ad-param`. **(k-4) Best-effort / residual:** ad-exclusion is a heuristic — a sufficiently disguised ad embed may slip through. This residual is acceptable because: (1) `--embedded-videos` is opt-in by the operator, (2) cap (`--embedded-videos-max`) bounds total embed count, (3) per-embed failure isolation means a slipped-through ad that returns no transcript is logged and skipped harmlessly, and (4) the prepare envelope's `details` log gives the operator full visibility. The residual and its boundary conditions are documented in `skills/wiki-import/SKILL.md` alongside the SSRF residual. |

---

## 4. Use cases

- **UC-1 (YouTube auto-route).** Operator: `wiki-import prepare --source https://youtu.be/NSVTpCfBMK8 ...`
  No `--video` flag. `_video_host()` returns `unambiguous_video`. `dispatch_fetch` invokes
  `_fetch_transcript()`. Transcript binary fetches captions via yt-dlp. `FetchResult.ok=True`,
  `engine="transcript:embedded-captions"`, stat sidecar carries title/uploader/duration.
  `ensure_source_frontmatter` injects `source:` (no FM in the .txt). Prepare envelope emits
  `raw_path`, `kind` (detected: `meeting` or `article`), `reason_harness: summarizing-meetings`.

- **UC-2 (Vimeo).** `https://vimeo.com/12345` → `unambiguous_video` → same transcript path.
  Captions via yt-dlp if available; ASR fallback if not (no ffmpeg needed for a non-HLS source).
  `engine="transcript:embedded-captions"` or `"transcript:whisper-cli"`.

- **UC-3 (X Broadcast auto-route).** `https://x.com/i/broadcasts/<id>` → `unambiguous_video`
  → transcript-fetcher. Broadcast has no captions → ASR path. If ffmpeg present and a whisper
  backend exists → transcript produced. `engine="transcript:macwhisper"` (or similar).
  `quality_flag` absent. `_raw` written; kind detected as `meeting`.

- **UC-4 (X status URL — default stays html, no regression).** `https://x.com/user/status/123`
  with no `--video` flag. `_video_host()` returns `ambiguous_x_status`. `dispatch_fetch` skips
  the video tier → existing html path. Behavior is byte-for-byte identical to today. This is
  the regression guard for all text-tweet imports.

- **UC-5 (X status with `--video` — text+video concatenation).** `--source https://x.com/user/status/123
  --video`. `_video_host()` returns `ambiguous_x_status`. `dispatch_fetch` enters Decision-3
  path: (1) html fetch → tweet prose; (2) transcript fetch → video audio. Both succeed.
  `_raw/<slug>.md` = `## Tweet\n\n<prose>\n\n## Video Transcript\n\n<transcript>`.
  `FetchResult.engine="html+transcript:embedded-captions"`. No content lost.

- **UC-6 (`--video` on a text-only tweet — graceful fallback).** `--source https://x.com/user/status/999
  --video`. Transcript binary exits 3 ("no transcript producible" — tweet has no attached media).
  `dispatch_fetch` falls back to the html result. `FetchResult.ok=True` from html, `engine="html"`.
  No error surfaced to the operator beyond a note in `details`. `_raw` is the tweet prose.

- **UC-7 (X Broadcast without ASR backend — typed dep error, no `_raw`).** `--source
  https://x.com/i/broadcasts/<id>` (unambiguous_video). Transcript binary exits 7 (ffmpeg absent
  or no whisper backend). `_fetch_transcript()` maps exit 7 → `ImportArticleError(exit_code=
  EXIT_DEP_MISSING)`. Prepare returns exit 6. Envelope: `{"error": "DEP_MISSING", "details":
  {"kind": "no_asr_backend", "remediation": "install ffmpeg + whisper backend"}}`. `_raw` not
  written (R-3 preserved).

- **UC-8 (Login-walled video — cookies guidance).** A private Vimeo or protected X video.
  Transcript binary exits 5 (HTTP 403). `_fetch_transcript()` maps exit 5 → FETCH_FAILED with
  hint: "supply `--cookies-from-browser <browser>` or `--cookies-file <path>`". Prepare exits 10.
  `_raw` not written.

- **UC-9 (NEG — plain article URL is byte-unchanged).** `--source https://example.com/article`.
  `_video_host()` returns `not_video`. `dispatch_fetch` enters the pre-existing html branch.
  No transcript binary invoked; behavior identical to pre-task code.

- **UC-12 (`--embedded-videos` — main video passes, ad embeds logged as skipped).** A blog post
  carries three iframes: one `player.vimeo.com/video/123` in the article body, one
  `www.youtube.com/embed/abc` inside `<div class="adsbygoogle">`, and one
  `pagead2.googlesyndication.com/...`. Discovery finds all three. Filtering: the Vimeo embed
  passes allowlist → denylist (clean) → ad-context (enclosing tag has no ad signal) → proceeds
  to fetch. The YouTube iframe passes allowlist but fails ad-context (`adsbygoogle` class) →
  logged `ad-context`, NOT fetched. The googlesyndication iframe fails both allowlist AND denylist
  → logged `not-allowlisted` + `ad-denylist`, NOT fetched. Result: exactly ONE transcript
  (Vimeo) appended to `_raw`; `engine = "html+embedded:1"`; the prepare envelope `details`
  lists all three embeds with their skip reasons. `_raw` written (article prose + 1 embed).

---

## 5. Acceptance / definition of done

1. **`pytest tests/` green** (all pre-existing tests pass; four core + five ad-exclusion test scenarios pass):
   - `test_video_dispatch_youtube_auto`: mock transcript binary returning ok txt+stat → verify
     `FetchResult.ok=True`, `engine` starts with `"transcript:"`, `_raw` written.
   - `test_video_dispatch_x_status_default_html`: x-status URL without `--video` → transcript
     binary is NOT invoked; html path taken (mock html binary called instead).
   - `test_video_dispatch_x_status_video_concat`: x-status with `--video`, both html + transcript
     mocks return ok → verify concatenated body has both sections.
   - `test_video_dispatch_broadcast_no_asr`: transcript mock exits 7 → verify exit 6,
     envelope `DEP_MISSING`, no `_raw` written.
   - Bonus (if time): `test_video_dispatch_x_status_video_text_only_fallback` (transcript mock
     exits 3 → html result returned, no error).
   - **Ad-exclusion (stub-first, offline HTML fixtures, transcript binary mocked):**
   - `test_embedded_ad_context_adsbygoogle`: `<ins class="adsbygoogle">` wrapping a youtube embed
     → transcript binary NOT called; skip reason `ad-context` in envelope `details`.
   - `test_embedded_denylist_googlesyndication`: a `googlesyndication.com` iframe and a
     `doubleclick.net` iframe → NOT fetched; skip reasons `not-allowlisted` / `ad-denylist`.
   - `test_embedded_ad_context_aside_related`: embed inside `<aside class="related-videos">` →
     NOT fetched; skip reason `ad-context`.
   - `test_embedded_one_real_two_ads`: page fixture with ONE main-content Vimeo embed + 2 ad
     embeds (one ad-context, one denylist) → exactly ONE transcript subprocess call; 2 embeds
     logged as skipped with distinct reasons; `engine = "html+embedded:1"`.
   - `test_embedded_youtube_ad_param`: youtube embed URL with `?ad_type=video_ads&...` →
     NOT fetched; skip reason `ad-param`.
2. **`mypy --strict scripts/` clean** on all modified files.
3. **No `import anthropic`** in any new or modified file (grep gate).
4. **`skills/wiki-import/SKILL.md`** updated: dispatch line shows three branches; deps section
   distinguishes yt-dlp-only (captioned) vs yt-dlp+ffmpeg+whisper (ASR); `--video` flag documented;
   `--embedded-videos` section documents always-on ad-exclusion, skip-reason logging, and residual.
5. **Ad-exclusion always-on:** no flag exists to disable ad-exclusion within `--embedded-videos`;
   the three filters (ad-network denylist / ad-context / ad-param) are unconditional; all five
   ad-exclusion test scenarios pass; skip reasons appear in envelope `details` for every dropped embed.
6. **VDD reviewers APPROVE**: `code-reviewer` (correctness, NF-2 regression proof) +
   `critic-security` (SSRF residual, H-6 frontmatter injection, cookies handling, argv safety,
   H-6 stat values through `_fm_safe`, ad-exclusion bounded-regex ReDoS safety) +
   `critic-logic` (edge-case coverage, Decision 3 concat, exit-code mapping, R-3 `_raw`
   non-write invariant, ad-exclusion filter ordering, skip-reason logging completeness).
7. **Architecture docs** updated: `docs/ARCHITECTURE.md` §2.3 fetch-dispatch diagram extended to
   three branches; `docs/architectures/open-questions.md` carries Q-044-* entries including
   Q-044-11 (ad-exclusion heuristic + documented residual).

---

## 6. Risks / open questions

- **Q-044-1 (transcript-fetcher location).** The conventional `--transcript-bin` default path
  must be agreed: `~/.claude/skills/transcript-fetcher/scripts/fetch.py` (symlink-deployed like
  `html`/`pdf`) vs the Universal-skills source path. If not symlink-deployed, the operator must
  always pass `--transcript-bin`. Recommendation: document both; default to the symlink path with
  a clear "absent → exit 6" contract.
- **Q-044-2 (stat sidecar field names).** The implementation assumes `transcript_origin`,
  `quality_flag`, `title`, `uploader`, `upload_date`, `duration_sec` from the sidecar. Confirm
  these against the transcript-fetcher SKILL.md §4 / `example_output_stat.json`. Any mismatch
  is a silent null (graceful) but should be tested.
- **Q-044-3 (Skool URL shape for classifier).** The `_video_host()` classifier must identify
  Skool lesson URLs (`/<community>/classroom/<id>?md=<lesson-id>`) vs non-lesson Skool pages
  (landing/about/calendar — rejected by the skill). Confirm the URL pattern used for the
  lesson-vs-non-lesson guard and encode it in the classifier (not just the host).
- **Q-044-4 (transcript binary timeout).** Broadcasts/Spaces with ASR can be long. The suggested
  `_TIMEOUT_TRANSCRIPT = 300` seconds may be insufficient for a 2-hour Space. Should be an
  env-overridable constant (e.g. `WIKI_TRANSCRIPT_TIMEOUT_S`), documented in SKILL.md.
- **Q-044-5 (concatenation separator).** Decision 3 concatenation uses `## Tweet` / `## Video
  Transcript` headers. Confirm with operator that these headings do not conflict with the
  `summarizing-meetings` harness's structural expectations for speaker-attributed content.
- **Q-044-6 (`_detect.py` orthogonality verification).** The spec says "no change" — but the
  Planning phase MUST read `_detect.py` and confirm that `_THREAD_HOSTS` in that file (currently
  includes `"x.com/"`) correctly assigns kind `thread` to x.com sources even when the body is a
  transcript. If the concatenated body overrides the URL signal, the operator's `--kind` override
  is the safety valve — document this in SKILL.md.
- **Q-044-7 (SSRF residual).** Like the pdf download path, operator-supplied video URLs are
  passed to the transcript subprocess which makes HTTPS calls. This is documented as the same
  residual SSRF surface — acknowledged, operator-trusted. Confirm critic-security sign-off.
- **Q-044-8 (`--video` flag scope in `apply`).** The `--video` flag is a `prepare`-time routing
  hint. Does `apply` need to know it was used (e.g. to set a different note `type:` or engine
  field)? Lean: no — `apply` receives `--kind` from prepare's envelope and the `engine` is in
  the `_raw` frontmatter provenance. No new `apply` arg needed. Verify in Architecture phase.
- **Q-044-9 (embedded-video design rationale — capped raw-HTML scan).** Why not compose with the
  html skill's output? The html skill strips iframes before emitting Markdown and its `meta.json`
  carries no embed URLs; the raw HTML scan is the only viable mechanism. Document in
  `docs/architectures/open-questions.md`.
- **Q-044-10 (discovery mechanism — html-skill-compose ruled out).** Confirmed: `meta.json` from
  the html skill does not carry embed URLs; raw-HTML scan with a SIZE-CAPPED GET is the chosen
  approach. No alternative remain. Closed in Architecture phase.
- **Q-044-11 (ad-exclusion heuristic + documented residual).** The three ad-exclusion filters
  (denylist / ad-context / ad-param) are deterministic regex/string heuristics, not a DOM parser
  or an LLM. A sufficiently disguised ad (e.g. no ad signal in class/id, hosted on an allowlisted
  host, no ad query params) may slip through. The residual is bounded by: opt-in flag, cap,
  per-embed failure isolation, and full skip-reason logging. Architecture phase MUST document this
  residual in `docs/architectures/open-questions.md` and confirm that the bounded-regex ad-context
  scan cannot be tricked into a catastrophic backtrack on attacker-controlled HTML content (ReDoS
  review: the character window is a fixed-length slice, the attribute match is a simple alternation
  with no nested quantifiers — safe by construction). Security reviewer sign-off required.

---

## 7. Implementation deltas (build + dogfood — recorded by /update-docs)

As-shipped reconciliations with the spec; **none changed scope** (all green: 1720 tests,
`mypy --strict`, zero-DDL/zero-deps, no `import anthropic`).

- **S0 contract reconciliation** (verified against the real `transcript-fetcher` source — resolves
  Q-044-2): (i) `transcript_origin` is set ONLY by the X adapter — youtube/vimeo/skool leave it null
  — so `engine` falls back to the stat's `chosen_track_kind` (+`asr_backend` for ASR) instead of
  emitting `transcript:unknown` (refines R-9); (ii) `title`/`uploader`/`upload_date` populate ONLY
  with `--with-description`, so wiki-import ALWAYS passes it (so R-3f yields a real title/author/date);
  (iii) transcript exit **6** = rate-limit (HTTP 429) → FETCH_FAILED (exit 10). Shipped exit map:
  7→DEP_MISSING(6) · 6→FETCH_FAILED(10) · 5→cookies(10) · 3→no-media. Sidecar = `<out>.txt.stat.json`.
- **VDD L-1 fix:** `_fetch_x_status_with_video` re-raises a transcript dep-missing (exit 7) when the
  html fetch ALSO failed (login-walled tweet), surfacing the actionable DEP_MISSING (exit 6 +
  remediation) instead of a generic FETCH_FAILED — symmetric with the no-media/auth/rate branch.
  (VDD gate: 1 confirmed finding fixed; 2 refuted as test-granularity bikeshedding.)
- **Slug-length fix (pre-existing bug, surfaced by the x-status dogfood):** a titleless source (a
  tweet whose whole body becomes the og:title) produced a >255-byte `_raw/<slug>.md` filename →
  `OSError [Errno 63] File name too long`. `_derive_slug` now byte-caps the slug (≤180 B, hyphen-
  boundary backoff). NOT a TASK 044 regression (any long title triggered it). Follow-up filed:
  [`docs/issues/task-044-x-status-slug-instability.md`](issues/task-044-x-status-slug-instability.md).
- **Dogfood:** both test URLs imported into `personal` — the article via `engine=html` (unchanged
  not_video path), the x-status via `--video` → `engine=html+transcript:embedded-captions` concat;
  2 notes + 10 concept pages filed + indexed.

(Design rationale → `docs/architectures/open-questions.md` Q-044-*.)
