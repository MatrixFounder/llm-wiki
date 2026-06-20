#!/usr/bin/env python3
"""obsidian-active-note — resolve the focused / open Obsidian note to an explicit path.

Skill-local deterministic resolver for the ``obsidian-cli`` active-note resolution protocol
(TASK 041 / ADR-008). Vendor-agnostic: a plain stdlib executable any LLM CLI (Claude Code,
Codex, Gemini, pi, hermes, …) can shell out to. **No** ``import anthropic``; **stdlib only**.

It turns the live Obsidian app's active-file / open-tab state into an EXPLICIT path so the
agent can then carry an explicit ``path=`` on the actual mutation (never the CLI's implicit
active-file default — ADR-008 keeps the E-11 footgun guard).

Modes (subcommands):
  focused                  resolve the active/focused note  (bare-reference / MEDIUM branch)
  tabs                     list OPEN markdown tabs (title + view-type) for descriptor matching
  resolve --title "<T>"    resolve an open-tab title to a path (descriptor branch, step 2)
  match --descriptor "<d>" descriptor → unique open note + vault-unique basename (HIGH) | else (LOW ask)

Exit codes (see ``EXIT_*``):
  0 ok · 2 usage · 3 no-active-file · 4 app-not-running · 5 cli-absent ·
  6 vault-mismatch · 7 ambiguous · 8 headless

WRONG-TARGET GUARD (TASK 041 critic F-1): ``obsidian file file=<title>`` resolves a title
*wikilink-style across the whole vault* — it is NOT pinned to the open tab. So ``match``
verifies the resolved file's basename is **unique in the vault** (``obsidian files ext=md``);
if another file shares that basename the resolve cannot be proven to be the open tab → it
**fails to AMBIGUOUS (→ ASK)** rather than mutating a possibly-wrong file silently.

Headless note (ADR-008 / arch-review M-3): the wrapper NEVER auto-probes for headless — any
``obsidian`` subcommand would launch the GUI. The CALLER decides headless from the environment
*before* invoking the wrapper. ``EXIT_HEADLESS`` fires only as belt-and-braces when the caller
sets ``WIKI_HEADLESS=1``.

Descriptor matching note: ``match_descriptor`` is a deterministic case-insensitive
token-substring guard (len==1 → HIGH, len!=1 → LOW). Cross-language / semantic matching of a
descriptor to a note title is the calling agent's job (it can read ``tabs`` output and reason);
the wrapper guarantees only that an ambiguous or empty match never resolves to a silent target.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# ── exit codes ────────────────────────────────────────────────────────────────
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NO_ACTIVE_FILE = 3
EXIT_APP_NOT_RUNNING = 4
EXIT_CLI_ABSENT = 5
EXIT_VAULT_MISMATCH = 6
EXIT_AMBIGUOUS = 7
EXIT_HEADLESS = 8

_ERROR_PREFIX = "Error:"  # obsidian errors (No active file / File "X" not found) start with this
_TAB_RE = re.compile(r"^\[([^\]]+)\]\s*(.*)$")
_TAB_ID_RE = re.compile(r"\t([0-9a-fA-F]{6,})\s*$")  # trailing `\t<hexid>` from `tabs ids`


class ResolveError(Exception):
    """Carries a wrapper exit code for a resolution failure."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


