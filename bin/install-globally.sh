#!/usr/bin/env bash
# Usage: bin/install-globally.sh
#
# Make the wiki-* CLIs and Claude Code skills available from any project.
# Idempotent (ln -sfn).
#
#   1. Symlinks `bin/wiki-*` wrappers into `~/.local/bin/` (or $WIKI_INSTALL_BIN).
#   2. Symlinks `skills/wiki-*/` into `~/.claude/skills/wiki-*/`.
#   3. Symlinks `commands/wiki-*.md` into `~/.claude/commands/wiki-*.md`.
#   4. Symlinks `workflows/wiki-enrich.md` into `~/.claude/skills/wiki-enrich/`
#      reference path (workflow is owned by the skill).
#
# Prereqs: this repo's venv is set up (`python3 -m venv .venv && pip install -r requirements.txt`).
#
# After running: ensure `~/.local/bin` is on PATH, then `/wiki-*` slash commands
# work from any Claude Code project, and `wiki-search "x"` etc. work from any shell.
set -euo pipefail

REPO="$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$0")")/.." && pwd)"
BIN_DIR="${WIKI_INSTALL_BIN:-$HOME/.local/bin}"
CLAUDE_SKILLS="$HOME/.claude/skills"
CLAUDE_COMMANDS="$HOME/.claude/commands"

[[ -d "$REPO/.venv" ]] || {
  echo "error: $REPO/.venv not found. Run python3 -m venv .venv && pip install -r requirements.txt first." >&2
  exit 1
}

mkdir -p "$BIN_DIR" "$CLAUDE_SKILLS" "$CLAUDE_COMMANDS"

# 1. wrappers → ~/.local/bin/
count_bin=0
for wrapper in "$REPO"/bin/wiki-*; do
  [[ -f "$wrapper" && -x "$wrapper" ]] || continue
  name="$(basename "$wrapper")"
  ln -sfn "$wrapper" "$BIN_DIR/$name"
  count_bin=$((count_bin + 1))
done

# 2. skills → ~/.claude/skills/
count_skills=0
for src in "$REPO"/skills/wiki-*/; do
  [[ -d "$src" ]] || continue
  name="$(basename "$src")"
  ln -sfn "$src" "$CLAUDE_SKILLS/$name"
  count_skills=$((count_skills + 1))
done

# 3. commands → ~/.claude/commands/
count_commands=0
for src in "$REPO"/commands/wiki-*.md; do
  [[ -f "$src" ]] || continue
  name="$(basename "$src")"
  ln -sfn "$src" "$CLAUDE_COMMANDS/$name"
  count_commands=$((count_commands + 1))
done

echo "Installed globally:"
echo "  wrappers     → $BIN_DIR             ($count_bin)"
echo "  skills       → $CLAUDE_SKILLS       ($count_skills)"
echo "  commands     → $CLAUDE_COMMANDS     ($count_commands)"

# PATH check
case ":$PATH:" in
  *":$BIN_DIR:"*)
    echo ""
    echo "✓ $BIN_DIR is on PATH"
    ;;
  *)
    echo ""
    echo "⚠ $BIN_DIR is NOT on PATH. Add this line to your shell rc:"
    echo "    export PATH=\"$BIN_DIR:\$PATH\""
    ;;
esac

# wiki-ingest reminder
if ! command -v wiki-ingest >/dev/null 2>&1; then
  echo ""
  echo "⚠ \`wiki-ingest\` not on PATH — \`/wiki-enrich\` requires it (v1.1+)."
  echo "  Install the wiki-ingest skill separately; see docs/WIKI-INGEST-V1.1-CONTRACT.md."
fi
