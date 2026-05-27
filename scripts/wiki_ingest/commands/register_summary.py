"""`register-summary` subcommand — ingest a pre-made summary into _sources/.

Security-critical: this is the only command that reads an
operator-supplied path outside the vault. Defences (per the May-2026
VDD-multi pass):

- **S-M1 inbox containment**: `--inbox-root` / `WIKI_INGEST_INBOX_ROOT`
  refuses paths outside the configured inbox, AND a hard-coded
  sensitive-path blocklist (`/.ssh/`, `/.aws/`, `/.gnupg/`, `/etc/shadow`,
  `/etc/passwd`, `/.config/`) refuses common credential leaks even when
  no inbox is set.
- **Symlink refusal**: `.is_symlink()` short-circuit before stat.
- **Size cap**: `MAX_SUMMARY_BYTES` (50 MiB) refuses `/dev/zero`.
- **L-H5 structural rewrite**: concept/entity names containing `/` or
  `\\` are rebuilt via `_splice_frontmatter_fields`, NOT `str.replace`
  (which mangles prefix-overlapping names like `Railway 24/7` vs
  `Railway 24/7 Deployment`).
- **S-M6 hard-reject**: newlines / control chars in `title` / `slug` /
  `date` frontmatter values fail-closed before they reach the agent.
- **S-H1 containment**: target path verified via `is_relative_to`.
- **Symlink-target overwrite refusal**: refuse to write through a
  symlink at `_sources/<slug>.md`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from wiki_ingest._frontmatter import _splice_frontmatter_fields, split_frontmatter
from wiki_ingest._safety import (
    MAX_SUMMARY_BYTES,
    _CTRL_CHARS_RE,
    _is_relative_to,
    _safe_for_json,
    _safe_name,
    die,
    read_text,
    slugify,
    write_text,
)
from wiki_ingest._vault import ensure_schema

SUMMARY_KIND_HINTS = ("lesson-summary", "meeting-summary", "source", "summary")


def register(sub: argparse._SubParsersAction) -> None:
    """Attach the `register-summary` subparser."""
    p = sub.add_parser("register-summary",
                       help="ingest an already-generated summary file into "
                            "_sources/ (skip summarizing-meetings)")
    p.add_argument("vault")
    p.add_argument("--summary-path", required=True,
                   help="path to the pre-made summary markdown file")
    p.add_argument("--slug", help="override slug (default: slugify of title)")
    p.add_argument("--title", help="override title (default: from frontmatter)")
    p.add_argument("--force", action="store_true",
                   help="overwrite _sources/<slug>.md if it already exists")
    p.add_argument("--inbox-root",
                   help="if set, refuse summaries outside this directory "
                        "(defense against agent-argv injection reading /etc/, "
                        "~/.aws, etc.). Env var: WIKI_INGEST_INBOX_ROOT")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=execute)


def execute(args: argparse.Namespace) -> int:
    """Copy a pre-made summary file into _sources/ and return its metadata."""
    vault = Path(args.vault).resolve()
    ensure_schema(vault)
    # S-M1b — check `is_symlink()` BEFORE `.resolve()` (resolve follows the
    # link, after which `is_symlink()` is always False on the real target).
    # We also evaluate the sensitive-path blocklist on BOTH the unresolved
    # and resolved forms — an attacker-supplied symlink like
    # `inbox/innocuous.md -> /etc/passwd` must fail-close on the target.
    unresolved = Path(args.summary_path)
    if unresolved.is_symlink():
        die(f"summary path is a symlink ({unresolved} → "
            f"{os.readlink(unresolved)}); refusing to follow", code=8)
    summary_path = unresolved.resolve()
    if not summary_path.is_file():
        die(f"summary file not found: {summary_path}")

    # S-M1 — optional inbox containment. If WIKI_INGEST_INBOX_ROOT is set or
    # --inbox-root is passed, refuse to read summary files outside it. This
    # closes the prompt-injection-chained exfil where the agent could be
    # tricked into registering `~/.aws/credentials` as a summary.
    inbox_root = getattr(args, "inbox_root", None) or os.environ.get(
        "WIKI_INGEST_INBOX_ROOT")
    if inbox_root:
        inbox_path = Path(inbox_root).expanduser().resolve()
        # Check the UNRESOLVED form too — a symlink-into-inbox pointing
        # outside would otherwise slip past the containment.
        if not _is_relative_to(summary_path, inbox_path) \
                or not _is_relative_to(unresolved, inbox_path):
            die(f"summary file {unresolved} is outside inbox root "
                f"{inbox_path}; move it into the inbox or unset "
                f"WIKI_INGEST_INBOX_ROOT", code=8)

    # Refuse common sensitive paths even when no inbox root is configured —
    # belt-and-braces against an attacker-influenced argv. Check both the
    # unresolved form (what the operator typed) AND the resolved form
    # (where the file actually lives).
    for sp_str in (str(unresolved), str(summary_path)):
        for forbidden in ("/.ssh/", "/.aws/", "/.gnupg/", "/etc/shadow",
                          "/etc/passwd", "/.config/"):
            if forbidden in sp_str:
                die(f"refusing to read summary from sensitive path {sp_str}",
                    code=8)
    try:
        st = summary_path.stat()
    except OSError as e:
        die(f"cannot stat summary file {summary_path}: {e}")
    if st.st_size > MAX_SUMMARY_BYTES:
        die(f"summary file {summary_path} exceeds MAX_SUMMARY_BYTES="
            f"{MAX_SUMMARY_BYTES} ({st.st_size}B)", code=6)
    text = read_text(summary_path, max_bytes=MAX_SUMMARY_BYTES)
    warnings: list[str] = []
    fm, body = split_frontmatter(text, warnings=warnings)

    # Auto-normalize concept/entity names that contain '/' or '\\' — these are
    # rejected by _safe_name in upsert-page, so summaries written by an LLM
    # that happily emit 'Railway 24/7 Deployment' would otherwise be unusable.
    # STRUCTURAL rewrite (L-H5 / P-M2): re-serialize the affected list fields
    # rather than `str.replace`, which is nondeterministic when one name is a
    # substring of another (e.g. `Railway 24/7` vs `Railway 24/7 Deployment`).
    name_rewrites: dict[str, str] = {}

    def _normalize_for_fs(name: str) -> str:
        s = name.replace("/", "-").replace("\\", "-").replace("~", "")
        s = re.sub(r"\s*-\s*", "-", s)
        s = re.sub(r"-+", "-", s).strip("- ")
        while s.startswith("."):
            s = s[1:]
        return s

    def _entry_bare_name(entry: str) -> str:
        m = re.match(r"^\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]$", entry.strip())
        return m.group(1).strip() if m else entry.strip()

    affected_fields: list[str] = []
    for field in ("concepts", "related"):
        for entry in (fm.get(field) or []):
            if not isinstance(entry, str):
                continue
            bare = _entry_bare_name(entry)
            if "/" in bare or "\\" in bare:
                norm = _normalize_for_fs(bare)
                if norm and norm != bare:
                    name_rewrites[bare] = norm
                    if field not in affected_fields:
                        affected_fields.append(field)

    if name_rewrites:
        # Rebuild ONLY the affected list fields and splice the new YAML
        # representation back into the frontmatter region.
        def _rewrite_entry(entry: str) -> str:
            bare = _entry_bare_name(entry)
            if bare not in name_rewrites:
                return entry
            new_bare = name_rewrites[bare]
            # Preserve the [[…]] wrapping if the original entry had it.
            m = re.match(r"^\[\[([^\]|]+?)(\|[^\]]+)?\]\]$", entry.strip())
            if m:
                alias = m.group(2) or ""
                return f"[[{new_bare}{alias}]]"
            return new_bare

        for field in affected_fields:
            fm[field] = [_rewrite_entry(e) if isinstance(e, str) else e
                         for e in (fm.get(field) or [])]

        text = _splice_frontmatter_fields(text, affected_fields, fm)
        warnings.append(
            "auto-normalized concept/entity names containing '/' or '\\' "
            "(filesystem-unsafe, frontmatter-only): "
            + ", ".join(f"{o!r} → {n!r}" for o, n in name_rewrites.items())
        )

    # Reject frontmatter values containing newlines OR markdown-header
    # spoofing characters — they would propagate to subsequent
    # `append-log --title` / `update-index --source-title` calls and break
    # the grep-friendly log/index formats. (S-M6 hard-reject; the
    # _safe_for_json filter is the soft-output safety net.)
    for fm_key in ("title", "slug", "date"):
        v = fm.get(fm_key)
        if isinstance(v, str):
            if "\n" in v or "\r" in v:
                die(f"frontmatter `{fm_key}` contains newlines; clean the "
                    f"summary file before registering")
            if _CTRL_CHARS_RE.search(v):
                die(f"frontmatter `{fm_key}` contains control characters; "
                    f"clean the summary file before registering")

    fm_title = fm.get("title")
    if args.title:
        title = args.title
    elif fm_title and fm_title != "⚠️ UNKNOWN":
        title = fm_title
    else:
        title = summary_path.stem
        warnings.append(
            f"summary has no `title:` frontmatter (or it's ⚠️ UNKNOWN); "
            f"falling back to filename stem {title!r}. Pass --title to override."
        )
    if not title:
        die("summary has no usable title; pass --title")
    fm_type = (fm.get("type") or fm.get("kind") or "").lower()
    if fm_type and fm_type not in SUMMARY_KIND_HINTS:
        warnings.append(
            f"frontmatter type/kind={fm_type!r} not in known summary hints "
            f"{SUMMARY_KIND_HINTS}; proceeding anyway"
        )
    if not fm.get("concepts") and not fm.get("related"):
        warnings.append(
            "summary frontmatter has no `concepts:` and no `related:` — "
            "Phase 3 will have nothing to upsert. Operator should review."
        )

    raw_slug = args.slug or slugify(title)
    if not raw_slug:
        die("could not derive slug from title; pass --slug")
    slug = _safe_name(raw_slug, kind="slug")
    sources_dir = vault / "_sources"
    target = sources_dir / f"{slug}.md"
    # containment check via is_relative_to — see S-H1
    if not _is_relative_to(target, sources_dir):
        die(f"refusing to write outside {sources_dir}: {target}")

    # Skip copy if already inside _sources/ at the target path
    already_in_place = (summary_path == target)
    target_exists = target.exists()
    # Refuse to overwrite a symlink at the target — see write_text.
    if target_exists and target.is_symlink():
        die(f"_sources/{slug}.md is a symlink; refusing to overwrite "
            f"({target} → {os.readlink(target)})", code=7)

    action = "skipped"
    backup_path: Path | None = None
    if already_in_place:
        action = "in-place (already at target)"
    elif target_exists and not args.force:
        die(f"_sources/{slug}.md already exists; pass --force to overwrite "
            f"(or use a different --slug)", code=3)
    else:
        # L-L9: on --force overwrite, snapshot the prior content to a
        # `<slug>.md.backup-<timestamp>` sibling BEFORE the write. The
        # operator can then diff the two and restore if needed. Skip the
        # backup on `--dry-run` (no write happens anyway).
        if target_exists and not args.dry_run:
            import time as _time
            ts = _time.strftime("%Y%m%dT%H%M%S")
            backup_path = target.parent / f"{target.stem}.md.backup-{ts}"
            try:
                backup_path.write_bytes(target.read_bytes())
            except OSError:
                backup_path = None  # best-effort; don't block the write
        # Use the atomic write helper so a crash mid-copy leaves the previous
        # target intact (or no target at all), not a truncated half-write.
        write_text(target, text, args.dry_run)
        action = "overwritten" if target_exists else "copied"

    # extract upsert hints
    concepts = list(fm.get("concepts") or [])
    related_raw = list(fm.get("related") or [])
    # strip [[...]] from related entries to get bare names
    related = []
    for r in related_raw:
        m = re.match(r"^\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]$", r.strip())
        related.append(m.group(1).strip() if m else r.strip())

    result = {
        "summary_source": str(summary_path),
        "target_page": str(target.relative_to(vault)),
        "action": action,
        "slug": slug,
        "title": title,
        "date": fm.get("date") or "",
        "concepts": concepts,
        "related": related,
        "warnings": warnings,
    }
    if backup_path is not None and backup_path.exists():
        result["backup_path"] = str(backup_path.relative_to(vault))
    # Strip control chars + cap scalar lengths before echoing into the agent
    # context (S-M6 — prompt-injection-via-frontmatter defense).
    print(json.dumps(_safe_for_json(result), indent=2, ensure_ascii=False))
    return 0
