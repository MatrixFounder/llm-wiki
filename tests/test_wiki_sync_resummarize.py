"""TASK 019 — `wiki-sync` re-summarization policy (skip-if-summarized + `--force`
+ per-folder rule overrides). Built bead-by-bead under Stub-First / strict-TDD
(`docs/PLAN.md`):

- bead 00: anchor + **back-compat byte-identity** lock (AC-7).
- beads 01–02: `$def Resummarize` schema + `SyncConfig.resummarize` + loader parse.
- beads 03–04: `_resummarize.py` surface + per-folder cascade resolver.
- beads 05–07: D2a provenance DAL, gate (D1∪D2a + mode), D2b mirror + ReDoS.
- bead 08: `--force` CLI + report + workflow `sources:` writeback.

End-to-end acceptance over `samples/Demand-generation` lives in
`tests/test_wiki_sync_resummarize_e2e.py` (bead 09).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from scripts.wiki_index.layout_config import resolve_layout_config
from scripts.wiki_index.models import Page, Vault
from scripts.wiki_index.sqlite_repository import SQLiteRepository
import pytest

from scripts.wiki_index.sync_config import (
    DetectConfig,
    ProvenanceConfig,
    ResummarizeConfig,
    SyncConfigError,
    load_sync_config,
)
from scripts.wiki_index.sync_config import MirrorConfig, MirrorKey
from scripts.wiki_skills._resummarize import (
    Caches,
    _mirror_match,
    apply_policy,
    resolve_policy,
    summary_exists,
)
from scripts.wiki_skills._sync import Decision
from scripts.wiki_skills.wiki_sync import _build_entries, _build_parser


def _write_sync_yaml(vault_root: Path, text: str) -> None:
    _folder_yaml(vault_root, text)


def _folder_yaml(d: Path, text: str) -> None:
    (d / ".wiki").mkdir(parents=True, exist_ok=True)
    (d / ".wiki" / "sync.yaml").write_text(text, encoding="utf-8")


_VALID_RESUMMARIZE = (
    "resummarize:\n"
    "  mode: if-missing\n"
    "  detect:\n"
    "    source_state: true\n"
    "    provenance_ref:\n"
    "      enabled: true\n"
    "      fields: [source, sources]\n"
    "    mirror:\n"
    "      enabled: true\n"
    "      raw_dirs: [Transcripts]\n"
    "      summary_dir: Summary\n"
    "      match: group-key\n"
    "      key:\n"
    "        raw_regex: '^(?P<lesson>\\d+)'\n"
    "        summary_regex: '^(?P<lesson>\\d+)'\n"
    "        template: '${lesson}'\n"
    "        flags: [ignorecase]\n"
)


def _repo(tmp_path: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    repo.register_vault(Vault(
        vault_id="demand-gen", name="demand-gen", root_path=tmp_path,
        schema_version="5.0", registered_at=datetime(2026, 6, 7),
    ))
    return repo


def _entries(tmp_path: Path, repo: SQLiteRepository) -> dict[str, dict]:
    zone = tmp_path / "zone"
    config = load_sync_config(tmp_path)
    layout = resolve_layout_config(tmp_path)
    return {e["path"]: e for e in
            _build_entries(repo, "demand-gen", zone, tmp_path, config, layout)}


def test_anchor_collects() -> None:
    assert True


def test_backcompat_byte_identity_no_resummarize(tmp_path: Path) -> None:
    """AC-7 LOCK: with NO `resummarize:` block, a raw source keeps its TASK 018
    action/reason. The re-summarization gate (added in bead 06) is a *no-op* when
    no policy is configured — re-run this test after beads 02/06/07."""
    repo = _repo(tmp_path)
    zone = tmp_path / "zone"
    zone.mkdir()
    (zone / "lec.txt").write_text("transcript body", encoding="utf-8")

    by_path = _entries(tmp_path, repo)
    # A raw text source is the gate's only target — it MUST stay `ingest` when
    # there is no `resummarize:` block (back-compat / byte-identity).
    assert by_path["zone/lec.txt"]["action"] == "ingest"
    assert by_path["zone/lec.txt"]["reason"] == "text-source"
    assert by_path["zone/lec.txt"]["is_unchanged"] is False


# ---------------------------------------------------------------------------
# Phase 1 — schema + loader (beads 01 STUB → 02 LOGIC)
# ---------------------------------------------------------------------------


def test_resummarize_absent_is_none(tmp_path: Path) -> None:
    """No `resummarize:` block → `SyncConfig.resummarize is None` (back-compat)."""
    assert load_sync_config(tmp_path).resummarize is None


def test_resummarize_valid_block_validates(tmp_path: Path) -> None:
    """A full, valid `resummarize:` block passes strict schema validation."""
    _write_sync_yaml(tmp_path, _VALID_RESUMMARIZE)
    load_sync_config(tmp_path)  # must not raise


def test_resummarize_unknown_key_rejected(tmp_path: Path) -> None:
    """A misspelled key under `resummarize` → INVALID_SYNC_CONFIG (strict)."""
    _write_sync_yaml(tmp_path, "resummarize:\n  modee: always\n")
    with pytest.raises(SyncConfigError) as exc:
        load_sync_config(tmp_path)
    assert exc.value.code == "INVALID_SYNC_CONFIG"
    assert "modee" not in str(exc.value)  # value never echoed (CWE-209/117)


def test_resummarize_omitted_detect_defaults_source_state(tmp_path: Path) -> None:
    """OQ-5: a block with no `detect:` → `{source_state: True}` only (D2a/D2b off)."""
    _write_sync_yaml(tmp_path, "resummarize:\n  mode: always\n")
    r = load_sync_config(tmp_path).resummarize
    assert r is not None and r.mode == "always"
    assert r.detect.source_state is True
    assert r.detect.provenance_ref.enabled is False
    assert r.detect.mirror.enabled is False


def test_resummarize_full_block_roundtrips(tmp_path: Path) -> None:
    """Full block → typed, frozen dataclasses with the right values."""
    _write_sync_yaml(tmp_path, _VALID_RESUMMARIZE)
    r = load_sync_config(tmp_path).resummarize
    assert r is not None and r.mode == "if-missing"
    assert r.detect.provenance_ref.enabled is True
    assert r.detect.provenance_ref.fields == ("source", "sources")
    m = r.detect.mirror
    assert m.enabled is True and m.raw_dirs == ("Transcripts",)
    assert m.summary_dir == "Summary" and m.match == "group-key"
    assert m.summary_ext == ".md"  # default applied
    assert m.key is not None and m.key.template == "${lesson}"
    assert m.key.flags == ("ignorecase",)


def test_resummarize_bad_mode_rejected(tmp_path: Path) -> None:
    """An out-of-enum `mode` → INVALID_SYNC_CONFIG (strict)."""
    _write_sync_yaml(tmp_path, "resummarize:\n  mode: sometimes\n")
    with pytest.raises(SyncConfigError):
        load_sync_config(tmp_path)


def test_resummarize_group_key_shorthand_defaults_match(tmp_path: Path) -> None:
    """`group_key` shorthand with no explicit `match` → match defaults to group-key."""
    _write_sync_yaml(
        tmp_path,
        "resummarize:\n  detect:\n    mirror:\n      enabled: true\n"
        "      group_key: '^(\\d+)'\n",
    )
    r = load_sync_config(tmp_path).resummarize
    assert r is not None and r.detect.mirror.match == "group-key"
    assert r.detect.mirror.group_key == "^(\\d+)"


# ---------------------------------------------------------------------------
# Phase 2 — `_resummarize.py` surface (bead 03) + cascade resolver (bead 04)
# ---------------------------------------------------------------------------


def test_resolve_policy_none_when_no_block(tmp_path: Path) -> None:
    p = tmp_path / "Module-01" / "Transcripts" / "x.txt"
    assert resolve_policy(p, vault_root=tmp_path) is None


def test_resolve_policy_cascade_deepest_wins_partial(tmp_path: Path) -> None:
    """AC-5 + partial override: folder `mode` wins; folder INHERITS root `detect`."""
    _write_sync_yaml(
        tmp_path,
        "resummarize:\n  mode: if-missing\n  detect:\n"
        "    provenance_ref:\n      enabled: true\n",
    )
    mod = tmp_path / "Module-01"
    mod.mkdir()
    _folder_yaml(mod, "resummarize:\n  mode: always\n")  # only `mode`

    pol = resolve_policy(mod / "Transcripts" / "02-1.txt", vault_root=tmp_path)
    assert pol is not None and pol.mode == "always"               # folder wins
    assert pol.detect.provenance_ref.enabled is True              # inherited (partial merge)

    other = resolve_policy(tmp_path / "Module-02" / "x.txt", vault_root=tmp_path)
    assert other is not None and other.mode == "if-missing"       # root only


def test_resolve_policy_divergent_regex_per_folder(tmp_path: Path) -> None:
    """AC-5: Module-NN uses `^(\\d+)`, Lessons uses `^(\\d{8})` (date)."""
    _write_sync_yaml(tmp_path, "resummarize:\n  mode: if-missing\n")
    (tmp_path / "Module-01").mkdir()
    _folder_yaml(tmp_path / "Module-01",
                 "resummarize:\n  detect:\n    mirror:\n      enabled: true\n"
                 "      group_key: '^(\\d+)'\n")
    (tmp_path / "Lessons").mkdir()
    _folder_yaml(tmp_path / "Lessons",
                 "resummarize:\n  detect:\n    mirror:\n      enabled: true\n"
                 "      group_key: '^(\\d{8})'\n")
    m = resolve_policy(tmp_path / "Module-01" / "Transcripts" / "02-1.txt", vault_root=tmp_path)
    le = resolve_policy(tmp_path / "Lessons" / "Transcripts" / "20260326-01.txt", vault_root=tmp_path)
    assert m is not None and m.detect.mirror.group_key == "^(\\d+)"
    assert le is not None and le.detect.mirror.group_key == "^(\\d{8})"


def test_resolve_policy_cache_memoizes(tmp_path: Path) -> None:
    """AC-10: two files in the same dir tree → one read per dir (order-independent)."""
    _write_sync_yaml(tmp_path, "resummarize:\n  mode: always\n")
    (tmp_path / "a").mkdir()
    caches = Caches()
    resolve_policy(tmp_path / "a" / "x.txt", vault_root=tmp_path, caches=caches)
    n1 = len(caches.raw)
    resolve_policy(tmp_path / "a" / "y.txt", vault_root=tmp_path, caches=caches)
    assert len(caches.raw) == n1  # same dirs → no new reads
    assert (tmp_path / "a") in caches.resolved  # resolved policy memoized per parent


def test_resolve_policy_symlinked_parent_refused(tmp_path: Path) -> None:
    """Security: a symlinked `<folder>/.wiki` escaping the folder → SyncConfigError."""
    evil = tmp_path.parent / "evil-wiki-019"
    evil.mkdir(exist_ok=True)
    (evil / "sync.yaml").write_text("resummarize:\n  mode: never\n", encoding="utf-8")
    mod = tmp_path / "Module-01"
    mod.mkdir()
    try:
        (mod / ".wiki").symlink_to(evil, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not supported here")
    try:
        with pytest.raises(SyncConfigError):
            resolve_policy(mod / "x.txt", vault_root=tmp_path)
    finally:
        (evil / "sync.yaml").unlink()
        evil.rmdir()


def test_apply_policy_stub_noop(tmp_path: Path) -> None:
    """Bead 03 stub + bead 06 back-compat: `policy=None` → gate is a no-op."""
    repo = _repo(tmp_path)
    d = Decision("ingest", "text-source")
    out = apply_policy(
        d, path=tmp_path / "x.txt", rel="x.txt", vault_root=tmp_path,
        repo=repo, vault_id="demand-gen", policy=None, force=False,
    )
    assert out is d


# ---------------------------------------------------------------------------
# Phase 3 — D2a provenance DAL (bead 05)
# ---------------------------------------------------------------------------


def _upsert_page(repo: SQLiteRepository, vault_id: str, slug: str, fm: dict) -> None:
    repo.upsert_page(Page(
        vault_id=vault_id, slug=slug, project="_vault_", type="summary",
        title=slug, file_path=f"Summary/{slug}.md", date=None,
        last_modified=datetime(2026, 6, 7), file_hash="h-" + slug,
        frontmatter_json=fm, body_excerpt="", tags=[],
    ))


def _repo2(tmp_path: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "g.db")
    repo.apply_schema()
    for vid in ("demand-gen", "other-vault"):
        repo.register_vault(Vault(
            vault_id=vid, name=vid, root_path=tmp_path / vid,
            schema_version="5.0", registered_at=datetime(2026, 6, 7),
        ))
    return repo


def test_d2a_scalar_source(tmp_path: Path) -> None:
    repo = _repo2(tmp_path)
    _upsert_page(repo, "demand-gen", "lec-02", {"source": "_raw/x.txt"})
    assert repo.find_pages_citing_source(
        "demand-gen", "_raw/x.txt", ("source", "sources")) == ["lec-02"]


def test_d2a_list_sources_n_to_1(tmp_path: Path) -> None:
    repo = _repo2(tmp_path)
    _upsert_page(repo, "demand-gen", "lec-02",
                 {"sources": ["t/02-1.txt", "t/02-2.txt"]})
    assert repo.find_pages_citing_source(
        "demand-gen", "t/02-1.txt", ("source", "sources")) == ["lec-02"]
    assert repo.find_pages_citing_source(
        "demand-gen", "t/02-2.txt", ("source", "sources")) == ["lec-02"]


def test_d2a_negative(tmp_path: Path) -> None:
    repo = _repo2(tmp_path)
    _upsert_page(repo, "demand-gen", "lec-02", {"source": "_raw/other.txt"})
    assert repo.find_pages_citing_source(
        "demand-gen", "_raw/x.txt", ("source", "sources")) == []


def test_d2a_vault_scoped(tmp_path: Path) -> None:
    repo = _repo2(tmp_path)
    _upsert_page(repo, "other-vault", "lec-02", {"source": "_raw/x.txt"})
    assert repo.find_pages_citing_source(
        "demand-gen", "_raw/x.txt", ("source", "sources")) == []


def test_d2a_injection_safe(tmp_path: Path) -> None:
    repo = _repo2(tmp_path)
    _upsert_page(repo, "demand-gen", "lec-02", {"source": "_raw/x.txt"})
    crafted = "_raw/x.txt' OR '1'='1"
    assert repo.find_pages_citing_source(
        "demand-gen", crafted, ("source", "sources")) == []  # bound → literal, no injection


def test_d2a_bad_field_skipped(tmp_path: Path) -> None:
    repo = _repo2(tmp_path)
    _upsert_page(repo, "demand-gen", "lec-02", {"source": "_raw/x.txt"})
    # a non-allowlisted field is skipped, never raises
    assert repo.find_pages_citing_source(
        "demand-gen", "_raw/x.txt", ("Bad Field", "source")) == ["lec-02"]


def test_all_cited_sources_set(tmp_path: Path) -> None:
    """The hoisted citation set (perf fix) captures scalar + list values, vault-scoped."""
    repo = _repo2(tmp_path)
    _upsert_page(repo, "demand-gen", "a", {"source": "t/01.txt"})
    _upsert_page(repo, "demand-gen", "b", {"sources": ["t/02-1.txt", "t/02-2.txt"]})
    _upsert_page(repo, "other-vault", "c", {"source": "t/99.txt"})
    got = repo.all_cited_sources("demand-gen", ("source", "sources"))
    assert got == {"t/01.txt", "t/02-1.txt", "t/02-2.txt"}  # other-vault excluded


def test_all_cited_sources_structured_objects(tmp_path: Path) -> None:
    """TASK 023 — a `sources:` element may be a STRUCTURED OBJECT
    (`generate-detailed-meeting-summary` emits ``{id, url, file}``), not a bare
    path string. all_cited_sources must harvest the scalar string members so a
    basename match on `file:` (the transcript basename) links the summary to its
    raw. Mixed string + object lists and a scalar string field must still work."""
    repo = _repo2(tmp_path)
    _upsert_page(repo, "demand-gen", "lec-01", {"sources": [
        {"id": "059RZHWA5Qg", "url": "https://youtu.be/059RZHWA5Qg",
         "file": "059RZHWA5Qg.ru.txt"},
    ]})
    _upsert_page(repo, "demand-gen", "lec-02", {"sources": [
        "t/plain.txt",  # legacy bare-string element alongside an object
        {"file": "t/structured.txt"},
    ]})
    got = repo.all_cited_sources("demand-gen", ("source", "sources"))
    # every scalar string member harvested (all describe the same source)
    assert "059RZHWA5Qg.ru.txt" in got
    assert "059RZHWA5Qg" in got
    assert "https://youtu.be/059RZHWA5Qg" in got
    assert "t/plain.txt" in got and "t/structured.txt" in got
    # basename projection (provenance_ref.match=basename) finds the transcript
    from pathlib import PurePosixPath
    basenames = {PurePosixPath(x).name for x in got}
    assert "059RZHWA5Qg.ru.txt" in basenames


# ---------------------------------------------------------------------------
# Phase 3 — the gate (bead 06): D1 ∪ D2a + mode + monotonicity
# ---------------------------------------------------------------------------

_IF_MISSING_D1 = ResummarizeConfig(mode="if-missing", detect=DetectConfig(source_state=True))
_IF_MISSING_D2A = ResummarizeConfig(
    mode="if-missing",
    detect=DetectConfig(source_state=False,
                        provenance_ref=ProvenanceConfig(enabled=True)),
)


def _gate(repo, d, policy, *, rel="zone/lec.txt", force=False):
    return apply_policy(
        d, path=Path("/x.txt"), rel=rel, vault_root=Path("/"),
        repo=repo, vault_id="demand-gen", policy=policy, force=force,
    )


def test_gate_monotonic_upsert_untouched(tmp_path: Path) -> None:
    """The gate NEVER touches `upsert`/`skip` — only `ingest`/`convert+ingest`."""
    repo = _repo2(tmp_path)
    repo.set_source_state("demand-gen", "sync", "zone/lec.txt", "source_hash", "h")
    for d in (Decision("upsert", "ready-note"), Decision("skip", "binary")):
        assert _gate(repo, d, _IF_MISSING_D1) is d


def test_gate_d1_source_state(tmp_path: Path) -> None:
    repo = _repo2(tmp_path)
    repo.set_source_state("demand-gen", "sync", "zone/lec.txt", "source_hash", "h")
    out = _gate(repo, Decision("ingest", "text-source"), _IF_MISSING_D1)
    assert out.action == "skip" and out.reason == "summary-exists:source_state"


def test_gate_d2a_provenance(tmp_path: Path) -> None:
    repo = _repo2(tmp_path)
    _upsert_page(repo, "demand-gen", "lec", {"source": "zone/lec.txt"})
    out = _gate(repo, Decision("ingest", "text-source"), _IF_MISSING_D2A)
    assert out.action == "skip" and out.reason == "summary-exists:provenance"


def test_gate_d2a_basename_match(tmp_path: Path) -> None:
    """vdd-multi MED-1 fix: `provenance_ref.match: basename` now actually matches by
    basename (was a silent no-op)."""
    repo = _repo2(tmp_path)
    _upsert_page(repo, "demand-gen", "lec", {"source": "lec.txt"})  # frontmatter = basename
    policy = ResummarizeConfig(
        mode="if-missing",
        detect=DetectConfig(source_state=False,
                            provenance_ref=ProvenanceConfig(enabled=True, match="basename")),
    )
    # raw rel is a deep path; basename `lec.txt` should match the cited basename
    out = _gate(repo, Decision("ingest", "text-source"), policy, rel="Module-01/Transcripts/lec.txt")
    assert out.action == "skip" and out.reason == "summary-exists:provenance"


def test_gate_never_force_reason_forced(tmp_path: Path) -> None:
    """vdd-multi MED-2 fix: `--force` under `mode: never` now sets reason='forced'
    (uniform with if-missing), not the original reason."""
    repo = _repo2(tmp_path)
    out = _gate(repo, Decision("ingest", "text-source"),
                ResummarizeConfig(mode="never"), force=True)
    assert out.action == "ingest" and out.reason == "forced"


def test_gate_no_match_stays_actionable(tmp_path: Path) -> None:
    repo = _repo2(tmp_path)
    d = Decision("ingest", "text-source")
    assert _gate(repo, d, _IF_MISSING_D1) is d  # no marker, no page → unchanged


def test_gate_mode_never(tmp_path: Path) -> None:
    repo = _repo2(tmp_path)
    out = _gate(repo, Decision("ingest", "text-source"),
                ResummarizeConfig(mode="never"))
    assert out.action == "skip" and out.reason == "resummarize-never"
    # never still does NOT touch upsert
    up = Decision("upsert", "ready-note")
    assert _gate(repo, up, ResummarizeConfig(mode="never")) is up


def test_gate_mode_always(tmp_path: Path) -> None:
    repo = _repo2(tmp_path)
    repo.set_source_state("demand-gen", "sync", "zone/lec.txt", "source_hash", "h")
    d = Decision("ingest", "text-source")
    assert _gate(repo, d, ResummarizeConfig(mode="always")) is d  # never gated


def test_gate_force_rearms(tmp_path: Path) -> None:
    repo = _repo2(tmp_path)
    repo.set_source_state("demand-gen", "sync", "zone/lec.txt", "source_hash", "h")
    out = _gate(repo, Decision("ingest", "text-source"), _IF_MISSING_D1, force=True)
    assert out.action == "ingest" and out.reason == "forced"


def test_build_entries_d1_gate_integration(tmp_path: Path) -> None:
    """End-to-end through `_build_entries`: a recorded raw is gated to skip."""
    repo = _repo(tmp_path)
    _write_sync_yaml(tmp_path,
                     "resummarize:\n  mode: if-missing\n  detect:\n    source_state: true\n")
    zone = tmp_path / "zone"
    zone.mkdir()
    (zone / "lec.txt").write_text("body", encoding="utf-8")
    repo.set_source_state("demand-gen", "sync", "zone/lec.txt", "source_hash", "h")

    by_path = _entries(tmp_path, repo)
    assert by_path["zone/lec.txt"]["action"] == "skip"
    assert by_path["zone/lec.txt"]["reason"] == "summary-exists:source_state"


# ---------------------------------------------------------------------------
# Phase 3 — D2b filesystem mirror (bead 07): stem-relpath + group-key + ReDoS
# ---------------------------------------------------------------------------


def _mk(p: Path, text: str = "x") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_d2b_group_key_n_to_1(tmp_path: Path) -> None:
    """N transcripts `02-*` ↔ one summary `02 - ….md` (key `^(\\d+)`)."""
    mod = tmp_path / "Module-01"
    _mk(mod / "Transcripts" / "02-1 Решение vs транзакция-1.txt")
    _mk(mod / "Transcripts" / "02-2 Решение vs транзакция-2.txt")
    _mk(mod / "Summary" / "02 - Решение vs транзакция.md")
    mirror = MirrorConfig(enabled=True, raw_dirs=("Transcripts",),
                          summary_dir="Summary", match="group-key", group_key=r"^(\d+)")
    assert _mirror_match(mod / "Transcripts" / "02-1 Решение vs транзакция-1.txt",
                         vault_root=tmp_path, mirror=mirror, caches=Caches()) is True
    assert _mirror_match(mod / "Transcripts" / "02-2 Решение vs транзакция-2.txt",
                         vault_root=tmp_path, mirror=mirror, caches=Caches()) is True


def test_d2b_group_key_negative(tmp_path: Path) -> None:
    """A raw whose key has no matching summary → not covered."""
    mod = tmp_path / "Module-01"
    _mk(mod / "Transcripts" / "08-1 New lesson.txt")
    _mk(mod / "Summary" / "02 - Existing.md")
    mirror = MirrorConfig(enabled=True, raw_dirs=("Transcripts",),
                          summary_dir="Summary", match="group-key", group_key=r"^(\d+)")
    assert _mirror_match(mod / "Transcripts" / "08-1 New lesson.txt",
                         vault_root=tmp_path, mirror=mirror, caches=Caches()) is False


def test_d2b_stem_relpath_same_dir(tmp_path: Path) -> None:
    """Same-dir office↔md: `Resources/X.docx` covered iff `Resources/X.md` exists."""
    res = tmp_path / "Module-04" / "Resources"
    _mk(res / "Алгоритм_первой_встречи.docx")
    _mk(res / "Алгоритм_первой_встречи.md")
    _mk(res / "Orphan.pptx")
    mirror = MirrorConfig(enabled=True, raw_dirs=("Resources",),
                          summary_dir=".", match="stem-relpath", summary_ext=".md")
    assert _mirror_match(res / "Алгоритм_первой_встречи.docx",
                         vault_root=tmp_path, mirror=mirror, caches=Caches()) is True
    assert _mirror_match(res / "Orphan.pptx",
                         vault_root=tmp_path, mirror=mirror, caches=Caches()) is False


def test_d2b_asymmetric_regex_template(tmp_path: Path) -> None:
    """Per-side regex + template: raw `M01_L02_part3` ↔ summary `02 - …` via lesson key."""
    mod = tmp_path / "Module-01"
    _mk(mod / "Transcripts" / "M01_L02_part3.txt")
    _mk(mod / "Summary" / "02 - Title.md")
    mirror = MirrorConfig(
        enabled=True, raw_dirs=("Transcripts",), summary_dir="Summary",
        match="group-key",
        key=MirrorKey(raw_regex=r"M\d+_L(?P<lesson>\d+)",
                      summary_regex=r"^(?P<lesson>\d+)", template="${lesson}"),
    )
    assert _mirror_match(mod / "Transcripts" / "M01_L02_part3.txt",
                         vault_root=tmp_path, mirror=mirror, caches=Caches()) is True


def test_d2b_date_key(tmp_path: Path) -> None:
    """Lessons date-key: `20260326-01.txt` ↔ `20260326_….md` (key `^(\\d{8})`)."""
    le = tmp_path / "Lessons"
    _mk(le / "Transcripts" / "20260326-01 - Sales обучение.txt")
    _mk(le / "Summary" / "20260326_Sales обучение.md")
    mirror = MirrorConfig(enabled=True, raw_dirs=("Transcripts",),
                          summary_dir="Summary", match="group-key", group_key=r"^(\d{8})")
    assert _mirror_match(le / "Transcripts" / "20260326-01 - Sales обучение.txt",
                         vault_root=tmp_path, mirror=mirror, caches=Caches()) is True


def test_d2b_empty_key_no_false_collision(tmp_path: Path) -> None:
    """vdd-multi LOW-1: a regex that matches the empty string yields no key (None),
    so unrelated files don't all collide on `""` → no false skip."""
    mod = tmp_path / "Module-01"
    _mk(mod / "Transcripts" / "Notes.txt")
    _mk(mod / "Summary" / "Other.md")
    mirror = MirrorConfig(enabled=True, raw_dirs=("Transcripts",),
                          summary_dir="Summary", match="group-key", group_key=r"\d*")
    assert _mirror_match(mod / "Transcripts" / "Notes.txt",
                         vault_root=tmp_path, mirror=mirror, caches=Caches()) is False


