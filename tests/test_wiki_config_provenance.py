"""TASK 058 Phase 1 — the provenance engine's RELEASE GATE (R-058-1).

Two properties, asserted over every cascade fixture:

1. **Equivalence**: the engine's merged RAW blocks, parsed through the SAME
   `_parse_*` functions, equal the REAL resolver's output
   (`resolve_policy` / `resolve_summarize`). Frozen dataclasses → deep `==`.
2. **Origin consistency**: every pointer the engine attributes to a LEVEL holds
   exactly the value that level's raw block carries at that pointer.

Plus the R-058-10 evolution invariant: a synthetic field injected into the
schema doc surfaces in the UI model with zero code changes.

TASK 061 (R-061-4/5) adds the third property, over the SAME fixtures:

3. **No dangling provenance pointer**: every pointer `show` reports provenance
   for is REACHABLE in `effective`. The parsed-dataclass path used to drop any
   schema key the frozen dataclass does not declare, while `_assign_origins`
   (which walks the RAW block) still recorded a pointer for it — a pointer with
   no value, invisible in every downstream surface.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.wiki_index.sync_config import (
    SummarizeConfig,
    _load_validated_raw,
    _parse_resummarize,
    _parse_summarize,
)
from scripts.wiki_skills._resummarize import resolve_policy, resolve_summarize
from scripts.wiki_skills.wiki_config import main
from scripts.wiki_skills.wiki_config._provenance import (
    SyncConfigLevelError,
    compute_folder_provenance,
    scan_tree,
)
from scripts.wiki_skills.wiki_config._report import build_report_model, render_html
from scripts.wiki_skills.wiki_config._report_md import render_show_report
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


def _assert_cascade_invariants(folder: Path, root: Path) -> None:
    """The properties EVERY cascade fixture must hold. Asserted from the ONE
    helper every fixture already calls, so a new fixture inherits them instead of
    having to remember them (TC-07-1).

    Property 1 — equivalence: engine merged+parsed == the real resolver. The
    R-061-4 overlay reshapes `effective` (a DISPLAY surface) only; `merged_raw`,
    the surface this equivalence is computed from, is untouched.

    Property 3 — no dangling provenance pointer (R-061-4).
    """
    prov = compute_folder_provenance(folder, root)
    merged_res = prov.merged_raw.get("resummarize")
    engine_res = _parse_resummarize(merged_res) if merged_res is not None else None
    assert engine_res == resolve_policy(folder / "f.md", vault_root=root)
    merged_sum = prov.merged_raw.get("summarize")
    engine_sum = _parse_summarize(merged_sum or {}) or SummarizeConfig()
    assert engine_sum == resolve_summarize(folder / "f.md", vault_root=root)
    _assert_no_dangling_pointer(folder, root)


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
    _assert_cascade_invariants(sub, tmp_path)
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
    _assert_cascade_invariants(lessons, tmp_path)
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
    _assert_cascade_invariants(zone, tmp_path)
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
    _assert_cascade_invariants(deep, tmp_path)
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
    _assert_cascade_invariants(leaf, tmp_path)
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
    _assert_cascade_invariants(bd, tmp_path)
    _assert_origin_consistency(bd, tmp_path)
    prov = compute_folder_provenance(bd, tmp_path)
    label = "06 - Business Development/Встречи"
    assert prov.origins["/summarize/profile"].origin == label
    assert prov.origins["/summarize/extract_concepts"].origin == label
    assert prov.effective["summarize"]["profile"] == "meeting"


def test_unconfigured_vault_all_defaults(tmp_path: Path) -> None:
    sub = tmp_path / "Anything"
    sub.mkdir()
    _assert_cascade_invariants(sub, tmp_path)
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
    _assert_cascade_invariants(sub, tmp_path)
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


# --------------------------------------------------------------------------- #
# TASK 061 / R-061-4 + R-061-5 — a new key inside a PARSED cascading block
# --------------------------------------------------------------------------- #
#
# The R-058-10 test above (`test_evolution_new_schema_field_needs_no_code`)
# injects a new top-level BLOCK — the case that already works, because
# `_provenance.py`'s `else:` branch passes the merged RAW dict straight through.
# A key added INSIDE an existing parsed block (`summarize` / `resummarize`) took
# the frozen-dataclass path instead, which renders ONLY the dataclass's declared
# fields — so the key vanished from `effective` while `_assign_origins` (walking
# the RAW block) still recorded a provenance pointer for it.
#
# Census of the surfaces a dropped key vanishes from (grep `\.effective`, not a
# claim) — all four are fed by the ONE `compute_folder_provenance` dict:
#   1. `__init__.py:_cmd_show`      → the `show` JSON envelope   (asserted below)
#   2. `_report_md.render_show_report` → the `show --report` md   (asserted below)
#   3. `_report.build_report_model` → the HTML `report` rows      (asserted below)
#   4. `_server.py:/api/folder`     → `serve`'s schema-driven form (same dict;
#      `_app_html.js:fieldState` reads `byPointer(FOLDER.effective, ...)`, so the
#      field renders with a provenance badge but a BLANK value)


def _patch_schema_with_future_knobs(
    schema_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Add a synthetic `future_knob` to the two PARSED cascading blocks
    (`Summarize`, `Resummarize`) and to the NESTED `Detect`, in a copy of the
    shipped schema — then point BOTH independent schema consumers at that copy.

    Census (grep `_SCHEMA_PATH|SYNC_SCHEMA_PATH` across `scripts/`): the sync
    schema has exactly TWO readers, each with its own module-level cache —
    patching one and not the other yields a harness error (a strict-schema
    rejection), not the bug under test.

    | consumer                            | path constant                | cache          |
    |-------------------------------------|------------------------------|----------------|
    | `sync_config._load_validated_raw`   | `sync_config._SCHEMA_PATH`   | `_VALIDATOR`   |
    | `_uimodel.build_ui_model`           | `_uimodel.SYNC_SCHEMA_PATH`  | `_MODEL_CACHE` |
    """
    import scripts.wiki_index.sync_config as sync_config_mod
    import scripts.wiki_skills.wiki_config._uimodel as uimodel_mod

    doc = copy.deepcopy(load_sync_schema_doc())
    for def_name in ("Summarize", "Resummarize", "Detect"):
        doc["$defs"][def_name]["properties"]["future_knob"] = {
            "type": "string",
            "description": "synthetic future knob (TASK 061 gate)",
        }
    schema_copy = schema_dir / "sync-config.schema.yaml"
    schema_copy.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    monkeypatch.setattr(sync_config_mod, "_SCHEMA_PATH", schema_copy)
    monkeypatch.setattr(sync_config_mod, "_VALIDATOR", None)
    monkeypatch.setattr(uimodel_mod, "SYNC_SCHEMA_PATH", schema_copy)
    monkeypatch.setattr(uimodel_mod, "_MODEL_CACHE", None)


