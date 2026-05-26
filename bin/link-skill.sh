#!/usr/bin/env bash
# Usage: bin/link-skill.sh <skill-name>
# Creates .claude/skills/<name> -> ../../skills/<name>
set -euo pipefail
name="${1:?usage: $0 <skill-name>}"
[[ -d "skills/$name" ]] || { echo "skills/$name not found" >&2; exit 1; }
ln -sfn "../../skills/$name" ".claude/skills/$name"
echo "linked: .claude/skills/$name -> ../../skills/$name"