def test_d2b_unicode_digit_stem_no_crash(tmp_path: Path) -> None:
    """vdd-multi LOW-2: a Unicode-numeric stem (`²`, `isdigit()` but not `int()`-able)
    under a permissive regex must not crash `_norm`/the scan."""
    mod = tmp_path / "Module-01"
    _mk(mod / "Transcripts" / "².txt")
    _mk(mod / "Summary" / "².md")
    mirror = MirrorConfig(enabled=True, raw_dirs=("Transcripts",),
                          summary_dir="Summary", match="group-key", group_key=r"(.+)")
    # verbatim key "²" both sides → match; the point is it does NOT raise ValueError
    assert _mirror_match(mod / "Transcripts" / "².txt",
                         vault_root=tmp_path, mirror=mirror, caches=Caches()) is True


def test_d2b_summary_dir_traversal_refused(tmp_path: Path) -> None:
    """vdd-multi security LOW: an operator `summary_dir` escaping the vault → no-match
    (the scope is contained), never an out-of-vault probe."""
    mod = tmp_path / "Module-01"
    _mk(mod / "Transcripts" / "01-1.txt")
    mirror = MirrorConfig(enabled=True, raw_dirs=("Transcripts",),
                          summary_dir="../../../../../../tmp", match="group-key",
                          group_key=r"^(\d+)")
    assert _mirror_match(mod / "Transcripts" / "01-1.txt",
                         vault_root=tmp_path, mirror=mirror, caches=Caches()) is False


