#!/usr/bin/env bash
# scripts/sync_wiki_ingest.sh — refresh `scripts/wiki_ingest/` from upstream
# (Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/) using rsync,
# with SHA256-content-hash divergence detection. See task-004-02 + R-49 +
# scripts/wiki_ingest/VENDORED_FROM.md.
#
# Usage:
#   bash scripts/sync_wiki_ingest.sh [--source PATH] [--dry-run]
#                                    [--accept-local-divergence] [--help]
#
# Exit codes:
#   0  — success (sync applied, or dry-run completed)
#   1  — generic failure (source not found, hash divergence, etc.)
#   2  — usage error
#
# Divergence policy: before overwriting any vendored file, compare its
# current SHA256 against `VENDORED_FROM.md::file_hashes`. If divergence
# is detected AND the file is NOT listed in `local_patches`, abort with
# a per-file diff list. The `--accept-local-divergence` flag bypasses
# this guard; operator MUST follow up by adding a `local_patches[]` entry.

set -euo pipefail
umask 022

# --- Defaults ---------------------------------------------------------- #
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEFAULT_SOURCE="$REPO_ROOT/../Universal-skills/skills/wiki-ingest/scripts/wiki_ingest"
SOURCE_PATH="$DEFAULT_SOURCE"
DRY_RUN=0
ACCEPT_DIVERGENCE=0
VENDORED_DIR="$REPO_ROOT/scripts/wiki_ingest"
VENDORED_FROM="$VENDORED_DIR/VENDORED_FROM.md"

# --- Argument parsing -------------------------------------------------- #
usage() {
    cat <<'EOF'
Usage: sync_wiki_ingest.sh [OPTIONS]

Options:
  --source PATH                Upstream wiki_ingest/ directory to copy from.
                               Default: ../Universal-skills/skills/wiki-ingest/scripts/wiki_ingest/
  --dry-run                    Print what would be synced without modifying files.
  --accept-local-divergence    Bypass hash divergence guard. Operator MUST add
                               a local_patches[] entry to VENDORED_FROM.md after.
  --help                       Print this message and exit 0.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source)
            [[ $# -ge 2 ]] || { echo "error: --source requires an argument" >&2; exit 2; }
            SOURCE_PATH="$2"
            shift 2
            ;;
        --dry-run) DRY_RUN=1; shift ;;
        --accept-local-divergence) ACCEPT_DIVERGENCE=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "error: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

# --- Preflight --------------------------------------------------------- #
SOURCE_PATH="$(cd "$SOURCE_PATH" 2>/dev/null && pwd)" || {
    echo "error: upstream source directory not found: $SOURCE_PATH" >&2
    exit 1
}

[[ -d "$VENDORED_DIR" ]] || {
    echo "error: vendored directory not found: $VENDORED_DIR" >&2
    echo "       run task-004-01 (vendor-bootstrap) first" >&2
    exit 1
}

[[ -f "$VENDORED_FROM" ]] || {
    echo "error: provenance file not found: $VENDORED_FROM" >&2
    exit 1
}

# --- Divergence check (Python helper for portable hashing + table parse) #
export SYNC_VENDORED_DIR="$VENDORED_DIR"
export SYNC_VENDORED_FROM="$VENDORED_FROM"
export SYNC_ACCEPT_DIVERGENCE="$ACCEPT_DIVERGENCE"

python3 <<'PYEOF'
import hashlib, os, re, sys
from pathlib import Path

vendored_dir = Path(os.environ["SYNC_VENDORED_DIR"])
vendored_from = Path(os.environ["SYNC_VENDORED_FROM"])
accept_divergence = os.environ["SYNC_ACCEPT_DIVERGENCE"] == "1"

md = vendored_from.read_text(encoding="utf-8")
recorded: dict[str, str] = {}
in_file_hashes = False
for line in md.splitlines():
    if line.startswith("## file_hashes"):
        in_file_hashes = True
        continue
    if in_file_hashes and line.startswith("## "):
        break
    if in_file_hashes:
        m = re.match(r"\|\s*`([^`]+)`\s*\|\s*`([0-9a-fA-F]{64})`\s*\|", line)
        if m:
            recorded[m.group(1)] = m.group(2)

if not recorded:
    print("error: could not parse file_hashes block from VENDORED_FROM.md",
          file=sys.stderr)
    sys.exit(1)

# Parse local_patches[*].path entries.
local_patched: set[str] = set()
in_lp = False
for line in md.splitlines():
    if line.startswith("## local_patches"):
        in_lp = True
        continue
    if in_lp and line.startswith("## "):
        break
    if in_lp:
        m = re.match(r"\d+\.\s+\*\*path\*\*:\s*`([^`]+)`", line)
        if m:
            local_patched.add(m.group(1))

diverged: list[tuple[str, str, str]] = []
for f in sorted(vendored_dir.rglob("*.py")):
    rel = f.relative_to(vendored_dir).as_posix()
    if rel not in recorded:
        continue
    current = hashlib.sha256(f.read_bytes()).hexdigest()
    if current != recorded[rel] and rel not in local_patched:
        diverged.append((rel, recorded[rel], current))