# ── obsidian invocation (the single monkeypatched seam) ─────────────────────────
def _run_obsidian(args: list[str], *, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    """Run ``obsidian <args>`` and return the completed process."""
    return subprocess.run(["obsidian", *args], capture_output=True, text=True, timeout=timeout)


def _obs(subargs: list[str], base: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return _run_obsidian(base + subargs)
    except (subprocess.SubprocessError, OSError) as exc:  # timeout / launch failure
        raise ResolveError(EXIT_APP_NOT_RUNNING, f"obsidian call failed: {exc}") from exc


def _base(vault: Optional[str]) -> list[str]:
    return [f"vault={vault}"] if vault else []


def _first_nonblank(text: str) -> str:
    return next((ln for ln in text.splitlines() if ln.strip()), "")


# ── parsers (pure; unit-tested against captured fixtures) ────────────────────────
def parse_file_info(text: str) -> dict[str, str]:
    """Parse ``obsidian file`` TSV output (``key\\tvalue`` per line) → dict."""
    info: dict[str, str] = {}
    for line in text.splitlines():
        if "\t" in line:
            key, _, value = line.partition("\t")
            info[key.strip()] = value.strip()
    return info


def parse_tabs(text: str) -> list[dict[str, str]]:
    """Parse ``obsidian tabs`` output (``[view-type] Title`` + optional trailing ``\\t<id>``)."""
    tabs: list[dict[str, str]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        line, tab_id = raw, ""
        m_id = _TAB_ID_RE.search(raw)  # only a trailing `\t<hex>` is an id (a tab in a title is not)
        if m_id:
            tab_id = m_id.group(1)
            line = raw[: m_id.start()]
        match = _TAB_RE.match(line.strip())
        if not match:
            continue
        entry: dict[str, str] = {"view_type": match.group(1).strip(), "title": match.group(2).strip()}
        if tab_id:
            entry["id"] = tab_id
        tabs.append(entry)
    return tabs


def markdown_tabs(tabs: list[dict[str, str]]) -> list[dict[str, str]]:
    """Filter parsed tabs to the ``markdown`` view-type (the note tabs)."""
    return [t for t in tabs if t.get("view_type") == "markdown"]


def match_descriptor(notes: list[dict[str, str]], descriptor: str) -> list[dict[str, str]]:
    """Open markdown notes whose title contains every whitespace token of ``descriptor``.

    The descriptor-branch guard: callers treat len==1 as a unique open-tab match (the HIGH
    candidate), and len==0 / len>1 as LOW (ask) — so a wrong-file mutation can never happen
    silently. (Substring, case-insensitive; semantic/cross-language matching is the agent's job.)
    """
    tokens = [t for t in descriptor.lower().split() if t]
    if not tokens:
        return []
    return [n for n in notes if all(tok in n.get("title", "").lower() for tok in tokens)]


# ── resolvers ───────────────────────────────────────────────────────────────────
def _require_cli() -> None:
    if shutil.which("obsidian") is None:
        raise ResolveError(EXIT_CLI_ABSENT, "obsidian CLI not found on PATH")


def _enrich(info: dict[str, str], vault: Optional[str]) -> dict[str, str]:
    base = _base(vault)
    rel = info.get("path", "")
    root = _obs(["vault", "info=path"], base).stdout.strip()
    name = _obs(["vault", "info=name"], base).stdout.strip()
    if not root or not Path(root).is_absolute():  # fail-closed: no usable absolute root → app issue
        raise ResolveError(EXIT_APP_NOT_RUNNING, f"obsidian did not return an absolute vault root: {root!r}")
    return {"path": rel, "name": info.get("name", ""), "vault": name, "abs": str(Path(root) / rel)}


def _resolve_file(file_arg: Optional[str], vault: Optional[str], *, missing_code: int) -> dict[str, str]:
    base = _base(vault)
    subargs = ["file"] + ([f"file={file_arg}"] if file_arg else [])
    proc = _obs(subargs, base)
    blob = proc.stdout or ""
    if proc.stderr:
        blob = f"{blob}\n{proc.stderr}" if blob else proc.stderr
    # obsidian reports missing files as `Error: No active file…` / `Error: File "X" not found.`
    # (both rc=0). Anchor on the Error: PREFIX of the first non-blank line — NOT an unanchored
    # substring over the TSV (a note literally named "… not found" must NOT be misread as missing).
    if _first_nonblank(blob).startswith(_ERROR_PREFIX):
        raise ResolveError(missing_code, f"obsidian: {_first_nonblank(blob)}")
    info = parse_file_info(proc.stdout)
    if "path" not in info:  # not an Error:, but no parseable path either → app not running / unexpected
        raise ResolveError(EXIT_APP_NOT_RUNNING, "obsidian returned no file info (app not running?)")
    return _enrich(info, vault)


def resolve_focused(vault: Optional[str] = None) -> dict[str, str]:
    """Resolve the active/focused note → {path, name, vault, abs}."""
    _require_cli()
    return _resolve_file(None, vault, missing_code=EXIT_NO_ACTIVE_FILE)


def resolve_title(title: str, vault: Optional[str] = None) -> dict[str, str]:
    """Resolve an open-tab title → {path, name, vault, abs} via ``file=`` (wikilink-style)."""
    _require_cli()
    return _resolve_file(title, vault, missing_code=EXIT_NO_ACTIVE_FILE)


def list_open_notes(vault: Optional[str] = None) -> list[dict[str, str]]:
    """List open markdown tabs (title + view-type)."""
    _require_cli()
    return markdown_tabs(parse_tabs(_obs(["tabs"], _base(vault)).stdout))


def vault_basename_count(stem: str, vault: Optional[str] = None) -> int:
    """How many vault ``.md`` files share this basename ``stem`` (case-insensitive).

    Used by ``match`` to prove the wikilink ``file=<title>`` resolve was unambiguous: a stem
    shared by >1 file means the resolve could have picked the wrong same-named note (F-1).
    """
    out = _obs(["files", "ext=md"], _base(vault)).stdout
    target = stem.lower()
    return sum(1 for ln in out.splitlines() if ln.strip() and Path(ln.strip()).stem.lower() == target)


# ── CLI ──────────────────────────────────────────────────────────────────────────
def _headless_guard() -> None:
    if os.environ.get("WIKI_HEADLESS") == "1":
        raise ResolveError(EXIT_HEADLESS, "WIKI_HEADLESS=1 — caller must not invoke the resolver headless")


def _check_vault(res: dict[str, str], expect: Optional[str]) -> None:
    if not expect:
        return
    actual = res.get("vault", "")
    if not actual:  # fail-CLOSED: cannot verify identity → treat as a mismatch, never silently pass
        raise ResolveError(EXIT_VAULT_MISMATCH, f"could not verify the active vault against expected {expect!r}")
    if actual != expect:
        raise ResolveError(EXIT_VAULT_MISMATCH, f"active vault {actual!r} != expected {expect!r}")


def _emit(obj: object, fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(obj, ensure_ascii=False))
        return
    items = obj if isinstance(obj, list) else [obj]
    for item in items:
        assert isinstance(item, dict)
        if fmt == "path":
            # never silently emit a bare title as if it were a path (a tab entry has no path)
            print(item.get("abs") or item.get("path") or "")
        else:  # tsv
            print("\t".join(str(item.get(k, "")) for k in ("path", "abs", "vault", "title", "view_type")))


def build_parser() -> argparse.ArgumentParser:
    # default=SUPPRESS so an option absent before the subcommand is not re-defaulted
    # (clobbered) by the subparser when it appears after it — parents+subparsers gotcha.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--vault", default=argparse.SUPPRESS, help="Obsidian vault NAME (omit → ambient active vault)")
    common.add_argument("--expect-vault", default=argparse.SUPPRESS, help="error EXIT_VAULT_MISMATCH if the resolved vault differs")
    common.add_argument("--format", choices=("json", "path", "tsv"), default=argparse.SUPPRESS)

    p = argparse.ArgumentParser(prog="obsidian-active-note", description=__doc__, parents=[common])
    sub = p.add_subparsers(dest="mode", required=True)
    sub.add_parser("focused", parents=[common], help="resolve the active/focused note")
    sub.add_parser("tabs", parents=[common], help="list open markdown tabs")
    rp = sub.add_parser("resolve", parents=[common], help="resolve an open-tab title to a path")
    rp.add_argument("--title", required=True)
    mp = sub.add_parser("match", parents=[common], help="descriptor → unique open note (HIGH) | none/many (ask)")
    mp.add_argument("--descriptor", required=True)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    vault = getattr(args, "vault", None)
    expect_vault = getattr(args, "expect_vault", None)
    fmt = getattr(args, "format", "json")
    try:
        _headless_guard()
        _require_cli()
        if args.mode == "focused":
            res = resolve_focused(vault)
            _check_vault(res, expect_vault)
            _emit(res, fmt)
        elif args.mode == "tabs":
            _emit(list_open_notes(vault), fmt)
        elif args.mode == "resolve":
            res = resolve_title(args.title, vault)
            _check_vault(res, expect_vault)
            _emit(res, fmt)
        elif args.mode == "match":
            hits = match_descriptor(list_open_notes(vault), args.descriptor)
            if len(hits) == 0:
                raise ResolveError(EXIT_NO_ACTIVE_FILE, "no open note matches the descriptor")
            if len(hits) > 1:
                raise ResolveError(EXIT_AMBIGUOUS, "multiple open notes match the descriptor — disambiguate")
            res = resolve_title(hits[0]["title"], vault)
            # F-1 guard: file=<title> is a vault-global wikilink resolve, NOT pinned to the open
            # tab. The no-ask path requires PROOF the resolve is unambiguous: the resolved .md file
            # must appear EXACTLY ONCE in the vault by basename. count!=1 (0 = couldn't corroborate
            # — app glitch / non-md / stem mismatch; >1 = duplicate) → can't prove it's the open tab → ASK.
            if vault_basename_count(Path(res["path"]).stem, vault) != 1:
                raise ResolveError(EXIT_AMBIGUOUS, "resolved title is not a provably-unique basename in the vault — disambiguate")
            _check_vault(res, expect_vault)
            _emit(res, fmt)
        else:  # pragma: no cover
            return EXIT_USAGE
        return EXIT_OK
    except ResolveError as exc:
        print(f"obsidian-active-note: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
