"""Concrete `IndexRepository` backed by SQLite — the DAL domain-package (TASK 056).

Until TASK 055 this was a single 2227-line module (`sqlite_repository.py`);
TASK 056 split it into per-table-family mixin modules composed here. The
public import surface is FROZEN — consumers keep writing::

    from scripts.wiki_index.sqlite_repository import (
        SQLiteRepository, AliasCollisionError, VaultRegistrationError,
    )

Layout (see docs/architectures/system-architecture.md §3.2):

- `_base.py`         — `SQLiteRepositoryBase(IndexRepository)`: connection +
                       PRAGMAs, lifecycle, `_SCHEMA_PATH`, exceptions, `_in_clause`
- `_vaults.py`       — vault registry CRUD
- `_pages.py`        — pages CRUD (M-4 ON CONFLICT contract)
- `_refs_graph.py`   — page_entity_refs + backlinks + typed-edge graph
- `_search.py`       — FTS5 search (edge: `_SearchMixin(_PagesMixin)`)
- `_health_rules.py` — R-15/R-19 declared-rules analyses
- `_health_scan.py`  — structural integrity scans (orphans, drift, …)
- `_events.py`       — log events + batch runs
- `_entities.py`     — entity CRUD, candidates, mentions, aliases
- `_merge.py`        — entity merge (edge: `_MergeMixin(_EntitiesMixin)`)
- `_state.py`        — query/verify/source state + citation readers

C3 rule: a mixin carrying a dependency edge precedes its dependency; the
super-mixins `_PagesMixin`/`_EntitiesMixin` are OMITTED from the composite
tuple below (inherited transitively via `_SearchMixin`/`_MergeMixin`).
"""

from __future__ import annotations

from scripts.wiki_index.sqlite_repository._base import (
    _SCHEMA_PATH,
    AliasCollisionError,
    SQLiteRepositoryBase,
    VaultRegistrationError,
)
from scripts.wiki_index.sqlite_repository._events import _EventsMixin
from scripts.wiki_index.sqlite_repository._health_rules import _HealthRulesMixin
from scripts.wiki_index.sqlite_repository._health_scan import _HealthScanMixin
from scripts.wiki_index.sqlite_repository._merge import _MergeMixin
from scripts.wiki_index.sqlite_repository._refs_graph import _RefsGraphMixin
from scripts.wiki_index.sqlite_repository._search import _SearchMixin
from scripts.wiki_index.sqlite_repository._state import _StateMixin
from scripts.wiki_index.sqlite_repository._vaults import _VaultsMixin

__all__ = [
    "SQLiteRepository",
    "SQLiteRepositoryBase",
    "AliasCollisionError",
    "VaultRegistrationError",
    "_SCHEMA_PATH",
]


class SQLiteRepository(
    _VaultsMixin,
    _SearchMixin,
    _RefsGraphMixin,
    _HealthRulesMixin,
    _HealthScanMixin,
    _MergeMixin,
    _EventsMixin,
    _StateMixin,
    SQLiteRepositoryBase,
):
    """SQLite-backed `IndexRepository`, assembled from the domain mixins above.

    Behaviour is the pre-056 monolith's, relocated verbatim; the full test
    suite + `mypy --strict` are the behaviour-freeze gates (TASK 056 R5).
    """
