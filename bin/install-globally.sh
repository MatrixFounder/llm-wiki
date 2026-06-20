#!/usr/bin/env bash
# Usage: bin/install-globally.sh
#
# Make the wiki-* CLIs and Claude Code skills/commands available from any project.
# RUN THIS after adding (or renaming) a `bin/wiki-*`, `skills/wiki-*/`, or `commands/wiki-*.md`
# — new entries are NOT auto-propagated, so a freshly-added skill/CLI (e.g. wiki-import,
# wiki-graph, wiki-health) is invisible to the `claude` CLI and the shell until this re-runs.
#
# Three global surfaces:
#   ~/.local/bin/<cli>            → repo bin/<cli>            (PATH binaries; $WIKI_INSTALL_BIN)
#   ~/.claude/skills/<name>       → repo skills/<name>/       (Skill tool)
#   ~/.claude/commands/<name>.md  → repo commands/<name>.md   (slash commands)
#
# Safe + idempotent: creates a MISSING link, REPAIRS a stale link that already points into
# THIS repo, and SKIPS (never clobbers) a real file/dir or a link owned by another tool
# (e.g. ~/.claude/skills/wiki-ingest → the Universal-skills repo). Never deletes data.
#
# Prereqs: this repo's venv (`python3 -m venv .venv && pip install -r requirements.txt`).
# After running: ensure `~/.local/bin` is on PATH; then `/wiki-*` + `wiki-* ` work anywhere.
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

n_new=0; n_repaired=0; n_ok=0; n_skip=0
# safe_link <target> <linkpath>: install/repair links into THIS repo; never clobber foreign ones.
safe_link() {
  local target="$1" lp="$2" name; name="$(basename "$lp")"
  if [[ -L "$lp" ]]; then
    local cur; cur="$(readlink "$lp")"
    if [[ "$cur" == "$target" ]]; then n_ok=$((n_ok+1)); return; fi
    case "$cur" in
      "$REPO"/*) ln -sfn "$target" "$lp"; echo "  repaired $name"; n_repaired=$((n_repaired+1));;
      *)         echo "  SKIP    $name → $cur (owned by another tool)"; n_skip=$((n_skip+1));;
    esac
  elif [[ -e "$lp" ]]; then
    echo "  SKIP    $name (a real file/dir exists)"; n_skip=$((n_skip+1))
  else
    ln -s "$target" "$lp"; echo "  linked  $name"; n_new=$((n_new+1))
  fi
}

echo "CLIs → $BIN_DIR"
for wrapper in "$REPO"/bin/wiki-*; do                 # executable wrappers only (skip *.sh helpers)
  [[ -f "$wrapper" && -x "$wrapper" ]] || continue
  safe_link "$wrapper" "$BIN_DIR/$(basename "$wrapper")"
done
# obsidian-active-note: the obsidian-cli skill's active-note resolver (TASK 041) — not a wiki-* CLI.
[[ -x "$REPO/bin/obsidian-active-note" ]] && safe_link "$REPO/bin/obsidian-active-note" "$BIN_DIR/obsidian-active-note"
echo "skills → $CLAUDE_SKILLS"
for src in "$REPO"/skills/wiki-*/; do
  [[ -d "$src" ]] || continue
  safe_link "${src%/}" "$CLAUDE_SKILLS/$(basename "$src")"
done
echo "commands → $CLAUDE_COMMANDS"
for src in "$REPO"/commands/wiki-*.md; do
  [[ -f "$src" ]] || continue
  safe_link "$src" "$CLAUDE_COMMANDS/$(basename "$src")"
done

echo ""
echo "global install: ${n_new} new, ${n_repaired} repaired, ${n_ok} already-ok, ${n_skip} skipped"

# PATH check
case ":$PATH:" in
  *":$BIN_DIR:"*) echo "✓ $BIN_DIR is on PATH" ;;
  *) echo "⚠ $BIN_DIR is NOT on PATH — add: export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

# wiki-ingest is a SEPARATE skill (not in this repo) that /wiki-enrich needs.
command -v wiki-ingest >/dev/null 2>&1 || \
  echo "⚠ \`wiki-ingest\` not on PATH — \`/wiki-enrich\` needs it; see docs/WIKI-INGEST-V1.1-CONTRACT.md."
