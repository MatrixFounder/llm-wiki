# 057-04 — [W3-2][W3-3] announcement wiring: dispatch marker → prepare exit 0, no writes

**Goal:** the 004 announcement tweet produces `{action:"announcement_only", broadcast_url,
hint}` exit 0 and a byte-identical vault; `--video` and plain tweets are untouched.

**Context (read):** `_fetch.py::dispatch_fetch` (:887 — the `ambiguous_x_status` default falls
into the html branch at :926), `__init__.py::prepare` (:238 fetch-failed emit; `_imgtmp`
lifecycle :250).

**Steps:**
1. `dispatch_fetch`: in the html branch, when `is_url and host_class == "ambiguous_x_status"
   and not video` and `res.ok`: `url_bc = _announcement_only(res.raw_text)`; on match reclaim
   the html temp dir with prepare's own None-guard idiom (`__init__.py:250`):
   `tmp = res.attachments_dir.parent if res.attachments_dir else None` → guarded
   `shutil.rmtree(tmp, ignore_errors=True)` (`attachments_dir` is `Path | None` — the no-images
   path already cleaned up and returns None; plan-review F2) and return
   `FetchResult(ok=False, engine="html", error={"error": "AnnouncementOnly", "type":
   "AnnouncementOnly", "exit_code": 0, "details": {"kind": "announcement_only",
   "broadcast_url": url_bc, "url": source}})`. (Embedded-videos append never runs — that hook
   is `not_video`-gated already.)
2. `prepare`: BEFORE the generic fetch-failed emit, branch on
   `result.error.details.kind == "announcement_only"` → emit
   `{"action": "announcement_only", "source": args.source, "broadcast_url": …,
   "hint": "re-run prepare on the broadcast URL, or pass --video to concatenate
   tweet + transcript"}`, exit 0. Nothing written (the short-circuit is before slug/_raw/kind).
3. No change to the `video=True` route (heuristic never runs there) nor to `not_video` URLs.

**Tests:**
- prepare on the announcement fixture (monkeypatched `_fetch_html`) → exit 0, envelope has
  `broadcast_url` + hint; assert the vault tree (rglob set) is identical before/after —
  no `_raw/`, no `_attachments/`.
- html temp dir with attachments is reclaimed on the announcement path (tmp dir gone).
- plain text tweet (no link) → today's `prepared` envelope (regression).
- `--video` on the same URL → concat path unchanged (`test_import_video.py` suite green
  unmodified — [W3-3]).

**Verification:** `pytest tests/test_import_article_prepare.py tests/test_import_video.py
tests/test_import_announcement.py -q`; `mypy --strict scripts/`.
