# task-017-09 — [LOGIC] `_extract_frontmatter_type` regex fast-path (P-3)

**Parent:** TASK 017. **Depends on:** 017-00. **RTM:** R-017-2a, AC-017-3 (part).

## Goal
Replace per-file PyYAML parsing in `check_drift`'s type-extraction with a regex fast-path,
keeping a PyYAML fallback so the extracted `type:` is byte-identical to today on the corpus.

## Design (locked — ARCHITECTURE.md §8.4)
`scripts/wiki_index/sqlite_repository.py::_extract_frontmatter_type(body)` currently splits on
`---\n` and `yaml.safe_load(parts[1])`. New:
```python
if not body.startswith("---\n"):
    return None
parts = body.split("---\n", 2)
if len(parts) < 3:
    return None
fm_block = parts[1]
m = re.search(r"^type:[ \t]*(\S.*?)[ \t]*$", fm_block, re.MULTILINE)
if m:
    val = m.group(1)
    if val[:1] not in "[{|>&*\"'":            # trivial scalar → trust the fast path
        return val
# non-trivial (quoted/folded/flow/anchor) OR no match → PyYAML fallback (today's path)
import yaml as _yaml
try:
    fm = _yaml.safe_load(fm_block) or {}
except _yaml.YAMLError:
    return None
val = fm.get("type") if isinstance(fm, dict) else None
return val if isinstance(val, str) else None
```
This keeps the `read_bytes()`+sha256 (default integrity unchanged, D-017-B); only the YAML
parse is skipped for the common `type: word` case.

## Steps
1. Implement the fast-path + fallback exactly as above.
2. GREEN `test_extract_type_regex_equals_pyyaml`: a matrix of frontmatter samples
   (`type: concept`, `type: "summary"`, `type: 'query'`, folded `type: >`, a list, no type,
   trailing comment) — assert the new fn == an oracle running PyYAML on the same block.

## Verification
- `pytest -q -k "extract_type"` GREEN; existing `check_drift` / type-mismatch tests green;
  `mypy --strict scripts/` clean.
