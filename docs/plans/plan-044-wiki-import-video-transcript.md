# PLAN 044 — video sources for wiki-import via transcript-fetcher

Add a THIRD wrapped external-skill fetch branch (`transcript-fetcher`) to `dispatch_fetch` alongside
`html`/`pdf` — composition, not reinvention (ADR-001 "Wrap + Index"). **NF-2 is the gate:** a
`not_video` URL takes the pre-existing html/pdf path byte-for-byte (the new media-tier sits BEFORE the
html branch but only fires on a video-shaped URL or an explicit `--video`). Throughout: **no `import
anthropic`** (Decision-17 — routing is URL-shape + `--video`, never an LLM guess / network probe);
**zero SQLite DDL** (`user_version` 7 untouched); **zero new Python runtime deps** (`requirements.txt`
unchanged — the binary is external, fail-fast via `require_bin` like html/pdf); `mypy --strict scripts/`;
H-6 (stat-sidecar scalars through `_fm_safe`) + R-3 (raw written ONLY on a non-empty ok fetch) +
`validate_inside_vault` (R-26) hold; vendor-agnostic (subprocess + flags). `_detect.py`/`--kind` stays
ORTHOGONAL (no new kind, no new harness — always `summarizing-meetings`). ARCHITECTURE §2.3.2 +
open-questions Q-044-* are the design record; this plan ships them.

**R-13 (opt-in `--embedded-videos`, beads S13–S16; ARCHITECTURE §2.3.3, Q-044-9/10/11):** on a
`not_video` html page ONLY, optionally discover + transcribe `<iframe>` video embeds via a single
SIZE-CAPPED raw-HTML GET (the html skill strips iframes before Markdown, so its output cannot be
reused — Q-044-10) + a bounded ReDoS-safe scan. **Ad-exclusion is ALWAYS-ON** (no off switch —
operator hard requirement): the fixed filter chain is `allowlist → ad-network denylist → ad-context
→ ad-param → dedup → cap → fetch`, every discovered embed logged with its skip reason in the envelope
`details` (NO silent behavior), per-embed failure isolation (a supplementary embed never aborts the
page). Reuses `_fetch_transcript`/`_video_host`/`_fm_safe` unmodified; opt-in + cap + isolation +
allowlist egress bound + bounded regex keep it Decision-17 / H-6 / NF-2 clean. S17 is the FINAL VDD
gate (its critic-security + critic-logic explicitly cover the ad-exclusion chain, allowlist egress,
and ReDoS).

## Atomic checklist (stub-first per step; Red→Green; each bead = one verifiable gate)

- **S0 — Branch + contract pin (do FIRST — the entry gate; R-1..R-11, Q-044-1/2/3).** Branch
  `task-044-wiki-import-video-transcript`. RE-READ the transcript-fetcher CLI contract
  (`/Users/sergey/dev-projects/Universal-skills/skills/transcript-fetcher/SKILL.md §4`) +
  `examples/example_output_stat.json`, and pin the EXACT facts the wrapper depends on into THIS bead
  (then ARCHITECTURE §2.3.2): (i) **stat sidecar path** = `<out>.txt.stat.json` (Q-044-2), fields
  `transcript_origin`, `quality_flag`, `title`, `uploader`, `upload_date`, `duration_sec` (record any
  name mismatch — a missing field is a graceful null); (ii) **typed exit codes** — 2 usage, 3 no
  transcript producible, 5 source-auth (401/403), 6 rate-limit, 7 MissingDependency (`details.remediation`
  hint), 1 unexpected (note: this differs from the wiki-import exit map — exit 3 = no-media→fallback,
  exit 5 = cookies hint, exit 7 = dep-missing); (iii) **host allowlist + Skool lesson URL pattern**
  `/<community>/classroom/<id>?md=<lesson-id>` (Q-044-3) and the label-boundary host rule (rejects
  `evil-youtube.com`). Identify the EXACT `dispatch_fetch` insertion point: a new media-tier BEFORE the
  `is_url and not bare.endswith(".pdf")` html branch (`_fetch.py` L323). *Gate:* contract facts pinned in
  this bead; insertion point + exit-code translation table recorded (no code yet).

- **S1 — `_video_host()` classifier — STUB + RED test (R-1).** Add `def _video_host(url: str) -> str:`
  to `_fetch.py` returning a literal STUB (`"not_video"`) — a PURE function, no I/O, no imports beyond
  stdlib `re`/urllib (R-1g, NF-1c). Add module constants for the host sets
  (`_VIDEO_HOSTS_YOUTUBE`/`_VIDEO_HOSTS_VIMEO`/`_VIDEO_HOSTS_SKOOL`/`_VIDEO_HOSTS_X`) + the X
  broadcast/space/status regexes + the Skool lesson regex. Add `tests/test_video_host.py` (or extend
  `test_import_article_fetch.py`) asserting the FULL truth table — RED against the stub: youtube.com /
  youtu.be / m./music./www. → `unambiguous_video` (a); vimeo.com / www. / player. → `unambiguous_video`
  (b); a Skool `/classroom/<id>?md=<lesson>` → `unambiguous_video`, a Skool `/about`/landing →
  `not_video` (c, Q-044-3); `x.com|twitter.com/i/broadcasts/<id>` + `/i/spaces/<id>` →
  `unambiguous_video` (d); `x.com|twitter.com/<user>/status/<id>` → `ambiguous_x_status` (e); plain
  article URL + local path → `not_video` (f); `evil-youtube.com` / `youtube.com.evil.net` → `not_video`
  (h, label-boundary). *Gate:* test imports + runs RED (documented expected failures); function importable;
  `grep import anthropic` clean.

