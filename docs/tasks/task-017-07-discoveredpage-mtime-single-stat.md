# task-017-07 — [LOGIC] `DiscoveredPage.mtime` single-stat walk (P-2)

**Parent:** TASK 017. **Depends on:** 017-00. **RTM:** R-017-3a/b, AC-017-2.

## Goal
Capture each file's mtime from the **one** stat the discovery walk already does, so the delta
path (017-08) and the `--mtime-skip` drift path (017-11) reuse it instead of re-statting.

## Design (locked — ARCHITECTURE.md §3.5 "Single-stat walk")
`DiscoveredPage` is a `NamedTuple` (layout_config.py:134) — add a trailing field with a
default (back-compat for any positional construction):
```python
class DiscoveredPage(NamedTuple):
    path: Path
    slug: str
    project: str
    extra_tags: tuple[str, ...]
    raw_type: str | None = None
    mtime: float | None = None        # NEW — st_mtime captured during the walk
```
In `iter_pages`, replace the `not path.is_file()` guard with a single stat:
```python
try:
    st = path.stat()
except OSError:
    continue
if not stat.S_ISREG(st.st_mode):
    continue
...
out.append(DiscoveredPage(..., raw_type=entry.type, mtime=st.st_mtime))
```
Iteration order, match-set, ignore/extension/system-file filters all unchanged → karpathy
byte-identity holds (the golden snapshot compares path/slug/project, not mtime).

## Steps
1. Add the `mtime` field.
2. Convert the `is_file()` check to one `path.stat()` deriving is-file + mtime; populate the
   tuple.
3. GREEN `test_iter_pages_populates_mtime` (every `DiscoveredPage.mtime` is a float ≈ the
   file's real mtime); existing `iter_pages` ordering + `test_karpathy_byte_identity` green.

## Verification
- `pytest -q -k "iter_pages or byte_identity"` GREEN; `mypy --strict scripts/` clean.
