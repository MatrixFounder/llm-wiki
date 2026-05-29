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
    """The vendored DEFAULT_SUBDIRS + SCHEMA_FILE must equal the host's
    **INGEST_SHARED_SUBDIRS** + SCHEMA_FILE, byte-for-byte.

    The shared contract is the set of subdirs the wiki-ingest *file-synthesis*
    layer produces (source / concept / entity) — NOT the full host
    `PAGE_SUBDIRS`. Since TASK 007 (R-6), the host walks an additional
    host-only page subdir (`_queries`, RAG answer pages written by
    `wiki-query`) that the vendored ingest snapshot legitimately knows nothing
    about. So the byte-for-byte drift guard targets `INGEST_SHARED_SUBDIRS`
    (the genuinely-shared subset) and we separately assert the host superset
    relationship below.

    If the byte-for-byte assertion fails, sync the vendored copy (upstream
    first) or update `scripts.wiki_index.layout.INGEST_SHARED_SUBDIRS` to
    match — §7.4 Vendoring Policy. (Forward: ROADMAP R-X1 folds this
    shared-vs-host-only split into the per-vault layout config.)"""
    assert tuple(vendored_layout.DEFAULT_SUBDIRS) == host_layout.INGEST_SHARED_SUBDIRS, (
        "vendored wiki_ingest DEFAULT_SUBDIRS != host INGEST_SHARED_SUBDIRS — "
        "upstream-first sync needed per §7.4 Vendoring Policy"
    )
    assert vendored_layout.SCHEMA_FILE == host_layout.SCHEMA_FILE, (
        "vendored wiki_ingest SCHEMA_FILE != host SCHEMA_FILE — "
        "upstream-first sync needed per §7.4 Vendoring Policy"
    )
    # Defence-in-depth on the SUBDIR_TO_KIND keyset — same subdir names
    # are the namespace for both the vendored mapping and the shared subset.
    assert set(vendored_layout.SUBDIR_TO_KIND.keys()) == set(host_layout.INGEST_SHARED_SUBDIRS), (
        "vendored SUBDIR_TO_KIND keys != host INGEST_SHARED_SUBDIRS — "
        "one side knows about a shared tier the other doesn't"
    )


def test_host_page_subdirs_is_superset_of_ingest_shared() -> None:
    """`PAGE_SUBDIRS` (everything `discover_pages`/drift/render walk) is the
    host superset: the wiki-ingest-shared subdirs + host-only subdirs, with no
    overlap and no loss. Guards against a future edit that drops a shared
    subdir from the walk or double-lists a host-only one."""
    shared = set(host_layout.INGEST_SHARED_SUBDIRS)
    host_only = set(host_layout.HOST_ONLY_SUBDIRS)
    page = set(host_layout.PAGE_SUBDIRS)
    assert shared & host_only == set(), "shared and host-only subdirs must be disjoint"
    assert page == shared | host_only, "PAGE_SUBDIRS must be exactly shared ∪ host-only"
    assert shared <= page, "every ingest-shared subdir must be walked by the host"
    # `_queries` is host-only and NOT part of the vendored ingest contract.
    assert host_layout.QUERIES_SUBDIR in host_only
    assert host_layout.QUERIES_SUBDIR not in vendored_layout.DEFAULT_SUBDIRS
