"""Sanity test: vendored wiki_ingest package is importable.

Phase 1 stub asserts `__version__ == "1.1.0"` on the empty skeleton.
Phase 2 (after rsync of upstream) asserts:
  (a) the upstream entry point `commands.ingest.execute` is importable (R-45(e));
  (b) the `sys.modules` vendoring shim resolves absolute imports
      (`from wiki_ingest import X`) from MULTIPLE submodules — not just one
      lucky path — so we know the shim is comprehensive.
"""

from __future__ import annotations


def test_vendored_import() -> None:
    """R-45(a) + R-45(e): package importable, upstream `execute` callable."""
    from scripts.wiki_ingest import __version__
    assert __version__ == "1.1.0", __version__

    from scripts.wiki_ingest.commands.ingest import execute
    assert callable(execute)


def test_vendoring_shim_resolves_absolute_imports() -> None:
    """Vendoring shim (`sys.modules.setdefault("wiki_ingest", ...)`) must
    make absolute imports `from wiki_ingest import X` work from EVERY
    submodule the package exposes, not just the one that bead 004-01
    happened to test by accident. If only some imports work, downstream
    beads (especially I-V.5 wiki-enrich-refactor calling vendored.ingest)
    will explode at runtime.

    This test imports the package, then validates that the bare-name
    alias resolves submodules across all three layers of the upstream's
    F1/F2/F3 architecture (per `scripts/wiki_ingest/__init__.py` docstring).
    """
    # Trigger shim by importing the package.
    import scripts.wiki_ingest  # noqa: F401

    # F1 (safety primitives) — minimum-load test
    from wiki_ingest import _safety
    assert hasattr(_safety, "__name__")

    # F2 (markdown engine)
    from wiki_ingest import _frontmatter, _markdown
    assert _frontmatter is not None
    assert _markdown is not None

    # F3 (vault / command layer)
    from wiki_ingest import _vault, _dispatch
    assert _vault is not None
    assert _dispatch is not None

    # Submodule access via wiki_ingest.commands (loaded once package alias resolves)
    from wiki_ingest.commands import ingest as ingest_cmd
    from wiki_ingest.commands import scan as scan_cmd
    assert callable(getattr(ingest_cmd, "execute", None)), \
        "commands.ingest.execute must exist (vendoring + upstream contract)"
    assert callable(getattr(scan_cmd, "execute", None)), \
        "commands.scan.execute must exist (vendoring + upstream contract)"
