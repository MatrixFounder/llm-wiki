"""Stable exit codes + error-envelope helpers for `wiki-import-article`.

Decision-17: one JSON envelope per subcommand + a stable exit code. These codes
are the contract (`prepare`/`apply` callers branch on them); keep them stable.
"""
from __future__ import annotations

from typing import Any

# Exit codes (contract — see SKILL.md §exit codes).
EXIT_OK = 0
EXIT_USAGE = 1          # argparse / internal usage error
EXIT_BAD_ARG = 2        # malformed argument value (bad JSON, missing field)
EXIT_DEP_MISSING = 6    # a required external skill binary (html2md/pdf) is absent
EXIT_FETCH_FAILED = 10  # deterministic fetch/convert failed (propagated from html2md/pdf)


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
