# Task 068-02: obsidian_selection.py skeleton (argparse + seam + stubs)

**Phase:** 0 — Stub-First · **RTM:** R-068-3, R-068-4 · **Priority:** Critical · **Depends on:** none · **Tag:** [STUB CREATION]

## Goal
Create the stdlib-only wrapper skeleton mirroring `obsidian_active_note.py`: the module header, the exit-
code constants, the single monkeypatched `_run_obsidian` seam, the full argparse surface, and stubbed
`read`/`apply` handlers returning a not-implemented envelope — importable and `mypy --strict` clean.

## New file
- `skills/obsidian-cli/scripts/obsidian_selection.py` (entrypoint `obsidian-selection`):
  - Module docstring in the sibling's style (purpose, subcommands, exit codes, the **no-`eval`-ever**
    and **base64-both-directions** invariants, the nonce read-back contract).
  - `from __future__ import annotations`; stdlib only (`argparse`, `base64`, `json`, `os`, `shutil`,
    `subprocess`, `sys`, `time`, `uuid`, `pathlib`, `typing`). **No** `import anthropic`/`from anthropic`.
  - Exit-code constants: `EXIT_OK=0`, `EXIT_USAGE=2`, `EXIT_NO_SELECTION=3`, `EXIT_APP_NOT_RUNNING=4`,
    `EXIT_CLI_ABSENT=5`, `EXIT_VAULT_MISMATCH=6`, `EXIT_GUARD_REFUSED=7`, `EXIT_HEADLESS=8`,
    `EXIT_PLUGIN_ABSENT=9`.
  - `class SelectionError(Exception)` carrying `.code` (mirror `ResolveError`).
  - `def _run_obsidian(args, *, timeout=30.0) -> subprocess.CompletedProcess[str]` — the SINGLE seam.
  - `def _await_result(nonce, *, sleep=time.sleep, deadline=…, poll=0.1) -> dict` — the nonce read-back
    poll seam, present at skeleton (stub body may `raise SelectionError(EXIT_APP_NOT_RUNNING)` for now).
    Its `sleep`/clock is **injectable** (default `time.sleep`) so the 068-03 exit-4 *timeout* test drives
    it with a no-op sleep and a fake clock — the deterministic surface the RED roster binds to; **it must
    exist and be named in the skeleton** so 068-03's timeout case is stable, not invented in 068-05/06.
  - `build_parser()` — subparsers `read` and `apply` sharing a `common` parent
    (`--vault`, `--expect-vault`, `--format {json,path,tsv}`, all `default=SUPPRESS` like the sibling to
    avoid the parents+subparsers clobber). `apply` adds `--path`, `--expect-b64`, `--replacement-b64`,
    `--from-json`, `--wiki-vault`.
  - Stub `do_read(...)` / `do_apply(...)` returning `{"ok": False, "reason": "not-implemented"}` and the
    sentinel exit code **`1`** — deliberately **OUTSIDE** the asserted `0/2–9` set, so no per-exit-code
    test in 068-03 can pass green-by-omission against the stub. Wired through a `main(argv=None) -> int`
    that catches `SelectionError` and prints `obsidian-selection: <msg>` to stderr (sibling pattern).

## Test cases
- **TC-01 (R-068-3):** `importlib`-load the module (as `tests/test_obsidian_active_note.py` does) succeeds.
- **TC-02 (R-068-3):** `grep -E "import anthropic|from anthropic" obsidian_selection.py` → no hits.
- **TC-03 (R-068-4):** the nine exit-code constants exist with the exact integer values above.
- **TC-04:** `mypy --strict skills/obsidian-cli/scripts/obsidian_selection.py` clean.

## Acceptance criteria
- [ ] Module imports; argparse exposes `read` + `apply` with the listed options; stubs return a
      not-implemented envelope.
- [ ] `mypy --strict` clean; no `anthropic` import; exit-code constants correct.

## Notes
`[STUB CREATION]` — no obsidian calls, no base64, no nonce yet (068-05/068-06 fill them). The seam and
the argparse shape must be final so the 068-03 tests bind to a stable surface.
