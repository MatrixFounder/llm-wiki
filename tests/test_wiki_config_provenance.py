"""TASK 058 Phase 1 — the provenance engine's RELEASE GATE (R-058-1).

Two properties, asserted over every cascade fixture:

1. **Equivalence**: the engine's merged RAW blocks, parsed through the SAME
   `_parse_*` functions, equal the REAL resolver's output
   (`resolve_policy` / `resolve_summarize`). Frozen dataclasses → deep `==`.
2. **Origin consistency**: every pointer the engine attributes to a LEVEL holds
   exactly the value that level's raw block carries at that pointer.

Plus the R-058-10 evolution invariant: a synthetic field injected into the
schema doc surfaces in the UI model with zero code changes.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from scripts.wiki_index.sync_config import (
    SummarizeConfig,
    _load_validated_raw,
    _parse_resummarize,
    _parse_summarize,
)
from scripts.wiki_skills._resummarize import resolve_policy, resolve_summarize
from scripts.wiki_skills.wiki_config._provenance import (
    SyncConfigLevelError,
    compute_folder_provenance,
    scan_tree,
)
from scripts.wiki_skills.wiki_config._uimodel import (
    SCOPE_CASCADING,
    build_ui_model,
    load_sync_schema_doc,
    top_level_keys,
)


def _folder_yaml(d: Path, text: str) -> None:
    (d / ".wiki").mkdir(parents=True, exist_ok=True)
    (d / ".wiki" / "sync.yaml").write_text(text, encoding="utf-8")


_ROOT_FULL = (
    "zones:\n"
    "  - 'Lessons/**'\n"
    "exclude:\n"
    "  - '_inbox/**'\n"
    "resummarize:\n"
    "  mode: if-missing\n"
    "  detect:\n"
    "    source_state: true\n"
    "    provenance_ref:\n"
    "      enabled: true\n"
    "      fields: [source, sources]\n"
    "      match: vault-rel-path\n"
    "    mirror:\n"
    "      enabled: true\n"
    "      raw_dirs: [Transcripts]\n"
    "      summary_dir: Summary\n"
    "      match: group-key\n"
    "      group_key: '^(\\d+)'\n"
    "summarize:\n"
    "  profile: article\n"
)

# The samples/Demand-generation/Lessons shape: only group_key differs.
_CHILD_GROUP_KEY = (
    "resummarize:\n"
    "  detect:\n"
    "    mirror:\n"
    "      enabled: true\n"
    "      raw_dirs: [Transcripts]\n"
    "      summary_dir: Summary\n"
    "      group_key: '^(\\d{8})'\n"
)


def _assert_equivalence(folder: Path, root: Path) -> None:
    """Property 1: engine merged+parsed == real resolver."""
    prov = compute_folder_provenance(folder, root)
    merged_res = prov.merged_raw.get("resummarize")
    engine_res = _parse_resummarize(merged_res) if merged_res is not None else None
    assert engine_res == resolve_policy(folder / "f.md", vault_root=root)
    merged_sum = prov.merged_raw.get("summarize")
    engine_sum = _parse_summarize(merged_sum or {}) or SummarizeConfig()
    assert engine_sum == resolve_summarize(folder / "f.md", vault_root=root)


def _lookup(block: dict[str, Any], pointer_tail: list[str]) -> Any:
    cur: Any = block
    for part in pointer_tail:
        assert isinstance(cur, dict), f"non-dict at {part}"
        cur = cur[part]
    return cur


def _assert_origin_consistency(folder: Path, root: Path) -> None:
    """Property 2: an origin label points at the level that truly holds the value.

    Checked for LEAF pointers only: a dict pointer's origin means "this level
    INTRODUCED the subtree" — its descendants may legitimately be overridden by
    deeper levels afterwards, so whole-subtree value equality does not hold."""
    prov = compute_folder_provenance(folder, root)
    for pointer, origin in prov.origins.items():
        if origin.origin == "default":
            continue
        parts = pointer.lstrip("/").split("/")
        block_name = parts[0]
        merged = prov.merged_raw.get(block_name)
        if merged is None:
            continue  # root-only key — value lives in the root raw dict
        merged_val = _lookup(merged, parts[1:])
        if isinstance(merged_val, dict):
            continue
        level_dir = root if origin.origin == "root" else root / origin.origin
        level_block = _load_validated_raw(level_dir).get(block_name)
        assert isinstance(level_block, dict)
        assert merged_val == _lookup(level_block, parts[1:])


def test_root_only_config(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, _ROOT_FULL)
    sub = tmp_path / "Lessons"
    sub.mkdir()
    _assert_equivalence(sub, tmp_path)
    prov = compute_folder_provenance(sub, tmp_path)
    assert prov.origins["/resummarize/mode"].origin == "root"
    assert prov.origins["/summarize/profile"].origin == "root"
    # parser-injected defaults are tagged `default`, not `root`
    assert prov.origins["/summarize/diagrams"].origin == "default"
    assert prov.origins["/zones"].origin == "root"
    assert prov.origins["/zones"].scope == "root-only"


def test_partial_child_override_inherits_parent(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, _ROOT_FULL)
    lessons = tmp_path / "Lessons"
    _folder_yaml(lessons, _CHILD_GROUP_KEY)
    _assert_equivalence(lessons, tmp_path)
    _assert_origin_consistency(lessons, tmp_path)
    prov = compute_folder_provenance(lessons, tmp_path)
    # overridden leaf → child; shadow records the displaced root
    gk = prov.origins["/resummarize/detect/mirror/group_key"]
    assert gk.origin == "Lessons" and "root" in gk.shadows
    # untouched sibling detector settings inherit from root
    assert prov.origins["/resummarize/detect/provenance_ref/enabled"].origin == "root"
    assert prov.origins["/resummarize/mode"].origin == "root"
    # effective value is the child's
    assert prov.effective["resummarize"]["detect"]["mirror"]["group_key"] == "^(\\d{8})"


def test_list_replace_not_extend(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, _ROOT_FULL)
    zone = tmp_path / "Zone"
    _folder_yaml(zone, (
        "resummarize:\n"
        "  detect:\n"
        "    provenance_ref:\n"
        "      fields: [origin]\n"
    ))
    _assert_equivalence(zone, tmp_path)
    prov = compute_folder_provenance(zone, tmp_path)
    assert prov.effective["resummarize"]["detect"]["provenance_ref"]["fields"] == ["origin"]
    fields = prov.origins["/resummarize/detect/provenance_ref/fields"]
    assert fields.origin == "Zone" and "root" in fields.shadows


def test_key_block_introduced_at_deep_level(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, _ROOT_FULL)
    deep = tmp_path / "A" / "B"
    _folder_yaml(deep, (
        "resummarize:\n"
        "  detect:\n"
        "    mirror:\n"
        "      key:\n"
        "        raw_regex: '^(?P<n>\\d+)'\n"
        "        summary_regex: '^(?P<n>\\d+)'\n"
        "        template: '${n}'\n"
    ))
    _assert_equivalence(deep, tmp_path)
    _assert_origin_consistency(deep, tmp_path)
    prov = compute_folder_provenance(deep, tmp_path)
    # a whole subtree introduced at one level claims every descendant pointer
    assert prov.origins["/resummarize/detect/mirror/key"].origin == "A/B"
    assert prov.origins["/resummarize/detect/mirror/key/template"].origin == "A/B"


def test_three_level_shadow_chain(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "resummarize:\n  mode: if-missing\n")
    mid = tmp_path / "Mid"
    _folder_yaml(mid, "resummarize:\n  mode: always\n")
    leaf = mid / "Leaf"
    _folder_yaml(leaf, "resummarize:\n  mode: never\n")
    _assert_equivalence(leaf, tmp_path)
    prov = compute_folder_provenance(leaf, tmp_path)
    mode = prov.origins["/resummarize/mode"]
    assert mode.origin == "Mid/Leaf"
    assert mode.shadows == ("root", "Mid")
    # the intermediate folder's own view stops at its level
    prov_mid = compute_folder_provenance(mid, tmp_path)
    assert prov_mid.origins["/resummarize/mode"].origin == "Mid"


def test_cyrillic_and_space_folder_names(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, _ROOT_FULL)
    bd = tmp_path / "06 - Business Development" / "Встречи"
    _folder_yaml(bd, "summarize:\n  profile: meeting\n  extract_concepts: false\n")
    _assert_equivalence(bd, tmp_path)
    _assert_origin_consistency(bd, tmp_path)
    prov = compute_folder_provenance(bd, tmp_path)
    label = "06 - Business Development/Встречи"
    assert prov.origins["/summarize/profile"].origin == label
    assert prov.origins["/summarize/extract_concepts"].origin == label
    assert prov.effective["summarize"]["profile"] == "meeting"


def test_unconfigured_vault_all_defaults(tmp_path: Path) -> None:
    sub = tmp_path / "Anything"
    sub.mkdir()
    _assert_equivalence(sub, tmp_path)
    prov = compute_folder_provenance(sub, tmp_path)
    assert prov.effective["resummarize"] is None
    assert prov.origins["/resummarize"].origin == "default"
    assert prov.effective["summarize"] == {
        "profile": "auto", "diagrams": False,
        "extract_concepts": True, "target_subdir": "",
    }
    assert prov.levels == [] and prov.warnings == []


def test_root_only_key_in_subfolder_is_ignored_and_warned(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, "exclude:\n  - '_inbox/**'\n")
    sub = tmp_path / "Zone"
    _folder_yaml(sub, "exclude:\n  - 'Zone-local/**'\nsummarize:\n  profile: lesson\n")
    _assert_equivalence(sub, tmp_path)
    prov = compute_folder_provenance(sub, tmp_path)
    # the subfolder exclude must NOT leak into the effective view
    assert prov.effective["exclude"] == ["_inbox/**"]
    assert prov.origins["/exclude"].origin == "root"
    warning = next(w for w in prov.warnings
                   if w["code"] == "NON_CASCADING_KEY_IN_SUBFOLDER")
    assert warning["level"] == "Zone" and warning["keys"] == ["exclude"]


def test_broken_ancestor_raises_with_level(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, _ROOT_FULL)
    bad = tmp_path / "Bad"
    _folder_yaml(bad, "resummarize: [not, a, mapping\n")
    leaf = bad / "Leaf"
    leaf.mkdir()
    with pytest.raises(SyncConfigLevelError) as exc_info:
        compute_folder_provenance(leaf, tmp_path)
    assert exc_info.value.level == "Bad"
    assert exc_info.value.reason == "PARSE"


def test_scan_tree_overridden_by_and_ignored(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, _ROOT_FULL)
    lessons = tmp_path / "Lessons"
    _folder_yaml(lessons, _CHILD_GROUP_KEY)
    stray = tmp_path / "Stray"
    _folder_yaml(stray, "exclude:\n  - 'x/**'\n")
    nodes = {n.folder: n for n in scan_tree(tmp_path)}
    assert set(nodes) == {".", "Lessons", "Stray"}
    root_node = nodes["."]
    assert root_node.defines["/resummarize/detect/mirror/group_key"] == SCOPE_CASCADING
    assert root_node.overridden_by["/resummarize/detect/mirror/group_key"] == ("Lessons",)
    assert nodes["Stray"].ignored == ("exclude",)
    assert nodes["Lessons"].error is None


def test_scan_tree_survives_broken_file(tmp_path: Path) -> None:
    _folder_yaml(tmp_path, _ROOT_FULL)
    bad = tmp_path / "Bad"
    _folder_yaml(bad, ": : :\n")
    nodes = {n.folder: n for n in scan_tree(tmp_path)}
    assert nodes["Bad"].error is not None
    assert nodes["Bad"].error["code"] == "INVALID_SYNC_CONFIG"
    assert nodes["."].error is None


def test_walk_vault_tree_capped_and_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 3a: `scan_tree`'s walk was uncapped; `walk_vault_tree` (the ONE
    walk `scan_tree` and `/api/tree` now share — finding 2c) must stop at the
    cap and report truncation, matching the endpoint's prior 5000-dir
    contract."""
    from scripts.wiki_skills.wiki_config import _provenance as prov_mod

    monkeypatch.setattr(prov_mod, "_TREE_WALK_CAP", 3)
    _folder_yaml(tmp_path, _ROOT_FULL)
    for i in range(10):
        (tmp_path / f"Extra{i}").mkdir()
    walked, truncated = prov_mod.walk_vault_tree(tmp_path)
    assert truncated is True
    assert len(walked) == 3