- **S2 — `_video_host()` logic GREEN (R-1).** Implement the classifier: parse the host via
  `urlsplit(...).hostname`, lower-case, match each host set with the label-boundary rule
  (`host == h or host.endswith("." + h)` — same idiom as `_X_HOSTS` at L146 / `_is_x_login_wall`); X
  branch distinguishes `/i/broadcasts/`+`/i/spaces/` (unambiguous) from `/<user>/status/<id>`
  (ambiguous) by path regex; Skool requires the lesson-path regex (host alone is `not_video`). Make
  `tests/test_video_host.py` GREEN. *Gate:* `pytest tests/test_video_host.py` green; `mypy --strict
  scripts/` clean on `_fetch.py`; classifier is I/O-free (no subprocess/urllib call inside it).

- **S3 — `_fetch_transcript()` + `_transcript_python()` — STUB + RED test (R-3, R-4, R-7..R-11).** Add
  `_transcript_python(script_path)` (copy `_pdf_python`, L114 — prefer the skill's own
  `scripts/.venv/bin/python`). Add `_TIMEOUT_TRANSCRIPT` (300 s, env-overridable via
  `WIKI_TRANSCRIPT_TIMEOUT_S` — Q-044-4). Add `def _fetch_transcript(transcript_bin, url, *, lang,
  max_duration_min=None, cookies_from_browser=None, cookies_file=None) -> FetchResult:` as a STUB
  returning `FetchResult(ok=False, engine="transcript")`. Extend the `FetchResult` dataclass with
  `quality_flag: str | None = None` (R-8b). Add `tests/test_fetch_transcript.py` mocking `subprocess.run`
  + a temp `.txt`+`.stat.json` writer (the SAME pattern as `_wa_run`/`fake_run` in
  `test_import_article_fetch.py`) — RED: (a) ok run → `engine == "transcript:<origin>"`, `raw_text` ==
  the .txt body, `title`/`author`/`date` from stat (R-3c-f, R-9a); (b) `--json-errors` ALWAYS in argv +
  the venv python from `_transcript_python` (R-11f, R-3a-b); (c) passthrough flags appear in argv ONLY
  when set (R-11a-e); (d) exit 7 → `ImportArticleError(exit_code=EXIT_DEP_MISSING)` carrying the
  `details.remediation`/no_asr_backend hint (R-7a-b,e); (e) exit 5 → FETCH_FAILED error with the
  cookies-from-browser/cookies-file hint (R-10a-b); (f) exit 3 → a typed no-media signal the caller can
  detect (R-6a); (g) `quality_flag == "english_auto_translation"` from stat → surfaced on FetchResult
  (R-8a-b); (h) temp dir cleaned in a `finally` even on error (R-3g). *Gate:* test runs RED; importable.

