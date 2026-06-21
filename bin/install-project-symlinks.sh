#!/usr/bin/env bash
# Usage: bin/install-project-symlinks.sh
#
# Bulk-create the in-repo vendor-tree symlinks for every canonical entry under
# skills/, commands/, workflows/ — so the .claude/ (Claude Code) and .agent/ (agentic
# framework) trees see the project's own skills/commands/workflows. Run after adding a new
# skills/<name>/, commands/<name>.md, or workflows/<name>.md (NOT auto-propagated).
#
# Vendor mapping (targets are repo-RELATIVE, so the tree stays portable):
#   .claude/skills/<name> + .agent/skills/<name> + .pi/skills/<name> → ../../skills/<name>
#   .claude/commands/<name>.md                                       → ../../commands/<name>.md
#   .agent/workflows/<name>.md                                       → ../../workflows/<name>.md
# (.pi/skills is pi's project skill-discovery dir — TASK 043; pi also reads ~/.pi/skills globally.)
#
# Safe + idempotent: creates a MISSING link, REPAIRS a stale repo-relative link, and SKIPS
# (never clobbers/nests-into) a REAL file/dir or a link pointing outside the repo tree.
# (A blind `ln -sfn` into an existing real dir would create a link INSIDE it — this avoids that.)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

n_new=0; n_repaired=0; n_ok=0; n_skip=0
# safe_link <relative-target> <linkpath>: only manage repo-relative (`../../…`) links.
safe_link() {
  local target="$1" lp="$2" name; name="$(basename "$lp")"
  if [[ -L "$lp" ]]; then
    local cur; cur="$(readlink "$lp")"
    if [[ "$cur" == "$target" ]]; then n_ok=$((n_ok+1)); return; fi
    case "$cur" in
      ../../skills/*|../../commands/*|../../workflows/*)
        ln -sfn "$target" "$lp"; echo "  repaired $lp"; n_repaired=$((n_repaired+1));;
      *) echo "  SKIP    $lp → $cur (foreign link)"; n_skip=$((n_skip+1));;
    esac
  elif [[ -e "$lp" ]]; then
    echo "  SKIP    $lp (a real file/dir exists — not a symlink; resolve by hand)"; n_skip=$((n_skip+1))
  else
    ln -s "$target" "$lp"; echo "  linked  $lp"; n_new=$((n_new+1))
  fi
}

if [[ -d skills ]]; then
  mkdir -p .claude/skills .agent/skills .pi/skills
  for src in skills/*/; do
    [[ -d "$src" ]] || continue
    name="$(basename "$src")"
    safe_link "../../skills/$name" ".claude/skills/$name"
    safe_link "../../skills/$name" ".agent/skills/$name"
    safe_link "../../skills/$name" ".pi/skills/$name"      # TASK 043: pi discovery
  done
fi
if [[ -d commands ]]; then
  mkdir -p .claude/commands
  for src in commands/*.md; do
    [[ -f "$src" ]] || continue
    safe_link "../../commands/$(basename "$src")" ".claude/commands/$(basename "$src")"
  done
fi
if [[ -d workflows ]]; then
  mkdir -p .agent/workflows
  for src in workflows/*.md; do
    [[ -f "$src" ]] || continue
    safe_link "../../workflows/$(basename "$src")" ".agent/workflows/$(basename "$src")"
  done
fi

echo ""
echo "project symlinks: ${n_new} new, ${n_repaired} repaired, ${n_ok} already-ok, ${n_skip} skipped"
