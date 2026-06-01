---
id: L-008-1
type: known-issue
status: open
opened_at: 2026-05-29
category: logic
severity: LOW
slug: l-008-1-verification-slug-not-length-capped
---

# `verification_slug` not length-capped

- **Symptom**: the derived `verify-<query-slug>` adds a 7-char prefix without a
  length cap; a max-length (80-char) query slug yields an 87-char verification
  slug/filename. Harmless on modern filesystems; no `pages.slug` length CHECK.
- **Fix plan**: cap to a filesystem-safe length if a real long-slug case appears.
  Defer — query slugs are question-derived and typically short.
