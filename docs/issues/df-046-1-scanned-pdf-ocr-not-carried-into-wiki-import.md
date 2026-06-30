---
id: DF-046-1
type: known-issue
status: open
opened_at: 2026-06-30
category: capability-regression
slug: df-046-1-scanned-pdf-ocr-not-carried-into-wiki-import
---

# Scanned/image-only PDF OCR not carried into the converged wiki-import path

- **Symptom**: An image-only (scanned) PDF that the **pre-P2** `wiki-sync` inline pipeline would
  OCR (and then summarise) is, after TASK 046 P2 (converged construct path), **un-summarisable**:
  `wiki-import prepare` extracts no text → `FETCH_FAILED` (exit 10), and with no commit-marker the
  file re-fails every scan.
- **Root cause**: The retired inline `wiki-sync` Step 4a had a **wired OCR remediation hop**
  (`pdf_extract.py` exit 10 `DocumentScanned` → `pdf_ocr.py --lang eng+rus` → re-extract → continue
  as ingest, with `needs-ocr`/`ocr-failed:<type>` fallbacks). TASK 046 moved all conversion into
  `wiki-import prepare`, which has **no OCR** (`_pdf_to_text` returns `ok=False` on empty text →
  `FETCH_FAILED`). The OCR hop was not carried over. Surfaced by the P2 multi-agent review.
- **Current mitigation (TASK 046 P2)**: the `wiki-sync` recipe instructs the executor to read the
  pdf skill's `DocumentScanned` signal from the error envelope, flag the file **`needs-ocr`**, and
  skip it (no commit-marker) — so the operator is told the file needs OCR rather than it failing
  silently. The pdf skill still ships `pdf_ocr.py`; only the wiring is missing.
- **Fix (separate task)**: add a scanned-PDF OCR remediation hop **inside `wiki-import prepare`**
  (on the pdf skill's exit-10 `DocumentScanned`, run `pdf_ocr.py` → re-extract → continue), so BOTH
  the direct `/wiki-import` path and the `wiki-sync` batch driver gain OCR at once. Until then,
  scanned PDFs must be OCR'd out-of-band before import.
- **Scope**: explicitly **out of scope** for TASK 046 (see `docs/TASK.md` Out-of-scope).
