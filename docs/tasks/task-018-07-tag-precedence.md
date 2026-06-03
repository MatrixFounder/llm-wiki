# task-018-07 — [LOGIC] tag vocabulary + precedence

**Parent:** TASK 018. **Depends on:** 018-05. **RTM:** E2.1/E2.3, AC-4, Q-018-7.

## Goal
The `.md` content-tag layer + the precedence ladder.

## Design (locked — Q-018-7)
Accept BOTH `#wiki/{raw,skip,keep}` (frontmatter `tags:` or inline `#wiki/...`) AND a
frontmatter field `wiki: {raw,skip,keep}`. Precedence: **`skip` > `raw` > `keep` > default**.
`_raw/` (`in_raw=True`) ≡ implicit `raw`. `#wiki/keep` only rescues a `.md` inside an
`exclude:` zone (`in_exclude_zone=True`) from the excluded-zone skip; the resulting action is
then decided by the raw/type rules.

## Steps
1. Parse tags + the `wiki:` field (namespace from `config.tag_namespace`, default `wiki`).
2. Apply precedence: `skip`→`skip(reason=wiki/skip)`; then if `in_exclude_zone` and not `keep`
   → `skip(reason=excluded-zone)`; then `raw`/`in_raw`→`ingest`; else fall through to 09 (type).
3. GREEN `test_tag_precedence` (skip-wins; raw; keep-rescues-exclude-zone; `_raw/`≡raw).

## Verification
- `pytest -q -k "classify or tag_precedence"` GREEN; `mypy --strict` clean.
