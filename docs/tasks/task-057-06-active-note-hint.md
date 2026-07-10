# 057-06 — [W2-3] active-note secondary hint

**Goal:** `active_note_folder(vault_root)` returns the focused note's vault-relative folder
when the optional resolver is available and inside-vault — and None in every other case,
never raising, never a hard dependency.

**Context (read):** 057-00 scaffold; `skills/obsidian-cli/scripts/obsidian_active_note.py`
(`folder` subcommand :414; typed exits — treat ANY non-zero as unavailable, no per-code
allowlist); ARCHITECTURE §2.3.5 W2 step 2.

**Steps (in `_folder.py`):**
1. `shutil.which("obsidian-active-note")` → None when absent.
2. `subprocess.run([bin, "folder", "--format", "json"], capture_output=True, text=True,
   timeout=timeout_s)`; TimeoutExpired/OSError/non-zero exit → None.
3. Parse stdout JSON (dict with a folder path field — pin the exact key against the resolver
   source when implementing); non-JSON/missing key → None.
4. Containment: resolve the folder; must exist AND be inside `vault_root.resolve()`
   (`is_relative_to`) → return its vault-relative posix string; else None.

**Tests** (stub executable written into a tmp dir prepended to PATH):
- prints `{"folder": "<vault>/03 - Learning"}` exit 0 → `"03 - Learning"`.
- exit 3 (no active file) → None.
- folder outside the vault → None.
- binary absent (PATH scrubbed) → None.
- hangs > timeout (sleep) → None (use a 1 s test timeout).

**Verification:** `pytest tests/test_import_folder_inference.py -q`; `mypy --strict scripts/`.
