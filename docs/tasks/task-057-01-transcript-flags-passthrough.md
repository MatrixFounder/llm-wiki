# 057-01 — [W1-1][W1-2] transcript robustness flags pass through

**Goal:** `--concurrent-fragments` / `--media-timeout-sec` reach the transcript-fetcher argv
from the `wiki-import prepare` CLI; omitted → absent (skill env/defaults rule).

**Context (read):** `_fetch.py:693` `_fetch_transcript` (argv at :705), callers at :759
(`_fetch_x_status_with_video`), :865 (`_append_embedded_videos`), :915 (`dispatch_fetch`);
`__init__.py::_build_parser` prepare flags (~:887 video block) + `prepare()` dispatch call
(~:220).

**Steps:**
1. `_fetch_transcript(..., concurrent_fragments: int | None = None, media_timeout_sec: int |
   None = None)`; after the cookies appends: non-None → `argv += ["--concurrent-fragments",
   str(n)]` / `["--media-timeout-sec", str(n)]`.
2. Thread the pair through `_fetch_x_status_with_video`, `_append_embedded_videos` (embeds
   forward them too — the skill ignores them on non-X hosts), and `dispatch_fetch(...)` params.
3. `__init__.py`: prepare gains `--transcript-concurrency` / `--transcript-media-timeout`
   (`type=_positive_int` — argparse type fn rejecting < 1 with ArgumentTypeError, value kept
   out of the message), `default=None`; pass to `dispatch_fetch`.
4. SKILL doc sync deferred to 057-08.

**Tests** (`tests/test_import_video.py` style — monkeypatch `subprocess.run`, capture argv):
- flags set → both appear with values on: unambiguous-video path, x-status `--video` path,
  embedded-videos path.
- flags omitted → neither string appears in argv (all three paths).
- CLI: `--transcript-concurrency 0` → exit 2 usage.

**Verification:** `pytest tests/test_import_video.py tests/test_import_prepare_acquire.py -q`;
`mypy --strict scripts/`.
