# Task 046-02 (P1b) — wiki-import prepare: universal acquire+normalize

Beads: B7 (stub) · B8 (R-6, office) · B9 (R-7, vtt). Stub-First.

## Goal
`wiki-import prepare` accepts **any** supported source format and writes `_raw/<slug>.md`:
add **office (docx/pptx/xlsx)** conversion and **`.vtt`/`.srt`** de-timestamp branches to
`dispatch_fetch` (on top of the existing url/pdf/video/md/txt). This absorbs the conversion
that `wiki-sync` currently does, so `wiki-sync` can delegate raw files of any format.

## Context (files to edit)
- `scripts/wiki_skills/wiki_import_article/_fetch.py` — `dispatch_fetch` local-file tail (lines ~682–694).
- Reuse: the `docx`/`pptx`/`xlsx` harness skills (invoked via `Skill({...})` in the recipe, or their
  scripts); `transcript-fetcher/scripts/sources/_vtt_to_text.py` for de-timestamping.
- New test: `tests/test_import_prepare_acquire.py`. Reference: `tests/test_import_article_prepare.py`,
  `tests/test_import_video.py`.

## Steps
1. **B7** — create test file with 2 `@pytest.mark.skip` stubs.
2. **B8 (R-6)** — in `dispatch_fetch`, before the `.md/.txt` branch: if `bare.endswith((".docx",".pptx",".xlsx"))`
   → run the matching converter to markdown → `FetchResult(ok=bool(text.strip()), raw_text=text,
   engine="convert-office", title=..., ...)`. Office conversion is a subprocess/skill call — keep it a
   thin wrapper (ADR-001 "Wrap + Index"); fail-fast with a typed envelope if the converter bin is absent.
3. **B9 (R-7)** — if `bare.endswith((".vtt",".srt"))` → pipe through `_vtt_to_text.py` (de-timestamp)
   → `FetchResult(ok=..., raw_text=plain, engine="vtt", ...)`.

## Test Cases
- **TC-E2E-01 (B8/R-6)** `test_import_prepare_office`: a small `.docx` fixture → `prepare` writes a
  non-empty `_raw/<slug>.md`, envelope `action: prepared`, `engine` reflects office conversion.
- **TC-E2E-02 (B9/R-7)** `test_import_prepare_vtt`: a `.vtt` fixture with cue timings → `_raw/<slug>.md`
  has the cue timings stripped (plain transcript text).

## Verification
`pytest tests/test_import_prepare_acquire.py tests/test_import_article_prepare.py -v` green.
`mypy --strict scripts/` clean. Missing converter bin → typed `DEP_MISSING`/exit 6 (no junk `_raw`).

## Acceptance
- [ ] office + vtt fixtures produce correct `_raw/<slug>.md`.
- [ ] existing prepare tests (url/pdf/video/md) unchanged (regression).
- [ ] mypy --strict clean; dependency-missing path is typed, not a crash.
