"""Tests for `wiki-sync` (TASK 018 / R-11) — format-aware, tag-routed ingest
dispatcher.

This module is built up bead-by-bead under Stub-First / strict-TDD (PLAN.md):
- Phase 1 (01–04): `source_state` DAL `sync` partition + `.wiki/sync.yaml` loader.
- Phase 2 (05–09): `classify_file` routing brain.
- Phase 3 (10–13): own bounded walk + `wiki-sync scan` plan-emit.

End-to-end acceptance (AC-1..14) lives in `tests/test_wiki_sync_e2e.py` (bead 15).

Anchor (bead 00): the module collects and the baseline suite is unchanged.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts.wiki_index.layout_config import (
    LayoutConfig,
    load_layout_config,
    resolve_layout_config,
)
from scripts.wiki_index.models import Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
from scripts.wiki_index.sync_config import (
    WIKI_SYNC_CONFIG_MAX_BYTES,
    SyncConfig,
    SyncConfigError,
    TranscriptDedupConfig,
    load_sync_config,
)
from scripts.wiki_skills._sync import (
    Candidate,
    Decision,
    classify_file,
    iter_sync_candidates,
    transcript_variant_skips,
)


def _karpathy_layout(tmp_path: Path) -> LayoutConfig:
    """The default (karpathy) layout for a config-less vault root."""
    return resolve_layout_config(tmp_path)


def _classify(
    path: Path,
    *,
    vault_root: Path,
    config: SyncConfig | None = None,
    layout: LayoutConfig | None = None,
    in_raw: bool = False,
    in_exclude_zone: bool = False,
) -> Decision:
    return classify_file(
        path,
        vault_root=vault_root,
        config=config or SyncConfig(),
        layout=layout or _karpathy_layout(vault_root),
        in_raw=in_raw,
        in_exclude_zone=in_exclude_zone,
    )


def _write_sync_yaml(vault_root: Path, text: str) -> None:
    (vault_root / ".wiki").mkdir(parents=True, exist_ok=True)
    (vault_root / ".wiki" / "sync.yaml").write_text(text, encoding="utf-8")


def test_anchor_collects() -> None:
    """Placeholder so the new module collects before any wiki-sync code lands."""
    assert True


# ---------------------------------------------------------------------------
# Phase 1 — `source_state` DAL `sync` partition (beads 01 STUB → 02 LOGIC)
# ---------------------------------------------------------------------------


def _repo(tmp_path: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    for vid in ("vault-one", "vault-two"):
        repo.register_vault(Vault(
            vault_id=vid, name=vid, root_path=tmp_path / vid,
            schema_version="5.0", registered_at=datetime(2026, 6, 3),
        ))
    return repo


def test_source_state_roundtrip(tmp_path: Path) -> None:
    """set then get returns the value."""
    repo = _repo(tmp_path)
    repo.set_source_state("vault-one", "sync", "courses/x.vtt", "source_hash", "abc")
    assert repo.get_source_state("vault-one", "sync", "courses/x.vtt", "source_hash") == "abc"
    repo.close()


def test_source_state_missing_returns_none(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert repo.get_source_state("vault-one", "sync", "nope", "source_hash") is None
    repo.close()


def test_source_state_zero_ddl(tmp_path: Path) -> None:
    """The `sync` partition is data, not schema: it does not advance `user_version`
    (the live pin is 7 since TASK 034) and the write is accepted (no `source_kind`
    CHECK to reject it). Closes Q-018-8."""
    repo = _repo(tmp_path)
    repo.set_source_state("vault-one", "sync", "courses/x.vtt", "source_hash", "h1")
    uv = repo._connect().execute("PRAGMA user_version").fetchone()[0]
    assert uv == 7
    assert repo.get_source_state("vault-one", "sync", "courses/x.vtt", "source_hash") == "h1"
    repo.close()


def test_source_state_overwrite_in_place(tmp_path: Path) -> None:
    """A second `set` updates in place — exactly one row (ON CONFLICT DO UPDATE)."""
    repo = _repo(tmp_path)
    repo.set_source_state("vault-one", "sync", "courses/x.vtt", "source_hash", "first")
    repo.set_source_state("vault-one", "sync", "courses/x.vtt", "source_hash", "second")
    assert repo.get_source_state("vault-one", "sync", "courses/x.vtt", "source_hash") == "second"
    n = repo._connect().execute(
        "SELECT COUNT(*) AS n FROM source_state "
        "WHERE vault_id='vault-one' AND source_kind='sync' AND scope='courses/x.vtt'"
    ).fetchone()["n"]
    assert n == 1
    repo.close()


def test_source_state_multi_vault_isolation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    repo.set_source_state("vault-one", "sync", "a.md", "source_hash", "x")
    assert repo.get_source_state("vault-two", "sync", "a.md", "source_hash") is None
    repo.close()


def test_source_state_partition_isolation(tmp_path: Path) -> None:
    """The generic accessor honours `source_kind` — a `sync` row does not leak
    into the `query` partition (and vice-versa)."""
    repo = _repo(tmp_path)
    repo.set_source_state("vault-one", "sync", "q1", "source_hash", "synchash")
    repo.record_query_state("vault-one", "q1", "queryhash")
    assert repo.get_source_state("vault-one", "sync", "q1", "source_hash") == "synchash"
    assert repo.get_source_state("vault-one", "query", "q1", "question_hash") == "queryhash"
    repo.close()


# ---------------------------------------------------------------------------
# Phase 1 — `.wiki/sync.yaml` loader (beads 03 STUB → 04 LOGIC)
# ---------------------------------------------------------------------------


def test_sync_config_absent_returns_defaults(tmp_path: Path) -> None:
    """No `.wiki/sync.yaml` → built-in defaults (not an error)."""
    cfg = load_sync_config(tmp_path)
    assert isinstance(cfg, SyncConfig)
    assert cfg.tag_namespace == "wiki"
    assert cfg.zones == () and cfg.exclude == ()


def test_sync_config_valid_parses(tmp_path: Path) -> None:
    """A well-formed config round-trips into the dataclass."""
    _write_sync_yaml(tmp_path, (
        "zones:\n  - courses/**\n"
        "exclude:\n  - 'templates/**'\n"
        "tag_namespace: wiki\n"
        "extensions:\n  text:\n    - .log\n  skip:\n    - .tmp\n"
    ))
    cfg = load_sync_config(tmp_path)
    assert cfg.zones == ("courses/**",)
    assert cfg.exclude == ("templates/**",)
    assert cfg.extensions_text == (".log",)
    assert cfg.extensions_skip == (".tmp",)


def test_sync_config_rejects_misspelled_key(tmp_path: Path) -> None:
    """A misspelled top-level key → INVALID_SYNC_CONFIG (strict schema)."""
    _write_sync_yaml(tmp_path, "zonez:\n  - courses/**\n")  # 'zonez' typo
    with pytest.raises(SyncConfigError) as ei:
        load_sync_config(tmp_path)
    assert ei.value.code == "INVALID_SYNC_CONFIG"
    # CWE-209: the error must not echo the offending key/value.
    assert "courses" not in str(ei.value)


def test_safe_load_alone_expands_anchor() -> None:
    """SEC-N3 evidence (strict-TDD RED proof): plain `yaml.safe_load` EXPANDS a
    billion-laughs bomb — it is NOT a defense. This is exactly why the loader
    needs `_NoAliasSafeLoader`."""
    import yaml as _yaml

    bomb = (
        "a: &a [x, x, x, x, x, x, x, x, x]\n"
        "b: &b [*a, *a, *a, *a, *a, *a, *a, *a, *a]\n"
        "c: [*b, *b, *b, *b, *b, *b, *b, *b, *b]\n"
    )
    expanded = _yaml.safe_load(bomb)
    # 9 * 9 = 81 leaf lists under `c`, each a 9-element expansion → proves aliases
    # are followed, not left as references.
    assert len(expanded["c"]) == 9
    assert len(expanded["c"][0]) == 9
    assert expanded["c"][0][0] == ["x"] * 9


def test_sync_config_rejects_yaml_anchor(tmp_path: Path) -> None:
    """A YAML anchor/alias (billion-laughs vector) → refused at compose time."""
    bomb = (
        "zones: &a\n  - x\n"
        "exclude: *a\n"
    )
    _write_sync_yaml(tmp_path, bomb)
    with pytest.raises(SyncConfigError) as ei:
        load_sync_config(tmp_path)
    assert ei.value.code == "INVALID_SYNC_CONFIG"


def test_sync_config_rejects_unused_anchor(tmp_path: Path) -> None:
    """Even an UNUSED anchor definition is refused (defense in depth)."""
    _write_sync_yaml(tmp_path, "zones: &unused\n  - x\n")
    with pytest.raises(SyncConfigError):
        load_sync_config(tmp_path)


def test_sync_config_size_cap(tmp_path: Path) -> None:
    """A `.wiki/sync.yaml` over 256 KiB → refused BEFORE read."""
    big = "zones:\n" + ("  - " + "a" * 64 + "\n") * 5000  # > 256 KiB
    assert len(big.encode("utf-8")) > WIKI_SYNC_CONFIG_MAX_BYTES
    _write_sync_yaml(tmp_path, big)
    with pytest.raises(SyncConfigError) as ei:
        load_sync_config(tmp_path)
    assert ei.value.code == "INVALID_SYNC_CONFIG"


def test_sync_config_rejects_deep_nesting(tmp_path: Path) -> None:
    """A sub-256 KiB but deeply-nested ANCHORLESS payload (the composer-recursion
    DoS the anchor-ban can't touch) → controlled INVALID_SYNC_CONFIG, NOT an
    uncaught RecursionError traceback (critic-security HIGH, SEC-N3 follow-up)."""
    payload = "zones: " + ("[" * 3000)  # ~3 KiB, well under the cap
    assert len(payload.encode("utf-8")) < WIKI_SYNC_CONFIG_MAX_BYTES
    _write_sync_yaml(tmp_path, payload)
    with pytest.raises(SyncConfigError) as ei:
        load_sync_config(tmp_path)
    assert ei.value.code == "INVALID_SYNC_CONFIG"
    # CWE-209: the controlled error must not carry file content / internals.
    assert "[" not in ei.value.detail


# ---------------------------------------------------------------------------
# Phase 2 — classifier (`classify_file`) — beads 05 STUB → 06–09 LOGIC
# ---------------------------------------------------------------------------


def _md(path: Path, frontmatter_block: str | None, body: str) -> Path:
    """Write a markdown file with an optional `---` frontmatter block."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (f"---\n{frontmatter_block}\n---\n{body}" if frontmatter_block is not None
            else body)
    path.write_text(text, encoding="utf-8")
    return path


