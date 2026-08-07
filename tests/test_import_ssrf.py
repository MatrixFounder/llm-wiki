"""TASK 072 P1b — the two egress call sites must go through a GUARDED fetch, not bare `urlopen`.

`_fetch.py` had exactly two outbound HTTP sites (`_download_pdf`, `_download_raw_html`), both
`urllib.request.urlopen`, both carrying `# noqa: S310 (operator URL)`. That justification was
falsified twice over:

  * `/wiki-reload` re-fetches a URL taken out of a note's OWN frontmatter — that is H-6 **data**,
    not operator input; and
  * urllib follows 30x silently, so every hop after hop 0 is attacker-chosen regardless of who
    typed hop 0.

The guard is not re-implemented here. It lives in the external `html` skill's fetch ladder
(resolve → pin → assert-public → bounded read), and this suite proves our call sites actually go
THROUGH it, end-to-end, in a real subprocess.

★ WHY THE POSITIVE CONTROL IS THE POINT (Rule 4). A refusal suite that only ever feeds hostile
input cannot distinguish a working guard from a `return False`. Every refusal case here is paired
with the SAME url passing when `HTML_SSRF_ALLOW_NETS` arms the exception — same corpus, same rule,
opposite verdict. That is the discrimination control, and it runs fully offline against a
localhost server: no external network, no flakiness, nothing skipped.

★ NOTHING HERE SKIPS. If the external skill is missing, these tests FAIL as a dependency error.
A skipped guard test is a vacuous green — the failure mode this whole task exists to remove.
"""

from __future__ import annotations

import ast
import http.server
import os
import socketserver
import subprocess
import threading
from pathlib import Path

import pytest

from scripts.wiki_skills.wiki_import_article import _fetch
from scripts.wiki_skills.wiki_import_article._errors import ImportArticleError

_LOOPBACK_NET = "127.0.0.0/8"

#: Hostile targets a guard must refuse WITHOUT any external network. Each is a real SSRF class.
_HOSTILE = [
    ("loopback", "http://127.0.0.1:9/x"),
    ("rfc1918", "http://10.0.0.1/x"),
    ("link-local-metadata", "http://169.254.169.254/latest/meta-data/"),
    ("ipv6-loopback", "http://[::1]:9/x"),
    ("non-http-scheme", "file:///etc/passwd"),
]


# ------------------------------------------------------------------------------------------
# Dependency — a FAILURE, never a skip.
# ------------------------------------------------------------------------------------------

def test_the_guarded_launcher_is_resolvable_and_supports_the_verb() -> None:
    """If this fails, every test below is meaningless — so it fails loudly instead of skipping."""
    launcher = _fetch.resolve_skill_bin("html_launcher")
    assert Path(launcher).expanduser().exists(), (
        f"html launcher not found at {launcher!r}. This is a DEPENDENCY failure, not a reason to "
        "skip: without it the two egress sites have no guard. Install the `html` skill or set "
        "$WIKI_HTML_LAUNCHER_BIN."
    )
    helptext = subprocess.run(
        [str(Path(launcher).expanduser()), "--help"],
        capture_output=True, text=True, timeout=60).stdout
    # ★ The probe string is `html get URL`, NOT a bare `get`: a bare grep matches
    # `--target-selector` and would make a fail-CLOSED probe fail OPEN.
    assert "html get URL" in helptext, (
        "the installed `html` skill has no raw-bytes `get` verb (TASK 072 / Q-072-1 = B). "
        "Update the skill; do NOT fall back to urlopen."
    )


# ------------------------------------------------------------------------------------------
# Structural — the guard cannot be bypassed by a future edit.
# ------------------------------------------------------------------------------------------

def _urlopen_calls(path: Path) -> list[int]:
    """Line numbers of every `urlopen(...)` call in a module, by AST (not grep: the docstrings in
    this very file mention `urlopen`, and a grep-based guard would match its own prose)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
            if name == "urlopen":
                out.append(node.lineno)
    return out


def test_fetch_module_makes_no_bare_urlopen_call() -> None:
    src = Path(_fetch.__file__)
    calls = _urlopen_calls(src)
    assert not calls, (
        f"{src.name} still calls urlopen at line(s) {calls} — an unguarded egress site. "
        "Route it through the `html get` verb via resolve_skill_bin('html_launcher')."
    )


def test_the_structural_guard_can_actually_fire(tmp_path: Path) -> None:
    """Mutation control: the AST scanner must see a urlopen call when one exists."""
    probe = tmp_path / "probe.py"
    probe.write_text("import urllib.request\nx = urllib.request.urlopen('http://x')\n", encoding="utf-8")
    assert _urlopen_calls(probe) == [2]
    probe.write_text("# urlopen mentioned only in a comment\n", encoding="utf-8")
    assert _urlopen_calls(probe) == []


# ------------------------------------------------------------------------------------------
# End-to-end through the ACTUAL call sites.
# ------------------------------------------------------------------------------------------

class _Handler(http.server.BaseHTTPRequestHandler):
    body = b"<html><iframe src='https://www.youtube.com/embed/OK'></iframe></html>"
    redirect_to: str | None = None

    def do_GET(self) -> None:
        if self.redirect_to:
            self.send_response(302)
            self.send_header("Location", self.redirect_to)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *a: object) -> None:  # silence the test log
        pass


@pytest.fixture()
def local_server():
    """A real HTTP server on loopback. Loopback is PRIVATE, so the guard refuses it by default —
    which is exactly what makes it a two-sided control: arm `HTML_SSRF_ALLOW_NETS` and the same
    URL must succeed."""
    srv = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}/page"
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture()
def unarmed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard armed: no allow-net exception, whatever the developer's shell has set."""
    monkeypatch.delenv("HTML_SSRF_ALLOW_NETS", raising=False)


