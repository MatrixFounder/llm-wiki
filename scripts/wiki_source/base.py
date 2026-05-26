"""SourceAdapter contract — input normalization layer.

Adapters convert different source kinds (manual markdown, future transcript
via wiki-ingest workflow, future light LLM summary) into a uniform
`SourceOutput` that `wiki-index-upsert` consumes.

Phase 3a ships `wiki-source-manual` only (task-001-07 stub → task-001-24 impl).
Phase 3b adds `wiki-source-transcript` (R-06.3) and `wiki-source-light` (R-24).
All adapters share this base.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from scripts.wiki_index.models import PageRef, TrustLevel

SourceKind = Literal["manual", "transcript", "light"]
"""Adapter discriminator. Mirrors `interactions.source_kind` enum subset."""


@dataclass(frozen=True)
class SourceItem:
    """One unit of work handed to an adapter's `fetch()`.

    Class B (derivable): source_path + vault_root + vault_id are mirrors of
    filesystem + vault registry state.
    """

    kind: SourceKind
    source_path: Path
    """Absolute path to the source file (e.g. existing markdown or transcript .txt)."""

    vault_root: Path
    """Absolute path to the Obsidian vault root. Used for path-traversal guard."""

    vault_id: str
    """Stable vault identity from WIKI_SCHEMA.md::vault_id."""

    extra: dict[str, Any] = field(default_factory=dict)
    """Adapter-specific options (e.g. transcript adapter: `output_dir`, `model`)."""


@dataclass(frozen=True)
class SourceOutput:
    """Normalized result handed back from `fetch()` to the calling skill.

    Class B: every field is derivable from the adapter's input + computation.
    """

    page_slug: str
    project: str
    """'_vault_' for vault-root tier; '<course-slug>' for course-local."""

    output_path: Path
    """Absolute path to the markdown file the adapter wrote/identified.
    For `manual` adapter: same as `SourceItem.source_path`. For `transcript`:
    the LLM-generated summary file. For `light`: the single-call summary file."""

    file_hash: str
    """sha256(body) of the markdown file at output_path."""

    trust_level: TrustLevel
    """R-15.3: manual='high', transcript='medium', light='medium'."""

    frontmatter: dict[str, Any]
    """Parsed YAML frontmatter from output_path."""

    body_text: str
    """Full body of output_path (without frontmatter). Caller may normalize
    via R-07.5 before storing in `pages.body_excerpt`."""

    refs: list[PageRef]
    """Parsed wiki-link + footnote references from body. Trust level on each
    matches the adapter's class default unless overridden per-ref."""


class SourceAdapter(abc.ABC):
    """Abstract source adapter — input normalization contract.

    Adapter lifecycle per `fetch()` call:
      1. Caller constructs `SourceItem` with source_path + vault context.
      2. Adapter validates path (path-traversal guard in concrete impls).
      3. Adapter produces `SourceOutput` — either reading existing markdown
         (manual) or invoking a sub-tool (transcript: wiki-ingest workflow).
      4. Caller upserts via `repo.upsert_page` + `repo.replace_refs`.
    """

    @abc.abstractmethod
    def authenticate(self, config: dict[str, Any]) -> None:
        """First-run setup. No-op for manual; OAuth for future email/cloud
        sources. Idempotent — safe to call repeatedly."""
        ...

    @abc.abstractmethod
    def fetch(self, item: SourceItem) -> SourceOutput:
        """Main entry. Produces the normalized output for one source.

        Implementations MUST:
          - Validate `item.source_path` is inside `item.vault_root` (R-26
            path-traversal). Raise `ValueError` or adapter-specific error
            on violation — never index outside-vault paths.
          - Set `trust_level` per R-15.3 (manual=high, transcript=medium,
            light=medium).
        """
        ...

    @abc.abstractmethod
    def dedup_state_key(self, item: SourceItem) -> str:
        """Stable key for `source_state` table — used by adapters that need
        idempotency (e.g. transcript A4 short-circuit per ADR-002 Phase 3b
        contract). Manual adapter returns a no-op key but the method must
        still exist for interface conformance.

        Typical impl: `sha256(str(item.source_path).encode())[:16]`.
        """
        ...