# --- bead 06: extension routing (case-folded) ---


def test_ext_routing_convert(tmp_path: Path) -> None:
    f = tmp_path / "report.docx"
    f.write_bytes(b"PK\x03\x04docx-bytes")
    d = _classify(f, vault_root=tmp_path)
    assert d.action == "convert+ingest"
    assert d.converter == "docx"
    assert d.staged_target == "_raw/.staging/report-docx.md"


def test_ext_routing_pdf_uppercase(tmp_path: Path) -> None:
    """Case-folded suffix: `.PDF` routes like `.pdf` (AC-3)."""
    f = tmp_path / "Slides.PDF"
    f.write_bytes(b"%PDF-1.7 bytes")
    d = _classify(f, vault_root=tmp_path)
    assert d.action == "convert+ingest" and d.converter == "pdf"
    assert d.staged_target == "_raw/.staging/slides-pdf.md"


def test_ext_routing_vtt_detimestamp(tmp_path: Path) -> None:
    f = tmp_path / "lecture.vtt"
    f.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nhello\n", encoding="utf-8")
    d = _classify(f, vault_root=tmp_path)
    assert d.action == "ingest" and d.normalize == "vtt-detimestamp"


def test_ext_routing_txt_no_normalize(tmp_path: Path) -> None:
    f = tmp_path / "raw.txt"
    f.write_text("plain notes that are reasonably long content here\n", encoding="utf-8")
    d = _classify(f, vault_root=tmp_path)
    assert d.action == "ingest" and d.normalize is None