@pytest.mark.parametrize("label,url", _HOSTILE, ids=[c[0] for c in _HOSTILE])
def test_raw_html_download_refuses_hostile_targets(label: str, url: str, unarmed: None) -> None:
    """SIGNAL — every hostile class refused, through the real `_download_raw_html`."""
    with pytest.raises(ImportArticleError) as exc:
        _fetch._download_raw_html(url)
    assert exc.value.code in {"FETCH_FAILED", "DEPENDENCY_MISSING"}
    assert exc.value.code != "DEPENDENCY_MISSING", (
        f"{label}: refused for the WRONG reason (missing dependency, not a guard decision)")


@pytest.mark.parametrize("label,url", _HOSTILE, ids=[c[0] for c in _HOSTILE])
def test_pdf_download_refuses_hostile_targets(label: str, url: str, unarmed: None) -> None:
    """SIGNAL — the same classes refused through the real `_download_pdf`."""
    with pytest.raises(ImportArticleError) as exc:
        _fetch._download_pdf(url)
    assert exc.value.code != "DEPENDENCY_MISSING", (
        f"{label}: refused for the WRONG reason (missing dependency, not a guard decision)")


def test_raw_html_download_refuses_loopback_by_default(local_server: str, unarmed: None) -> None:
    """SIGNAL half of the control — a LIVE, reachable server is still refused because it is private."""
    with pytest.raises(ImportArticleError):
        _fetch._download_raw_html(local_server)


def test_raw_html_download_succeeds_when_the_guard_permits_the_net(
        local_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """★ CONTROL half — the SAME url, the SAME code path, permitted. Without this, every refusal
    above is equally consistent with a guard that refuses everything."""
    monkeypatch.setenv("HTML_SSRF_ALLOW_NETS", _LOOPBACK_NET)
    body = _fetch._download_raw_html(local_server)
    assert "youtube.com/embed/OK" in body, f"guard permitted but no bytes came back: {body[:200]!r}"


def test_pdf_download_succeeds_when_the_guard_permits_the_net(
        local_server: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """CONTROL half for the PDF site — proves it too is routed, not merely refusing."""
    monkeypatch.setenv("HTML_SSRF_ALLOW_NETS", _LOOPBACK_NET)
    out = _fetch._download_pdf(local_server)
    try:
        assert out.exists() and out.stat().st_size > 0
        assert b"youtube.com/embed/OK" in out.read_bytes()
    finally:
        out.unlink(missing_ok=True)


def test_redirect_to_a_private_host_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """★ The case the old `# noqa: S310 (operator URL)` justification could not survive: hop 0 is
    permitted, hop 1 is attacker-chosen. urllib followed this silently."""
    class _Redirector(_Handler):
        redirect_to = "http://169.254.169.254/latest/meta-data/"

    srv = socketserver.TCPServer(("127.0.0.1", 0), _Redirector)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/redir"
    try:
        # hop 0 permitted (loopback allowed); hop 1 is link-local and must still be refused.
        monkeypatch.setenv("HTML_SSRF_ALLOW_NETS", _LOOPBACK_NET)
        with pytest.raises(ImportArticleError):
            _fetch._download_raw_html(url)
    finally:
        srv.shutdown()
        srv.server_close()


def test_oversize_page_is_reported_not_silently_truncated(
        monkeypatch: pytest.MonkeyPatch, local_server: str) -> None:
    """★ The deliberate behaviour change, asserted so it cannot regress to a silent prefix scan.

    The old code read 2 MiB and scanned the PREFIX. A regex over a truncated document can split an
    `<iframe` tag across the boundary and silently lose (or mangle) an embed — a wrong answer
    reported as a complete one. Over-cap is now an explicit refusal that the caller logs.
    """
    monkeypatch.setenv("HTML_SSRF_ALLOW_NETS", _LOOPBACK_NET)
    monkeypatch.setattr(_fetch, "_EMBED_FETCH_MAX_BYTES", 8)  # smaller than the served body
    with pytest.raises(ImportArticleError) as exc:
        _fetch._download_raw_html(local_server)
    assert exc.value.details.get("kind") == "too-large", exc.value.details