def test_d2b_dead_detector_warns(tmp_path: Path, caplog) -> None:
    """Dead-detector guard (dogfood finding): mirror enabled + summaries present but the
    group_key regex keys NONE of them (e.g. the YAML double-backslash bug) → no match +
    a one-shot WARN, so the silent-inert detector becomes observable."""
    import logging
    mod = tmp_path / "Module-01"
    _mk(mod / "Transcripts" / "01-1.txt")
    _mk(mod / "Summary" / "01 - X.md")
    _mk(mod / "Summary" / "02 - Y.md")
    # a regex that matches neither the raw nor any summary stem (digits-then-ZZZ)
    mirror = MirrorConfig(enabled=True, raw_dirs=("Transcripts",), summary_dir="Summary",
                          match="group-key", group_key=r"(\d+)ZZZ")
    with caplog.at_level(logging.WARNING, logger="wiki_sync.resummarize"):
        out = _mirror_match(mod / "Transcripts" / "01-1.txt",
                            vault_root=tmp_path, mirror=mirror, caches=Caches())
    assert out is False
    assert any("keyed 0 of 2 summaries" in r.getMessage() for r in caplog.records)


def test_d2b_bad_regex_rejected_by_load_gate(tmp_path: Path) -> None:
    """The mirror-regex load-gate rejects an uncompilable / budget-busting operator
    regex (`INVALID_SYNC_CONFIG`, exit 6) BEFORE it runs on any file — closes the
    per-scan ReDoS-amplification window (vdd-multi security MED). The pattern is never
    echoed (CWE-209). Deterministic (uncompilable → `regex.error` → rejected)."""
    mod = tmp_path / "Module-01"
    _mk(mod / "Transcripts" / "01-1.txt")
    _mk(mod / "Summary" / "01 - X.md")
    mirror = MirrorConfig(enabled=True, raw_dirs=("Transcripts",),
                          summary_dir="Summary", match="group-key", group_key="(")
    with pytest.raises(SyncConfigError) as exc:
        _mirror_match(mod / "Transcripts" / "01-1.txt",
                      vault_root=tmp_path, mirror=mirror, caches=Caches())
    assert exc.value.code == "INVALID_SYNC_CONFIG"
    assert "(" not in str(exc.value).split(":", 1)[1]  # pattern not echoed in the detail


