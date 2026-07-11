"""TASK 058 — `wiki-config serve`: the local web editor (form + YAML tab).

Backend: stdlib `http.server`, SINGLE-THREADED (writes serialize by
construction). Frontend: ONE inline HTML page (vanilla JS, no CDN, CSP) whose
form is rendered at runtime from `GET /api/schema` — the UI model projection of
`config/sync-config.schema.yaml` — so a new schema field appears in the form
with zero changes here (R-058-10).

Security model (R-058-9):
  * bind 127.0.0.1, ephemeral port by default;
  * `secrets.token_hex(32)` shown only in the URL FRAGMENT (never sent in
    requests/Referer/logs); every /api/* call must echo it in the
    `X-Wiki-Config-Token` header, compared via `hmac.compare_digest`;
  * ZERO cookies → no ambient authority → CSRF-immune by construction; plus a
    Host-header allowlist (DNS-rebinding guard) and JSON-only POST bodies;
  * folder ids are vault-relative and re-validated with `validate_inside_vault`;
  * fixes/templates dispatch by id against freshly-computed whitelists — the
    server never executes a client-supplied string and never shells out;
  * every write goes through the SAME ruamel sandwich + backup + TOCTOU path
    as the CLI (`rewrite_text` / `gate_text` / `write_backup`).
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import secrets
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import scripts.wiki_index.layout_config as _lc
from scripts.wiki_index.layout_config import is_pattern_redos_safe
from scripts.wiki_index.security import PathTraversalError, validate_inside_vault
from scripts.wiki_index.sync_config import SyncConfigError

from ._app_html import APP_HTML
from ._backups import (
    WikiDirSymlinkError,
    ensure_wiki_writable,
    list_backups,
    restore_backup,
    write_backup,
)
from ._doctor import apply_plans, build_plans, FixPlan
from ._edit import EditDowngrade, PointerEdit, gate_text, rewrite_text
from ._findings import ConfigFinding, sort_findings
from ._lint import lint_vault
from ._provenance import (
    compute_folder_provenance,
    scan_tree_from_walk,
    walk_vault_tree,
)
from ._templates import discover_templates, render_for_init, SyncTemplate, TemplateError
from ._uimodel import build_ui_model
from scripts.wiki_skills._common import atomic_write_text

_MAX_BODY = 512 * 1024


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _State:
    """Server-side session state. Single-threaded/single-writer by
    construction (module docstring) — cross-request caches below are safe
    because no request can interleave with another; every mutating POST
    handler calls `invalidate()` on success so a cache never outlives the
    state it was computed from."""

    def __init__(self, vault_root: Path, token: str) -> None:
        self.vault_root = vault_root
        self.token = token
        self.allowed_hosts: set[str] = set()
        self._tree_cache: dict[str, Any] | None = None
        self._lint_cache: tuple[list[ConfigFinding], list[FixPlan]] | None = None
        self._templates_cache: dict[str, SyncTemplate] | None = None

    def invalidate(self) -> None:
        self._tree_cache = None
        self._lint_cache = None
        self._templates_cache = None

    def lint_and_plans(self) -> tuple[list[ConfigFinding], list[FixPlan]]:
        if self._lint_cache is None:
            findings, _files_checked = lint_vault(self.vault_root)
            plans, _manual = build_plans(sort_findings(findings), self.vault_root)
            self._lint_cache = (findings, plans)
        return self._lint_cache

    def tree_payload(self) -> dict[str, Any]:
        if self._tree_cache is None:
            walked, truncated = walk_vault_tree(self.vault_root)
            folders = [{"rel": wf.label, "configured": wf.configured}
                      for wf in walked]
            nodes = scan_tree_from_walk(walked)
            self._tree_cache = {
                "vault_root": str(self.vault_root),
                "folders": folders, "truncated": truncated,
                "nodes": [n.to_json() for n in nodes],
            }
        return self._tree_cache

    def templates(self) -> dict[str, SyncTemplate]:
        if self._templates_cache is None:
            self._templates_cache = discover_templates(self.vault_root)
        return self._templates_cache


def _make_handler(state: _State) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "wiki-config"
        protocol_version = "HTTP/1.1"

        # -- plumbing ---------------------------------------------------- #

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass  # never log query strings / bodies

        def _json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            host = self.headers.get("Host", "")
            if host not in state.allowed_hosts:
                return False
            supplied = self.headers.get("X-Wiki-Config-Token", "")
            return hmac.compare_digest(supplied, state.token)

        def _read_json_body(self) -> dict[str, Any] | None:
            if self.headers.get("Content-Type", "").split(";")[0].strip() \
                    != "application/json":
                return None
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return None
            if not 0 < length <= _MAX_BODY:
                return None
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return None
            return payload if isinstance(payload, dict) else None

        def _resolve_rel(self, rel: str) -> Path | None:
            if "\x00" in rel or rel.startswith("/") or rel.startswith("~"):
                return None
            candidate = state.vault_root if rel in (".", "") \
                else state.vault_root / rel
            try:
                resolved = validate_inside_vault(candidate, state.vault_root)
            except (PathTraversalError, OSError):
                return None
            return resolved if resolved.is_dir() else None

        # -- GET ----------------------------------------------------------- #

        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            if url.path == "/":
                body = APP_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'none'; style-src 'unsafe-inline'; "
                    "script-src 'unsafe-inline'; connect-src 'self'")
                self.end_headers()
                self.wfile.write(body)
                return
            if not url.path.startswith("/api/"):
                self._json({"error": "NOT_FOUND"}, 404)
                return
            if not self._authorized():
                self._json({"error": "FORBIDDEN"}, 403)
                return
            if url.path == "/api/schema":
                model = build_ui_model()
                self._json({"fields": [
                    {"pointer": s.pointer, "kind": s.kind, "scope": s.scope,
                     "enum": list(s.enum) if s.enum else None,
                     "default": s.default, "description": s.description,
                     "format": s.fmt, "items_kind": s.items_kind}
                    for s in model.values()
                ]})
                return
            if url.path == "/api/tree":
                self._json(state.tree_payload())
                return
            if url.path == "/api/templates":
                registry = state.templates()
                self._json({"templates": [t.to_json() for t in registry.values()
                                          if t.valid and not t.shadowed]})
                return
            if url.path == "/api/folder":
                rel = parse_qs(url.query).get("rel", ["."])[0]
                folder = self._resolve_rel(rel)
                if folder is None:
                    self._json({"error": "FOLDER_NOT_FOUND"}, 404)
                    return
                self._folder_payload(rel, folder)
                return
            if url.path == "/api/backups":
                rel = parse_qs(url.query).get("rel", ["."])[0]
                folder = self._resolve_rel(rel)
                if folder is None:
                    self._json({"error": "FOLDER_NOT_FOUND"}, 404)
                    return
                self._json({"backups": [
                    {"name": e.name, "size": e.size, "mtime": e.mtime}
                    for e in list_backups(folder)
                ]})
                return
            self._json({"error": "NOT_FOUND"}, 404)

        def _folder_payload(self, rel: str, folder: Path) -> None:
            from ._edit import parse_text_no_schema

            target = folder / ".wiki" / "sync.yaml"
            text = ""
            own: dict[str, Any] | None = None
            if target.is_file() and not target.is_symlink():
                try:
                    text = target.read_text(encoding="utf-8")
                    own = parse_text_no_schema(text)
                except (OSError, SyncConfigError):
                    own = None
            payload: dict[str, Any] = {
                "rel": rel, "text": text,
                "hash": _sha256_text(text) if text else None,
                "own": own,
                "is_root": folder.resolve() == state.vault_root.resolve(),
            }
            try:
                prov = compute_folder_provenance(folder, state.vault_root)
                payload["effective"] = prov.effective
                payload["provenance"] = {
                    p: o.to_json() for p, o in prov.origins.items()}
                payload["warnings"] = prov.warnings
            except SyncConfigError as exc:
                payload["broken"] = {"reason": exc.reason, "detail": exc.detail,
                                     "level": getattr(exc, "level", None)}
            findings, plans = state.lint_and_plans()
            file_rel = ".wiki/sync.yaml" if rel in (".", "") \
                else f"{rel}/.wiki/sync.yaml"
            payload["findings"] = [f.to_json() for f in findings
                                   if f.file == file_rel]
            payload["fix_plans"] = [p.to_json() for p in plans
                                    if p.finding.file == file_rel]
            self._json(payload)

        # -- POST ---------------------------------------------------------- #

        def do_POST(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            if not url.path.startswith("/api/"):
                self._json({"error": "NOT_FOUND"}, 404)
                return
            if not self._authorized():
                self._json({"error": "FORBIDDEN"}, 403)
                return
            body = self._read_json_body()
            if body is None:
                self._json({"error": "BAD_REQUEST",
                            "hint": "JSON body with Content-Type "
                                    "application/json required"}, 400)
                return
            route = {
                "/api/validate": self._post_validate,
                "/api/write": self._post_write,
                "/api/fix": self._post_fix,
                "/api/template": self._post_template,
                "/api/test-regex": self._post_test_regex,
                "/api/delete-config": self._post_delete_config,
                "/api/restore": self._post_restore,
            }.get(url.path)
            if route is None:
                self._json({"error": "NOT_FOUND"}, 404)
                return
            route(body)

        def _post_validate(self, body: dict[str, Any]) -> None:
            text = body.get("text")
            if not isinstance(text, str):
                self._json({"error": "BAD_REQUEST"}, 400)
                return
            try:
                gate_text(text)
                self._json({"ok": True})
            except SyncConfigError as exc:
                self._json({"ok": False, "reason": exc.reason,
                            "detail": exc.detail})

        def _post_write(self, body: dict[str, Any]) -> None:
            rel = str(body.get("rel", "."))
            folder = self._resolve_rel(rel)
            if folder is None:
                self._json({"error": "FOLDER_NOT_FOUND"}, 404)
                return
            try:
                ensure_wiki_writable(folder, state.vault_root)
            except WikiDirSymlinkError:
                self._json({"error": "WIKI_DIR_SYMLINK"}, 409)
                return
            target = folder / ".wiki" / "sync.yaml"
            before = target.read_text(encoding="utf-8") if target.is_file() else ""
            has_expected = "expected_hash" in body
            expected = body.get("expected_hash")
            # An ABSENT key is an opt-out (a scripted caller not tracking
            # drift at all) — unchanged. A key PRESENT with JSON `null` means
            # the client's `BASEHASH` was captured when the folder had NO
            # config yet (_app_html.py: `body.hash` is null exactly then); a
            # file now existing is itself the drift — two tabs both doing
            # "create override" must not silently let the second clobber the
            # first's write.
            if before and has_expected and (
                expected is None
                or (isinstance(expected, str) and expected != _sha256_text(before))
            ):
                self._json({"error": "CONFIG_DRIFTED"}, 409)
                return
            edits_raw = body.get("edits")
            text = body.get("text")
            try:
                if isinstance(edits_raw, list):
                    edits = [
                        PointerEdit(op=str(e.get("op", "")),
                                    pointer=str(e.get("pointer", "")),
                                    value=e.get("value"))
                        for e in edits_raw if isinstance(e, dict)
                    ]
                    if not edits or any(e.op not in ("set", "unset")
                                        for e in edits):
                        self._json({"error": "BAD_REQUEST"}, 400)
                        return
                    after = rewrite_text(before, edits)
                elif isinstance(text, str):
                    gate_text(text)  # full hardened gate on raw-tab saves
                    after = text
                else:
                    self._json({"error": "BAD_REQUEST"}, 400)
                    return
            except SyncConfigError as exc:
                self._json({"error": exc.code, "reason": exc.reason,
                            "detail": exc.detail}, 422)
                return
            except EditDowngrade as exc:
                self._json({"error": "EDIT_REFUSED", "detail": exc.detail}, 422)
                return
            backup = write_backup(folder) if before else None
            (folder / ".wiki").mkdir(parents=True, exist_ok=True)
            atomic_write_text(target, after)
            state.invalidate()
            self._json({"ok": True, "hash": _sha256_text(after),
                        "backup": backup})

        def _post_delete_config(self, body: dict[str, Any]) -> None:
            """Remove a folder's OWN sync.yaml — the folder falls back to the
            inherited cascade. Backed up first (restorable via `wiki-config
            restore` — the backups dir is deliberately kept)."""
            rel = str(body.get("rel", "."))
            folder = self._resolve_rel(rel)
            if folder is None:
                self._json({"error": "FOLDER_NOT_FOUND"}, 404)
                return
            try:
                ensure_wiki_writable(folder, state.vault_root)
            except WikiDirSymlinkError:
                self._json({"error": "WIKI_DIR_SYMLINK"}, 409)
                return
            target = folder / ".wiki" / "sync.yaml"
            if not target.is_file() or target.is_symlink():
                self._json({"error": "NO_CONFIG"}, 404)
                return
            backup = write_backup(folder)
            try:
                target.unlink()
            except OSError:
                self._json({"error": "DELETE_FAILED"}, 409)
                return
            state.invalidate()
            self._json({"ok": True, "backup": backup})

        def _post_restore(self, body: dict[str, Any]) -> None:
            """Restore a folder's sync.yaml from a NAMED backup (the recovery
            path for an accidental delete). The current state — if any — is
            backed up first, so restore is itself reversible."""
            rel = str(body.get("rel", "."))
            folder = self._resolve_rel(rel)
            if folder is None:
                self._json({"error": "FOLDER_NOT_FOUND"}, 404)
                return
            try:
                ensure_wiki_writable(folder, state.vault_root)
            except WikiDirSymlinkError:
                self._json({"error": "WIKI_DIR_SYMLINK"}, 409)
                return
            name = body.get("name")
            if not isinstance(name, str):
                self._json({"error": "BAD_REQUEST"}, 400)
                return
            try:
                restored_from, backup_of_current = restore_backup(folder, name)
            except (FileNotFoundError, ValueError):
                self._json({"error": "BACKUP_NOT_FOUND"}, 404)
                return
            except OSError:
                # restore_backup can fail AFTER write_backup already committed
                # the pre-restore snapshot — don't let the caches survive it
                state.invalidate()
                self._json({"error": "RESTORE_FAILED"}, 409)
                return
            state.invalidate()
            from scripts.wiki_index.sync_config import _load_validated_raw

            valid = True
            try:
                _load_validated_raw(folder)
            except SyncConfigError:
                valid = False
            self._json({"ok": True, "restored_from": restored_from,
                        "backup_of_current": backup_of_current,
                        "restored_file_valid": valid})

        def _post_fix(self, body: dict[str, Any]) -> None:
            plan_id = body.get("id")
            if not isinstance(plan_id, str):
                self._json({"error": "BAD_REQUEST"}, 400)
                return
            _findings, plans = state.lint_and_plans()
            selected = [p for p in plans if p.plan_id == plan_id]
            if not selected:
                self._json({"error": "PLAN_NOT_FOUND"}, 404)
                return
            try:
                results, _diffs, exit_code = apply_plans(
                    state.vault_root, selected, yes=True, dry_run=False,
                    no_backup=False)
            except OSError:
                # an unguarded backup/write inside apply_plans can raise AFTER
                # an earlier file already committed — the caches must not
                # survive a partial mutation (vdd-multi iteration-2 finding)
                state.invalidate()
                self._json({"error": "FIX_FAILED"}, 500)
                return
            state.invalidate()
            self._json({"ok": exit_code == 0,
                        "files": [r.to_json() for r in results]},
                       200 if exit_code == 0 else 409)

        def _post_template(self, body: dict[str, Any]) -> None:
            rel = str(body.get("rel", "."))
            folder = self._resolve_rel(rel)
            if folder is None:
                self._json({"error": "FOLDER_NOT_FOUND"}, 404)
                return
            try:
                ensure_wiki_writable(folder, state.vault_root)
            except WikiDirSymlinkError:
                self._json({"error": "WIKI_DIR_SYMLINK"}, 409)
                return
            name = body.get("template")
            registry = state.templates()
            template = registry.get(str(name))
            if template is None or not template.valid:
                self._json({"error": "TEMPLATE_NOT_FOUND"}, 404)
                return
            is_root = folder.resolve() == state.vault_root.resolve()
            if template.level == "root" and not is_root:
                self._json({"error": "TEMPLATE_LEVEL_MISMATCH"}, 409)
                return
            variables = body.get("vars") or {}
            if not isinstance(variables, dict):
                self._json({"error": "BAD_REQUEST"}, 400)
                return
            target = folder / ".wiki" / "sync.yaml"
            if target.is_file() and not body.get("force"):
                self._json({"error": "CONFIG_EXISTS",
                            "hint": "pass force:true (a backup is taken)"}, 409)
                return
            try:
                rendered = render_for_init(
                    template, {str(k): str(v) for k, v in variables.items()})
                gate_text(rendered)
            except TemplateError as exc:
                self._json({"error": exc.code, **exc.data}, 422)
                return
            except SyncConfigError as exc:
                self._json({"error": exc.code, "reason": exc.reason}, 422)
                return
            backup = write_backup(folder) if target.is_file() else None
            (folder / ".wiki").mkdir(parents=True, exist_ok=True)
            atomic_write_text(target, rendered)
            state.invalidate()
            self._json({"ok": True, "backup": backup,
                        "template": template.name,
                        "version": template.version})

        def _post_test_regex(self, body: dict[str, Any]) -> None:
            from scripts.wiki_skills._resummarize import _compose_key

            pattern = body.get("pattern")
            sample = body.get("sample")
            if not isinstance(pattern, str) or not isinstance(sample, str) \
                    or len(sample) > 512:
                self._json({"error": "BAD_REQUEST"}, 400)
                return
            if not is_pattern_redos_safe(pattern, operator=True):
                self._json({"ok": False,
                            "detail": "pattern is uncompilable or exceeds the "
                                      "ReDoS budget"})
                return
            key = _compose_key(
                Path(sample).stem, pattern, None,
                deadline=time.monotonic() + min(_lc.WIKI_REDOS_BUDGET_S, 2.0))
            self._json({"ok": True, "key": key})

    return Handler


def serve(vault_root: Path, *, port: int = 0,
          open_browser: bool = False,
          started: "list[str] | None" = None) -> HTTPServer:
    """Build (and return) the configured single-threaded server. The caller
    runs `serve_forever()`; tests drive it from a thread. `started` (if given)
    receives the full tokened URL."""
    token = secrets.token_hex(32)
    state = _State(vault_root, token)
    server = HTTPServer(("127.0.0.1", port), _make_handler(state))
    actual_port = server.server_address[1]
    state.allowed_hosts = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}
    url = f"http://127.0.0.1:{actual_port}/#t={token}"
    if started is not None:
        started.append(url)
    if open_browser:  # pragma: no cover
        import webbrowser

        webbrowser.open(url)
    return server


def run_serve(vault_root: Path, *, port: int = 0,
              open_browser: bool = False) -> int:  # pragma: no cover
    import sys

    started: list[str] = []
    server = serve(vault_root, port=port, open_browser=open_browser,
                   started=started)
    # The tokened URL reaches the operator via stderr only; the fragment never
    # appears in any request the server could log.
    print("wiki-config serve — open this URL (Ctrl-C to stop):", file=sys.stderr)
    print(started[0], file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
