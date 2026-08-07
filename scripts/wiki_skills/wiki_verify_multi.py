"""`wiki-verify-multi` CLI — off-by-default multi-critic verification of a filed
`wiki-query` answer against its cited sources (TASK 008 / R-8).

Decision-17 two-pass skill: deterministic Python plumbing only — the four-critic
audit between `prepare` and `apply` lives in the calling agent's context (the
`wiki-verify` prompt skill). There is no `import anthropic`.

- `prepare <query-slug>` (R-8.1): load the audited query page + its cited source
  bodies (read via the STORED `pages.file_path` — layout-agnostic, NEVER a
  reconstructed `<subdir>/<slug>.md`; C-8/NFR-7) → a verification envelope
  `{vault_id, query_slug, question, answer_excerpt, answer_hash, is_unchanged,
  verification_slug, examined[], examined_count, missing_cites[]}`. Refuses
  `NO_SOURCES` when the query page cites nothing.
- `apply` (R-8.3/8.4/8.6/8.7/8.8): grounding-checked verdict write-back of
  `_verifications/<slug>.md` + self-index; non-zero exit on a FAIL verdict; the
  Class-A answer is NEVER mutated. (Lands in beads 008-06 / 008-07.)

Layout-agnostic invariant (C-8/NFR-7): every page/source body is read via
`pages.file_path` + the DAL; the verdict surface is declared ONLY via
`layout.VERIFICATIONS_SUBDIR`. A grep guard (test) asserts this module contains
no literal `PAGE_SUBDIRS` member.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date as _date
from datetime import datetime as _datetime
from pathlib import Path
from typing import Any

import frontmatter

from scripts.wiki_index.factory import make_repo
from scripts.wiki_index.layout import VAULT_TIER_PROJECT, VERIFICATIONS_SUBDIR
from scripts.wiki_index.models import LogEvent
from scripts.wiki_index.policy import (
    PolicyError,
    PolicyProfile,
    allowed_levels,
    effective_level,
    resolve_policy,
)
from scripts.wiki_index.repository import IndexRepository
from scripts.wiki_index.security import PathTraversalError, validate_inside_vault
from scripts.wiki_skills._common import (
    ORCH_ID_RE,
    actor_id,
    atomic_write_text,
    build_repo_config,
    emit,
    emit_prepare_with_integrity,
    sanitize_markdown_text,
)

_MAX_SLUG_LEN = 80
_MAX_PAGE_BYTES = 1024 * 1024  # 1 MiB — generous for an answer / cited source body
_MAX_VERDICT_BYTES = 256 * 1024  # 256 KiB
_EXCERPT_CHARS = 1500
_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ORCH_RE = ORCH_ID_RE  # TASK 050: shared shape (no copy to drift)

# Q-008-e: the PASS/FAIL rule is severity-based and enforced in Python (not
# trusted to the LLM). FAIL iff any `factual`/`security` finding has severity
# >= --fail-on (default 'high'); `logic`/`completeness` are advisory below it.
_SEV_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
_FAIL_LENSES = {"factual", "security"}
_VALID_LENSES = {"factual", "logic", "security", "completeness"}
_MAX_CITES = 100  # defense-in-depth cap on processed cites (a query cites few)


class _PageTooLarge(Exception):
    """A page file exceeded the read cap."""


def _orchestrator_id(value: str) -> str:
    """argparse validator for --orchestrator-id (defends a library caller too;
    the CLI default 'orchestrator' passes)."""
    if not _ORCH_RE.fullmatch(value):  # fullmatch: `$` alone admits a trailing \n
        raise argparse.ArgumentTypeError("must match ^[a-z0-9._:@-]{1,64}$")
    return value


# -----------------------------------------------------------------------------
# helpers
# -----------------------------------------------------------------------------
def _read_page_text(vault_root: Path, file_path: str) -> str:
    """Read a page's file via its STORED vault-relative ``pages.file_path``
    (layout-agnostic — NEVER reconstruct ``<subdir>/<slug>.md``), vault-inside +
    ``O_NOFOLLOW`` + byte-bounded. Raises ``PathTraversalError`` / ``OSError`` /
    ``_PageTooLarge``."""
    path = validate_inside_vault(vault_root / file_path, vault_root)
    if path.is_symlink():
        raise PathTraversalError("refusing symlinked page file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        data = os.read(fd, _MAX_PAGE_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > _MAX_PAGE_BYTES:
        raise _PageTooLarge()
    return data.decode("utf-8", errors="replace")


def _answer_hash(answer_body: str) -> str:
    """sha256 over the audited answer body — the verdict's TOCTOU anchor
    (`apply` recomputes it; a mismatch → ANSWER_CHANGED)."""
    return hashlib.sha256(answer_body.encode("utf-8")).hexdigest()


def _verify_hash(
    answer_hash: str, examined: list[dict[str, str]],
    audience: str | None = None,
) -> str:
    """Q-008-b idempotency key: sha256 over the answer_hash + the ordered
    examined ``project/slug`` **set** — re-triggers a re-verify when the answer
    body changes OR the cited-source *set* changes (add/remove a cite). Like
    TASK 007's `question_hash`, it keys on the slug set, NOT each source's body
    content; an in-place rewrite of a cited source that keeps its slug does not
    change this hash (documented in KNOWN_ISSUES L-008-2, vdd-multi L-5).

    TASK 049 (vdd-multi logic-MED): the audience folds in ONLY when a profile
    is active — OFF keeps the hash bytes unchanged (NFR-1). Combined with
    `apply --verify-hash`, a prepare/apply audience drift fails loudly as
    `VERIFY_CONTEXT_CHANGED` instead of silently re-deriving a differently-
    scoped examined set."""
    parts = [answer_hash]
    parts.extend(f"{e['project']}/{e['slug']}" for e in examined)
    if audience is not None:
        parts.append("\x00audience:" + audience)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _load_query_page(
    repo: IndexRepository, vault_id: str, vault_root: Path, query_slug: str,
) -> tuple[str, list[str], str] | None:
    """Load the audited query page → (question, cites, answer_body), or None if
    it is absent / not a `type=query` page / unreadable. Query pages are always
    vault-tier (`_vault_`)."""
    page = repo.get_page(vault_id, query_slug, VAULT_TIER_PROJECT)
    if page is None or page.type != "query":
        return None
    try:
        text = _read_page_text(vault_root, page.file_path)
    except (PathTraversalError, OSError, _PageTooLarge):
        return None
    post = frontmatter.loads(text)
    question = str(post.get("question", "") or "")
    raw_cites = post.get("cites")
    cites = [c for c in raw_cites if isinstance(c, str)] if isinstance(raw_cites, list) else []
    return question, cites, post.content


def _gather_examined(
    repo: IndexRepository, vault_id: str, vault_root: Path, cites: list[str],
    profile: PolicyProfile | None = None,
) -> tuple[list[dict[str, str]], list[str], int]:
    """Resolve each cited ``project/slug`` to its page + body (read via
    ``pages.file_path``). A cite with no `pages` row (or unreadable) is EXCLUDED
    from the examined set and recorded in ``missing`` (plan-review m-3) — so a
    verdict finding citing it correctly trips `FINDING_SOURCE_NOT_EXAMINED` in
    `apply`. TASK 049 (R-5): under an active policy `profile` an out-of-tier
    cite is excluded BEFORE its body is read and only COUNTED (never named —
    CWE-209 posture); the gate lives in this SHARED helper so prepare and apply
    derive the same examined set (an asymmetric gate would break the grounding
    gate, same reason as the `_MAX_CITES` cap). Returns
    (examined, missing, restricted_count)."""
    examined: list[dict[str, str]] = []
    missing: list[str] = []
    restricted = 0
    allowed = allowed_levels(profile) if profile is not None else None
    # Defense-in-depth cap (vdd-multi P-2): a query cites a handful of sources;
    # bound the get_page + file-read work against a pathologically large `cites:`
    # (e.g. a hand-edited Class-A page). Applied in the SHARED helper so prepare
    # and apply derive the SAME examined set (an asymmetric cap would break the
    # grounding gate). Overflow is reported in `missing` so the operator sees it.
    if len(cites) > _MAX_CITES:
        missing.extend(cites[_MAX_CITES:])
        cites = cites[:_MAX_CITES]
    for c in cites:
        if "/" not in c:
            missing.append(c)
            continue
        proj, _, slug = c.rpartition("/")
        proj, slug = proj.strip(), slug.strip()
        if not proj or not slug:
            missing.append(c)
            continue
        sp = repo.get_page(vault_id, slug, proj)
        if sp is None:
            missing.append(c)
            continue
        if (allowed is not None and profile is not None
                and effective_level(sp.frontmatter_json, profile.default_level)
                not in allowed):
            # Out-of-tier: never read the body, never name the cite.
            restricted += 1
            continue
        try:
            body = frontmatter.loads(_read_page_text(vault_root, sp.file_path)).content
        except (PathTraversalError, OSError, _PageTooLarge):
            missing.append(c)
            continue
        examined.append({
            "project": proj, "slug": slug, "title": sp.title,
            "body_excerpt": body[:_EXCERPT_CHARS],
        })
    return examined, missing, restricted


# -----------------------------------------------------------------------------
# prepare (R-8.1)
# -----------------------------------------------------------------------------
def prepare(args: argparse.Namespace) -> int:
    if not _SLUG_RE.match(args.query_slug):
        return emit({"error": "INVALID_SLUG", "field": "query-slug",
                     "reason": "must be kebab-case ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"}, 2)
    if args.slug is not None and not _SLUG_RE.match(args.slug):
        return emit({"error": "INVALID_SLUG", "field": "slug",
                     "reason": "must be kebab-case"}, 2)
    try:
        vault_root = Path(args.vault_root).resolve(strict=True)
    except OSError:
        return emit({"error": "INVALID_VAULT_ROOT", "field": "vault-root",
                     "reason": "does not exist"}, 2)
    # TASK 049 (R-5): resolve the policy profile — MUST match apply's (the
    # examined set feeds verify_hash; the gate lives in the shared helper).
    try:
        profile = resolve_policy(vault_root, args.audience)
    except PolicyError as exc:
        err = "INVALID_AUDIENCE" if exc.field == "audience" else "INVALID_POLICY"
        return emit({"error": err, "field": exc.field, "reason": str(exc)}, 2)

    config = build_repo_config(  # TASK 022: vault_root already resolved (required flag)
        args.vault, vault_root=vault_root, db_path_flag=args.db_path)
    repo = make_repo(config)
    try:
        loaded = _load_query_page(repo, args.vault, vault_root, args.query_slug)
        if loaded is None:
            return emit({"error": "QUERY_NOT_FOUND", "field": "query-slug",
                         "reason": "no indexed type=query page with that slug "
                                   "(or its file is unreadable)"}, 2)
        question, cites, answer_body = loaded
        if not cites:
            return emit({"error": "NO_SOURCES", "field": "cites",
                         "reason": "the query page cites nothing; refusing to "
                                   "verify an answer with no sources"}, 2)

        examined, missing, restricted = _gather_examined(
            repo, args.vault, vault_root, cites, profile)
        if not examined:
            # cites was non-empty but EVERY entry is malformed or points at an
            # unindexed/unreadable page → there is nothing to verify against;
            # refuse rather than file a vacuous PASS over zero sources (vdd-multi
            # L-3). The missing entries are reported for the operator to fix.
            return emit({"error": "NO_SOURCES", "field": "cites",
                         "reason": f"the query cites {len(cites)} source(s) but none "
                                   "are indexed/readable; nothing to verify against",
                         }, 2)
        a_hash = _answer_hash(answer_body)
        # The verdict page must NOT share the query page's `pages` PK
        # (vault_id, slug, project) — the PK is subdir-independent, so a verdict
        # at `_verifications/<query-slug>.md` (slug=<query-slug>, project=_vault_)
        # would collide with the query page and OVERWRITE its index row. Default
        # to a distinct `verify-<query-slug>` slug (found-in-dev fix, operator-
        # approved). `verifies:` still points at the query (`_vault_/<query-slug>`).
        verification_slug = args.slug or f"verify-{args.query_slug}"
        v_hash = _verify_hash(
            a_hash, examined,
            audience=profile.audience if profile is not None else None)
        is_unchanged = repo.check_verify_state(args.vault, verification_slug) == v_hash
        env: dict[str, Any] = {
            "vault_id": args.vault,
            "query_slug": args.query_slug,
            "question": question,
            "answer_excerpt": answer_body[:_EXCERPT_CHARS],
            "answer_hash": a_hash,
            "verify_hash": v_hash,
            "is_unchanged": is_unchanged,
            "verification_slug": verification_slug,
            "examined": examined,
            "examined_count": len(examined),
            "missing_cites": missing,
        }
        if profile is not None:
            # TASK 049: count only, never content/slugs (CWE-209); emitted
            # ONLY when a profile is active (NFR-1 — OFF envelope unchanged).
            env["restricted_count"] = restricted
            env["audience"] = profile.audience
        # H-5: verify the wiki-verify contract's pin before the orchestrator loads it.
        return emit_prepare_with_integrity(env, "wiki-verify")
    finally:
        repo.close()


# -----------------------------------------------------------------------------
# apply (R-8.3 / 8.7 / 8.8 write-side; R-8.4 / 8.6 index lands in 008-07)
# -----------------------------------------------------------------------------
def _read_verdict_payload(args: argparse.Namespace, vault_root: Path) -> str:
    """Read the verdict JSON from stdin or a vault-inside file, bounded +
    ``O_NOFOLLOW``. Raises ``_PageTooLarge`` / ``PathTraversalError`` / ``OSError``."""
    if args.verdict_stdin:
        data = sys.stdin.buffer.read(_MAX_VERDICT_BYTES + 1)
        if len(data) > _MAX_VERDICT_BYTES:
            raise _PageTooLarge()
        return data.decode("utf-8")
    assert args.verdict_file is not None
    path = validate_inside_vault(Path(args.verdict_file), vault_root)
    if path.is_symlink():
        raise PathTraversalError("refusing symlinked verdict file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        data = os.read(fd, _MAX_VERDICT_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > _MAX_VERDICT_BYTES:
        raise _PageTooLarge()
    return data.decode("utf-8")


def _is_fail(findings: list[Any], fail_on: str) -> bool:
    """Q-008-e authoritative PASS/FAIL rule (Python-enforced, not trusted to the
    LLM): FAIL iff any `factual`/`security` finding has severity >= --fail-on.
    `--fail-on=none` never fails."""
    if fail_on == "none":
        return False
    thresh = _SEV_ORDER.get(fail_on, _SEV_ORDER["high"])
    # Case-normalise lens + severity: an LLM commonly emits `severity:"High"` /
    # `lens:"Factual"`; a case-sensitive compare would silently treat a real
    # high-severity factual finding as non-failing (→ PASS), defeating the whole
    # "Python rule overrides the LLM" premise (vdd-multi L-1). `apply` also
    # rejects out-of-vocab severity/lens up front, so this is belt-and-braces.
    return any(
        isinstance(f, dict)
        and str(f.get("lens", "")).strip().lower() in _FAIL_LENSES
        and _SEV_ORDER.get(str(f.get("severity", "")).strip().lower(), 0) >= thresh
        for f in findings
    )


def _render_verdict_page(
    query_project: str, query_slug: str, verdict: str, critics: list[Any],
    answer_hash: str, today: str, cites: list[str], findings: list[Any],
) -> str:
    """Build the Class A `_verifications/<slug>.md`: frontmatter (`type`,
    `verifies`, `verdict`, `critics`, `answer_hash`, `date`, optional `cites`,
    `tags`) + a sanitised findings body + a trailing `## Sources` `[[slug]]`
    list. Untrusted finding fields (which quote the answer/sources) are
    sanitised individually via `sanitize_markdown_text`; the markdown structure
    is trusted."""
    lines = [f"Critics: {', '.join(sanitize_markdown_text(str(c)) for c in critics)}",
             "", "## Findings", ""]
    if not findings:
        lines.append("_No findings._")
    for f in findings:
        if not isinstance(f, dict):
            continue
        lens = sanitize_markdown_text(str(f.get("lens", "")))
        sev = sanitize_markdown_text(str(f.get("severity", "")))
        claim = sanitize_markdown_text(str(f.get("claim", "")))
        note = sanitize_markdown_text(str(f.get("note", "")))
        src = f.get("source")
        src_part = (f" (source: {sanitize_markdown_text(src)})"
                    if isinstance(src, str) and src else "")
        lines.append(f"- **[{lens}/{sev}]** {claim}{src_part} — {note}")
    md: dict[str, Any] = {
        "type": "verification",
        "title": f"Verdict: {query_slug}",
        "verifies": f"{query_project}/{query_slug}",
        "verdict": verdict,
        "critics": list(critics),
        "answer_hash": answer_hash,
        "date": today,
    }
    if cites:
        md["cites"] = list(cites)
    md["tags"] = ["verification"]
    out = frontmatter.dumps(frontmatter.Post("\n".join(lines), **md))
    if cites:
        sources = "\n".join(f"- [[{c.rpartition('/')[2]}]]" for c in cites)
        out = f"{out}\n\n## Sources\n\n{sources}\n"
    return out


def _index_verification_page(
    repo: IndexRepository, vault_id: str, vault_root: Path, page_path: Path,
) -> None:
    """Self-index the filed verdict page via DIRECT DAL calls on the repo's
    single connection — ``upsert_page`` + ``replace_refs`` (R-8.4). Explicitly
    NOT ``index_from_manifest`` / ``main(argv)`` (the H-PERF-3 / P-8 N+1; a
    verdict page is exactly one page, NFR-5). Reuses the reindex page-build +
    ``_frontmatter_refs`` so the apply-written ``pages`` row + ``verifies``
    (+ optional ``cited``) refs are **byte-identical** to a
    ``wiki-reindex --full`` rebuild — the UC-26 §D8 symmetry (008-09) depends
    on this. (Perf note, vdd-multi P-1: this re-reads the file we just wrote via
    the manual adapter rather than reusing the in-memory ``content`` — the
    deliberate cost of the byte-identity guarantee, same as
    ``wiki_query._index_query_page`` / Q-007-2. The re-read is trusted + small:
    the bytes were written microseconds ago from the bounded verdict payload.)"""
    from scripts.wiki_index.normalization import normalize_frontmatter
    from scripts.wiki_index.reindex import _build_page, _frontmatter_refs
    from scripts.wiki_source.base import SourceItem
    from scripts.wiki_source.manual import ManualSourceAdapter

    item = SourceItem(kind="manual", source_path=page_path,
                      vault_root=vault_root, vault_id=vault_id)
    out = ManualSourceAdapter().fetch(item)
    updated_fm, db_type = normalize_frontmatter(out.frontmatter,
                                                source_path=page_path)
    page = _build_page(out, vault_id, db_type, page_path, vault_root, updated_fm)
    repo.upsert_page(page)
    all_refs = list(out.refs)
    all_refs.extend(_frontmatter_refs(
        db_type, updated_fm, vault_id, out.page_slug, out.project, []))
    repo.replace_refs(vault_id, out.page_slug, out.project, all_refs)


def apply(args: argparse.Namespace) -> int:
    if not _SLUG_RE.match(args.verification_slug):
        return emit({"error": "INVALID_SLUG", "field": "verification-slug",
                     "reason": "must be kebab-case"}, 2)
    if not _SLUG_RE.match(args.query_slug):
        return emit({"error": "INVALID_SLUG", "field": "query-slug",
                     "reason": "must be kebab-case"}, 2)
    if not _HASH_RE.match(args.answer_hash):
        return emit({"error": "INVALID_ANSWER_HASH", "field": "answer-hash",
                     "reason": "must be 64 lowercase hex chars"}, 2)
    try:
        vault_root = Path(args.vault_root).resolve(strict=True)
    except OSError:
        return emit({"error": "INVALID_VAULT_ROOT", "field": "vault-root",
                     "reason": "does not exist"}, 2)
    # TASK 049 (R-5): same-profile resolution as prepare — the shared
    # _gather_examined gate keeps the examined set symmetric.
    try:
        profile = resolve_policy(vault_root, args.audience)
    except PolicyError as exc:
        err = "INVALID_AUDIENCE" if exc.field == "audience" else "INVALID_POLICY"
        return emit({"error": err, "field": exc.field, "reason": str(exc)}, 2)

    config = build_repo_config(  # TASK 022: vault_root already resolved (required flag)
        args.vault, vault_root=vault_root, db_path_flag=args.db_path)
    repo = make_repo(config)
    try:
        # 1. Load the audited query page; recompute answer_hash (TOCTOU).
        loaded = _load_query_page(repo, args.vault, vault_root, args.query_slug)
        if loaded is None:
            return emit({"error": "QUERY_NOT_FOUND", "field": "query-slug",
                         "reason": "no indexed type=query page with that slug"}, 2)
        _question, cites, answer_body = loaded
        if _answer_hash(answer_body) != args.answer_hash:
            return emit({"error": "ANSWER_CHANGED", "field": "answer-hash",
                         "reason": "the answer changed since prepare; re-run "
                                   "wiki-verify-multi (no auto-retry)"}, 2)

        # 2. Re-derive the examined set (Q-008-c — from cites:, as prepare did;
        # same profile → same gate → symmetric set).
        examined, _missing, restricted = _gather_examined(
            repo, args.vault, vault_root, cites, profile)
        examined_keys = {f"{e['project']}/{e['slug']}" for e in examined}
        # 2b. TASK 049 (vdd-multi logic-MED): --verify-hash is the loud
        # prepare/apply symmetry gate (mirrors wiki-query's QUESTION_CHANGED).
        # When the orchestrator passes prepare's verify_hash (the documented
        # loop does), a drifted audience OR a changed examined set is rejected
        # here — BEFORE any verdict content is filed under the wrong scope.
        recomputed_v_hash = _verify_hash(
            args.answer_hash, examined,
            audience=profile.audience if profile is not None else None)
        if args.verify_hash is not None and args.verify_hash != recomputed_v_hash:
            return emit({"error": "VERIFY_CONTEXT_CHANGED", "field": "verify-hash",
                         "reason": "the examined set / audience changed since "
                                   "prepare; re-run wiki-verify-multi (no "
                                   "auto-retry)"}, 2)

        # 3. Load + parse the verdict JSON (bounded, vault-inside, O_NOFOLLOW).
        try:
            raw = _read_verdict_payload(args, vault_root)
        except _PageTooLarge:
            return emit({"error": "VERDICT_TOO_LARGE", "field": "verdict",
                         "reason": f"exceeds {_MAX_VERDICT_BYTES} bytes"}, 4)
        except (PathTraversalError, OSError):
            return emit({"error": "INVALID_VERDICT", "field": "verdict-file",
                         "reason": "not a regular file inside the vault root"}, 4)
        try:
            verdict_obj = json.loads(raw)
        except json.JSONDecodeError:
            return emit({"error": "VERDICT_PARSE_ERROR", "field": "verdict",
                         "reason": "not valid JSON"}, 4)

        # 4. Validate the verdict shape.
        if not isinstance(verdict_obj, dict):
            return emit({"error": "INVALID_VERDICT", "field": "verdict",
                         "reason": "must be a JSON object"}, 4)
        findings = verdict_obj.get("findings", [])
        critics = verdict_obj.get("critics", [])
        if (verdict_obj.get("verdict") not in ("pass", "fail")
                or not isinstance(findings, list)
                or not isinstance(critics, list)):
            return emit({"error": "INVALID_VERDICT", "field": "verdict",
                         "reason": "expected {verdict: pass|fail, critics: [], findings: []}"}, 4)
        for f in findings:
            if not isinstance(f, dict) or "lens" not in f:
                return emit({"error": "INVALID_VERDICT", "field": "findings",
                             "reason": "each finding needs at least a 'lens'"}, 4)
            # Validate lens + severity against the canonical (lowercased) enums —
            # matches the wiki-verify contract AND closes the case-drift / out-of-
            # vocab hole (vdd-multi L-1): a mis-cased or invented severity/lens
            # must be rejected, not silently downgraded to non-failing. Never
            # echo the offending value (CWE-117/209).
            if str(f.get("lens", "")).strip().lower() not in _VALID_LENSES:
                return emit({"error": "INVALID_VERDICT", "field": "findings.lens",
                             "reason": "lens must be factual|logic|security|completeness"}, 4)
            if str(f.get("severity", "")).strip().lower() not in _SEV_ORDER:
                return emit({"error": "INVALID_VERDICT", "field": "findings.severity",
                             "reason": "severity must be low|medium|high|critical"}, 4)
            # 5. Grounding gate (R-8.8): a finding's source (if any) must be in
            # the examined set, keyed on the full project/slug. Never echo it.
            src = f.get("source")
            if src is not None and (not isinstance(src, str) or src not in examined_keys):
                return emit({"error": "FINDING_SOURCE_NOT_EXAMINED",
                             "field": "findings.source",
                             "reason": "a finding cites a source not in the examined set"}, 4)

        # 6. Authoritative verdict (Python rule — overrides the LLM's self-report
        # so it can't claim 'pass' while emitting a high-severity factual finding).
        derived = "fail" if _is_fail(findings, args.fail_on) else "pass"
        cite_set = sorted({
            f["source"] for f in findings
            if isinstance(f, dict) and isinstance(f.get("source"), str) and f.get("source")
        })
        today = _date.today().isoformat()
        content = _render_verdict_page(
            VAULT_TIER_PROJECT, args.query_slug, derived, critics,
            args.answer_hash, today, cite_set, findings)

        # 7. Write Class A `_verifications/<slug>.md` (mkdir — a migrated v4 vault
        # has no dir yet, CMP-4; symlink-refuse; content-hash skip; --force).
        # The `_queries/<slug>.md` answer is NEVER opened for write (D-008-3).
        vdir = vault_root / VERIFICATIONS_SUBDIR
        vdir.mkdir(parents=True, exist_ok=True)
        try:
            safe_dir = validate_inside_vault(vdir, vault_root)
        except PathTraversalError:
            return emit({"error": "INVALID_VAULT_ROOT", "field": "vault-root",
                         "reason": "verifications dir resolves outside the vault root"}, 2)
        page_path = safe_dir / f"{args.verification_slug}.md"
        if page_path.is_symlink():
            return emit({"error": "INVALID_VERIFICATION_PAGE", "field": "verification-slug",
                         "reason": "target is a symlink (refused)"}, 4)
        changed = True
        if page_path.exists() and not args.force:
            try:
                fd = os.open(page_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            except OSError:
                fd = None
            if fd is not None:
                try:
                    existing = os.read(fd, _MAX_VERDICT_BYTES + 1)
                finally:
                    os.close(fd)
                if existing.decode("utf-8", errors="replace") == content:
                    changed = False
        if changed:
            atomic_write_text(page_path, content)

        # 8. Self-index (R-8.4) + record verify-state (R-8.6) + one `verify` log
        # event — all on the repo's single connection (direct DAL, no N+1).
        v_hash = recomputed_v_hash
        indexed = False
        if changed:
            _index_verification_page(repo, args.vault, vault_root, page_path)
            repo.record_verify_state(args.vault, args.verification_slug, v_hash)
            verify_details: dict[str, Any] = {
                "verdict": derived,
                "verifies": f"{VAULT_TIER_PROJECT}/{args.query_slug}",
                "orchestrator_id": args.orchestrator_id,
            }
            # TASK 050 (R-2): optional actor identity from WIKI_ACTOR_ID.
            _actor = actor_id()
            if _actor is not None:
                verify_details["actor"] = _actor
            repo.append_log_event(LogEvent(
                vault_id=args.vault, event_ts=_datetime.now(),
                event_type="verify", subject=args.verification_slug,
                pages_created_json=[], pages_updated_json=[],
                details_json=verify_details,
            ))
            indexed = True
        elif repo.check_verify_state(args.vault, args.verification_slug) != v_hash:
            # Content-hash skip (unchanged page) but the verify-state row is
            # absent/stale — e.g. a prior `apply` crashed between the file write
            # and record_verify_state, or the page was hand-authored. Re-arm the
            # idempotency state so `prepare` can short-circuit (vdd-multi L-2);
            # without this the four-critic audit would re-run on every invocation.
            repo.record_verify_state(args.vault, args.verification_slug, v_hash)

        env: dict[str, Any] = {
            "vault_id": args.vault,
            "verification_slug": args.verification_slug,
            "verifies": f"{VAULT_TIER_PROJECT}/{args.query_slug}",
            "verdict": derived,
            "page_indexed": indexed,
            "action": "filed" if changed else "unchanged",
        }
        if profile is not None:
            env["restricted_count"] = restricted
            env["audience"] = profile.audience
        # The verdict is the machine signal: exit 6 on FAIL (the page IS still
        # filed — a SUCCESS envelope, no `error` key). Deliberate divergence from
        # the family's `6 = error` convention (SEC-4); callers branch on stdout
        # (`verdict`), not `$?`. `--fail-on=none` removes THIS path to 6.
        # ⚠️ It does NOT make the process "always exit 0": build_repo_config
        # (called before any of this) emits INVALID_INDEX_DB with exit 6 too, so
        # code 6 is ambiguous for the caller. Branch on the `error` key, not `$?`.
        return emit(env, 6 if derived == "fail" else 0)
    finally:
        repo.close()


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wiki-verify-multi")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser(
        "prepare", help="Assemble the verification envelope (no LLM call).")
    pp.add_argument("query_slug", help="slug of the filed _queries/<slug>.md to verify")
    pp.add_argument("--vault", required=True)
    pp.add_argument("--vault-root", required=True)
    pp.add_argument("--slug", default=None,
                    help="Override the derived verification slug (kebab-case; "
                         "default: the query slug).")
    pp.add_argument("--audience", default=None, metavar="LEVEL",
                    help="TASK 049 (ADR-009): least-privilege critics — an "
                         "out-of-tier cited source is excluded from the "
                         "envelope (counted in restricted_count, never named). "
                         "MUST match the value passed to `apply` (the examined "
                         "set feeds verify_hash + the grounding gate).")
    pp.add_argument("--db-path", default=None)
    pp.set_defaults(func=prepare)

    ap = sub.add_parser(
        "apply", help="Grounding-checked verdict write-back (+ index in 008-07).")
    ap.add_argument("--vault", required=True)
    ap.add_argument("--vault-root", required=True)
    ap.add_argument("--verification-slug", required=True)
    ap.add_argument("--query-slug", required=True)
    ap.add_argument("--answer-hash", required=True,
                    help="The answer_hash prepare emitted, verbatim (64 hex). "
                         "Recomputed here; mismatch → ANSWER_CHANGED.")
    ap.add_argument("--verify-hash", default=None,
                    help="TASK 049: the verify_hash prepare emitted. Recomputed "
                         "here from the re-derived examined set (+ audience); "
                         "mismatch → VERIFY_CONTEXT_CHANGED (exit 2). Optional "
                         "for back-compat; the documented loop passes it.")
    g_v = ap.add_mutually_exclusive_group(required=True)
    g_v.add_argument("--verdict-stdin", action="store_true")
    g_v.add_argument("--verdict-file", default=None)
    ap.add_argument("--audience", default=None, metavar="LEVEL",
                    help="TASK 049: MUST match the value passed to `prepare` "
                         "(same gate in the shared examined-set helper).")
    ap.add_argument("--fail-on", default="high",
                    choices=["critical", "high", "medium", "low", "none"],
                    help="Verdict severity threshold (Q-008-e). FAIL iff any "
                         "factual/security finding >= this. 'none' → always exit 0.")
    ap.add_argument("--orchestrator-id", default="orchestrator",
                    type=_orchestrator_id)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--db-path", default=None)
    ap.set_defaults(func=apply)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    func = args.func
    return int(func(args))


if __name__ == "__main__":
    sys.exit(main())
