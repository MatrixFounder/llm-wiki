# task-018-15 — E2E acceptance + fixtures

**Parent:** TASK 018. **Depends on:** 018-13 (deterministic), 018-14 (orchestrated path). **RTM:** AC-1..14.

## Goal
Lock the acceptance criteria with durable fixtures, incl. the operator's real sidecar samples.

## Steps
1. `tests/fixtures/sync/**`: the operator's **real `yaml:dbfolder`** note (from the chat sample),
   a Bases note (` ```base `), a Dataview note (` ```dataviewjs `), an **embedded-dataview content
   note** (prose + a dataview block), a folder-note (`X/X.md`), a `.vtt` (with timestamps), an
   empty `.txt`, a tiny `.docx` **or** a stub converter shim, a type-less prose `.md`, a `#wiki/skip`
   draft, a `#wiki/raw` note.
2. `tests/test_wiki_sync_e2e.py` asserting:
   - **AC-2/2b** view-sidecars skip; embedded-dataview note → `upsert`.
   - **AC-3/4** extension + tag routing matrix (incl. `.PDF`, `.excalidraw.md`, precedence).
   - **AC-1/10** valid plan JSON; two scans byte-identical.
   - **AC-5** re-run no-op (after a recorded `sync` row, the entry is `is_unchanged`).
   - **AC-14** convert+ingest convergence: the staged `_raw/.staging/…` output is NOT re-discovered
     on a second walk/scan.
   - **AC-6** `--dry-run` leaves vault + DB byte-unchanged.
   - **AC-11** empty + unparseable-frontmatter never raise.
   - **AC-12** unmappable-type → skip; same-stem convert sources → distinct `.staging/` targets.

## Verification
- `pytest -q tests/test_wiki_sync_e2e.py` GREEN; full suite + `mypy --strict` clean.