# ---------------------------------------------------------------------------
# TASK 021 / HIGH-1 — merge/split visibility for N:1 mirror skips (Option A)
# ---------------------------------------------------------------------------


def _groupkey_mirror() -> MirrorConfig:
    return MirrorConfig(enabled=True, raw_dirs=("Transcripts",),
                        summary_dir="Summary", match="group-key", group_key=r"^(\d+)")


def test_high1_groupkey_uncited_warns(tmp_path: Path, caplog) -> None:
    """An N:1 group-key match with `warn_uncited=True` keeps the match (skip) AND emits
    the merge/split WARN naming the key, the raw, the colliding summary, and both levers.
    The reachability invariant: `summary_exists` only sets `warn_uncited` once D1/D2a have
    failed, so a `_mirror_match` warn is by construction the uncited-same-key case."""
    import logging
    mod = tmp_path / "Module-01"
    _mk(mod / "Transcripts" / "07-2 brand new.txt")
    _mk(mod / "Summary" / "07 - Лекция.md")
    raw = mod / "Transcripts" / "07-2 brand new.txt"
    with caplog.at_level(logging.WARNING, logger="wiki_sync.resummarize"):
        out = _mirror_match(raw, vault_root=tmp_path, mirror=_groupkey_mirror(),
                            caches=Caches(), warn_uncited=True)
    assert out is True  # skip behaviour unchanged
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert "07 - Лекция.md" in msg and "'7'" in msg  # _norm strips the leading zero
    assert "MERGE" in msg and "SPLIT" in msg and "--force" in msg


