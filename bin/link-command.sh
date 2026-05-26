#!/usr/bin/env bash
# Usage: bin/link-command.sh <command-name>
# Creates .claude/commands/<name>.md -> ../../commands/<name>.md
# (Commands are Claude-Code-specific; the .agent/ tree has no equivalent —
# agent-side dispatch lives in .agent/workflows/. Use bin/link-workflow.sh
# for the workflow file when the command references one.)
# Run from the repo root.
set -euo pipefail

name="${1:?usage: $0 <command-name>}"
[[ -f "commands/$name.md" ]] || { echo "commands/$name.md not found" >&2; exit 1; }

mkdir -p .claude/commands
ln -sfn "../../commands/$name.md" ".claude/commands/$name.md"
echo "linked: .claude/commands/$name.md -> ../../commands/$name.md"
