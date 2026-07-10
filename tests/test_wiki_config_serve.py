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


def test_regex_tester(client: tuple[Client, Path]) -> None:
    c, _ = client
    status, body = c.request("POST", "/api/test-regex",
                             {"pattern": "^(\\d{8})",
                              "sample": "20260326-01 lesson.vtt"})
    assert status == 200 and body["ok"] is True and body["key"] == "20260326"
    status, body = c.request("POST", "/api/test-regex",
                             {"pattern": "^(a|a)+$", "sample": "aaaa"})
    assert status == 200 and body["ok"] is False
