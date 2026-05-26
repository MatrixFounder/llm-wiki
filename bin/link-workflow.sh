#!/usr/bin/env bash
# Usage: bin/link-workflow.sh <workflow-name>
# Creates .agent/workflows/<name>.md -> ../../workflows/<name>.md
# Workflows live agent-side (the agentic-development framework reads them
# from .agent/workflows/). Run from the repo root.
set -euo pipefail

name="${1:?usage: $0 <workflow-name>}"
[[ -f "workflows/$name.md" ]] || { echo "workflows/$name.md not found" >&2; exit 1; }

mkdir -p .agent/workflows
ln -sfn "../../workflows/$name.md" ".agent/workflows/$name.md"
echo "linked: .agent/workflows/$name.md -> ../../workflows/$name.md"
