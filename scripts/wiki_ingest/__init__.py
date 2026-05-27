"""Internal package for the wiki-ingest skill.

Status (as of bead 015-01): only `_safety.py` is realised. The remaining
modules below land in beads 015-02..015-11; until then their symbols
still live in `wiki_ops.py` behind back-compat re-exports.

Layered model (one-way dependency rule, F3 → F2 → F1):

    F3 · Vault & Command Layer
        commands/*.py     (one CLI subcommand per module)
        _vault.py         (vault layout constants + walk + tail_log)
        _classify.py      (classify-folder helpers)

    F2 · Markdown / Frontmatter Engine
        _markdown.py      (section / wikilink / masking primitives)
        _frontmatter.py   (YAML split + structural splice)

    F1 · Safety & I/O Primitives
        _safety.py        (atomic I/O · NFKC · safe_inline · safe_for_json)

Rules:
- No command imports another command.
- No `_<helper>` module imports `commands/`.
- The package has NO public API; the only stable surface is the
  `wiki_ops.py` CLI shim (see SKILL.md for the agent contract).

Tests live in ../tests/.
"""

# Single source of truth for the skill's version (TASK 017 R2.1). The
# `wiki_ops.py --version` action reads this constant; the matching
# minimum-version contract is documented in CONTRACT §7 (mirrored in
# references/manifest_schema.md). Bump format: semver MAJOR.MINOR.PATCH.
__version__ = "1.1.0"

# VENDORED-PATCH (bead 004-01, R-45): upstream submodules use absolute
# imports like `from wiki_ingest import _dispatch`, which work in
# standalone layout (Universal-skills/.../scripts/wiki_ingest sibling
# to `wiki_ops.py`) but fail in our nested namespace
# `scripts.wiki_ingest.*`. Standard vendoring shim: register this
# package under the bare name `wiki_ingest` in sys.modules so absolute
# imports resolve to this package. Same approach used by pip's
# `_vendor/__init__.py`. Documented in VENDORED_FROM.md::local_patches.
import sys as _sys
_sys.modules.setdefault("wiki_ingest", _sys.modules[__name__])
