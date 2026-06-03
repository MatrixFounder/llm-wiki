# task-018-05 — [STUB] classifier surface (`_sync.py`)

**Parent:** TASK 018. **Depends on:** 018-00. **RTM:** E1, E2. **Design:** functional-architecture.md *Sync Dispatcher → Classification*.

## Goal
Stub-First surface for the routing brain.

## Design (locked)
```python
@dataclass(frozen=True)
class Decision:
    action: Literal["convert+ingest", "ingest", "upsert", "skip"]
    reason: str
    converter: str | None = None        # docx|xlsx|pptx|pdf
    staged_target: str | None = None    # _raw/.staging/<slug(stem)>-<ext>.md
    normalize: str | None = None        # "vtt-detimestamp"

def classify_file(path: Path, *, vault_root: Path, config: SyncConfig, layout,
                  in_raw: bool, in_exclude_zone: bool) -> Decision: ...   # stub → Decision("skip","stub")
```

## Steps
1. New `scripts/wiki_skills/_sync.py` with `Decision` + the `classify_file` stub.
2. RED matrix in `tests/test_wiki_sync.py` (`test_classify_matrix`): one parametrized case per
   route (.docx→convert, .vtt→ingest, no-tag-typed .md→upsert, `#wiki/skip`→skip, dbfolder→skip)
   — all fail against the stub.

## Verification
- `pytest -q -k classify` → RED; `mypy --strict` clean.
