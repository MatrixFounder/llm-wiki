"""Package entry point so `python -m scripts.wiki_skills.wiki_extract_decisions`
works. Consumed by `bin/wiki-extract-decisions` and the integration tests.
"""
from __future__ import annotations

import sys

from . import main

if __name__ == "__main__":
    sys.exit(main())