def test_ext_routing_image_binary(tmp_path: Path) -> None:
    f = tmp_path / "diagram.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert _classify(f, vault_root=tmp_path).reason == "binary"


def test_ext_routing_unknown(tmp_path: Path) -> None:
    f = tmp_path / "data.xyz"
    f.write_text("???\n", encoding="utf-8")
    assert _classify(f, vault_root=tmp_path).reason == "unknown-ext"


def test_ext_routing_excalidraw_and_canvas_skip(tmp_path: Path) -> None:
    ex = _md(tmp_path / "draw.excalidraw.md", None, '{"type":"excalidraw"}')
    cv = tmp_path / "board.canvas"
    cv.write_text('{"nodes":[]}', encoding="utf-8")
    assert _classify(ex, vault_root=tmp_path) == Decision("skip", "excalidraw")
    assert _classify(cv, vault_root=tmp_path) == Decision("skip", "canvas")


def test_ext_routing_zero_byte_empty(tmp_path: Path) -> None:
    f = tmp_path / "empty.docx"
    f.write_bytes(b"")
    assert _classify(f, vault_root=tmp_path).reason == "empty-source"


def test_ext_routing_config_skip_override(tmp_path: Path) -> None:
    f = tmp_path / "scratch.log"
    f.write_text("some long-enough log line to be material content here\n", encoding="utf-8")
    cfg = SyncConfig(extensions_text=(".log",), extensions_skip=(".log",))
    # skip override wins over a text override for the same ext.
    assert _classify(f, vault_root=tmp_path, config=cfg).reason == "config-skip"


# --- bead 07: tag vocabulary + precedence (skip > raw > keep > default) ---


def test_tag_skip_wins_over_raw(tmp_path: Path) -> None:
    f = _md(tmp_path / "d.md", "tags: [wiki/raw, wiki/skip]", "body prose here")
    assert _classify(f, vault_root=tmp_path) == Decision("skip", "wiki/skip")


def test_tag_raw_ingests(tmp_path: Path) -> None:
    f = _md(tmp_path / "d.md", "tags:\n  - wiki/raw", "raw transcript text body")
    assert _classify(f, vault_root=tmp_path).action == "ingest"


def test_tag_wiki_field_skip(tmp_path: Path) -> None:
    f = _md(tmp_path / "d.md", "wiki: skip", "body prose here")
    assert _classify(f, vault_root=tmp_path).reason == "wiki/skip"


def test_tag_inline_body_tag(tmp_path: Path) -> None:
    f = _md(tmp_path / "d.md", "title: x", "intro\n#wiki/raw\nmore body")
    assert _classify(f, vault_root=tmp_path).action == "ingest"


def test_in_raw_dir_is_implicit_raw(tmp_path: Path) -> None:
    f = _md(tmp_path / "_raw" / "t.md", "title: x", "raw body content")
    assert _classify(f, vault_root=tmp_path, in_raw=True).action == "ingest"


def test_keep_rescues_exclude_zone(tmp_path: Path) -> None:
    """A `.md` in an `exclude:` zone is skipped UNLESS it carries `#wiki/keep`."""
    f = _md(tmp_path / "templates" / "t.md", "type: lesson-summary", "real body content")
    assert _classify(f, vault_root=tmp_path, in_exclude_zone=True).reason == "excluded-zone"
    f2 = _md(tmp_path / "templates" / "k.md",
             "type: lesson-summary\ntags: [wiki/keep]", "real body content")
    assert _classify(f2, vault_root=tmp_path, in_exclude_zone=True).action == "upsert"


# --- bead 08: generated-view sidecar + only-a-view guard ---


def test_view_dbfolder_frontmatter_skip(tmp_path: Path) -> None:
    f = _md(tmp_path / "DB.md", "database-plugin: dbfolder", "anything")
    assert _classify(f, vault_root=tmp_path).reason == "view:dbfolder"


def test_view_dbfolder_fenced_skip(tmp_path: Path) -> None:
    f = _md(tmp_path / "DB.md", "title: x", "```yaml:dbfolder\ncolumns: {}\n```")
    assert _classify(f, vault_root=tmp_path).reason == "view:dbfolder"


def test_view_base_fenced_skip(tmp_path: Path) -> None:
    f = _md(tmp_path / "v.md", None, "# Heading\n\n```base\nfilters: []\n```\n")
    assert _classify(f, vault_root=tmp_path).reason == "view:base"


def test_view_dataview_fenced_skip(tmp_path: Path) -> None:
    f = _md(tmp_path / "v.md", None, "```dataview\nLIST FROM #x\n```")
    assert _classify(f, vault_root=tmp_path).reason == "view:dataview"


def test_view_folder_note_thin_skip(tmp_path: Path) -> None:
    f = _md(tmp_path / "Area" / "Area.md", None, "# Area\n\n- [[a]]\n- [[b]]\n")
    assert _classify(f, vault_root=tmp_path).reason == "view:folder-note"