- **S4 — `_fetch_transcript()` logic GREEN (R-3, R-4, R-7, R-8, R-9, R-10, R-11).** Implement: argv =
  `[_transcript_python(bin), bin, url, "--out", tmp/"t.txt", "--json-errors", "--lang", lang]` + the set
  passthroughs (never a shell string — NF-3a); `subprocess.run(... timeout=_TIMEOUT_TRANSCRIPT,
  env=_skill_env())` in a `try` whose `finally` `rmtree`s the tempdir (R-3g). (`--lang` is ALWAYS in
  the base argv — never transcript-fetcher's own `ru` default — C-3; assert it in the S3/S4 test.) On returncode 0: read
  `tmp/"t.txt"` (raw_text) + `tmp/"t.txt.stat.json"`; `engine = f"transcript:{stat.get('transcript_origin','unknown')}"`
  (R-9a); `title=stat.get("title")`, `author=stat.get("uploader")`, `date=stat.get("upload_date")` (R-3f);
  `quality_flag=stat.get("quality_flag")` (R-8); `ok=bool(raw_text.strip())`. On non-zero: route the
  transcript-fetcher exit code via the S0 translation table — **7** → raise
  `ImportArticleError(EXIT_DEP_MISSING)` with the no_asr_backend remediation (R-7); **5** → FetchResult
  error with cookies hint, exit 10 (R-10); **3** → FetchResult carrying a `details.kind=="no_media"`
  marker (consumed by R-6 at dispatch); **else** → `_parse_skill_error`. Make `test_fetch_transcript.py`
  GREEN. *Gate:* `pytest tests/test_fetch_transcript.py` green; `mypy --strict scripts/` clean.

- **S5 — `dispatch_fetch` media-tier wiring — STUB + RED tests (R-2, R-6, NF-2).** Extend
  `dispatch_fetch` SIGNATURE with `transcript_bin: str`, `video: bool = False` (keyword-only,
  defaulted — so existing call sites stay valid until S8 wires the CLI), plus the passthrough kwargs
  (`lang`, `max_duration_min`, `cookies_from_browser`, `cookies_file`). Insert a media-tier STUB BEFORE
  the html branch (`raise NotImplementedError` / passthrough). Add to `test_import_article_fetch.py`
  (mock the transcript bin alongside H2M/PDFX) — RED: (a)
  `test_video_dispatch_youtube_auto` — `youtu.be/<id>`, no `--video` → transcript bin invoked, html NOT;
  `engine.startswith("transcript:")`, ok (R-2a, UC-1); (b)
  `test_video_dispatch_x_status_default_html` — `x.com/u/status/1` WITHOUT `video=True` → transcript bin
  NOT invoked, html path taken (R-2b, UC-4, the NF-2 regression guard); (c)
  `test_video_dispatch_broadcast_no_asr` — `x.com/i/broadcasts/<id>`, transcript mock exits 7 →
  `ImportArticleError(EXIT_DEP_MISSING)` raised / propagated (R-7, UC-7); (d)
  `test_video_dispatch_x_status_video_text_only_fallback` — `status` + `video=True`, transcript exits 3
  (no media) → falls back to the html result, `engine=="html"`, no error (R-6, UC-6); (e) a `not_video`
  plain article URL is byte-unchanged (assert the existing html-OK test still passes — NF-2a, UC-9);
  (f) `test_video_dispatch_youtube_no_media_fetch_failed` — `youtu.be/<id>` (unambiguous_video),
  transcript mock exits 3 (no media) → **FETCH_FAILED (exit 10), `_raw` NOT written, html mock NOT
  invoked** (R-6e, C-1 — no junk-html fallback on an unambiguous-video host).
  *Gate:* the six tests run RED; signature change keeps existing call sites compiling.

- **S6 — `dispatch_fetch` media-tier logic GREEN (R-2, R-5, R-6).** Implement the tier per the routing
  table: classify `host = _video_host(source)` (URL sources only); `unambiguous_video` → return
  `_fetch_transcript(...)` (R-2a); `ambiguous_x_status` AND NOT `video` → fall THROUGH to the existing
  html branch unchanged (R-2b); `ambiguous_x_status` AND `video` → the S7 concat path; `not_video` →
  existing html/pdf dispatch byte-for-byte (R-2d). The exit-3 no-media result from `_fetch_transcript`
  on an `ambiguous_x_status` falls back to the html path (R-6a-d) — mirror the existing
  `arxiv_no_html`/`pdf` fall-back idiom (L327-338). **On an `unambiguous_video` URL the exit-3
  (no_media) result is returned AS `FETCH_FAILED` (exit 10), `_raw` not written, NO html fallback**
  (no useful text path — R-6e, C-1); the no-media→html fallback is scoped EXCLUSIVELY to
  `ambiguous_x_status` + `--video`. Make `test_video_dispatch_youtube_auto` /
  `_x_status_default_html` / `_broadcast_no_asr` / `_x_status_video_text_only_fallback` /
  `_youtube_no_media_fetch_failed` GREEN; the `not_video` regression assertions stay green.
  *Gate:* those five + the pre-existing fetch suite green; `mypy --strict`.

- **S7 — x-status text+video CONCATENATION — STUB + RED then GREEN (R-5, Decision 3).** Add the
  concat path used by S6 when `ambiguous_x_status` AND `video`: (1) run `_fetch_html` on the status URL
  (tweet prose); (2) run `_fetch_transcript` on the same URL (video). RED test
  `test_video_dispatch_x_status_video_concat` (both mocks return ok): body ==
  `## Tweet\n\n<html_body>\n\n## Video Transcript\n\n<transcript_body>`, `engine ==
  "html+transcript:<origin>"` (R-5e-f), `quality_flag` propagated (R-5g, R-8). Edge branches in the SAME
  bead: html fails → transcript-only (R-5c); transcript exit-3 no-media → html-only (R-5d = R-6, already
  covered by S6's fallback test). Implement → GREEN. **Q-044-5 check:** confirm the `## Tweet` / `##
  Video Transcript` headings do not collide with the `summarizing-meetings` structural expectation;
  record the decision in ARCHITECTURE §2.3.2. *Gate:* concat test + the S6 suite green.

- **S8 — CLI flags + prepare wiring (R-2c, R-4, R-8b, R-11; NF-1).** In `__init__.py`: add to the
  `prepare` parser (`_build_parser`, ~L693) `--video` (`action="store_true"`), `--transcript-bin`
  (`default=_DEFAULT_TRANSCRIPT`, a new module constant pointing at the conventional symlink path
  `~/.claude/skills/transcript-fetcher/scripts/fetch.py` — Q-044-1, with the absent→exit-6 contract),
  and the passthroughs `--max-duration-min` (int), `--cookies-from-browser`, `--cookies-file`, `--lang`
  (default unset → `prepare` falls back to `_vault_language(vault_root)` — R-11a). Thread them through
  the `dispatch_fetch(...)` call in `prepare()` (L175). Add `quality_flag` to the prepare envelope's
  top-level key (R-8b) — emitted from `result.quality_flag`. **H-6 (NF-3c):** ensure stat scalars
  (`title`/`author`/`date`) flow through the EXISTING `ensure_source_frontmatter`/`_fm_safe` path (they
  already do — `_raw` has no FM so `ensure_source_frontmatter` injects `source:`; the title/author land
  in the envelope, not raw FM — confirm no new injection sink). Extend
  `tests/test_import_article_prepare.py`: a YouTube prepare (mock transcript bin) emits `engine` starting
  `transcript:`, writes `_raw`, surfaces `quality_flag`; a status-without-`--video` prepare is unchanged.
  *Gate:* prepare tests green; `mypy --strict`; `argparse` accepts the new flags.

- **S9 — `_detect.py` orthogonality VERIFICATION (R-12, Q-044-6) — verify-only, no functional change.**
  READ `_detect.py`: confirm `_THREAD_HOSTS` (`x.com/`, `twitter.com/`) still routes an x.com source to
  `thread`, and a timestamp/speaker-turn transcript body detects as `meeting` via `_looks_like_transcript`
  — both ALREADY correct (R-12a-d). Add to the existing `test_import_article_detect.py` an assertion (no
  code change to `_detect.py`): a transcript-shaped body from a youtube URL → `meeting`; an x-status →
  `thread` regardless of body (operator `--kind` is the override valve — document in SKILL.md). *Gate:*
  detect tests green; `git diff _detect.py` empty (verify-only).

- **S10 — SKILL.md docs via `skill-enhancer` (DoD 4; R-2, R-4, R-7, R-8, R-10, R-11).** Update
  `skills/wiki-import/SKILL.md`: the dispatch line (L46-50) → THREE branches (html / pdf / **transcript**)
  with the host-routing rule (unambiguous-video auto; `x-status` default-html, `--video` forces the
  concat path); the exit-codes table (L126-127) → the transcript dep-missing (exit 6) + the cookies/no-media
  cases; a **Dependencies** note distinguishing yt-dlp-ALWAYS (captioned video) vs ffmpeg+a whisper
  backend ONLY-for-ASR (caption-less Broadcasts/Spaces); document `--video`, `--transcript-bin`, the
  passthroughs, `WIKI_TRANSCRIPT_TIMEOUT_S`, and that a `quality_flag` in the prepare envelope MUST be
  surfaced to the operator BEFORE the REASON harness (R-8c). Version bump + Maintenance note. *Gate:*
  `skill-validator` clean; the dispatch line names three branches; `--video` documented.

- **S11 — ARCHITECTURE + open-questions finalization (DoD 6; NF-2).** Finalize ARCHITECTURE §2.3.2
  (the routing table + the S0-pinned exit-code translation + the S7 concat-heading decision +
  the Skool lesson-URL rule) and the §2.3 fetch-dispatch description (html/pdf → +transcript). Add
  `docs/architectures/open-questions.md` entries Q-044-1..Q-044-8 (resolve each to the shipped shape:
  the `--transcript-bin` default, stat field names, Skool URL, the timeout env-var, the concat
  separator, `_detect.py` orthogonality, the SSRF residual, the `apply`-arg lean = "no new apply arg").
  *Gate:* docs match shipped behavior; no PW-Q drift in `KNOWN_ISSUES.md` (no manual edit there).

> **R-13 amendment (beads S13–S16).** S0–S11 are unchanged. The original VDD + NF-2 regression
> gate (formerly S12) is RENUMBERED to **S17** and remains the FINAL bead — the R-13 work beads
> S13–S16 are inserted before it. (There is no S12 — its scope is now S17.)

- **S13 — `_discover_embedded_videos()` STUB + RED tests (R-13a-c, R-13k filter truth table).** Add
  `def _discover_embedded_videos(raw_html: str) -> list[tuple[str, str]]:` to `_fetch.py` returning a
  literal STUB (`[]`) — a PURE function over a raw-HTML string (no I/O, no subprocess, stdlib `re`/
  `urllib.parse` only — Decision-17, NF-1c). Add `_download_raw_html(url) -> str` STUB (mirrors
  `_download_pdf`, L252 — `urllib` + browser-UA + byte-cap `_EMBED_FETCH_MAX_BYTES`, default 2 MB,
  ReDoS-irrelevant; returns `""`). Add the module constants: `_EMBED_FETCH_MAX_BYTES = 2 * 1024 * 1024`;
  `_EMBED_ALLOW_PATTERNS` (the SAME allowlist as `_video_host()`: `youtube.com/embed`,
  `youtube-nocookie.com/embed`, `youtu.be`, `player.vimeo.com/video`, `vimeo.com`);
  `_AD_NETWORK_HOSTS` (denylist: `doubleclick.net`/`*.`, `googleads.g.doubleclick.net`,
  `g.doubleclick.net`, `googlesyndication.com`/`pagead2.`, `imasdk.googleapis.com`, `2mdn.net`,
  `adnxs.com`, `adservice.google.*`, label-boundary like `_VIDEO_HOSTS_*`); `_AD_CONTEXT_WORDS` (the
  word-boundary class/id/data-* alternation: `ad|ads|advert|advertisement|advertising|sponsor|
  sponsored|promo|promoted|dfp|adsbygoogle|googlead|outbrain|taboola|recommend|related|widget`);
  `_AD_PARAM_KEYS` (`ad_type`, `adformat`, `ad_companion`); `_EMBED_CONTEXT_WINDOW` (fixed-length
  char window for the bounded ad-context scan — ReDoS-safe by construction, no nested quantifiers,
  same posture as the layout-config load-gate). The discovery contract: return `(embed_url,
  skip_or_keep_reason)` pairs so the caller can log EVERY discovered embed (R-13f). Add
  `tests/test_embedded_discovery.py` with offline HTML fixtures encoding the **ad-exclusion filter-chain
  truth table** as RED tests (allowlist → ad-network denylist → ad-context → ad-param → dedup → cap →
  fetch — R-13b/k order): **(1)** `test_embedded_ad_context_adsbygoogle` — `<ins class="adsbygoogle">`
  wrapping a `www.youtube.com/embed/abc` → reason `ad-context`, NOT kept (DoD §5.1, R-13k-2); **(2)** TWO
  distinct denylist fixtures so the `ad-denylist` reason is exercised on a path the allowlist did NOT
  already drop (ADV-1): **(2a)** `test_embedded_not_allowlisted_googlesyndication` — a
  `pagead2.googlesyndication.com` iframe + a `googleads.g.doubleclick.net` iframe FAIL the allowlist
  FIRST → reason `not-allowlisted`, NOT kept (R-13c); **(2b)** `test_embedded_denylist_youtube_ima` —
  an **allowlist-PASSING** youtube embed whose `src` carries an ad endpoint/redirect (e.g.
  `www.youtube.com/embed/x` whose src embeds `imasdk.googleapis.com` / `googleads.g.doubleclick.net`)
  → reason **`ad-denylist`** — the ONLY path that reaches the belt-and-braces step-3 denylist (R-13k-1); **(3)** `test_embedded_ad_context_aside_related` — embed inside `<aside class="related-videos">`
  → reason `ad-context` (also covers `recommend|related`, `<aside>`, `[role=complementary]`,
  `[aria-hidden="true"]` — R-13k-2); **(4)** `test_embedded_one_real_two_ads` — fixture with ONE
  main-content `player.vimeo.com/video/123` + 2 ad embeds (one ad-context, one denylist) → EXACTLY one
  `keep`, two distinct skip reasons (R-13d/e/f); **(5)** `test_embedded_youtube_ad_param` —
  `www.youtube.com/embed/x?ad_type=video_ads` → reason `ad-param`, NOT kept (R-13k-3); **(6)** a clean
  allowlisted `youtu.be/<id>` outside any ad context → reason `keep`; **(7)** dedup — same allowlisted
  URL twice → one `keep` + one `dedup`. *Gate:* tests import + run RED (documented expected failures);
  `_discover_embedded_videos`/`_download_raw_html` importable; `grep import anthropic` clean; the
  ad-context regex is anchored + bounded-quantifier (assert no `.*` / nested `+*` by reading the source).

- **S14 — `_discover_embedded_videos()` logic GREEN (R-13b, R-13c, R-13k filter chain + ReDoS-safe**
  **bounded scan).** Implement the filter chain in the FIXED order over the raw HTML: (1) anchored,
  bounded-quantifier scan for `<iframe ... src="...">` URLs (no unbounded `.*` — bound the `src`
  attribute length); (2) **allowlist** — keep only `_EMBED_ALLOW_PATTERNS` matches (reuse `_video_host`'s
  label-boundary host idiom for the host portion); a non-match → reason `not-allowlisted` (logged, not
  raised); (3) **ad-network denylist** — drop any embed whose host (or a wrapping/redirect URL in the
  src) matches `_AD_NETWORK_HOSTS` → reason `ad-denylist` (belt-and-braces for youtube-hosted IMA/ad
  endpoints that pass step 2); (4) **ad-context** — for each surviving iframe, take a BOUNDED
  `_EMBED_CONTEXT_WINDOW` char slice of the HTML around the match and run a case-insensitive,
  word-boundary alternation over `_AD_CONTEXT_WORDS` on the nearest enclosing tag's class/id/data-*
  attributes, plus the `<ins class="adsbygoogle">` / `<aside>` / `[role=complementary]` /
  `[aria-hidden="true"]` container checks — NOT a full DOM parse, NOT an LLM judgment (Decision-17);
  match → reason `ad-context`; (5) **ad-param** — for a surviving youtube/youtube-nocookie URL, parse the
  query (`urllib.parse`) and drop on any `_AD_PARAM_KEYS` key (case-insensitive) → reason `ad-param`;
  (6) **dedup** — set-based on the normalized URL, second+ occurrences → reason `dedup`; the survivors
  carry reason `keep`. The function returns the full ordered `(url, reason)` log (every discovered embed
  appears exactly once) — cap is applied by the caller (S15) so the cap-dropped count is loggable.
  Implement `_download_raw_html` as the size-capped GET (same chunk-loop + `_EMBED_FETCH_MAX_BYTES` cap
  + `finally`-safe as `_download_pdf`; decode bytes best-effort to text). Make all seven
  `test_embedded_discovery.py` tests GREEN. *Gate:* `pytest tests/test_embedded_discovery.py` green;
  `mypy --strict scripts/` clean on `_fetch.py`; the function is subprocess-free + network-free (the GET
  lives in `_download_raw_html`, mocked in tests); re-confirm anchored/bounded regex (no catastrophic
  backtrack on attacker HTML — Q-044-11 ReDoS review).

- **S15 — `dispatch_fetch` embedded-append wiring + per-embed isolation + assembly — STUB + RED then**
  **GREEN (R-13a, R-13d-i).** Extend `dispatch_fetch` SIGNATURE with `embedded_videos: bool = False`,
  `embedded_videos_max: int = 5` (keyword-only, defaulted — existing call sites + S5's media-tier stay
  valid). Insert the embedded branch INSIDE the `not_video` html path ONLY (after the html result is
  `ok` and non-empty — strictly additive, never on `unambiguous_video`/`ambiguous_x_status`: NO-OP
  there per R-13a; the `--video`+`--embedded-videos` clash is rejected at the CLI layer S16, exit 2).
  STUB first (`raise NotImplementedError` inside the new branch), then implement: call
  `_download_raw_html(source)` → `_discover_embedded_videos(html)`; log EVERY `(url, reason)` to a
  `details["embedded"]` list (R-13f — NO silent behavior); apply the **cap** to the `keep` rows
  (survivors beyond `embedded_videos_max` → logged `cap`, R-13d); for each capped-in `keep` URL call
  `_fetch_transcript(... lang=lang ...)` (REUSED unmodified — R-13i; `--lang` ALWAYS forwarded, C-3);
  **per-embed isolation (R-13f)** — a transcript exit 3/5/7 for one embed is caught, logged
  `transcript-failure` (with the exit reason), and SKIPPED; it does NOT abort the page import (contrast
  R-6e §2.3.2 hard-fail). Assemble `_raw` (R-13g): article prose (primary) + each ok embed appended as
  `## Embedded video <k> — <title or url>`; `FetchResult.engine = "html+embedded:<count_transcribed>"`
  (count = embeds that produced a transcript); aggregate any embed `quality_flag` onto the FetchResult
  per R-8 (R-13h); `_raw` written only on the ok+non-empty html result (R-3). Add to
  `test_import_article_fetch.py` (mock the transcript bin + `_download_raw_html`) — RED then GREEN:
  **(a)** `test_embedded_one_real_two_ads` END-TO-END through `dispatch_fetch` — page with 1 main Vimeo
  + 2 ad embeds → EXACTLY ONE `_fetch_transcript` call, `engine=="html+embedded:1"`, `details["embedded"]`
  lists all three with reasons (DoD §5; UC-12); **(b)** `test_embedded_per_embed_isolation` — 2 keeps,
  first transcript exits 3 → second still fetched, `engine=="html+embedded:1"`, first logged
  `transcript-failure`, `_raw` still written (R-13f); **(c)** `test_embedded_cap` — 7 clean keeps,
  `embedded_videos_max=5` → 5 fetched, 2 logged `cap` (R-13d); **(d)** `test_embedded_dedup` — same
  allowlisted URL ×3 → one fetch, two `dedup` (R-13e); **(e)** `test_embedded_off_by_default` — same page,
  `embedded_videos=False` → `_download_raw_html`/`_fetch_transcript` NOT called, html path byte-unchanged
  (NF-2, R-13a); **(f)** `test_embedded_noop_on_video_host` — `youtu.be/<id>` + `embedded_videos=True`
  → embedded branch NOT entered (transcript path is the `unambiguous_video` tier, no raw-HTML GET — R-13a);
  **(g)** `test_embedded_quality_flag_aggregated` — one embed sidecar carries `english_auto_translation`
  → surfaced on the FetchResult (R-13h / R-8). *Gate:* the seven tests green; the pre-existing fetch +
  video suites stay green (NF-2); `mypy --strict scripts/`; `_raw` non-write verified on the not-ok html path.

- **S16 — CLI flags `--embedded-videos`/`--embedded-videos-max` + prepare wiring + SKILL.md (R-13a,**
  **R-13d, R-13f, R-13k-4 residual; DoD 4,5).** In `__init__.py`: add to the `prepare` parser
  (`_build_parser`, ~L693) `--embedded-videos` (`action="store_true"`, default off) and
  `--embedded-videos-max` (int, default 5). Enforce the **mutual-exclusion** with `--video` (passing
  BOTH → `parser.error(...)` / exit 2 — R-13a). Thread both through the `dispatch_fetch(...)` call in
  `prepare()` (L175). Surface the `details["embedded"]` skip-reason log into the prepare envelope's
  `details` list (R-13f — every discovered embed + WHY skipped: `ad-denylist`/`ad-context`/`ad-param`/
  `not-allowlisted`/`dedup`/`cap`/`transcript-failure`); aggregate any embed `quality_flag` into the
  envelope top-level `quality_flag` (R-13h / R-8b). **H-6 (R-13j):** any scalar derived from a discovered
  embed URL (title/url in the `## Embedded video` heading) flows through `_fm_safe` before reaching
  frontmatter (reuse the existing `ensure_source_frontmatter`/`_fm_safe` path — confirm no NEW injection
  sink). Extend `tests/test_import_article_prepare.py`: an `--embedded-videos` prepare over a mocked
  page+transcript bin emits `engine` starting `html+embedded:`, writes `_raw`, the envelope `details`
  carries the skip-reason log; a `--embedded-videos --video` invocation exits 2 (usage error); an
  invocation WITHOUT `--embedded-videos` is byte-unchanged (NF-2). Update `skills/wiki-import/SKILL.md`
  via `skill-enhancer`: document `--embedded-videos`/`--embedded-videos-max`, the **always-on
  ad-exclusion** (no off switch — operator hard requirement, R-13k), the filter-chain order, the
  skip-reason `details` log, and the **best-effort residual** (a disguised ad may slip; opt-in + cap +
  per-embed isolation + the full log bound the blast radius — R-13k-4) alongside the SSRF residual.
  Version bump + Maintenance note. *Gate:* prepare tests green; `mypy --strict`; `argparse` rejects
  `--video --embedded-videos`; `skill-validator` clean; SKILL.md documents always-on ad-exclusion + residual.

- **S17 — VDD gate + NF-2 regression gate (DoD 1,2,3,5,6; NF-1, NF-2, NF-3) — FINAL bead.** Full
  `pytest tests/` green (all pre-existing + the new video scenarios + the **six ad-exclusion scenarios**
  `test_embedded_ad_context_adsbygoogle` / `_not_allowlisted_googlesyndication` / `_denylist_youtube_ima`
  (ADV-1) / `_ad_context_aside_related` / `_one_real_two_ads` / `_youtube_ad_param`); `mypy --strict
  scripts/` clean. **NF-2 regression
  gate:** repo-wide `grep -rn 'import anthropic' scripts/wiki_skills/wiki_import_article/` CLEAN (NF-1c,
  Decision-17); `grep user_version sql/wiki-index-v2.sql` still `7` AND `git diff --stat sql/` empty
  (zero DDL — NF-2d); `git diff --stat requirements.txt` empty (zero new deps — NF-2e). Then
  `/vdd-multi` (code-reviewer + critic-security + critic-logic) on `_fetch.py` + `__init__.py` +
  SKILL.md + the new tests → fix → re-green. **critic-security focus:** SSRF residual (operator URL to
  the transcript subprocess — same as pdf, documented Q-044-7) **PLUS the embedded raw-HTML GET +
  allowlist egress bound (R-13c): the page cannot trigger a fetch to an arbitrary host — only the
  youtube/vimeo allowlist passes; the ad-network denylist is belt-and-braces (Q-044-11)**; **the
  ad-context + ad-param bounded-regex ReDoS safety (Q-044-11): the char window is a fixed-length slice,
  the attribute match is a simple alternation with no nested quantifiers — cannot catastrophically
  backtrack on attacker-controlled HTML**; cookies handling (`--cookies-file` path existence not content;
  `--cookies-from-browser` opt-in); argv-array invocation (no shell string — NF-3a); stat scalars +
  embed-URL scalars through `_fm_safe` / no new FM-injection sink (H-6, NF-3c, R-13j); temp-file cleanup
  (NF-3e); `_download_raw_html` byte-cap honored. **critic-logic focus:** Decision-3 concat, exit-code
  mapping (3/5/7), the no-media→html fallback, R-3 `_raw` non-write on every failure path, **PLUS the
  ad-exclusion filter ordering (allowlist → denylist → ad-context → ad-param → dedup → cap → fetch),
  always-on ad-exclusion (no off switch), skip-reason logging completeness (NO silent drop at any
  stage — every discovered embed is logged), per-embed failure isolation (one embed exit-3 does not
  abort the page), and the `--video`/`--embedded-videos` mutual-exclusion (exit 2)**. Commit on user
  request. *Gate:* all reviewers APPROVE; the regression gate is green; the five ad-exclusion scenarios pass.

## RTM coverage map (every TASK 044 R-/NF- item → bead(s))

| RTM | Requirement | Bead(s) |
|----|-------------|---------|
| **R-1** | `_video_host()` classifier (pure, label-boundary, Skool lesson) | S0 (pin), S1 (stub+RED), S2 (GREEN) |
| **R-2** | `dispatch_fetch` routing (Decision 1+2; no text-path regress) | S0 (insertion pt), S5 (stub+RED), S6 (GREEN), S8 (CLI `--video` wiring) |
| **R-3** | `_fetch_transcript()` shell-out (engine, raw_text, title/author/date, temp cleanup) | S3 (stub+RED), S4 (GREEN) |
| **R-4** | `--transcript-bin` + `require_bin` fail-fast (exit 6), `_TIMEOUT_TRANSCRIPT` | S3, S4, S8 (flag+default) |
| **R-5** | Decision 3 — `--video` on x-status: html+transcript CONCAT | S7 (stub+RED+GREEN) |
| **R-6** | No-media: `--video` status → html fallback; **unambiguous_video → FETCH_FAILED, no fallback (C-1)** | S5 (RED tests d,f), S6 (GREEN), S7 (R-5d edge) |
| **R-7** | Broadcast/Space no-ASR → exit 7 → typed dep error, no `_raw` | S3 (RED), S4 (map), S5 (RED test c), S6 (propagate), S8 (envelope exit 6) |
| **R-8** | `quality_flag: english_auto_translation` surfaced (FetchResult + envelope) | S3 (FetchResult field+RED), S4 (read stat), S8 (envelope key), S10 (SKILL.md surface-before-REASON) |
| **R-9** | `transcript_origin` provenance → `engine="transcript:<origin>"`; reuse `ensure_source_frontmatter` | S3 (RED), S4 (GREEN), S8 (no-FM injection reuse) |
| **R-10** | Login-walled video → exit 5 → cookies guidance, exit 10, no `_raw` | S3 (RED), S4 (map), S10 (SKILL.md hint) |
| **R-11** | Passthrough flags (`--lang`/`--max-duration-min`/`--cookies-*`); `--json-errors` always | S3 (RED), S4 (argv), S8 (CLI flags + `_vault_language` lang default) |
| **R-12** | `_detect.py`/`--kind` orthogonality — no functional change | S9 (verify-only + assertion) |
| **R-13** | Opt-in `--embedded-videos` — discover + transcribe `not_video`-page embeds; always-on ad-exclusion | S13 (discovery+filter-chain stub+RED), S14 (GREEN), S15 (dispatch append+isolation+assembly), S16 (CLI flags+SKILL.md), S17 (VDD) |
| ↳ R-13a | default-off / orthogonality / `--video` mutual-exclusion (exit 2) | S15 (NO-OP guards: tests e,f), S16 (CLI flag + mutual-exclusion) |
| ↳ R-13b | raw-HTML GET (`_download_raw_html`, `_EMBED_FETCH_MAX_BYTES`) + ReDoS-safe anchored scan | S13 (stub+RED), S14 (GREEN — size-cap + anchored bounded regex) |
| ↳ R-13c | allowlist (SSRF egress bound — youtube/vimeo only) | S13 (`_EMBED_ALLOW_PATTERNS`+RED), S14 (GREEN), S17 (critic-security egress bound) |
| ↳ R-13d | cap `--embedded-videos-max` (default 5; applied after filters) | S15 (cap logic + test c), S16 (CLI flag) |
| ↳ R-13e | dedup (set-based, after ad-exclusion) | S13/S14 (`dedup` reason), S15 (test d) |
| ↳ R-13f | per-embed failure isolation + skip-reason logging (NO silent behavior) | S15 (isolation + `details["embedded"]` log; test b), S16 (envelope `details`), S17 (critic-logic completeness) |
| ↳ R-13g | `_raw` assembly (`## Embedded video <k>`; `engine="html+embedded:<n>"`) | S15 (assembly; test a) |
| ↳ R-13h | provenance + `quality_flag` aggregation (R-8 reuse) | S15 (aggregate; test g), S16 (envelope key) |
| ↳ R-13i | reuse `_fetch_transcript`/`_video_host`/`require_bin`/`_fm_safe` unmodified | S14/S15 (by construction — no fetch logic duplicated) |
| ↳ R-13j | mypy strict / no `import anthropic` / `_fm_safe` on embed scalars | S13/S14 (Decision-17 by construction), S16 (`_fm_safe` reuse), S17 (mypy + grep gate) |
| ↳ R-13k-1 | ad-network host denylist (`_AD_NETWORK_HOSTS`) | S13 (denylist const+RED test 2), S14 (GREEN), S17 (critic-security belt-and-braces) |
| ↳ R-13k-2 | ad-context bounded ReDoS-safe scan (`_AD_CONTEXT_WORDS`, `<ins adsbygoogle>`/`<aside>`/role/aria) | S13 (RED tests 1,3), S14 (bounded-window GREEN), S17 (critic-security ReDoS) |
| ↳ R-13k-3 | youtube ad-param drop (`_AD_PARAM_KEYS`) | S13 (RED test 5), S14 (query-parse GREEN) |
| ↳ R-13k-4 | best-effort / residual documented + bounded blast radius | S16 (SKILL.md residual), S17 (critic-security sign-off, Q-044-11) |
| **NF-1** | Vendor-agnostic (subprocess+flags, no SDK, no `import anthropic`) | S1/S2 (by construction), S4, S8, S13/S14 (discovery pure+stdlib), S17 (grep gate) |
| **NF-2** | No regressions (not_video byte-unchanged; mypy; pytest; zero DDL; deps unchanged) | S5 (RED regress guard), S6 (GREEN), S15 (embedded off-by-default test e), S17 (mypy/pytest/DDL/deps gate) |
| **NF-3** | Security + H-6 (argv-array; cookies path; stat→`_fm_safe`; R-26; temp cleanup; SSRF residual; embed-egress allowlist; ReDoS) | S4 (argv+cleanup), S8 (FM reuse), S11 (SSRF doc), S14 (ReDoS-safe bounded scan), S15 (raw-HTML cap+allowlist egress), S16 (embed-scalar `_fm_safe`), S17 (critic-security) |

## Invariants / guards
- **Stub-first / Red→Green:** every logic bead is preceded by a stub+RED bead — S1→S2 (`_video_host`),
  S3→S4 (`_fetch_transcript`), S5→S6 (dispatch tier), S7 concat (stub+RED then GREEN in one bead),
  S13→S14 (`_discover_embedded_videos` + the filter-chain truth table), S15 (dispatch embedded append
  stub+RED then GREEN in one bead). The S17 VDD + NF-2 regression gate is the FINAL bead.
- **`--embedded-videos` opt-in / allowlist+denylist / always-on ad-exclusion / per-embed isolation
  (R-13):** the flag is **off by default** (NF-2 byte-identity when absent — S15 test e) and acts ONLY
  on the `not_video` html path (NO-OP on `unambiguous_video`/`ambiguous_x_status` — S15 test f); it is
  **mutually exclusive with `--video`** (exit 2 — S16). Discovery is **allowlist-bounded egress**
  (only youtube/vimeo embed hosts reach a subprocess — the page cannot trigger an arbitrary-host fetch,
  R-13c) backed by the **ad-network denylist** (belt-and-braces). **Ad-exclusion is ALWAYS-ON — there
  is no off switch** (operator hard requirement): the three filters (ad-network denylist → ad-context →
  ad-param) run unconditionally in the FIXED chain `allowlist → ad-denylist → ad-context → ad-param →
  dedup → cap → fetch` (S14/S15). Every discovered embed is logged with its reason in the envelope
  `details` — **NO silent drop at any stage** (R-13f). **Per-embed failure isolation:** one embed's
  exit-3/5/7 is logged `transcript-failure` and skipped, never aborting the page import (contrast
  R-6e §2.3.2 hard-fail — embedded videos are supplementary, S15 test b). The ad-context/ad-param
  scans are **bounded + anchored (ReDoS-safe by construction** — fixed char window, no nested
  quantifiers, layout-config load-gate posture; Q-044-11). Best-effort residual (a disguised ad may
  slip) is bounded by opt-in + cap + isolation + the full log, documented in SKILL.md (R-13k-4).
- **NF-2 byte-identity of the text path:** the media-tier fires ONLY on `unambiguous_video` or an
  explicit `--video` on a status; `not_video` and a default x-status take the EXISTING html/pdf code
  path unchanged (S5 RED guard + S6 GREEN; S15 embedded off-by-default guard; S17 grep + diff gate).
- **Decision-17:** routing is `_video_host()` (URL shape) + the `--video` flag — a PURE deterministic
  function; no `import anthropic`, no network "has-video" probe in the default path.
- **`--video` scope (TASK R-2f + R-6e):** `--video` changes behavior ONLY on `ambiguous_x_status`
  (forces the concat path); on a `not_video` URL it is an **intentional no-op** (html/pdf path, no
  transcript subprocess — preserves NF-2 byte-identity), and on `unambiguous_video` it is redundant
  (already auto-routed). The exit-3 no-media→html fallback is EXCLUSIVE to `ambiguous_x_status`; on an
  `unambiguous_video` URL exit-3 = `FETCH_FAILED` (exit 10, no fallback — C-1).
- **R-3 (`_raw` only on a non-empty ok fetch):** preserved on every transcript failure path — exit
  7/5/3 never reach the `raw_path.write_bytes` (the prepare layer already gates on `result.ok` — L184).
- **Zero-DDL (`user_version` 7) / zero new deps (`requirements.txt`) / `mypy --strict scripts/`** throughout
  (S17 gate). H-6 stat scalars + embed-URL scalars through `_fm_safe`; argv-array subprocess (no shell
  string); temp dirs cleaned in a `finally`; `_download_raw_html` byte-capped (`_EMBED_FETCH_MAX_BYTES`).
- **Rollback:** isolated branch; additive (a classifier, a fetch wrapper, a dispatch tier, CLI flags,
  an embed-discovery + ad-exclusion filter chain) + doc/SKILL edits → revert = drop the branch; no DB
  migration.

## Out of plan
- New `--kind` values / a new REASON harness — content-type detection stays orthogonal (always
  `summarizing-meetings`); `_detect.py` is verify-only (S9).
- Any change to the `apply` subcommand (note filing, concept extraction, indexing) — the `--video`
  flag is a `prepare`-time routing hint; `engine` provenance rides the `_raw` frontmatter + envelope
  (Q-044-8 lean: no new `apply` arg).
- ASR-backend installation in THIS repo, the `summarizing-meetings` harness, `wiki-enrich`,
  `wiki-reindex`, the SQLite schema/DAL — all unchanged.
- A network probe to decide "does this URL carry a video track" — explicitly excluded (Decision-17).
- Retiring/altering the existing html/pdf branches — they are extended-beside, never replaced.
- **A full DOM parser / an LLM ad-judge for embed/ad detection** — explicitly excluded (R-13k,
  Decision-17): ad-context is a BOUNDED, ReDoS-safe regex over a fixed char window, never a parse tree
  or a model call. A new runtime dep (e.g. an HTML parser library) is out — discovery is stdlib `re`/
  `urllib.parse` only (zero new deps, NF-2e).
- **An off-switch for ad-exclusion** — there is none by design (operator hard requirement): ads must
  NEVER be transcribed; `--embedded-videos` is the only opt-in control, ad-exclusion rides it always-on.
- **Discovering non-allowlisted embed hosts** — only youtube/vimeo embed patterns are honored (R-13c
  egress bound); any other `<iframe src>` is logged `not-allowlisted` and dropped, never fetched.
