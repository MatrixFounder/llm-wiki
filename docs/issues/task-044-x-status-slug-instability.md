---
id: TASK-044-X-SLUG
type: known-issue
status: open
opened_at: 2026-06-29
category: correctness
severity: SEV-3
slug: task-044-x-status-slug-instability
---

# x.com import: nondeterministic og:title → slug drift / duplicate `_raw`

> Found during the TASK 044 dogfood (importing `https://x.com/Av1dlive/status/...` with `--video`).
> The slug-LENGTH half is already FIXED (`_derive_slug` byte-cap, see *Resolution* below); the slug-
> STABILITY half (this issue) stays `open` as a non-blocking follow-up.

- **Symptom**: A titleless source has no real `<title>`, so the `html` skill falls back to the
  page's `og:title`. For an x.com status that is the **entire tweet body**. x.com serves a
  **nondeterministic** `og:title` across requests (sometimes wrapped `"(3) Avid on X: … / X"`,
  sometimes the bare tweet text), so two `prepare` runs of the SAME URL derive **different slugs**
  (`3-avid-on-x-…` vs `avid-you-can-build-…`) and write **two different `_raw/<slug>.md`** files —
  breaking import idempotency for x-status sources (a re-run does not overwrite the prior capture).

- **Two distinct defects, one fixed**:
  1. **Slug length (FIXED).** The full tweet body became a >255-byte slug → `OSError [Errno 63]
     File name too long` at `raw_path.write_bytes`. Fixed in `_derive_slug` (`__init__.py`) with a
     byte-safe cap (`_SLUG_MAX_BYTES = 180`, hyphen-boundary backoff) + regression test
     `test_derive_slug_caps_long_title`. NOT a TASK 044 regression — any long title triggered it.
  2. **Slug instability (THIS ISSUE, open).** Even capped, the slug is derived from a variable
     upstream `og:title`, so it is not stable per source URL → duplicate `_raw` + non-idempotent
     re-import for x-status (and any host with a volatile title).

- **Scope**: x.com / twitter.com status sources (the only common titleless source whose og:title is
  both long and volatile). Other sources have stable titles, so the length cap alone suffices there.

- **Proposed fix (follow-up task)**: for `ambiguous_x_status` / `unambiguous_video` sources, derive
  the slug **deterministically from the stable URL identity** (e.g. `x-<user>-status-<id>` /
  `<host>-<video_id>`) instead of the volatile `og:title`, falling back to the title only when no
  stable id is extractable. Keeps the `_raw` filename stable across re-runs → restores idempotency.
  Zero schema impact (slug derivation only).

- **Workaround (today)**: pass an explicit `--slug` for x-status imports, or accept that a re-run may
  create a second `_raw` (the operator removes the stale one).
