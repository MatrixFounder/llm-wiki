"""TASK 058 Phase 6 — `wiki-config serve`: the API contract, exercised against
a real in-process server over http.client. Security first: token auth, Host
allowlist, traversal refusal, sandwich-verified writes with backups."""

from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

import pytest

from scripts.wiki_skills.wiki_config._server import serve


def _folder_yaml(d: Path, text: str) -> None:
    (d / ".wiki").mkdir(parents=True, exist_ok=True)
    (d / ".wiki" / "sync.yaml").write_text(text, encoding="utf-8")


_ROOT = (
    "# root config\n"
    "exclude: ['_inbox/**']\n"
    "resummarize:\n"
    "  mode: if-missing\n"
    "summarize:\n"
    "  profile: article\n"
)


class Client:
    def __init__(self, vault_root: Path) -> None:
        started: list[str] = []
        self.server = serve(vault_root, started=started)
        self.url = urlparse(started[0])
        self.token = started[0].split("#t=")[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()

    def request(self, method: str, path: str, body: dict[str, Any] | None = None,
                *, token: str | None = "auto", host: str | None = None,
                content_type: str = "application/json") -> tuple[int, dict[str, Any]]:
        conn = http.client.HTTPConnection(self.url.hostname or "127.0.0.1",
                                          self.url.port, timeout=10)
        headers: dict[str, str] = {}
        if token == "auto":
            headers["X-Wiki-Config-Token"] = self.token
        elif token:
            headers["X-Wiki-Config-Token"] = token
        if host:
            headers["Host"] = host
        payload = None
        if body is not None:
            payload = json.dumps(body)
            headers["Content-Type"] = content_type
        conn.request(method, path, body=payload, headers=headers)
        response = conn.getresponse()
        raw = response.read().decode("utf-8")
        conn.close()
        try:
            return response.status, json.loads(raw)
        except ValueError:
            return response.status, {"_raw": raw}

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[tuple[Client, Path]]:
    _folder_yaml(tmp_path, _ROOT)
    c = Client(tmp_path)
    try:
        yield c, tmp_path
    finally:
        c.close()


# --------------------------------------------------------------------------- #
# shell + auth
# --------------------------------------------------------------------------- #


def test_root_serves_app_without_token(client: tuple[Client, Path]) -> None:
    c, _ = client
    status, body = c.request("GET", "/", token=None)
    assert status == 200
    assert "wiki-config" in body["_raw"]
    assert "Missing token" in body["_raw"]  # app demands the fragment token


def test_api_requires_token(client: tuple[Client, Path]) -> None:
    c, _ = client
    assert c.request("GET", "/api/tree", token=None)[0] == 403
    assert c.request("GET", "/api/tree", token="deadbeef" * 8)[0] == 403
    assert c.request("GET", "/api/tree")[0] == 200


def test_host_header_allowlist_blocks_dns_rebinding(
    client: tuple[Client, Path]
) -> None:
    c, _ = client
    status, _body = c.request("GET", "/api/tree", host="evil.example:80")
    assert status == 403


def test_post_requires_json_content_type(client: tuple[Client, Path]) -> None:
    c, _ = client
    status, _ = c.request("POST", "/api/validate", {"text": "zones: []\n"},
                          content_type="text/plain")
    assert status == 400


# --------------------------------------------------------------------------- #
# read endpoints
# --------------------------------------------------------------------------- #


def test_schema_endpoint_is_ui_model(client: tuple[Client, Path]) -> None:
    c, _ = client
    status, body = c.request("GET", "/api/schema")
    assert status == 200
    fields = {f["pointer"]: f for f in body["fields"]}
    assert fields["/summarize/profile"]["enum"] == ["auto", "meeting", "lesson",
                                                    "article"]
    assert fields["/zones"]["scope"] == "root-only"
    assert fields["/resummarize/detect/mirror/group_key"]["format"] == "regex"
    assert fields["/summarize/profile"]["description"]  # hints present


def test_folder_endpoint_effective_own_and_hash(
    client: tuple[Client, Path]
) -> None:
    c, root = client
    zone = root / "Zone"
    _folder_yaml(zone, "summarize:\n  profile: meeting\n")
    status, body = c.request("GET", "/api/folder?rel=Zone")
    assert status == 200
    assert body["own"] == {"summarize": {"profile": "meeting"}}
    assert body["effective"]["summarize"]["profile"] == "meeting"
    assert body["provenance"]["/summarize/profile"]["origin"] == "Zone"
    assert body["provenance"]["/resummarize/mode"]["origin"] == "root"
    assert body["hash"] and body["is_root"] is False


def test_folder_traversal_refused(client: tuple[Client, Path]) -> None:
    c, _ = client
    assert c.request("GET", "/api/folder?rel=..%2F..")[0] == 404
    assert c.request("GET", "/api/folder?rel=%2Fetc")[0] == 404


def test_templates_endpoint(client: tuple[Client, Path]) -> None:
    c, _ = client
    status, body = c.request("GET", "/api/templates")
    assert status == 200
    names = {t["name"] for t in body["templates"]}
    assert "meeting-zone" in names and "lessons-mirror" in names


# --------------------------------------------------------------------------- #
# write path (the sandwich over HTTP)
# --------------------------------------------------------------------------- #


def test_write_edits_preserves_comments_and_backs_up(
    client: tuple[Client, Path]
) -> None:
    c, root = client
    _status, folder = c.request("GET", "/api/folder?rel=.")
    status, body = c.request("POST", "/api/write", {
        "rel": ".",
        "edits": [{"op": "set", "pointer": "/summarize/profile",
                   "value": "meeting"}],
        "expected_hash": folder["hash"],
    })
    assert status == 200 and body["ok"] is True and body["backup"]
    text = (root / ".wiki" / "sync.yaml").read_text(encoding="utf-8")
    assert "# root config" in text          # comment preserved (ruamel sandwich)
    assert "profile: meeting" in text
    assert (root / ".wiki" / "backups").is_dir()


def test_write_rejects_invalid_result_nothing_written(
    client: tuple[Client, Path]
) -> None:
    c, root = client
    before = (root / ".wiki" / "sync.yaml").read_text(encoding="utf-8")
    status, body = c.request("POST", "/api/write", {
        "rel": ".",
        "edits": [{"op": "set", "pointer": "/summarize/profile",
                   "value": "bogus"}],
    })
    assert status == 422
    assert (root / ".wiki" / "sync.yaml").read_text(encoding="utf-8") == before
    assert "bogus" not in json.dumps(body)  # CWE-209


def test_write_toctou_drift_409(client: tuple[Client, Path]) -> None:
    c, root = client
    _status, folder = c.request("GET", "/api/folder?rel=.")
    _folder_yaml(root, _ROOT + "# drifted\n")
    status, body = c.request("POST", "/api/write", {
        "rel": ".", "text": "summarize:\n  profile: auto\n",
        "expected_hash": folder["hash"],
    })
    assert status == 409 and body["error"] == "CONFIG_DRIFTED"


def test_write_null_expected_hash_onto_now_existing_file_drifts(
    client: tuple[Client, Path]
) -> None:
    """Finding 2a: `expected_hash: null` means the client's tab loaded a
    folder with NO config yet — a config now existing (a second tab's
    concurrent "create override") must still 409, not silently overwrite."""
    c, root = client
    zone = root / "TwoTabs"
    zone.mkdir()
    _status, folder = c.request("GET", "/api/folder?rel=TwoTabs")
    assert folder["hash"] is None  # no config at load
    # a concurrent write lands first
    status, _ = c.request("POST", "/api/write", {
        "rel": "TwoTabs",
        "edits": [{"op": "set", "pointer": "/summarize/profile", "value": "auto"}],
    })
    assert status == 200
    # the first tab's save, still carrying its stale null baseline
    status, body = c.request("POST", "/api/write", {
        "rel": "TwoTabs",
        "edits": [{"op": "set", "pointer": "/summarize/profile", "value": "lesson"}],
        "expected_hash": None,
    })
    assert status == 409 and body["error"] == "CONFIG_DRIFTED"
    assert "profile: auto" in (zone / ".wiki" / "sync.yaml").read_text(
        encoding="utf-8")  # the concurrent write survives untouched


def test_write_raw_yaml_gated(client: tuple[Client, Path]) -> None:
    c, root = client
    status, _ = c.request("POST", "/api/write",
                          {"rel": ".", "text": "zonez: []\n"})
    assert status == 422  # schema-refused
    status, body = c.request("POST", "/api/validate", {"text": "zonez: []\n"})
    assert status == 200 and body["ok"] is False and body["reason"] == "SCHEMA"


def test_fix_endpoint_whitelist_dispatch(client: tuple[Client, Path]) -> None:
    c, root = client
    zone = root / "Zone"
    _folder_yaml(zone, "summarize:\n  profile: meting\n")
    _status, folder = c.request("GET", "/api/folder?rel=Zone")
    plans = folder["fix_plans"]
    assert plans and plans[0]["code"] == "SCHEMA_VIOLATION_ENUM"
    status, body = c.request("POST", "/api/fix", {"id": plans[0]["id"]})
    assert status == 200 and body["ok"] is True
    assert "profile: meeting" in (zone / ".wiki" / "sync.yaml").read_text(
        encoding="utf-8")
    # unknown plan id → 404, nothing executed
    assert c.request("POST", "/api/fix", {"id": "NOPE:x:y"})[0] == 404


def test_template_endpoint_level_and_exists_guards(
    client: tuple[Client, Path]
) -> None:
    c, root = client
    zone = root / "New Zone"
    zone.mkdir()
    status, _ = c.request("POST", "/api/template",
                          {"rel": "New Zone", "template": "root-baseline"})
    assert status == 409  # level mismatch
    status, body = c.request("POST", "/api/template",
                             {"rel": "New Zone", "template": "meeting-zone"})
    assert status == 200 and body["ok"] is True
    assert (zone / ".wiki" / "sync.yaml").is_file()
    # existing file without force → 409
    status, _ = c.request("POST", "/api/template",
                          {"rel": "New Zone", "template": "article-zone"})
    assert status == 409
    # with force → replaced, backup taken (the UI 're-init from template' path)
    status, body = c.request("POST", "/api/template",
                             {"rel": "New Zone", "template": "article-zone",
                              "force": True})
    assert status == 200 and body["ok"] is True and body["backup"]
    text = (zone / ".wiki" / "sync.yaml").read_text(encoding="utf-8")
    assert "article-zone" in text and (zone / ".wiki" / "backups").is_dir()


def test_cross_request_caches_invalidate_on_every_mutating_post(
    client: tuple[Client, Path]
) -> None:
    """Finding 2b: `/api/tree`, `/api/folder` findings/fix_plans, and
    `/api/templates` are cached on `_State` between requests — every mutating
    handler must invalidate ALL of them, or a later GET serves stale data."""
    c, root = client
    zone = root / "Zone9"
    zone.mkdir()

    # /api/tree cache: populate, then mutate via /api/write, must see the
    # new configured folder — not the cached pre-write snapshot.
    _status, tree_before = c.request("GET", "/api/tree")
    before_entry = next(f for f in tree_before["folders"] if f["rel"] == "Zone9")
    assert before_entry["configured"] is False
    status, _ = c.request("POST", "/api/write", {
        "rel": "Zone9",
        "edits": [{"op": "set", "pointer": "/summarize/profile", "value": "auto"}],
    })
    assert status == 200
    _status, tree_after = c.request("GET", "/api/tree")
    after_entry = next(f for f in tree_after["folders"] if f["rel"] == "Zone9")
    assert after_entry["configured"] is True

    # /api/folder findings+fix_plans cache: populate with a fixable finding,
    # then /api/fix it, must see the finding GONE afterwards.
    bad = root / "Zone10"
    _folder_yaml(bad, "summarize:\n  profile: meting\n")  # SCHEMA_VIOLATION_ENUM
    _status, folder_before = c.request("GET", "/api/folder?rel=Zone10")
    assert folder_before["fix_plans"]
    plan_id = folder_before["fix_plans"][0]["id"]
    status, fix_body = c.request("POST", "/api/fix", {"id": plan_id})
    assert status == 200 and fix_body["ok"] is True
    _status, folder_after = c.request("GET", "/api/folder?rel=Zone10")
    assert folder_after["findings"] == []
    assert folder_after["fix_plans"] == []

    # /api/templates cache: seed it BEFORE the vault template exists, then
    # drop one on disk — a stale read must still miss it — and only AFTER a
    # mutating POST invalidates the cache does it appear.
    _status, templates_seed = c.request("GET", "/api/templates")
    assert "custom-zone" not in {t["name"] for t in templates_seed["templates"]}
    vdir = root / ".wiki" / "templates"
    vdir.mkdir(parents=True)
    (vdir / "custom.yaml").write_text(
        "# wiki-config template: custom-zone v0.1.0\n"
        "# level: any\n"
        "# purpose: cache-invalidation regression fixture\n"
        "summarize:\n  profile: auto\n",
        encoding="utf-8")
    _status, templates_stale = c.request("GET", "/api/templates")
    assert "custom-zone" not in {t["name"] for t in templates_stale["templates"]}
    status, _ = c.request("POST", "/api/write", {
        "rel": "Zone9",
        "edits": [{"op": "set", "pointer": "/summarize/profile", "value": "lesson"}],
    })
    assert status == 200
    _status, templates_fresh = c.request("GET", "/api/templates")
    assert "custom-zone" in {t["name"] for t in templates_fresh["templates"]}


def test_symlinked_wiki_dir_refused_on_every_mutating_endpoint(
    client: tuple[Client, Path]
) -> None:
    """Finding 1b: a pre-planted `.wiki -> outside-dir` symlink must not let
    write/delete/restore/template redirect outside the vault (CWE-59) — every
    mutating handler now runs the SAME `ensure_wiki_writable` choke point."""
    import os

    c, root = client
    zone = root / "Symlinked"
    zone.mkdir()
    outside = root.parent / "outside-symlink-target"
    outside.mkdir()
    os.symlink(outside, zone / ".wiki")

    write_status, write_body = c.request("POST", "/api/write", {
        "rel": "Symlinked",
        "edits": [{"op": "set", "pointer": "/summarize/profile", "value": "auto"}],
    })
    assert write_status == 409 and write_body["error"] == "WIKI_DIR_SYMLINK"

    template_status, template_body = c.request("POST", "/api/template", {
        "rel": "Symlinked", "template": "meeting-zone"})
    assert template_status == 409 and template_body["error"] == "WIKI_DIR_SYMLINK"

    delete_status, delete_body = c.request(
        "POST", "/api/delete-config", {"rel": "Symlinked"})
    assert delete_status == 409 and delete_body["error"] == "WIKI_DIR_SYMLINK"

    restore_status, restore_body = c.request(
        "POST", "/api/restore", {"rel": "Symlinked", "name": "sync.yaml.x.bak"})
    assert restore_status == 409 and restore_body["error"] == "WIKI_DIR_SYMLINK"

    # nothing was ever written into (or read out of) the outside target
    assert list(outside.iterdir()) == []


def test_symlinked_leaf_refused_via_template_endpoint(
    client: tuple[Client, Path]
) -> None:
    """The logic critic's gap: `_post_template` (unlike `_post_write`) carried
    NO leaf-symlink guard at all before finding 1b's shared choke point."""
    import os

    c, root = client
    zone = root / "LeafSymlinked"
    (zone / ".wiki").mkdir(parents=True)
    outside_file = root.parent / "planted.yaml"
    outside_file.write_text("summarize:\n  profile: article\n", encoding="utf-8")
    os.symlink(outside_file, zone / ".wiki" / "sync.yaml")

    status, body = c.request("POST", "/api/template",
                             {"rel": "LeafSymlinked", "template": "meeting-zone",
                              "force": True})
    assert status == 409 and body["error"] == "WIKI_DIR_SYMLINK"
    # the planted file outside the vault was never touched
    assert outside_file.read_text(encoding="utf-8") == "summarize:\n  profile: article\n"


def test_tree_lists_full_hierarchy_with_configured_flags(
    client: tuple[Client, Path]
) -> None:
    c, root = client
    (root / "Plain" / "Deeper").mkdir(parents=True)
    zone = root / "Zone"
    _folder_yaml(zone, "summarize:\n  profile: meeting\n")
    status, body = c.request("GET", "/api/tree")
    assert status == 200
    flags = {f["rel"]: f["configured"] for f in body["folders"]}
    assert flags["."] is True and flags["Zone"] is True
    assert flags["Plain"] is False and flags["Plain/Deeper"] is False


def test_write_on_unconfigured_folder_creates_override(
    client: tuple[Client, Path]
) -> None:
    c, root = client
    plain = root / "Plain"
    plain.mkdir(exist_ok=True)
    status, body = c.request("POST", "/api/write", {
        "rel": "Plain",
        "edits": [{"op": "set", "pointer": "/summarize/profile",
                   "value": "lesson"}],
    })
    assert status == 200 and body["backup"] is None  # nothing existed to back up
    assert "profile: lesson" in (plain / ".wiki" / "sync.yaml").read_text(
        encoding="utf-8")


def test_delete_config_falls_back_to_inherited(
    client: tuple[Client, Path]
) -> None:
    c, root = client
    zone = root / "Zone2"
    _folder_yaml(zone, "summarize:\n  profile: meeting\n")
    _status, before = c.request("GET", "/api/folder?rel=Zone2")
    assert before["effective"]["summarize"]["profile"] == "meeting"
    status, body = c.request("POST", "/api/delete-config", {"rel": "Zone2"})
    assert status == 200 and body["ok"] is True and body["backup"]
    assert not (zone / ".wiki" / "sync.yaml").exists()
    assert (zone / ".wiki" / "backups").is_dir()  # restorable
    _status, after = c.request("GET", "/api/folder?rel=Zone2")
    assert after["own"] is None
    assert after["effective"]["summarize"]["profile"] == "article"  # ← root
    # second delete → 404 NO_CONFIG; traversal refused
    assert c.request("POST", "/api/delete-config", {"rel": "Zone2"})[0] == 404
    assert c.request("POST", "/api/delete-config", {"rel": "../.."})[0] == 404


def test_backups_list_and_restore_after_accidental_delete(
    client: tuple[Client, Path]
) -> None:
    """The accidental-delete recovery loop: edit (backup #1) → delete
    (backup #2) → list shows BOTH, newest first → restore a CHOSEN one
    byte-exact; bogus names refused."""
    c, root = client
    zone = root / "Zone3"
    original = "# precious\nsummarize:\n  profile: meeting\n"
    _folder_yaml(zone, original)
    # edit → backup #1 (of the original)
    status, _ = c.request("POST", "/api/write", {
        "rel": "Zone3",
        "edits": [{"op": "set", "pointer": "/summarize/profile",
                   "value": "lesson"}]})
    assert status == 200
    edited = (zone / ".wiki" / "sync.yaml").read_text(encoding="utf-8")
    # delete → backup #2 (of the edited state)
    status, _ = c.request("POST", "/api/delete-config", {"rel": "Zone3"})
    assert status == 200
    assert not (zone / ".wiki" / "sync.yaml").exists()
    # list: both backups, newest (the edited state) first
    status, body = c.request("GET", "/api/backups?rel=Zone3")
    assert status == 200 and len(body["backups"]) == 2
    names = [b["name"] for b in body["backups"]]
    assert all(n.startswith("sync.yaml.") for n in names)
    # restore the OLDER one (the pristine original) — user's choice honored
    status, body = c.request("POST", "/api/restore",
                             {"rel": "Zone3", "name": names[-1]})
    assert status == 200 and body["ok"] is True
    assert body["restored_file_valid"] is True
    restored = (zone / ".wiki" / "sync.yaml").read_text(encoding="utf-8")
    assert restored == original and restored != edited
    # bogus / traversal-shaped names are refused
    assert c.request("POST", "/api/restore",
                     {"rel": "Zone3", "name": "no-such.bak"})[0] == 404
    assert c.request("POST", "/api/restore",
                     {"rel": "Zone3", "name": "../../evil"})[0] == 404
    # a folder with no backups → empty list
    (root / "Fresh").mkdir()
    status, body = c.request("GET", "/api/backups?rel=Fresh")
    assert status == 200 and body["backups"] == []


def test_regex_tester(client: tuple[Client, Path]) -> None:
    c, _ = client
    status, body = c.request("POST", "/api/test-regex",
                             {"pattern": "^(\\d{8})",
                              "sample": "20260326-01 lesson.vtt"})
    assert status == 200 and body["ok"] is True and body["key"] == "20260326"
    status, body = c.request("POST", "/api/test-regex",
                             {"pattern": "^(a|a)+$", "sample": "aaaa"})
    assert status == 200 and body["ok"] is False


def test_symlinked_backups_dir_refused_on_mutating_endpoints(
    client: tuple[Client, Path]
) -> None:
    """vdd-multi iteration-2 (security): `.wiki` and `sync.yaml` are real, but
    `.wiki/backups -> outside` — write_backup/prune/restore would write, delete
    and read THROUGH the symlink (CWE-59 one level down). Every mutating
    endpoint must refuse before touching the path."""
    import os

    c, root = client
    zone = root / "BackupsLinked"
    _folder_yaml(zone, "summarize:\n  profile: article\n")
    outside = root.parent / "outside-backups-target"
    outside.mkdir()
    os.symlink(outside, zone / ".wiki" / "backups")

    _status, folder = c.request("GET", "/api/folder?rel=BackupsLinked")
    status, body = c.request("POST", "/api/write", {
        "rel": "BackupsLinked",
        "expected_hash": folder["hash"],
        "edits": [{"op": "set", "pointer": "/summarize/profile",
                   "value": "meeting"}],
    })
    assert status == 409 and body["error"] == "WIKI_DIR_SYMLINK"
    status, body = c.request("POST", "/api/delete-config",
                             {"rel": "BackupsLinked"})
    assert status == 409 and body["error"] == "WIKI_DIR_SYMLINK"
    status, body = c.request("POST", "/api/restore",
                             {"rel": "BackupsLinked", "name": "sync.yaml.x.bak"})
    assert status == 409 and body["error"] == "WIKI_DIR_SYMLINK"
    # nothing was written into (or deleted from) the outside target, and the
    # live config is untouched
    assert list(outside.iterdir()) == []
    assert (zone / ".wiki" / "sync.yaml").read_text(encoding="utf-8") \
        == "summarize:\n  profile: article\n"


def test_fix_oserror_after_partial_apply_invalidates_caches(
    client: tuple[Client, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """vdd-multi iteration-2 (logic): an OSError propagating out of
    `apply_plans` AFTER an earlier file already committed must not leave the
    `_State` caches stale — the handler answers 500 and invalidates."""
    import scripts.wiki_skills.wiki_config._server as server_mod

    c, root = client
    bad = root / "ZoneOsError"
    _folder_yaml(bad, "summarize:\n  profile: meting\n")  # enum typo → fixable
    _status, folder = c.request("GET", "/api/folder?rel=ZoneOsError")
    assert folder["fix_plans"]
    plan_id = folder["fix_plans"][0]["id"]

    # populate the tree cache, then change the disk BEHIND the server's back —
    # a cached read must still miss it (proves the cache is live)
    _status, _tree = c.request("GET", "/api/tree")
    sneaky = root / "SneakyZone"
    _folder_yaml(sneaky, "summarize:\n  profile: article\n")
    _status, tree_stale = c.request("GET", "/api/tree")
    assert not any(f["rel"] == "SneakyZone" for f in tree_stale["folders"])

    real_apply = server_mod.apply_plans

    def _boom(*args: object, **kwargs: object) -> object:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(server_mod, "apply_plans", _boom)
    status, body = c.request("POST", "/api/fix", {"id": plan_id})
    assert status == 500 and body["error"] == "FIX_FAILED"
    monkeypatch.setattr(server_mod, "apply_plans", real_apply)

    # the failed fix invalidated the caches → the next tree read recomputes
    # and sees the direct-disk change
    _status, tree_fresh = c.request("GET", "/api/tree")
    fresh_entry = next(f for f in tree_fresh["folders"]
                       if f["rel"] == "SneakyZone")
    assert fresh_entry["configured"] is True
