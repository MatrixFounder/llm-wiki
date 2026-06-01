---
id: R-X1-OBS-WALK
type: known-issue
status: open
opened_at: 2026-06-01
category: performance
severity: SEV-3
slug: r-x1-obsidian-multiglob-rewalk
---

# obsidian-personal multi-glob subtree re-walk

- **Symptom**: `iter_pages` runs one `Path.glob` per `paths[]` entry. The `obsidian-personal` layout has overlapping recursive `**` globs over the same root, so the deep subtree is `scandir`'d once per overlapping glob (~Nx I/O at scale). Karpathy/dev-project use non-overlapping subdir-rooted globs and are unaffected (byte-identity preserved).
- **Root cause**: per-glob walk instead of a single walk + in-memory matching.
- **Affected components**: `scripts/wiki_index/layout_config.py::iter_pages`; `scripts/wiki_index/layouts/obsidian-personal.yaml`.
- **Fix plan**: single-pass `os.walk`/`os.scandir` of the vault root, then match each discovered relative path against the ordered glob list (first-match-wins) in memory. Deferred (scale-gated): trigger when a real obsidian-personal vault exceeds ~2k files.
- **Prevention**: `ignore[]` evaluated before paths prunes service dirs.