def test_high1_groupkey_default_no_warn(tmp_path: Path, caplog) -> None:
    """`warn_uncited` defaults False → the N:1 match still skips, but stays silent
    (back-compat: the dead-detector test + all prior callers keep their behaviour)."""
    import logging
    mod = tmp_path / "Module-01"
    _mk(mod / "Transcripts" / "07-2 brand new.txt")
    _mk(mod / "Summary" / "07 - Лекция.md")
    with caplog.at_level(logging.WARNING, logger="wiki_sync.resummarize"):
        out = _mirror_match(mod / "Transcripts" / "07-2 brand new.txt",
                            vault_root=tmp_path, mirror=_groupkey_mirror(), caches=Caches())
    assert out is True
    assert not any("MERGE" in r.getMessage() for r in caplog.records)


def test_high1_stem_relpath_never_warns(tmp_path: Path, caplog) -> None:
    """`stem-relpath` (1:1, exact mirror) is unambiguous → never warns even with
    `warn_uncited=True` (only the coarse N:1 group-key path surfaces merge/split)."""
    import logging
    mod = tmp_path / "Module-01"
    _mk(mod / "Transcripts" / "lec.txt")
    _mk(mod / "Summary" / "lec.md")
    mirror = MirrorConfig(enabled=True, raw_dirs=("Transcripts",),
                          summary_dir="Summary", match="stem-relpath", summary_ext=".md")
    with caplog.at_level(logging.WARNING, logger="wiki_sync.resummarize"):
        out = _mirror_match(mod / "Transcripts" / "lec.txt", vault_root=tmp_path,
                            mirror=mirror, caches=Caches(), warn_uncited=True)
    assert out is True
    assert not any("MERGE" in r.getMessage() for r in caplog.records)


