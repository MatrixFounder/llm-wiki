"""Host layout-constants invariant (TASK 047 P2: de-vendored).

Until TASK 047 this file also drift-guarded the vendored `scripts.wiki_ingest._vault`
copy of the layout constants against the host `scripts.wiki_index.layout`. `wiki_ingest`
(and `wiki-enrich`) were retired, so the cross-surface drift guard is gone; what remains is
the HOST-only structural invariant that still matters: `PAGE_SUBDIRS` is exactly the
`INGEST_SHARED_SUBDIRS` file-synthesis subset ∪ the `HOST_ONLY_SUBDIRS` (e.g. `_queries`,
RAG answer pages) — the constants are still live (`layout.py` builds `PAGE_SUBDIRS` from both).
"""
from __future__ import annotations

from scripts.wiki_index import layout as host_layout


def test_host_page_subdirs_is_superset_of_ingest_shared() -> None:
    """`PAGE_SUBDIRS` (everything `discover_pages`/drift/render walk) == the ingest-shared
    subdirs ∪ the host-only subdirs, disjoint and lossless. Guards against a future edit that
    drops a shared subdir from the walk or double-lists a host-only one. Pins the R-X1 role
    split (`_queries` is host-only, NOT part of the shared file-synthesis subset)."""
    shared = set(host_layout.INGEST_SHARED_SUBDIRS)
    host_only = set(host_layout.HOST_ONLY_SUBDIRS)
    page = set(host_layout.PAGE_SUBDIRS)
    assert shared & host_only == set(), "shared and host-only subdirs must be disjoint"
    assert page == shared | host_only, "PAGE_SUBDIRS must be exactly shared ∪ host-only"
    assert shared <= page, "every ingest-shared subdir must be walked by the host"
    assert host_layout.QUERIES_SUBDIR in host_only, "_queries is a host-only subdir"
    assert host_layout.QUERIES_SUBDIR not in shared, "_queries is NOT part of the shared subset"
