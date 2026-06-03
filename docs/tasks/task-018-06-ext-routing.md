# task-018-06 — [LOGIC] extension routing (case-folded)

**Parent:** TASK 018. **Depends on:** 018-05. **RTM:** E1.1/E1.2, AC-3, EC-6.

## Goal
Route by **lower-cased** extension; the format front-stage of `classify_file`.

## Steps
1. `ext = path.suffix.lower()` (handle `.excalidraw.md` / `.canvas` via the full lower-cased
   name, checked **before** the generic `.md` branch).
2. Map: `.docx/.xlsx/.pptx/.pdf` → `convert+ingest` (+`converter`, +`staged_target` =
   `_raw/.staging/<slug(stem)>-<ext>.md`); `.txt/.vtt/.srt` → `ingest` (text-source; `.vtt/.srt`
   set `normalize="vtt-detimestamp"`); `.md` → defer to the content rules (07–09); known
   image/binary + unknown ext → `skip` (`reason=binary` / `unknown-ext`). Config `extensions`
   overrides extend the sets.
3. GREEN `test_ext_routing` (incl. `report.PDF`, `note.Md`, `x.excalidraw.md`, `d.canvas`).

## Verification
- `pytest -q -k "classify or ext_routing"` GREEN; `mypy --strict` clean.
