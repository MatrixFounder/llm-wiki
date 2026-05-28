"""Cross-package layout-constants invariant.

The vendored `scripts.wiki_ingest._vault` module (snapshot of
Universal-skills wiki-ingest per §7.4 Vendoring Policy) keeps its OWN
copy of layout constants — it has to, because the upstream package
ships without depending on this repo. Host code uses
`scripts.wiki_index.layout` as the single source of truth.

This test asserts the two surfaces agree on every string value an
operator might see at the vault filesystem. Catches silent drift if
either side is renamed before the other (e.g. a future
`_sources` → `pages` rename lands in `wiki_index.layout` but the
vendored copy still expects the old name, or vice versa). Either
direction breaks the integration pipeline; this test fails loudly the
moment the constants stop matching, instead of waiting for an
end-to-end run on a real vault to surface the divergence.

When this test fires, follow §7.4 Vendoring Policy: push the rename
upstream first, then `bash scripts/sync_wiki_ingest.sh` to pull the
matching value down.
"""
from __future__ import annotations

from scripts.wiki_index import layout as host_layout
from scripts.wiki_ingest import _vault as vendored_layout


def test_vendored_wiki_ingest_layout_constants_match_host() -> None:
    """Vendored DEFAULT_SUBDIRS + SCHEMA_FILE must equal the host's
    PAGE_SUBDIRS + SCHEMA_FILE values, byte-for-byte. If this test
    fails, sync the vendored copy (upstream first) or update
    `scripts.wiki_index.layout` to match."""
    assert tuple(vendored_layout.DEFAULT_SUBDIRS) == host_layout.PAGE_SUBDIRS, (
        "vendored wiki_ingest DEFAULT_SUBDIRS != host PAGE_SUBDIRS — "
        "upstream-first sync needed per §7.4 Vendoring Policy"
    )
    assert vendored_layout.SCHEMA_FILE == host_layout.SCHEMA_FILE, (
        "vendored wiki_ingest SCHEMA_FILE != host SCHEMA_FILE — "
        "upstream-first sync needed per §7.4 Vendoring Policy"
    )
    # Defence-in-depth on the SUBDIR_TO_KIND keyset — same subdir names
    # are the namespace for both the vendored mapping and PAGE_SUBDIRS.
    assert set(vendored_layout.SUBDIR_TO_KIND.keys()) == set(host_layout.PAGE_SUBDIRS), (
        "vendored SUBDIR_TO_KIND keys != host PAGE_SUBDIRS — "
        "one side knows about a tier the other doesn't"
    )