def test_high1_summary_exists_uncited_warns(tmp_path: Path, caplog) -> None:
    """Integration: provenance ENABLED but the raw is NOT cited → `summary_exists` falls
    through D1/D2a to D2b, returns `"mirror"`, and (because `warn_uncited=pr.enabled`)
    emits the merge/split WARN."""
    import logging
    repo = _repo(tmp_path)
    _mk(tmp_path / "Module-01" / "Transcripts" / "07-2 brand new.txt")
    _mk(tmp_path / "Module-01" / "Summary" / "07 - Лекция.md")
    policy = ResummarizeConfig(mode="if-missing", detect=DetectConfig(
        source_state=False, provenance_ref=ProvenanceConfig(enabled=True),
        mirror=_groupkey_mirror()))
    raw = tmp_path / "Module-01" / "Transcripts" / "07-2 brand new.txt"
    with caplog.at_level(logging.WARNING, logger="wiki_sync.resummarize"):
        which = summary_exists(raw, rel="Module-01/Transcripts/07-2 brand new.txt",
                               vault_root=tmp_path, repo=repo, vault_id="demand-gen",
                               policy=policy, caches=Caches())
    assert which == "mirror"
    assert any("MERGE" in r.getMessage() for r in caplog.records)


def test_high1_summary_exists_cited_no_warn(tmp_path: Path, caplog) -> None:
    """A raw that IS cited short-circuits at D2a (`"provenance"`) → mirror never runs →
    no merge/split warn (the merge is already explicit in `sources:`)."""
    import logging
    repo = _repo(tmp_path)
    rel = "Module-01/Transcripts/07-2 brand new.txt"
    _mk(tmp_path / rel)
    _mk(tmp_path / "Module-01" / "Summary" / "07 - Лекция.md")
    _upsert_page(repo, "demand-gen", "07-lekciya", {"sources": [rel]})
    policy = ResummarizeConfig(mode="if-missing", detect=DetectConfig(
        source_state=False, provenance_ref=ProvenanceConfig(enabled=True),
        mirror=_groupkey_mirror()))
    with caplog.at_level(logging.WARNING, logger="wiki_sync.resummarize"):
        which = summary_exists(tmp_path / rel, rel=rel, vault_root=tmp_path, repo=repo,
                               vault_id="demand-gen", policy=policy, caches=Caches())
    assert which == "provenance"
    assert not any("MERGE" in r.getMessage() for r in caplog.records)


