# task-018-12 — [STUB] `wiki-sync scan` CLI + wrappers

**Parent:** TASK 018. **Depends on:** 018-05. **RTM:** E3.1, E3.4, AC-9. **Design:** interfaces §5.4.

## Goal
Stand up the deterministic CLI shell (empty plan) + the shell/slash wrappers. **No `import anthropic`.**

## Steps
1. New `scripts/wiki_skills/wiki_sync.py` (+ `__main__` runnable via `python -m`): argparse
   `scan` subcommand — `<zone>` positional, `--vault`, `--vault-root`, `--dry-run`, `--db-path`.
   Emit a **hardcoded empty** plan JSON (`{vault_id, zone, generated_by:"wiki-sync/scan",
   entries:[], summary:{...0}}`) via `scripts.wiki_skills._common.emit`. Exit codes: `0` ok,
   `2` precondition (zone missing / outside vault / unregistered), `6` config-invalid. Errors
   never echo untrusted content (CWE-209/117).
2. New `bin/wiki-sync` wrapper (cd repo + `source .venv/bin/activate` + `exec python -m
   scripts.wiki_skills.wiki_sync "$@"`, `chmod +x`); new `commands/wiki-sync.md` slash command.
3. RED e2e `test_scan_emits_plan_envelope` (runs `scan` on a temp zone → valid JSON, `entries==[]`
   on the stub → assert the envelope shape; will be tightened in 13).

## Verification
- `python -m scripts.wiki_skills.wiki_sync scan <tmp> --vault v --vault-root <tmp>` → JSON, exit 0;
  `grep -L anthropic` on the module; `pytest -q -k scan_emits` GREEN-on-stub; `mypy --strict` clean.
