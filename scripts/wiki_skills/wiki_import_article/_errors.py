"""Stable exit codes + error-envelope helpers for `wiki-import-article`.

Decision-17: one JSON envelope per subcommand + a stable exit code. These codes
are the contract (`prepare`/`apply` callers branch on them); keep them stable.
"""
from __future__ import annotations

from typing import Any

# Exit codes (contract — see SKILL.md §exit codes).
EXIT_OK = 0
# NOT argparse. argparse's own status is 2, always (`wiki-import --bogus` → 2), and it exits
# before this constant is ever reached. This is the INTERNAL usage error only — the default
# exit_code of an ImportArticleError raised with no explicit code. (TASK 072 / 072-03d: the
# "argparse" half of this comment was false, and being source rather than markdown it was
# invisible to every doc census that grepped *.md.)
EXIT_USAGE = 1          # internal usage error (ImportArticleError default)
EXIT_BAD_ARG = 2        # malformed argument value (bad JSON, missing field)
EXIT_DEP_MISSING = 6    # a required external skill binary (html/pdf) is absent
EXIT_FETCH_FAILED = 10  # deterministic fetch/convert failed (propagated from html/pdf)


class ImportArticleError(Exception):
    """Domain error carrying a machine-readable code + envelope payload."""

    def __init__(self, code: str, message: str, *, exit_code: int = EXIT_USAGE,
                 details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = details or {}

    def envelope(self) -> dict[str, Any]:
        env: dict[str, Any] = {"error": self.code, "message": self.message}
        if self.details:
            env["details"] = self.details
        return env
