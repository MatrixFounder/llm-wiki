"""F3-boundary dispatch helper (TASK 017 bead 017-03 — resolves arch Q-2).

Lets `commands/ingest.py` invoke other atomic commands without violating
the "no command imports another command" invariant
(`docs/ARCHITECTURE.md` §3.2, enforced by `tests/test_architecture.py`).

The target command is imported AT CALL TIME inside `dispatch()` via
`importlib.import_module(...)` — a `Call` node, not an `Import`
statement. The AST walker in `test_architecture.py` only flags
syntactic `import` / `from … import …` nodes, so this pattern is
invisible to it. The deliberate carve-out is locked by
`test_architecture.py::test_dispatch_no_module_level_command_imports`,
which asserts `_dispatch.py` has ZERO module-level
`wiki_ingest.commands.*` imports — future maintainers reintroducing a
top-level `from wiki_ingest.commands import …` would fail the gate.

Security (T17-S9 / `references/exit_codes.md` matrix): `cmd_name` is
validated against a frozen whitelist BEFORE `importlib.import_module`
runs. Unknown / non-whitelisted names route to
`die("UNKNOWN_COMMAND", code=EXIT_USAGE)` — the orchestrator cannot
recurse via dispatch into itself or into broader operator-facing
commands.
"""
from __future__ import annotations

import argparse
import importlib

from wiki_ingest import _safety


# Exactly the five atomic ops the v1.1 `ingest` orchestrator composes.
# Adding a new entry here is a deliberate, reviewable change — DO NOT
# loosen this to a regex or build it from `commands/` dirlisting.
_ALLOWED_COMMANDS: frozenset = frozenset({
    "register-summary",
    "upsert-page",
    "update-index",
    "append-log",
    "log-event",
})


def dispatch(cmd_name: str, args: argparse.Namespace) -> int:
    """Invoke `wiki_ingest.commands.<cmd>.execute(args)`; propagate exit code.

    `cmd_name` is the hyphenated CLI form (e.g. `"upsert-page"`). The
    helper translates to the underscore form for the module path
    (`wiki_ingest.commands.upsert_page`).

    Unknown / non-whitelisted `cmd_name` → `die(..., code=EXIT_USAGE)`
    BEFORE any `importlib.import_module` call (T17-S9).
    """
    if cmd_name not in _ALLOWED_COMMANDS:
        _safety.die(f"UNKNOWN_COMMAND: {cmd_name!r} is not dispatchable; "
                    f"allowed: {sorted(_ALLOWED_COMMANDS)}",
                    code=_safety.EXIT_USAGE)
    module_name = cmd_name.replace("-", "_")
    mod = importlib.import_module(f"wiki_ingest.commands.{module_name}")
    return mod.execute(args)