def _reachable_pointers(tree: Any, prefix: str = "") -> set[str]:
    """Every JSON pointer that HAS a value in an `effective` tree — interior
    (dict) nodes AND leaves. A `None` block (`resummarize` unconfigured) is a
    leaf: its own pointer is reachable, it has no descendants."""
    out: set[str] = set()
    if isinstance(tree, dict):
        for key, child in tree.items():
            pointer = f"{prefix}/{key}"
            out.add(pointer)
            out |= _reachable_pointers(child, pointer)
    return out


def _assert_no_dangling_pointer(folder: Path, root: Path) -> None:
    """Property 3 (R-061-4): `show` never reports a provenance pointer that has
    no corresponding value in `effective`. Asserted against the pointer set the
    CLI actually emits, so it covers the nearest-ancestor fill in `_cmd_show`."""
    prov = compute_folder_provenance(folder, root)
    dangling = set(prov.origins) - _reachable_pointers(prov.effective)
    assert not dangling, (
        f"provenance pointers with no `effective` value: {sorted(dangling)}")


@pytest.mark.parametrize("pointer,yaml_body", [
    ("/summarize/future_knob", "summarize:\n  future_knob: kept\n"),
    ("/resummarize/future_knob", "resummarize:\n  future_knob: kept\n"),
    # NESTED: a shallow `{**raw, **parsed}` overlay would pass the two above and
    # still fail this one — "the fix covers the block" is exactly the claim this
    # task exists to distrust.
    ("/resummarize/detect/future_knob",
     "resummarize:\n  detect:\n    future_knob: kept\n"),
])
def test_parsed_block_unknown_key_reaches_effective(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pointer: str,
    yaml_body: str,
) -> None:
    """R-061-5: a key the SCHEMA accepts inside a parsed cascading block must
    reach `effective` — and therefore every surface derived from it — even
    though the frozen dataclass knows nothing about it.

    Parametrized over BOTH parsed blocks (`summarize` AND `resummarize`: the
    schema declares exactly two `x-wiki-scope: cascading` keys and BOTH take the
    dataclass path, so both carry the identical drop) plus a nested pointer.
    """
    _patch_schema_with_future_knobs(tmp_path, monkeypatch)
    vault = tmp_path / "vault"
    zone = vault / "Zone"
    zone.mkdir(parents=True)
    _folder_yaml(vault, yaml_body)  # defined at ROOT, read from the SUBFOLDER

    # (1) the `show` envelope — the pointer must resolve to a VALUE, not just to
    #     a provenance entry. THIS is the assertion that must be RED pre-fix.
    code = main(["show", "Zone", "--vault-root", str(vault)])
    envelope = json.loads(capsys.readouterr().out.strip())
    assert code == 0
    effective_pointers = _reachable_pointers(envelope["effective"])
    assert pointer in effective_pointers, (
        f"`effective` dropped {pointer}; `provenance` still points at it "
        f"({pointer in envelope['provenance']}) — a dangling pointer")

    # (2) the value survives the cascade + the parse unmangled.
    block, _, _tail = pointer.lstrip("/").partition("/")
    node: Any = envelope["effective"][block]
    for part in _tail.split("/"):
        node = node[part]
    assert node == "kept"

    # (3) the invariant, on this folder: no pointer without a value.
    assert set(envelope["provenance"]) <= effective_pointers
    _assert_no_dangling_pointer(zone, vault)

    # (4) the RENDERED surfaces (a key missing from `effective` has no row).
    prov = compute_folder_provenance(zone, vault)
    assert pointer in render_show_report(prov, vault)
    assert pointer in render_html(build_report_model(vault, []))