if diverged and not accept_divergence:
    print("error: local divergence detected — vendored files differ from",
          file=sys.stderr)
    print("       recorded hashes AND are not listed in local_patches[].",
          file=sys.stderr)
    print("       Re-run with --accept-local-divergence to override.", file=sys.stderr)
    print("       Diverged files:", file=sys.stderr)
    for rel, rec, cur in diverged:
        print(f"         - {rel}", file=sys.stderr)
        print(f"             recorded: {rec[:16]}…", file=sys.stderr)
        print(f"             current:  {cur[:16]}…", file=sys.stderr)
    sys.exit(1)

if diverged:
    print(f"warning: {len(diverged)} file(s) diverged from recorded hashes",
          file=sys.stderr)
    print("         --accept-local-divergence active; proceeding with rsync.",
          file=sys.stderr)
    print("         REMINDER: add local_patches[] entry to VENDORED_FROM.md",
          file=sys.stderr)
    print("         in the same commit (else next sync will catch it).",
          file=sys.stderr)

print(f"info: divergence-check passed ({len(recorded)} files checked, "
      f"{len(local_patched)} local-patched paths excluded).", file=sys.stderr)
PYEOF

# --- rsync ------------------------------------------------------------- #
RSYNC_FLAGS=(-av --delete
    --exclude=__pycache__ --exclude='*.pyc'
    --exclude='.AGENTS.md'
    --exclude='VENDORED_FROM.md'
    --exclude='LICENSE-upstream'  # Apache 2.0 §4 — required for redistribution; not in upstream tree
)
if [[ "$DRY_RUN" == "1" ]]; then
    RSYNC_FLAGS+=(--dry-run)
fi

echo "info: rsync from $SOURCE_PATH/ -> $VENDORED_DIR/" >&2
rsync "${RSYNC_FLAGS[@]}" "$SOURCE_PATH/" "$VENDORED_DIR/"

if [[ "$DRY_RUN" == "1" ]]; then
    echo "Dry run complete - no files were modified."
    exit 0
fi

# --- VENDORED_FROM.md rewrite ------------------------------------------ #
export SYNC_SOURCE_PATH="$SOURCE_PATH"

python3 <<'PYEOF'
import hashlib, os, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

vendored_dir = Path(os.environ["SYNC_VENDORED_DIR"])
vendored_from = Path(os.environ["SYNC_VENDORED_FROM"])
source_path = Path(os.environ["SYNC_SOURCE_PATH"])

upstream_root = source_path.parent.parent  # …/scripts/wiki_ingest -> …/scripts -> …/skills/wiki-ingest
try:
    sha = subprocess.run(
        ["git", "-C", str(upstream_root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
except (subprocess.CalledProcessError, FileNotFoundError):
    sha = "non-git"

synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

hashes: list[tuple[str, str]] = []
for f in sorted(vendored_dir.rglob("*.py")):
    rel = f.relative_to(vendored_dir).as_posix()
    h = hashlib.sha256(f.read_bytes()).hexdigest()
    hashes.append((rel, h))

md = vendored_from.read_text(encoding="utf-8")
local_patched: set[str] = set()
in_lp = False
for line in md.splitlines():
    if line.startswith("## local_patches"):
        in_lp = True
        continue
    if in_lp and line.startswith("## "):
        break
    if in_lp:
        m = re.match(r"\d+\.\s+\*\*path\*\*:\s*`([^`]+)`", line)
        if m:
            local_patched.add(m.group(1))

new_table = ["| path | sha256 | diverged? |", "|---|---|---|"]
for rel, h in hashes:
    is_div = "yes (local_patches)" if rel in local_patched else "no"
    new_table.append(f"| `{rel}` | `{h}` | {is_div} |")
new_table_text = "\n".join(new_table)

md = re.sub(
    r"^- \*\*source_commit\*\*:.*$",
    f"- **source_commit**: `{sha}`",
    md, count=1, flags=re.MULTILINE,
)
md = re.sub(
    r"^- \*\*synced_at\*\*:.*$",
    f"- **synced_at**: `{synced_at}`",
    md, count=1, flags=re.MULTILINE,
)

pattern = re.compile(
    r"^## file_hashes.*?(?=^## )",
    re.MULTILINE | re.DOTALL,
)
replacement = f"## file_hashes (current — may include local patches)\n\n{new_table_text}\n\n"
md, n = pattern.subn(replacement, md, count=1)
if n != 1:
    print("error: failed to locate file_hashes section for rewrite", file=sys.stderr)
    raise SystemExit(1)

vendored_from.write_text(md, encoding="utf-8")
sha_short = sha[:8] if sha != "non-git" else sha
print(f"info: VENDORED_FROM.md updated - source_commit={sha_short}, "
      f"synced_at={synced_at}, {len(hashes)} hashes refreshed.", file=sys.stderr)
PYEOF

echo "Sync complete." >&2
