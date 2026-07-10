# 057-03 — [W3-1] pure announcement heuristic

**Goal:** a deterministic string classifier that spots "announcement-of-broadcast" tweets:
LOW prose AND a first-party broadcast/space link → the broadcast URL; anything else → None.

**Context (read):** `_fetch.py:147–165` (X constants incl. `_X_BROADCAST_RE`, `_X_PROSE_FLOOR`),
:287 `_is_x_login_wall` (prose normalization to reuse); ARCHITECTURE §2.3.5 W3 + Q-057-4.

**Steps:**
1. Extract the login-wall prose normalization (drop FM → drop `[..](..)`/`![..](..)` → strip
   markdown punctuation → collapse whitespace) into `_normalized_prose(md) -> str`; rewire
   `_is_x_login_wall` onto it (behaviour-neutral — existing login-wall tests must stay green
   unmodified).
2. Constants: `_X_ANNOUNCEMENT_PROSE_FLOOR = 600`;
   `_X_BROADCAST_URL_RE = re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/i/(?:broadcasts|spaces)/[A-Za-z0-9]+", re.I)`
   (absolute-URL form of the `_X_BROADCAST_RE` route shape; allowlisted hosts only).
3. `_announcement_only(md: str) -> str | None`: search the RAW markdown (links live in
   `[..](..)` targets — search before link-stripping) for the first `_X_BROADCAST_URL_RE`
   match; no match → None; match + `len(_normalized_prose(md)) >= floor` → None (substantive
   tweet, spec Risk 2); else the matched URL.

**Tests** (new `tests/test_import_announcement.py`):
- 004-shaped fixture (short announcement text + `https://x.com/i/broadcasts/1abcDEF` +
  nav/trending chrome below the floor) → exact URL returned.
- Substantive tweet (≥ floor prose) containing the same link → None.
- Short tweet, NO broadcast link → None.
- Link on a non-allowlisted host (`evil.com/i/broadcasts/x`) → None.
- Existing login-wall tests green unmodified (normalization extraction is neutral).

**Verification:** `pytest tests/test_import_announcement.py tests/test_import_article_fetch.py -q`
(the latter proves the login-wall extraction is behaviour-neutral); `mypy --strict scripts/`.
