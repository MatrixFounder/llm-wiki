#!/usr/bin/env bash
# Usage: bin/link-command.sh <command-name>
# Creates .claude/commands/<name>.md -> ../../commands/<name>.md
set -euo pipefail
name="${1:?usage: $0 <command-name>}"
[[ -f "commands/$name.md" ]] || { echo "commands/$name.md not found" >&2; exit 1; }
ln -sfn "../../commands/$name.md" ".claude/commands/$name.md"
echo "linked: .claude/commands/$name.md -> ../../commands/$name.md"