def test_embedded_dataview_content_note_upserts(tmp_path: Path) -> None:
    """AC-2b anti-over-flag: a real note embedding a dataview block alongside
    prose is content → upsert (NOT skipped as a view)."""
    body = (
        "This is a substantial paragraph of real knowledge prose that clearly "
        "exceeds the material-prose threshold and should be indexed.\n\n"
        "```dataview\nLIST FROM #related\n```\n\nMore concluding prose follows here too.\n"
    )
    f = _md(tmp_path / "_sources" / "note.md", "type: lesson-summary", body)
    assert _classify(f, vault_root=tmp_path).action == "upsert"


# --- bead 09: unmappable-type (layout-general, W-1) + degenerate inputs ---


def test_unmappable_type_skips_karpathy(tmp_path: Path) -> None:
    """A type-less prose `.md` that `wiki-index-upsert` would reject → skip
    (NOT a crash) under karpathy."""
    f = _md(tmp_path / "prose.md", "title: Just prose", "a paragraph of real content here")
    assert _classify(f, vault_root=tmp_path).reason == "unmappable-type"


def test_unmappable_type_dev_project_glob(tmp_path: Path) -> None:
    """W-1 layout-general: under dev-project a type-less `adr/*.md` maps via the
    glob-inferred type → upsert (would wrongly skip under a karpathy hardcode).
    dev-project globs are relative to vault_root (= `<repo>/docs`)."""
    f = _md(tmp_path / "adr" / "ADR-001.md", "title: Some Decision", "body content")
    layout = load_layout_config(tmp_path, {"layout": "dev-project"})
    assert _classify(f, vault_root=tmp_path, layout=layout).action == "upsert"
    # ...and the SAME file under karpathy (no adr glob, no type) → unmappable.
    assert _classify(f, vault_root=tmp_path).reason == "unmappable-type"


def test_empty_md_body_skips(tmp_path: Path) -> None:
    f = _md(tmp_path / "blank.md", "title: x", "   \n\n")
    assert _classify(f, vault_root=tmp_path).reason == "empty-source"


def test_unparseable_frontmatter_no_raise(tmp_path: Path) -> None:
    """Malformed frontmatter → treated as no-frontmatter, routed by path, never
    raises (AC-11). The `reason` carries the `frontmatter-unparseable` marker."""
    f = tmp_path / "bad.md"
    f.write_text("---\n: : : not: valid: yaml\n---\nsome body prose content here\n",
                 encoding="utf-8")
    d = _classify(f, vault_root=tmp_path)  # must not raise
    assert d.action == "skip" and "frontmatter-unparseable" in d.reason


# ---------------------------------------------------------------------------
# Phase 3 — own bounded walk (beads 10 STUB → 11 LOGIC)
# ---------------------------------------------------------------------------


def _build_zone(root: Path) -> Path:
    """A heterogeneous zone: `.md`, `.txt`, `.vtt`, `.docx`, a pruned staged
    `.md`, an image, and a `.md` in an `exclude:`-zone (templates/)."""
    (root / "courses").mkdir(parents=True, exist_ok=True)
    (root / "courses" / "note.md").write_text("# n\nbody\n", encoding="utf-8")
    (root / "courses" / "raw.txt").write_text("plain\n", encoding="utf-8")
    (root / "courses" / "lec.vtt").write_text("WEBVTT\n", encoding="utf-8")
    (root / "courses" / "deck.docx").write_bytes(b"PK\x03\x04")
    (root / "courses" / "pic.png").write_bytes(b"\x89PNG")
    (root / "_raw" / ".staging").mkdir(parents=True, exist_ok=True)
    (root / "_raw" / ".staging" / "deck-docx.md").write_text("staged\n", encoding="utf-8")
    (root / "templates").mkdir(parents=True, exist_ok=True)
    (root / "templates" / "tmpl.md").write_text("# t\nbody\n", encoding="utf-8")
    (root / "templates" / "tmpl.vtt").write_text("WEBVTT\n", encoding="utf-8")
    return root


def test_walk_discovers_heterogeneous(tmp_path: Path) -> None:
    """`.md/.txt/.vtt/.docx` are discovered; images + staged outputs are not."""
    zone = _build_zone(tmp_path)
    cands = iter_sync_candidates(zone, vault_root=tmp_path, config=SyncConfig())
    rels = {c.rel for c in cands}
    assert {"courses/note.md", "courses/raw.txt", "courses/lec.vtt",
            "courses/deck.docx"} <= rels
    assert "courses/pic.png" not in rels          # image pruned pre-stat
    assert "_raw/.staging/deck-docx.md" not in rels  # staged output not re-discovered


def test_walk_excludes_staging(tmp_path: Path) -> None:
    _build_zone(tmp_path)
    cands = iter_sync_candidates(tmp_path, vault_root=tmp_path, config=SyncConfig())
    assert not any(".staging/" in c.rel for c in cands)


def test_walk_reads_md_in_exclude_zone(tmp_path: Path) -> None:
    """A `.md` under an `exclude:` zone IS yielded (so `#wiki/keep` can rescue it),
    flagged `in_exclude_zone`; a non-`.md` there is pruned."""
    _build_zone(tmp_path)
    cfg = SyncConfig(exclude=("templates/**",))
    cands = {c.rel: c for c in iter_sync_candidates(tmp_path, vault_root=tmp_path, config=cfg)}
    assert "templates/tmpl.md" in cands
    assert cands["templates/tmpl.md"].in_exclude_zone is True
    assert "templates/tmpl.vtt" not in cands  # non-.md in exclude zone pruned