def test_overlay_does_not_become_a_raw_passthrough(tmp_path: Path) -> None:
    """TC-07-2 — the PARSED value still WINS for every field the dataclass
    declares. The overlay preserves raw-only keys; it must not regress into
    handing back the raw dict (which would lose normalisation + injected
    defaults, and silently break the resolver-equivalence contract)."""
    # `target_subdir` is normalised by `_parse_summarize` (strip + drop trailing
    # `/`); the RAW value is "  x/  ". The parsed value must be the one shown.
    _folder_yaml(tmp_path, 'summarize:\n  target_subdir: "  x/  "\n')
    zone = tmp_path / "Zone"
    zone.mkdir()
    _assert_cascade_invariants(zone, tmp_path)
    prov = compute_folder_provenance(zone, tmp_path)
    assert prov.effective["summarize"]["target_subdir"] == "x"
    # ...while the RAW merged block (the equivalence surface) keeps the raw text.
    assert prov.merged_raw["summarize"]["target_subdir"] == "  x/  "
    # parser-injected defaults still appear for fields no level defines.
    assert prov.effective["summarize"]["profile"] == "auto"
    assert prov.effective["summarize"]["extract_concepts"] is True

    # `resummarize.mode`'s default (`if-missing`) still appears when the block is
    # configured but `mode` is not — the defaults jsonschema does NOT inject.
    _folder_yaml(tmp_path, "resummarize:\n  detect:\n    source_state: true\n")
    prov2 = compute_folder_provenance(zone, tmp_path)
    assert prov2.effective["resummarize"]["mode"] == "if-missing"
    assert prov2.origins["/resummarize/mode"].origin == "default"


def test_parsed_block_table_matches_the_schema_cascading_set() -> None:
    """The `_PARSED_BLOCKS` table may only name blocks the SCHEMA actually
    declares `x-wiki-scope: cascading`. A rename on one side and not the other
    would silently drop the block to the raw-passthrough branch, losing its
    parser's normalisation + injected defaults — the same fail-silent class
    R-061-4 fixes, so it gets a gate rather than a comment."""
    from scripts.wiki_skills.wiki_config._provenance import _PARSED_BLOCKS

    cascading = set(top_level_keys(build_ui_model(), SCOPE_CASCADING))
    assert set(_PARSED_BLOCKS) <= cascading, "a parsed block the schema does not cascade"
    # Today every cascading block is ALSO parsed. Stated, not assumed: a future
    # RAW cascading block must be a deliberate choice that updates this line.
    assert set(_PARSED_BLOCKS) == cascading == {"resummarize", "summarize"}


def test_raw_only_key_origin_is_its_level_not_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TC-07-3 — a key carried through the overlay keeps the origin
    `_assign_origins` gave it (the LEVEL that defined it). `_tag_defaults` only
    tags pointers with NO origin, so it must not relabel it `default`."""
    _patch_schema_with_future_knobs(tmp_path, monkeypatch)
    vault = tmp_path / "vault"
    zone = vault / "Zone"
    zone.mkdir(parents=True)
    _folder_yaml(vault, "summarize:\n  profile: article\n  future_knob: from-root\n")
    _folder_yaml(zone, "summarize:\n  future_knob: from-zone\n")

    prov = compute_folder_provenance(zone, vault)
    knob = prov.origins["/summarize/future_knob"]
    assert prov.effective["summarize"]["future_knob"] == "from-zone"
    assert knob.origin == "Zone"          # the level, NOT "default"
    assert knob.shadows == ("root",)      # the cascade still shadows correctly
    # the parsed sibling is unaffected
    assert prov.origins["/summarize/profile"].origin == "root"
    _assert_no_dangling_pointer(zone, vault)
