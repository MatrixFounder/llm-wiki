"""TASK 012-11 (PW-G) — one-shot KNOWN_ISSUES.md → per-file splitter.

Parses THIS repo's `docs/KNOWN_ISSUES.md` format —
`## [YYYY-MM-DD] <id> <title> [STATUS: <status>]` issue headers (interspersed
with `## <section>` group headers) followed by `- **Field**: …` body lines —
into per-issue Class-A files `docs/issues/<id>-<slug>.md` with frontmatter, the
body preserved **verbatim** (no lossy reflow). Anything the parser is not fully
confident about (unknown id-prefix → category, unparseable status) is listed in
`docs/issues/.migration-report.md` for operator review — **flagged, never dropped**
(NFR-6).

After migration the per-issue files are Class A; `docs/KNOWN_ISSUES.md` becomes a
Class-B auto-rendered ledger (PW-H). This is a one-shot tool; run once, review the
report, commit.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from slugify import slugify

from scripts.wiki_index.security import validate_inside_vault
from scripts.wiki_skills._common import atomic_write_text, emit

# `## [2026-05-26] L-1 entities.file_path … [STATUS: fixed 2026-05-29]`
_ISSUE_RE = re.compile(
    r"^##\s+\[(?P<date>\d{4}-\d{2}-\d{2})\]\s+(?P<id>\S+)\s+(?P<title>.+?)\s+"
    r"\[STATUS:\s*(?P<status>[^\]]+)\]\s*$"
)
_SECTION_RE = re.compile(r"^##\s+")
_SEV_RE = re.compile(r"\b(SEV-\d|HIGH|MED|MEDIUM|LOW|CRITICAL)\b", re.IGNORECASE)
_SAFE_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,200}")  # safe bare component, length-capped (NAME_MAX)

# id alpha-prefix → category (best-effort; ambiguous ones are flagged for review).
_CATEGORY_BY_PREFIX = {
    "P": "performance",
    "L": "logic",
    "D": "security",
    "H": "security",
    "Q": "quality",
    "DF": "dogfood",
}


@dataclass
class Issue:
    id: str
    opened_at: str
    title: str
    status_raw: str
    body_lines: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return self.status_raw.split()[0].rstrip(",").lower() if self.status_raw else "open"

    @property
    def severity(self) -> str:
        m = _SEV_RE.search(self.status_raw)
        return m.group(1).upper() if m else ""

    @property
    def prefix(self) -> str:
        m = re.match(r"[A-Za-z]+", self.id)
        return m.group(0) if m else ""

    @property
    def category(self) -> str:
        return _CATEGORY_BY_PREFIX.get(self.prefix, "uncategorized")

    @property
    def slug(self) -> str:
        return f"{slugify(self.id)}-{slugify(self.title)}"

    @property
    def body(self) -> str:
        # strip leading/trailing blank lines; preserve interior verbatim
        lines = self.body_lines[:]
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)

    @property
    def low_confidence_reasons(self) -> list[str]:
        reasons: list[str] = []
        if self.category == "uncategorized":
            reasons.append(f"unknown id-prefix {self.prefix!r} → category guessed 'uncategorized'")
        elif re.match(r"[A-Za-z]+-[A-Za-z]", self.id):
            # compound alpha prefix (H-PERF-3, L-V3.1): category was guessed from
            # the LEADING segment only, which can mislead (H-PERF-3 is perf, not
            # 'security'). Flag for operator review (critic-logic MED).
            reasons.append(
                f"compound id prefix in {self.id!r} → category {self.category!r} "
                f"guessed from the leading segment only; verify")
        if self.status not in ("open", "fixed", "wontfix", "documented", "by-design"):
            reasons.append(f"unusual status {self.status!r}")
        return reasons


def parse_issues(text: str) -> list[Issue]:
    """Parse issue blocks. A `## [date] id title [STATUS]` starts an issue; any
    other top-level `## …` (a section header) or another issue header ends the
    current body. **Fenced code blocks are honoured** (critic-logic MED): a
    ```` ``` ````/`~~~` fence opens a code region inside which a `## …` line is
    body content, NOT a section boundary — otherwise an issue body containing a
    fenced shell snippet would be silently truncated (NFR-6 data loss)."""
    issues: list[Issue] = []
    current: Issue | None = None
    in_fence = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            if current is not None:
                current.body_lines.append(line)
            continue
        if not in_fence:
            m = _ISSUE_RE.match(line)
            if m:
                current = Issue(id=m.group("id"), opened_at=m.group("date"),
                                title=m.group("title").strip(),
                                status_raw=m.group("status").strip())
                issues.append(current)
                continue
            if _SECTION_RE.match(line):
                current = None  # a top-level section header ends the body
                continue
        if current is not None:
            current.body_lines.append(line)
    return issues


def _issue_file(issue: Issue, slug: str) -> str:
    # `slug` is the EFFECTIVE (possibly collision-disambiguated) slug, so the
    # frontmatter `slug:` matches the on-disk filename (critic-logic residual).
    return (
        "---\n"
        f"id: {issue.id}\n"
        "type: known-issue\n"
        f"status: {issue.status}\n"
        f"opened_at: {issue.opened_at}\n"
        f"category: {issue.category}\n"
        + (f"severity: {issue.severity}\n" if issue.severity else "")
        + f"slug: {slug}\n"
        "---\n\n"
        f"# {issue.title}\n\n"
        f"{issue.body}\n"
    )


def _report(flagged: list[tuple[str, list[str]]]) -> str:
    lines = ["# KNOWN_ISSUES migration report", ""]
    if not flagged:
        lines.append("All issues parsed with full confidence. No manual review needed.")
    else:
        lines.append(f"{len(flagged)} issue(s) need operator review (flagged, NOT dropped):")
        lines.append("")
        for issue_id, reasons in flagged:
            lines.append(f"- **{issue_id}**: " + "; ".join(reasons))
    return "\n".join(lines).rstrip() + "\n"


def migrate(vault_root: Path, source: Path, *, dry_run: bool = False) -> dict[str, object]:
    issues = parse_issues(source.read_text(encoding="utf-8"))
    issues_dir = vault_root / "docs" / "issues"
    written: list[str] = []
    flagged: list[tuple[str, list[str]]] = []
    seen_slugs: dict[str, int] = {}
    if not dry_run:
        issues_dir.mkdir(parents=True, exist_ok=True)
    for issue in issues:
        reasons = list(issue.low_confidence_reasons)
        # Slug-collision detection (critic-logic MED): two issues whose id+title
        # slugify identically must NOT silently overwrite — disambiguate + flag.
        slug = issue.slug
        if slug in seen_slugs:
            seen_slugs[slug] += 1
            slug = f"{slug}-{seen_slugs[slug]}"
            reasons.append(f"slug collision with an earlier issue → disambiguated to {slug!r}")
        else:
            seen_slugs[slug] = 1
        if reasons:
            flagged.append((issue.id, reasons))
        # LOW-1 (critic-security): the untrusted-derived slug is the filename —
        # defensively assert it is a safe bare component (slugify guarantees this
        # today, but guard so a future slugify change can't yield `..`/`/`).
        if not _SAFE_SLUG_RE.fullmatch(slug):
            flagged.append((issue.id, [f"unsafe derived slug {slug!r} — skipped (no traversal)"]))
            continue
        rel = f"docs/issues/{slug}.md"
        if not dry_run:
            parent = validate_inside_vault(issues_dir, vault_root)  # parent is inside the vault
            atomic_write_text(parent / f"{slug}.md", _issue_file(issue, slug))
        written.append(rel)
    if not dry_run:
        atomic_write_text(issues_dir / ".migration-report.md", _report(flagged))
    return {"issues": len(issues), "written": written,
            "flagged": [fid for fid, _ in flagged], "dry_run": dry_run}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="migrate-known-issues")
    p.add_argument("--vault-root", required=True, help="Vault root (repo root).")
    p.add_argument("--source", default=None,
                   help="Source ledger (default: <vault-root>/docs/KNOWN_ISSUES.md).")
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    vault_root = Path(args.vault_root).resolve()
    source = Path(args.source) if args.source else vault_root / "docs" / "KNOWN_ISSUES.md"
    if not source.is_file():
        return emit({"error": "SOURCE_NOT_FOUND", "source": str(source)}, exit_code=2)
    result = migrate(vault_root, source, dry_run=args.dry_run)
    return emit({"action": "migrated", **result})


if __name__ == "__main__":
    sys.exit(main())