def test_walk_sets_in_raw(tmp_path: Path) -> None:
    (tmp_path / "_raw").mkdir()
    (tmp_path / "_raw" / "t.txt").write_text("x\n", encoding="utf-8")
    cands = {c.rel: c for c in iter_sync_candidates(tmp_path, vault_root=tmp_path, config=SyncConfig())}
    assert cands["_raw/t.txt"].in_raw is True


def test_walk_one_stat_per_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One `lstat()` per SURVIVING candidate — pruned-by-extension files cost no
    stat (P-2 single-stat discipline)."""
    _build_zone(tmp_path)
    import pathlib
    calls = {"n": 0}
    real = pathlib.Path.lstat

    def _spy(self: Path) -> os.stat_result:
        calls["n"] += 1
        return real(self)

    monkeypatch.setattr(pathlib.Path, "lstat", _spy)
    cands = iter_sync_candidates(tmp_path, vault_root=tmp_path, config=SyncConfig())
    # exactly one lstat per yielded candidate (image/staged were pruned pre-stat).
    assert calls["n"] == len(cands)
    assert len(cands) >= 4


def test_walk_refuses_symlinks(tmp_path: Path) -> None:
    """Symlinked files AND symlinked dirs are refused (O_NOFOLLOW posture)."""
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "a.md").write_text("# a\nbody\n", encoding="utf-8")
    target = tmp_path / "outside.md"
    target.write_text("# evil\nbody\n", encoding="utf-8")
    try:
        (tmp_path / "real" / "link.md").symlink_to(target)
        (tmp_path / "linkdir").symlink_to(tmp_path / "real", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported on this platform")
    rels = {c.rel for c in iter_sync_candidates(tmp_path, vault_root=tmp_path, config=SyncConfig())}
    assert "real/a.md" in rels
    assert "real/link.md" not in rels          # symlinked target file refused
    assert not any(r.startswith("linkdir/") for r in rels)  # symlinked dir not descended


# ---------------------------------------------------------------------------
# Phase 3 — `wiki-sync scan` CLI (beads 12 STUB → 13 LOGIC)
# ---------------------------------------------------------------------------

_VAULT = "sync-test-vault"


def _run_scan(zone: Path, vault_root: Path, db: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.wiki_skills.wiki_sync", "scan", str(zone),
         "--vault", _VAULT, "--vault-root", str(vault_root), "--db-path", str(db), *extra],
        capture_output=True, text=True, check=False,
    )


def test_scan_emits_plan_envelope(tmp_path: Path) -> None:
    """GREEN-on-stub: a valid plan envelope, exit 0, entries == [] (tightened in 13)."""
    vault = tmp_path / "vault"
    (vault / "courses").mkdir(parents=True)
    db = tmp_path / "g.db"
    res = _run_scan(vault / "courses", vault, db)
    assert res.returncode == 0, res.stderr
    plan = json.loads(res.stdout)
    assert plan["vault_id"] == _VAULT
    assert plan["zone"] == "courses"
    assert plan["generated_by"] == "wiki-sync/scan"
    assert plan["entries"] == []
    assert set(plan["summary"]) >= {"total", "convert+ingest", "ingest", "upsert", "skip", "unchanged"}


def test_scan_zone_missing_exit_2(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    db = tmp_path / "g.db"
    res = _run_scan(vault / "nope", vault, db)
    assert res.returncode == 2
    assert json.loads(res.stdout)["error"] == "ZONE_NOT_FOUND"


def test_scan_zone_outside_vault_exit_2(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    db = tmp_path / "g.db"
    res = _run_scan(outside, vault, db)
    assert res.returncode == 2
    assert json.loads(res.stdout)["error"] == "ZONE_OUTSIDE_VAULT"


def test_scan_bad_config_exit_6(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "courses").mkdir(parents=True)
    _write_sync_yaml(vault, "zonez: [x]\n")  # misspelled key → strict-schema reject
    db = tmp_path / "g.db"
    res = _run_scan(vault / "courses", vault, db)
    assert res.returncode == 6
    assert json.loads(res.stdout)["error"] == "INVALID_SYNC_CONFIG"


def test_scan_module_has_no_anthropic_import() -> None:
    """Decision-17: the deterministic CLI carries no LLM-client import."""
    src = (Path(__file__).resolve().parents[1]
           / "scripts" / "wiki_skills" / "wiki_sync.py").read_text(encoding="utf-8")
    assert "import anthropic" not in src
    assert "from anthropic" not in src


def _plan_zone(vault: Path) -> Path:
    """A zone exercising every classify route."""
    z = vault / "courses"
    z.mkdir(parents=True)
    (z / "deck.docx").write_bytes(b"PK\x03\x04deck")
    (z / "lec.vtt").write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhi\n", encoding="utf-8")
    _md(z / "ready.md", "type: lesson-summary", "a real summary body with content here")
    _md(z / "draft.md", "tags: [wiki/skip]", "draft body")
    _md(z / "db.md", "database-plugin: dbfolder", "anything")
    _md(z / "prose.md", "title: just prose", "a paragraph of real content here too")
    return z


def _register_vault(db: Path, vault: Path) -> None:
    repo = SQLiteRepository(db)
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id=_VAULT, name=_VAULT, root_path=vault,
        schema_version="5.0", registered_at=datetime(2026, 6, 3),
    ))
    repo.close()


def test_scan_plan_matrix(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    z = _plan_zone(vault)
    db = tmp_path / "g.db"
    _register_vault(db, vault)
    res = _run_scan(z, vault, db)
    assert res.returncode == 0, res.stderr
    by_path = {e["path"]: e for e in json.loads(res.stdout)["entries"]}
    assert by_path["courses/deck.docx"]["action"] == "convert+ingest"
    assert by_path["courses/deck.docx"]["staged_target"] == "_raw/.staging/deck-docx.md"
    assert by_path["courses/lec.vtt"]["action"] == "ingest"
    assert by_path["courses/lec.vtt"]["normalize"] == "vtt-detimestamp"
    assert by_path["courses/ready.md"]["action"] == "upsert"
    assert by_path["courses/draft.md"] == {**by_path["courses/draft.md"],
                                           "action": "skip", "reason": "wiki/skip"}
    assert by_path["courses/db.md"]["reason"] == "view:dbfolder"
    assert by_path["courses/prose.md"]["reason"] == "unmappable-type"
    # actionable entries carry a 64-hex source_hash; skips carry null.
    assert len(by_path["courses/ready.md"]["source_hash"]) == 64
    assert by_path["courses/db.md"]["source_hash"] is None
    # entries are sorted by vault-relative POSIX path (determinism).
    paths = [e["path"] for e in json.loads(res.stdout)["entries"]]
    assert paths == sorted(paths)


def test_scan_deterministic(tmp_path: Path) -> None:
    """AC-10: two scans of an untouched zone are byte-identical."""
    vault = tmp_path / "vault"
    z = _plan_zone(vault)
    db = tmp_path / "g.db"
    _register_vault(db, vault)
    a = _run_scan(z, vault, db)
    b = _run_scan(z, vault, db)
    assert a.returncode == 0 and b.returncode == 0
    assert a.stdout == b.stdout


def test_scan_dry_run_writes_nothing(tmp_path: Path) -> None:
    """AC-6: --dry-run mutates neither the vault tree nor the DB."""
    vault = tmp_path / "vault"
    z = _plan_zone(vault)
    db = tmp_path / "g.db"
    _register_vault(db, vault)
    before_tree = sorted(p.name for p in vault.rglob("*"))
    before_db = db.stat().st_size
    res = _run_scan(z, vault, db, "--dry-run")
    assert res.returncode == 0, res.stderr
    assert sorted(p.name for p in vault.rglob("*")) == before_tree
    assert db.stat().st_size == before_db
    assert "_raw" not in [p.name for p in vault.iterdir()]


def test_scan_reports_skips(tmp_path: Path) -> None:
    """AC-13: the --dry-run report lists every skip + its reason."""
    vault = tmp_path / "vault"
    z = _plan_zone(vault)
    db = tmp_path / "g.db"
    _register_vault(db, vault)
    res = _run_scan(z, vault, db, "--dry-run")
    assert res.returncode == 0
    assert "wiki/skip" in res.stdout
    assert "view:dbfolder" in res.stdout
    assert "unmappable-type" in res.stdout


def test_scan_is_unchanged(tmp_path: Path) -> None:
    """AC-5/AC-8: after a recorded `sync` source_state row, the matching entry is
    `is_unchanged:true` (the executor's commit-marker → re-run no-op)."""
    vault = tmp_path / "vault"
    z = _plan_zone(vault)
    db = tmp_path / "g.db"
    _register_vault(db, vault)
    first = json.loads(_run_scan(z, vault, db).stdout)
    ready = next(e for e in first["entries"] if e["path"] == "courses/ready.md")
    assert ready["is_unchanged"] is False
    # simulate the executor's commit marker
    repo = SQLiteRepository(db)
    repo.set_source_state(_VAULT, "sync", "courses/ready.md", "source_hash",
                          ready["source_hash"])
    repo.close()
    second = json.loads(_run_scan(z, vault, db).stdout)
    ready2 = next(e for e in second["entries"] if e["path"] == "courses/ready.md")
    assert ready2["is_unchanged"] is True
    assert second["summary"]["unchanged"] >= 1


def _run_record(rel: str, source_hash: str, db: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.wiki_skills.wiki_sync", "record", rel,
         "--source-hash", source_hash, "--vault", _VAULT, "--db-path", str(db), *extra],
        capture_output=True, text=True, check=False,
    )