def test_scan_tree_from_walk_matches_scan_tree(tmp_path: Path) -> None:
    """`/api/tree`'s single-walk path (`walk_vault_tree` + `scan_tree_from_walk`)
    must produce the SAME nodes as the `scan_tree` convenience wrapper it
    replaced (finding 2c: previously TWO separate `os.walk`s over the vault)."""
    from scripts.wiki_skills.wiki_config._provenance import (
        scan_tree_from_walk,
        walk_vault_tree,
    )

    _folder_yaml(tmp_path, _ROOT_FULL)
    lessons = tmp_path / "Lessons"
    _folder_yaml(lessons, _CHILD_GROUP_KEY)
    walked, truncated = walk_vault_tree(tmp_path)
    assert truncated is False
    direct = {n.folder: n for n in scan_tree_from_walk(walked)}
    via_wrapper = {n.folder: n for n in scan_tree(tmp_path)}
    assert direct.keys() == via_wrapper.keys()
    for label in direct:
        assert direct[label] == via_wrapper[label]


def test_build_ui_model_memoizes_until_schema_mtime_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 5: `build_ui_model()` must not re-read/re-parse the schema YAML
    on every call — but a rewrite at the SAME path (new mtime) must still be
    observed (an mtime-keyed cache, not a bare process-lifetime singleton;
    this is what keeps a test that swaps the schema path/content correct)."""
    import os

    import scripts.wiki_skills.wiki_config._uimodel as uimodel_mod

    schema_copy = tmp_path / "sync-config.schema.yaml"
    schema_copy.write_text(
        uimodel_mod.SYNC_SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(uimodel_mod, "SYNC_SCHEMA_PATH", schema_copy)
    monkeypatch.setattr(uimodel_mod, "_MODEL_CACHE", None)

    calls: list[int] = []
    real_loader = uimodel_mod.load_sync_schema_doc

    def _counting_loader(path: Path | None = None) -> dict[str, Any]:
        calls.append(1)
        return real_loader(path)

    monkeypatch.setattr(uimodel_mod, "load_sync_schema_doc", _counting_loader)

    model1 = uimodel_mod.build_ui_model()
    model2 = uimodel_mod.build_ui_model()
    assert len(calls) == 1  # second call served from cache, no re-parse
    assert set(model1) == set(model2)
    # the two returned dicts must be independent objects (copy-out guard):
    # mutating one must not corrupt the shared cached model.
    model1["/__poison__"] = model1["/summarize"]
    assert "/__poison__" not in uimodel_mod.build_ui_model()

    # a rewrite at the SAME path (forced mtime bump, filesystem-clock-safe)
    # must invalidate the cache, not serve the stale parse.
    st = schema_copy.stat()
    os.utime(schema_copy, ns=(st.st_atime_ns, st.st_mtime_ns + 1))
    uimodel_mod.build_ui_model()
    assert len(calls) == 2

    # an explicit schema_doc (the R-058-10 evolution test's synthetic doc)
    # always bypasses the cache — never counted, never cached.
    uimodel_mod.build_ui_model({"$defs": {"SyncConfig": {"properties": {}}}})
    assert len(calls) == 2


def test_evolution_new_schema_field_needs_no_code(tmp_path: Path) -> None:
    """R-058-10: a field added ONLY to the schema doc surfaces everywhere."""
    doc = copy.deepcopy(load_sync_schema_doc())
    doc["$defs"]["SyncConfig"]["properties"]["future_block"] = {
        "type": "object",
        "x-wiki-scope": "cascading",
        "description": "synthetic future block",
        "additionalProperties": False,
        "properties": {
            "knob": {"type": "string", "enum": ["a", "b"],
                     "description": "synthetic knob"},
        },
    }
    model = build_ui_model(doc)
    assert model["/future_block"].scope == SCOPE_CASCADING
    assert model["/future_block/knob"].enum == ("a", "b")
    assert model["/future_block/knob"].description == "synthetic knob"
    assert "future_block" in top_level_keys(model, SCOPE_CASCADING)


def test_ui_model_matches_shipped_schema() -> None:
    """The shipped schema's scope annotations mirror the resolver's reality."""
    model = build_ui_model()
    assert set(top_level_keys(model, SCOPE_CASCADING)) == {"resummarize", "summarize"}
    assert set(top_level_keys(model, "root-only")) == {
        "zones", "exclude", "tag_namespace", "extensions", "transcript_dedup",
    }
    assert model["/resummarize/detect/mirror/group_key"].fmt == "regex"
    assert model["/summarize/profile"].enum == ("auto", "meeting", "lesson", "article")
    assert model["/summarize/target_subdir"].fmt == "path"
