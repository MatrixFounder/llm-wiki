# Task 046-02 (P1b) — wiki-import prepare: universal acquire+normalize

Beads: B7 (stub) · B8 (R-6, office) · B9 (R-7, vtt). Stub-First.

## Goal
`wiki-import prepare` accepts **any** supported source format and writes `_raw/<slug>.md`:
add **office (docx/pptx/xlsx)** conversion and **`.vtt`/`.srt`** de-timestamp branches to
`dispatch_fetch` (on top of the existing url/pdf/video/md/txt). This absorbs the conversion
that `wiki-sync` currently does, so `wiki-sync` can delegate raw files of any format.

## Context (files edited) — as shipped
- `scripts/wiki_skills/wiki_import_article/_fetch.py` — `dispatch_fetch` local-file tail: new
  `.vtt/.srt` and `.docx/.pptx/.xlsx` branches; helpers `_read_text_fallback`, `_srt_to_vtt`,
  `_load_vtt_cleaner`/`_vtt_to_text`, `_load_soffice`/`_office_to_text`; `soffice_wrapper` param.
- `__init__.py` — `_DEFAULT_SOFFICE_WRAPPER`, `--soffice-wrapper` arg, threaded into `prepare`.
- **Reuse (ADR-001 "Wrap + Index"), imported by path — NOT reimplemented:**
  - `transcript-fetcher/scripts/sources/_vtt_to_text.py::vtt_text_to_plain` (the canonical WebVTT
    de-timestamper) for captions;
  - `pptx/scripts/_soffice.py::convert_to` (HARDENED soffice wrapper — throw-away UserInstallation
    profile → no lock contention, AF_UNIX sandbox shim, soffice-location fallback) for office.
- New test: `tests/test_import_prepare_acquire.py` (mocks both converters at their import boundary).

## Steps (as implemented)
1. **B7** — RED tests in `tests/test_import_prepare_acquire.py` (test `dispatch_fetch` directly).
2. **B8 (R-6)** — `.docx/.pptx/.xlsx` → `_office_to_text(p, wrapper_path=…)`: import the office
   skills' `_soffice` wrapper → `convert_to(src, td, "txt:Text")` → read the `.txt` with
   `utf-8-sig` (strips soffice's BOM) → `FetchResult(engine="convert-office")`. **MISSING LibreOffice
   = hard `DEP_MISSING` (exit 6)**, like html/pdf; a run-but-fail conversion = a typed soft
   `FetchResult` error (caller → FETCH_FAILED), never a junk `_raw`.
3. **B9 (R-7)** — `.vtt/.srt` → `_vtt_to_text(p)`: `.srt` is normalised to WebVTT first
   (`_srt_to_vtt`: comma→dot in cue timestamps + drop the standalone sequence-index line) because
   the cleaner's cue regex is dot-millisecond/VTT-specific; then `vtt_text_to_plain` →
   `FetchResult(engine="vtt")`. Encoding fallback (`utf-8-sig`/cp1251/utf-16) for legacy captions.

## Test Cases (shipped)
- **office:** happy (BOM stripped), missing-wrapper → exit 6, soffice-absent → exit 6,
  convert-fails → soft FetchResult error.
- **vtt:** happy (cleaner gets raw vtt verbatim), missing-cleaner → exit 6.
- **srt:** `_srt_to_vtt` unit (comma→dot, index dropped, numeric caption preserved) + dispatch-level
  (cleaner receives normalised WebVTT, no SRT commas). Real-cleaner + live-soffice smoke verified.

## Verification
`pytest tests/test_import_prepare_acquire.py tests/test_import_article_prepare.py -v` green (full
suite 1751 passed). `mypy --strict scripts/` clean. Missing LibreOffice → typed `DEP_MISSING`/exit 6
(no junk `_raw`).

## Acceptance
- [ ] office + vtt fixtures produce correct `_raw/<slug>.md`.
- [ ] existing prepare tests (url/pdf/video/md) unchanged (regression).
- [ ] mypy --strict clean; dependency-missing path is typed, not a crash.
