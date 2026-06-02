"""TASK 012-04 (PW-D) — config-driven ref extraction + stdlib-`re` ReDoS gate.

Pins: (1) the karpathy single wiki-link rule reproduces `extract_wiki_links`
byte-for-byte; (2) dev-project markdown-link (stem) + id-ref extraction;
(3) the ReDoS budget gate rejects a catastrophic operator regex at config-load —
for BOTH `ref_extraction[].regex` and `paths[].project_pattern` — while built-in
layouts pass; (4) an uncompilable ref regex is rejected at load.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wiki_index.layout_config import (
    LayoutConfigError,
    RefRule,
    load_layout_config,
)
from scripts.wiki_source.parsing import extract_refs, extract_wiki_links


def _vault(tmp_path: Path) -> Path:
    r = tmp_path / "v"; r.mkdir()
    return r


# --------------------------------------------------------------------------- #
# Byte-identity: karpathy wiki-link rule == extract_wiki_links
# --------------------------------------------------------------------------- #


def test_karpathy_extract_refs_equals_extract_wiki_links(tmp_path: Path) -> None:
    body = (
        "See [[Shadow AI]] and [[oauth-2|OAuth 2.0]].\n"
        "No links here.\n"
        "Two [[alpha]] [[beta]] on one line.\n"
        "Empty [[]] should be skipped.\n"
    )
    cfg = load_layout_config(_vault(tmp_path), {"layout": "karpathy"})
    assert extract_refs(body, cfg.ref_extraction) == extract_wiki_links(body)


# --------------------------------------------------------------------------- #
# dev-project: markdown-link (stem) + id-ref
# --------------------------------------------------------------------------- #


def test_markdown_link_stem_and_id_ref() -> None:
    rules = (
        RefRule(kind="markdown-link",
                regex=r"\[([^\]]+)\]\(([^)]+\.md(?:#[^)]+)?)\)",
                target_group=2, transform="stem"),
        RefRule(kind="id-ref",
                regex=r"\b(ADR-\d+|R-\d+(?:\.\d+)*|task-\d+(?:-\d+)*)\b",
                target_group=1),
    )
    body = "See [the ADR](adr/foo.md#why) which supersedes ADR-002 and task-012-04.\n"
    got = {target for (target, _, _) in extract_refs(body, rules)}
    assert "foo" in got          # markdown-link stem (foo.md#why → foo)
    assert "ADR-002" in got      # id-ref
    assert "task-012-04" in got  # id-ref


# --------------------------------------------------------------------------- #
# ReDoS budget gate
# --------------------------------------------------------------------------- #

# TASK 017 / R-X1-REDOS-RT: operator-supplied patterns now run (and are gate-probed)
# under the PyPI `regex` engine, which optimizes `(a+)+$`/`(x+x+)+y` to linear. The
# gate judges by the engine that RUNS the pattern, so the catastrophic exemplar must
# be one `regex` does NOT optimize away (alternation-ambiguity).
_CATASTROPHIC = r"(a|a)*$"  # catastrophic under the `regex` engine (~2.8 s at n=24)


def _override(root: Path, body: str) -> None:
    (root / ".wiki").mkdir(exist_ok=True)
    (root / ".wiki" / "layout.yaml").write_text(body, encoding="utf-8")


def test_redos_rejects_catastrophic_ref_regex(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    _override(root,
        "schema_version: '2.0'\nlayout: karpathy\nslug_strategy: identity\n"
        "type_mapping:\n  note: {db_type: summary, tag: null}\n"
        "paths:\n  - {glob: '**/*.md', project: '_vault_'}\n"
        f"ref_extraction:\n  - {{kind: id-ref, regex: '{_CATASTROPHIC}', target_group: 0}}\n")
    with pytest.raises(LayoutConfigError, match="ReDoS budget"):
        load_layout_config(root, {"layout": "karpathy"})


def test_redos_rejects_catastrophic_project_pattern(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    _override(root,
        "schema_version: '2.0'\nlayout: karpathy\nslug_strategy: identity\n"
        "type_mapping:\n  note: {db_type: summary, tag: null}\n"
        f"paths:\n  - {{glob: '**/*.md', project_pattern: '{_CATASTROPHIC}', project_template: 'x'}}\n")
    with pytest.raises(LayoutConfigError, match="ReDoS budget"):
        load_layout_config(root, {"layout": "karpathy"})


def test_uncompilable_ref_regex_rejected(tmp_path: Path) -> None:
    root = _vault(tmp_path)
    _override(root,
        "schema_version: '2.0'\nlayout: karpathy\nslug_strategy: identity\n"
        "type_mapping:\n  note: {db_type: summary, tag: null}\n"
        "paths:\n  - {glob: '**/*.md', project: '_vault_'}\n"
        "ref_extraction:\n  - {kind: id-ref, regex: '(?P<bad', target_group: 0}\n")
    with pytest.raises(LayoutConfigError, match="failed to compile"):
        load_layout_config(root, {"layout": "karpathy"})


def test_builtin_karpathy_passes_redos(tmp_path: Path) -> None:
    # The built-in karpathy patterns (wiki-link + 5 course project_patterns) are
    # pre-vetted → load succeeds, no ReDoS rejection.
    cfg = load_layout_config(_vault(tmp_path), {"layout": "karpathy"})
    assert len(cfg.ref_extraction) == 1