def test_high1_provenance_disabled_no_warn(tmp_path: Path, caplog) -> None:
    """Provenance DISABLED → operator opted into pure-key grouping → the N:1 skip stays
    but no per-file warn (would be noise on every group member)."""
    import logging
    repo = _repo(tmp_path)
    rel = "Module-01/Transcripts/07-2 brand new.txt"
    _mk(tmp_path / rel)
    _mk(tmp_path / "Module-01" / "Summary" / "07 - Лекция.md")
    policy = ResummarizeConfig(mode="if-missing", detect=DetectConfig(
        source_state=False, provenance_ref=ProvenanceConfig(enabled=False),
        mirror=_groupkey_mirror()))
    with caplog.at_level(logging.WARNING, logger="wiki_sync.resummarize"):
        which = summary_exists(tmp_path / rel, rel=rel, vault_root=tmp_path, repo=repo,
                               vault_id="demand-gen", policy=policy, caches=Caches())
    assert which == "mirror"
    assert not any("MERGE" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Phase 4 — `--force` CLI surface + report (bead 08)
# ---------------------------------------------------------------------------


def test_scan_parser_accepts_force() -> None:
    """`wiki-sync scan … --force` parses (the flag exists, defaults False)."""
    assert _build_parser().parse_args(
        ["scan", "z", "--vault", "v", "--force"]).force is True
    assert _build_parser().parse_args(
        ["scan", "z", "--vault", "v"]).force is False


def test_build_entries_force_rearms_recorded(tmp_path: Path) -> None:
    """`force=True` re-arms a raw the policy would skip → action stays, reason forced."""
    repo = _repo(tmp_path)
    _write_sync_yaml(tmp_path,
                     "resummarize:\n  mode: if-missing\n  detect:\n    source_state: true\n")
    zone = tmp_path / "zone"
    zone.mkdir()
    (zone / "lec.txt").write_text("body", encoding="utf-8")
    repo.set_source_state("demand-gen", "sync", "zone/lec.txt", "source_hash", "h")

    config = load_sync_config(tmp_path)
    layout = resolve_layout_config(tmp_path)
    forced = {e["path"]: e for e in
              _build_entries(repo, "demand-gen", zone, tmp_path, config, layout, force=True)}
    assert forced["zone/lec.txt"]["action"] == "ingest"
    assert forced["zone/lec.txt"]["reason"] == "forced"
