"""Private helpers shared across CLI scaffolds in this package.

Not exposed outside scripts/wiki_skills/. Underscore prefix marks intent.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    """Print one-line JSON and return ``exit_code``.

    Default success: ``exit_code=0``. Error envelopes (payloads containing
    an ``"error"`` key) MUST pass a non-zero code so shell scripts and
    test harnesses can detect failures via ``$?``. Convention (matches
    ``wiki_init._emit``): ``6`` for validation/look-up errors, ``7`` for
    interactive-confirm-required warnings.
    """
    print(json.dumps(payload, ensure_ascii=False), file=sys.stdout)
    return exit_code
