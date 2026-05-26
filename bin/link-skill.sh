#!/usr/bin/env bash
# Usage: bin/link-skill.sh <skill-name>
# Creates per-item symlinks in BOTH vendor trees pointing at the canonical
# source under skills/<name>:
#   .claude/skills/<name>  -> ../../skills/<name>
#   .agent/skills/<name>   -> ../../skills/<name>
# Run from the repo root.
set -euo pipefail

name="${1:?usage: $0 <skill-name>}"
[[ -d "skills/$name" ]] || { echo "skills/$name not found" >&2; exit 1; }

mkdir -p .claude/skills .agent/skills

ln -sfn "../../skills/$name" ".claude/skills/$name"
ln -sfn "../../skills/$name" ".agent/skills/$name"

echo "linked: .claude/skills/$name -> ../../skills/$name"
echo "linked: .agent/skills/$name  -> ../../skills/$name"
