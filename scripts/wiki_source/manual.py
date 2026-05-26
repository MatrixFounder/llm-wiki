"""`wiki-source-manual` adapter — real impl per task-001-24."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from scripts.wiki_index.models import PageRef
from scripts.wiki_index.security import validate_inside_vault
from scripts.wiki_source.base import SourceAdapter, SourceItem, SourceOutput
from scripts.wiki_source.parsing import (
    compute_file_hash,
    derive_slug,
    extract_wiki_links,
    parse_frontmatter,
)


class ManualSourceAdapter(SourceAdapter):
    """For existing markdown files. trust_level='high' per R-15.3 — content
    is operator-curated."""

    def authenticate(self, config: dict[str, Any]) -> None:
        """No-op. Manual adapter has no external system."""
        _ = config

    def fetch(self, item: SourceItem) -> SourceOutput:
        # R-26 path-traversal guard
        abs_source = validate_inside_vault(item.source_path, item.vault_root)
        frontmatter_dict, body_text = parse_frontmatter(abs_source)
        file_hash = compute_file_hash(body_text)
        slug, project = derive_slug(abs_source, item.vault_root.resolve(strict=True))
        links = extract_wiki_links(body_text)
        refs = [
            PageRef(
                vault_id=item.vault_id,
                page_slug=slug,
                page_project=project,
                entity_slug=target,
                ref_type="mentioned",  # ref_type CHECK enum value
                trust_level="high",   # R-15.3
                line_start=line_no,
                line_end=line_no,
                source_quote=quote,
            )
            for (target, line_no, quote) in links
        ]
        return SourceOutput(
            page_slug=slug,
            project=project,
            output_path=abs_source,
            file_hash=file_hash,
            trust_level="high",
            frontmatter=frontmatter_dict,
            body_text=body_text,
            refs=refs,
        )

    def dedup_state_key(self, item: SourceItem) -> str:
        """sha256(abs(source_path))[:16] — stable per-file key for source_state."""
        return hashlib.sha256(str(item.source_path).encode("utf-8")).hexdigest()[:16]
