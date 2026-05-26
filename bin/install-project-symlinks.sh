#!/usr/bin/env bash
# Usage: bin/install-project-symlinks.sh
#
# Bulk-create vendor-tree symlinks for every canonical entry under
# skills/, commands/, workflows/ in the repo root.
#
# Idempotent: re-running just refreshes symlinks (ln -sfn).
#
# Run this after `bash install.sh install --vendor claude` on a fresh
# clone — install.sh wires the framework, this script wires the project's
# own skills/commands/workflows.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

count=0
skipped=0

# 1. skills/<name>/ → both vendor trees
if [[ -d skills ]]; then
  mkdir -p .claude/skills .agent/skills
  for src in skills/*/; do
    [[ -d "$src" ]] || continue
    name="$(basename "$src")"
    ln -sfn "../../skills/$name" ".claude/skills/$name"
    ln -sfn "../../skills/$name" ".agent/skills/$name"
    count=$((count + 2))
  done
else
  skipped=$((skipped + 1))
fi

# 2. commands/<name>.md → .claude/commands/ only
if [[ -d commands ]]; then
  mkdir -p .claude/commands
  for src in commands/*.md; do
    [[ -f "$src" ]] || continue
    name="$(basename "$src")"
    ln -sfn "../../commands/$name" ".claude/commands/$name"
    count=$((count + 1))
  done
else
  skipped=$((skipped + 1))
fi

# 3. workflows/<name>.md → .agent/workflows/ only
if [[ -d workflows ]]; then
  mkdir -p .agent/workflows
  for src in workflows/*.md; do
    [[ -f "$src" ]] || continue
    name="$(basename "$src")"
    ln -sfn "../../workflows/$name" ".agent/workflows/$name"
    count=$((count + 1))
  done
else
  skipped=$((skipped + 1))
fi

echo "project symlinks: $count created/refreshed (skipped roots: $skipped)"
