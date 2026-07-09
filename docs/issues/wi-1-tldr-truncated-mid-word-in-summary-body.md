---
id: WI-1
type: known-issue
status: fixed
opened_at: 2026-07-09
closed_at: 2026-07-09
category: correctness
severity: SEV-3
slug: wi-1-tldr-truncated-mid-word-in-summary-body
---

# wiki-import: tldr `[:300]` cap truncates the rendered body section mid-word

- **Symptom**: In a filed `article`/`paper` note, the `## Кратко` (brief) / `## Саммари` body section ends mid-word — e.g. `…прицельно перемаскирующий только вероятно неверные токены. Пос` — because the tldr is hard-cut at 300 characters. The frontmatter `tldr:` scalar shows the same truncation. Surfaced 2026-07-09 importing `arxiv.org/abs/2510.08369` (`--kind paper --mode summary`); a 2-sentence tldr got sliced at char 300.
- **Root cause**: `_authoring.py:220` truncates once — `tldr = _fm_scalar(...)[:300]` — and the **same** truncated variable is reused for both the frontmatter scalar (`_authoring.py:281`) **and** the rendered body section (`_authoring.py:307` / `:311`, `## {t['brief']}\n\n{tldr}`). So a body-facing summary inherits a frontmatter-preview cap, and the cut is a raw character slice (no word/sentence boundary, no ellipsis).
- **Affected components**: `scripts/wiki_skills/wiki_import_article/_authoring.py` (lines 220, 281, 307, 311).
- **Fix plan**:
  1. Do **not** truncate the body copy — render the full tldr in `## Кратко`/`## Саммари`. The REASON contract already bounds tldr to "1–2 sentences", so the body needs no cap.
  2. Keep a cap **only** on the frontmatter scalar (it's a preview), and cut on a word/sentence boundary with a trailing `…` — never mid-grapheme. (Also confirm the cap counts characters, not bytes; Cyrillic makes the distinction matter for any byte-based variant.)
  3. Optional: cap the frontmatter scalar to the **first sentence** instead of a fixed char count.
- **Workaround (until fixed)**: author the tldr as a single sentence ≤ 300 chars ending on a period (what was done to repair the dogfood note).
- **Resolution (2026-07-09, TASK 055)**: split the one truncated variable into two in `_authoring.assemble_note`.
  The rendered body `## Кратко`/`## Саммари` section now carries the **full** tldr (no cap — the REASON
  contract already bounds it to 1–2 sentences). Only the frontmatter `tldr:` scalar is capped, via the new
  `_authoring._tldr_fm_preview()`: character-based (Python `str` slices by codepoint → Cyrillic counts as one,
  no byte/char mismatch), the cut lands on a **word boundary** with a trailing `…` (never mid-grapheme), and a
  tldr ≤ 300 chars is returned unchanged (frontmatter byte-identity preserved). The vdd logic/security critics
  converged on a coupled cleanup: the body-facing `tldr` now keeps its literal `"` (byte-matches the
  orchestrator-authored text → verbatim-quote resolution + sibling-scalar consistency), and `"`→`'` is
  normalized only at the frontmatter emission like every other scalar. Tests:
  `test_wi1_tldr_fm_preview_word_boundary_and_ellipsis`, `test_wi1_full_tldr_in_body_but_capped_in_frontmatter`,
  `test_wi1_tldr_keeps_raw_quotes_in_body_normalizes_in_frontmatter` (`tests/test_import_article_authoring.py`).
