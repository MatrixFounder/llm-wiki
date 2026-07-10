# 057-00 — `_folder.py` scaffold (stub-first)

**Goal:** the W2 folder-inference module exists with frozen, typed signatures; imports clean
under `mypy --strict`; test file scaffolded.

**Context (read):** `docs/TASK.md` W2-2..4; ARCHITECTURE §2.3.5 (W2 block);
`scripts/wiki_skills/wiki_import_article/__init__.py` (prepare), `scripts/wiki_index/models.py`
(`Page.file_path` vault-relative, `Page.title`), `scripts/wiki_index/repository.py::search_pages`.

**Create:** `scripts/wiki_skills/wiki_import_article/_folder.py`

```python
@dataclass
class FolderInference:
    folder: str | None          # --folder-form vault-relative folder, None = unresolved
    basis: str | None           # "series-sibling" | "active-note" | None
    confidence: str | None      # "high" | "medium" | None
    evidence: list[str]         # sibling file_paths (vault-relative)
    candidates: list[str]       # ranked distinct folders when ambiguous/unresolved

def series_stem(title: str | None) -> str | None: ...          # pure
def folder_for_hit(file_path: str, source_subdir: str) -> str | None: ...  # pure; None = machinery-excluded
def infer_folder(repo: IndexRepository, vault_id: str, title: str | None,
                 *, source_subdir: str) -> FolderInference: ...  # read-only DAL consumer
def active_note_folder(vault_root: Path, *, timeout_s: int = 10) -> str | None: ...  # subprocess hint
```

`IndexRepository` imported from `scripts.wiki_index.repository` — pin the DAL type (no `Any`;
plan-review F1); every def fully annotated so the module is `mypy --strict` clean from the
scaffold commit onward. `infer_folder` consumes `search_pages -> list[PageHit]`
(`scripts/wiki_index/models.py:168`): the `Page` is nested at `hit.page`
(`hit.page.title` / `hit.page.file_path`), the rank score at `hit.bm25_score` (plan-review F3).

Stub bodies: `series_stem`/`folder_for_hit`/`active_note_folder` return None;
`infer_folder` returns an all-None/empty `FolderInference`. Full docstrings now (they are the
contract); logic lands in 057-05/06.

**Create:** `tests/test_import_folder_inference.py` — import test + `FolderInference` shape test
(green immediately).

**Verification:** `pytest tests/test_import_folder_inference.py -q` green;
`mypy --strict scripts/` clean.
