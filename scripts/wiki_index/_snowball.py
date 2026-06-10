"""Thin typed wrapper around `snowballstemmer` (TASK 028 / Q-028-2, F-7).

`snowballstemmer` ships no `py.typed` marker, so `import snowballstemmer` is an
`import-untyped` error under `mypy --strict`. This module is the ONE place that
ignore lives — every other module imports the fully-typed `stem(word, lang)`
facade below, keeping the rest of `scripts/` strict-clean. (No
`types-snowballstemmer` package exists, so the wrapper is the only mechanism.)

The dep is pinned EXACT (`snowballstemmer==3.1.1`) because a stem-algorithm
change alters which pages a query matches, and that hit set feeds
`wiki-query`'s `question_hash` (C1). 36 languages are available; TASK 028 uses
`russian` + `english` (per-term by script).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import snowballstemmer  # type: ignore[import-untyped]


@lru_cache(maxsize=None)
def _stemmer(lang: str) -> Any:
    """Cache one stemmer instance per language (construction is non-trivial)."""
    return snowballstemmer.stemmer(lang)


def stem(word: str, lang: str) -> str:
    """Stem ``word`` with the snowball algorithm for ``lang`` (e.g. 'russian',
    'english'). Deterministic for the pinned version. Caller lowercases as
    needed (snowball assumes lowercase input)."""
    return str(_stemmer(lang).stemWord(word))
