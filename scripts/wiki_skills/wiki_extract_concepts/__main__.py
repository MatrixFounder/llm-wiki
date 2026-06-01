"""Package entry point so `python -m scripts.wiki_skills.wiki_extract_concepts`
keeps working after the TASK 016 module→package split.

Consumed by `bin/wiki-extract-concepts` and
`tests/test_wiki_extract_concepts_integration.py` (the `-m` subprocess).
"""
from __future__ import annotations

import sys

from . import main

if __name__ == "__main__":
    sys.exit(main())