def test_record_then_scan_is_unchanged(tmp_path: Path) -> None:
    """The executor commit-marker CLI (`record`) → next scan reads `is_unchanged`."""
    vault = tmp_path / "vault"
    z = _plan_zone(vault)
    db = tmp_path / "g.db"
    _register_vault(db, vault)
    first = json.loads(_run_scan(z, vault, db).stdout)
    ready = next(e for e in first["entries"] if e["path"] == "courses/ready.md")
    rec = _run_record("courses/ready.md", ready["source_hash"], db)
    assert rec.returncode == 0, rec.stderr
    assert json.loads(rec.stdout)["status"] == "recorded"
    second = json.loads(_run_scan(z, vault, db).stdout)
    assert next(e for e in second["entries"] if e["path"] == "courses/ready.md")["is_unchanged"] is True


def test_record_bad_hash_exit_2(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    _register_vault(db, tmp_path / "vault")
    rec = _run_record("courses/ready.md", "NOTAHASH", db)
    assert rec.returncode == 2
    assert json.loads(rec.stdout)["error"] == "INVALID_HASH"


def test_record_path_traversal_rejected(tmp_path: Path) -> None:
    db = tmp_path / "g.db"
    _register_vault(db, tmp_path / "vault")
    rec = _run_record("../../etc/passwd", "a" * 64, db)
    assert rec.returncode == 2
    assert json.loads(rec.stdout)["error"] == "INVALID_PATH"


# ---------------------------------------------------------------------------
# Adversarial-review regressions (critic-logic, Phase-3 gate)
# ---------------------------------------------------------------------------


def test_classify_type_as_list_no_crash(tmp_path: Path) -> None:
    """HIGH: a malformed `type:` (YAML list → unhashable `in` test) must NOT
    crash the classifier — it degrades to skip (AC-11)."""
    f = _md(tmp_path / "bad.md", "type: [a, b]", "a paragraph of real prose content here")
    d = _classify(f, vault_root=tmp_path)  # must not raise
    assert d.action == "skip" and d.reason == "unmappable-type"


def test_classify_tags_scalar_no_crash(tmp_path: Path) -> None:
    """HIGH: a non-iterable `tags:` with an otherwise-mappable `type:` must NOT
    crash (`list(5)` TypeError inside normalize_frontmatter)."""
    f = _md(tmp_path / "bad.md", "type: lesson-summary\ntags: 5", "real prose body content here")
    d = _classify(f, vault_root=tmp_path)  # must not raise
    assert d.action == "skip"


def test_inline_tag_inside_fence_not_routed(tmp_path: Path) -> None:
    """LOW: a `#wiki/skip` mentioned inside a fenced code example must NOT route
    the note to skip (over-flag / data loss)."""
    body = (
        "A real knowledge note documenting the sync tag vocabulary.\n\n"
        "```\n#wiki/skip\n```\n\nMore real prose after the example block.\n"
    )
    f = _md(tmp_path / "_sources" / "howto.md", "type: lesson-summary", body)
    assert _classify(f, vault_root=tmp_path).action == "upsert"


def test_terse_folder_note_with_prose_not_overflagged(tmp_path: Path) -> None:
    """LOW: a terse-but-real folder-note (one short sentence) is NOT skipped as a
    view — its prose keeps it as content."""
    f = _md(tmp_path / "Area" / "Area.md", "type: lesson-summary",
            "# Area\n\nNotes about my reading this year.\n")
    assert _classify(f, vault_root=tmp_path).action == "upsert"


def test_none_hash_never_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """MED: a file that fails to hash (None) must NOT read as is_unchanged — a
    `None == None` coincidence would silently skip actionable content."""
    from scripts.wiki_skills import wiki_sync as ws
    vault = tmp_path / "vault"
    z = _plan_zone(vault)
    db = tmp_path / "g.db"
    _register_vault(db, vault)
    repo = SQLiteRepository(db)
    layout = resolve_layout_config(vault)
    monkeypatch.setattr(ws, "_hash_file", lambda _p: None)
    entries = ws._build_entries(repo, _VAULT, z, vault, SyncConfig(), layout)
    repo.close()
    for e in entries:
        if e["action"] != "skip":
            assert e["source_hash"] is None
            assert e["is_unchanged"] is False


# ---------------------------------------------------------------------------
# /vdd-multi convergence regressions (final full-surface gate)
# ---------------------------------------------------------------------------


def test_md_oversize_skips_without_read(tmp_path: Path) -> None:
    """F1 (security MED): a `.md` over the cap is skipped (never slurped into RAM)
    → bounds the only unbounded-read lever in scan."""
    from scripts.wiki_skills._sync import WIKI_SYNC_MD_MAX_BYTES
    f = tmp_path / "huge.md"
    f.write_text("---\ntype: lesson-summary\n---\n" + ("x" * (WIKI_SYNC_MD_MAX_BYTES + 1024)),
                 encoding="utf-8")
    assert f.stat().st_size > WIKI_SYNC_MD_MAX_BYTES
    assert _classify(f, vault_root=tmp_path).reason == "oversize-source"


def test_bom_prefixed_md_upserts(tmp_path: Path) -> None:
    """F2 (logic MED): a UTF-8-BOM-prefixed note with a valid `type:` must upsert
    (the indexer strips the BOM; the classifier must agree — W-1 fidelity)."""
    f = tmp_path / "_sources" / "win.md"
    f.parent.mkdir(parents=True)
    f.write_text("﻿---\ntype: lesson-summary\n---\nReal summary body content here.\n",
                 encoding="utf-8")
    assert _classify(f, vault_root=tmp_path).action == "upsert"


def test_record_unregistered_vault_exit_2(tmp_path: Path) -> None:
    """F3 (logic MED): `record` against a schema-only DB with no registered vault
    → exit 2 VAULT_NOT_REGISTERED (the FK-miss branch)."""
    db = tmp_path / "g.db"
    repo = SQLiteRepository(db)
    repo.apply_schema()   # schema present, but NO vault registered
    repo.close()
    rec = _run_record("courses/x.md", "a" * 64, db)
    assert rec.returncode == 2
    assert json.loads(rec.stdout)["error"] == "VAULT_NOT_REGISTERED"


def test_is_clean_rel_rejects_dirty_paths() -> None:
    """F4 (security LOW): the `record` scope key must be canonical."""
    from scripts.wiki_skills.wiki_sync import _is_clean_rel
    assert _is_clean_rel("courses/note.md") is True
    assert _is_clean_rel("courses/My Note.md") is True   # spaces OK
    for bad in ("", "/abs.md", "a/../b", "a/./b", "trailing/", "a\\b.md",
                "a\x00b.md", "a\tb.md", "."):
        assert _is_clean_rel(bad) is False, bad


def test_sync_config_rejects_symlink(tmp_path: Path) -> None:
    """F5 (security LOW): a symlinked `.wiki/sync.yaml` is refused (O_NOFOLLOW)."""
    target = tmp_path / "real-config.yaml"
    target.write_text("zones: [x]\n", encoding="utf-8")
    (tmp_path / ".wiki").mkdir()
    try:
        (tmp_path / ".wiki" / "sync.yaml").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported on this platform")
    with pytest.raises(SyncConfigError) as ei:
        load_sync_config(tmp_path)
    assert ei.value.code == "INVALID_SYNC_CONFIG"


def test_sync_config_rejects_parent_symlink(tmp_path: Path) -> None:
    """F5-complete (security MED iter-2): a symlinked PARENT `.wiki/` dir pointing
    out-of-vault must be refused — full-path containment, not just the leaf."""
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside-wiki"
    outside.mkdir()
    (outside / "sync.yaml").write_text("zones: [x]\n", encoding="utf-8")
    try:
        (vault / ".wiki").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unsupported on this platform")
    # leaf is NOT a symlink (it's a real file inside the symlinked dir) — the
    # parent-chain containment check is what must catch this.
    assert not (vault / ".wiki" / "sync.yaml").is_symlink()
    with pytest.raises(SyncConfigError) as ei:
        load_sync_config(vault)
    assert ei.value.code == "INVALID_SYNC_CONFIG"


def test_classify_system_files_skip(tmp_path: Path) -> None:
    """Vault system files — per-vendor agent instructions (CLAUDE.md/GEMINI.md),
    the schema, and projections (index.md/log.md) — are skipped by wiki-sync,
    consistent with the indexer (so a `scan .` never upserts them)."""
    for name in ("CLAUDE.md", "GEMINI.md", "WIKI_SCHEMA.md", "index.md", "log.md"):
        f = _md(tmp_path / name, "type: lesson-summary", "real body content here")
        d = _classify(f, vault_root=tmp_path)
        assert d.action == "skip" and d.reason == "system-file", name


def test_view_in_exclude_zone_skips(tmp_path: Path) -> None:
    """L3 (documented): a view sidecar inside an `exclude:` zone still skips; the
    exclude gate wins the reason over the view marker (both → skip, no action
    difference). Locks the current ordering."""
    f = _md(tmp_path / "templates" / "DB.md", "database-plugin: dbfolder", "x")
    d = _classify(f, vault_root=tmp_path, in_exclude_zone=True)
    assert d.action == "skip" and d.reason == "excluded-zone"


# --------------------------------------------------------------------------- #
# TASK 023 — transcript FORMAT dedup (transcript_variant_skips)
# --------------------------------------------------------------------------- #

def _cand(rel: str) -> Candidate:
    return Candidate(path=Path("/v") / rel, rel=rel, mtime=0.0,
                     in_raw=False, in_exclude_zone=False)


def test_dedup_before_first_dot_youtube_captions() -> None:
    """YouTube-id captions: `.txt` wins; all `.vtt` variants (incl .ru-orig/.en)
    demote to skip, keyed by the id before the first dot."""
    cands = [_cand("t/ID.ru.txt"), _cand("t/ID.ru.vtt"),
             _cand("t/ID.ru-orig.vtt"), _cand("t/ID.en.vtt")]
    skips = transcript_variant_skips(cands, identity_mode="before-first-dot")
    assert skips == {
        "t/ID.ru.vtt": ".txt", "t/ID.ru-orig.vtt": ".txt", "t/ID.en.vtt": ".txt"}


def test_dedup_stem_same_stem_only() -> None:
    """'stem' groups only an exact same-stem .vtt with its .txt; the -orig/.en
    variants have a DIFFERENT stem so they are NOT grouped (kept)."""
    cands = [_cand("t/ID.ru.txt"), _cand("t/ID.ru.vtt"),
             _cand("t/ID.ru-orig.vtt"), _cand("t/ID.en.vtt")]
    assert transcript_variant_skips(cands, identity_mode="stem") == {
        "t/ID.ru.vtt": ".txt"}


def test_dedup_lone_caption_kept() -> None:
    """A lone caption with no higher-preference sibling is KEPT (still ingested)."""
    cands = [_cand("a/X.ru-orig.vtt"), _cand("b/Y.ru-orig.vtt")]
    assert transcript_variant_skips(cands, identity_mode="before-first-dot") == {}


def test_dedup_same_best_rank_ties_kept() -> None:
    """Two files at the same best rank (two .txt) are BOTH kept — no data loss
    from a wrong grouping; only a STRICTLY higher-preference format demotes."""
    cands = [_cand("t/A.ru.txt"), _cand("t/A.en.txt")]
    assert transcript_variant_skips(cands, identity_mode="before-first-dot") == {}


def test_dedup_per_directory_grouping() -> None:
    """Same identity in DIFFERENT directories is NOT cross-grouped."""
    cands = [_cand("c1/ID.ru.txt"), _cand("c2/ID.ru.vtt")]
    assert transcript_variant_skips(cands, identity_mode="before-first-dot") == {}


def test_dedup_ignores_non_prefer_ext() -> None:
    """Files whose suffix is not in prefer_ext (.md, .pdf) are never deduped."""
    cands = [_cand("t/ID.ru.txt"), _cand("t/ID.md"), _cand("t/ID.pdf")]
    assert transcript_variant_skips(cands, identity_mode="before-first-dot") == {}


def test_dedup_config_parses_and_defaults(tmp_path: Path) -> None:
    """`transcript_dedup` parses; absence ≡ None (disabled, back-compat)."""
    assert load_sync_config(tmp_path).transcript_dedup is None  # no .wiki/sync.yaml
    wiki = tmp_path / ".wiki"; wiki.mkdir()
    (wiki / "sync.yaml").write_text(
        "transcript_dedup:\n  enabled: true\n  identity: before-first-dot\n"
        "  prefer_ext: ['.txt', '.vtt']\n", encoding="utf-8")
    td = load_sync_config(tmp_path).transcript_dedup
    assert td == TranscriptDedupConfig(
        enabled=True, prefer_ext=(".txt", ".vtt"), identity="before-first-dot")


def test_dedup_config_rejects_bad_identity(tmp_path: Path) -> None:
    """A non-enum `identity` → INVALID_SYNC_CONFIG (strict schema), never a crash."""
    wiki = tmp_path / ".wiki"; wiki.mkdir()
    (wiki / "sync.yaml").write_text(
        "transcript_dedup:\n  enabled: true\n  identity: bogus\n", encoding="utf-8")
    with pytest.raises(SyncConfigError):
        load_sync_config(tmp_path)
