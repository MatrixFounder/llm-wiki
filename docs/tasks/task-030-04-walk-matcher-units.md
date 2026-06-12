# 030-04 — Walk matcher pure units (R-030-3/6, unwired)

**RTM:** R-030-3 + R-030-6 (unit leg). **UC:** UC-30-3. **Depends:** —.

## Goal
Two pure, independently-tested functions in `layout_config.py` — no engine wiring
yet (Stub-First: structure + units before the swap).

## Units
1. **`_advance_alive(pattern_state, segment, *, is_symlink) -> pattern_state | None`**
   — the alive-set core (Q-030-2 v3): advance a pattern's match state across one
   directory segment; `**` consumes ≥0 segments; `*`/`[...]`/literals match one
   segment via rules consistent with `PurePosixPath.full_match`; returns None
   (dead) when the pattern cannot match below — **PROPER-prefix rule**: a
   pattern with no remaining segments to consume is dead for descent (a dir
   named `foo.md` does not descend via `*.md`); **symlink rule**: when
   `is_symlink`, a pattern survives ONLY if it consumes this component with an
   explicit non-`**` segment (per-entry `Path.glob` union parity).
2. **`_prunable_ignore(dir_rel_posix, ignore) -> bool`** — True iff the dir is
   covered by a `<prefix>/**`-shaped ignore glob (conservative: ONLY pattern
   shapes that imply all descendants ignored prune; `**/*.base`-style file
   patterns never prune).

## RED first — unit tables (parametrized)
- karpathy paths[]: root dir → descend (Lessons/_sources… anchored); `.obsidian` →
  NO pattern prefix-match → no descend; `Lessons` → descend; `Lessons/X` →
  descend; `Lessons/X/attachments` → no descend.
- obsidian-personal: root → descend; `02 - Area` → descend (entries 4/5);
  `02 - Area/Sub/_raw` → `_prunable_ignore` True (`**/_raw/**`); `.obsidian` →
  prunable + no prefix-match; `_daily/2026` → descend (entry-1 `**`).
- `**` edge: pattern `Lessons/*/_sources/**/*.md` vs dir `Lessons/X/_sources/a/b`
  → descend (`**` open-ended); dir `Lessons/X/_concepts` → that pattern no, a
  sibling pattern yes. Trailing-`**` (`Lessons/**` — 3.13+ matches files too):
  pattern-exhaustion-into-`**` keeps the pattern alive. Mid-`**`-then-literal
  (`docs/**/img/*.md`). A *directory* literally named `foo.md` → dead via `*.md`
  (proper-prefix), file `foo.md` matches. Dot-named files matched by wildcards.
  Symlink table: explicit-segment survival, `**`-death, dual-reach
  (the H-1 fixture: `Areas/**/*.md` + `Areas/*/notes/*.md`, `Areas/link`
  symlinked — alive-set below `link` contains ONLY the explicit entry).
- **Property check (strengthened — arch-review MED):** for generated fixture
  trees (incl. symlink topologies), full **DiscoveredPage-tuple equality**
  (path, slug, project, extra_tags, raw_type, ordering) between a
  reference matcher driven by the alive-sets and the CURRENT per-glob engine —
  not bare reachability-set equality.

## Acceptance
- ✅ All unit tables green; property check green on karpathy + obsidian-personal +
  dev-project built-ins AND ≥2 operator-override layouts (one overlapping, one
  with symlink topology).
- ✅ Functions pure (no I/O beyond the property-check fixtures), mypy strict; NOT
  yet called by `iter_pages` (zero behavior change this bead — full suite green
  unmodified).
- ✅ Sarcasmotron pass.
