#!/usr/bin/env bash
# Usage: bin/install-globally.sh
#
# Make the wiki-* CLIs and Claude Code skills/commands available from any project.
# RUN THIS after adding (or renaming) a `bin/wiki-*`, `skills/wiki-*/`, or `commands/wiki-*.md`
# — new entries are NOT auto-propagated, so a freshly-added skill/CLI (e.g. wiki-import,
# wiki-graph, wiki-health) is invisible to the `claude` CLI and the shell until this re-runs.
#
# Global surfaces:
#   ~/.local/bin/<cli>            → repo bin/<cli>            (PATH binaries; $WIKI_INSTALL_BIN)
#   ~/.claude/skills/<name>       → repo skills/<name>/       (Claude Code Skill tool)
#   ~/.claude/commands/<name>.md  → repo commands/<name>.md   (Claude slash commands)
#   ~/.pi/skills/<name>           → repo skills/<name>/       (pi skills — TASK 043; pi
#                                                              auto-exposes /skill:<name>)
# The PATH binaries are shared (vendor-neutral); each agent gets the same wiki-* + obsidian-cli
# skills. (`obsidian-cli` is now installed too — previously only the wiki-* skills were.)
#
# Safe + idempotent: creates a MISSING link, REPAIRS a stale link that already points into
# THIS repo, and SKIPS (never clobbers) a real file/dir or a link owned by another tool
# (e.g. ~/.claude/skills/summarizing-meetings → the Universal-skills repo). Never deletes data.
#
# Prereqs: this repo's venv (`python3 -m venv .venv && pip install -r requirements.txt`).
# After running: ensure `~/.local/bin` is on PATH; then `/wiki-*` + `wiki-* ` work anywhere.
set -euo pipefail

REPO="$(cd "$(dirname "$(readlink -f "$0" 2>/dev/null || python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$0")")/.." && pwd)"
BIN_DIR="${WIKI_INSTALL_BIN:-$HOME/.local/bin}"
CLAUDE_SKILLS="$HOME/.claude/skills"
CLAUDE_COMMANDS="$HOME/.claude/commands"
PI_SKILLS="$HOME/.pi/skills"           # TASK 043: pi's global skill discovery dir

[[ -d "$REPO/.venv" ]] || {
  echo "error: $REPO/.venv not found. Run python3 -m venv .venv && pip install -r requirements.txt first." >&2
  exit 1
}

mkdir -p "$BIN_DIR" "$CLAUDE_SKILLS" "$CLAUDE_COMMANDS" "$PI_SKILLS"

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
# ★ ENUMERATE THE POPULATION — NEVER GUESS IT FROM A NAME PREFIX.
#
# This globbed `skills/wiki-*/ + obsidian-cli/`, and that filter SILENTLY EXCLUDED the two
# most important skills in the repo. The naming convention is that a CLI skill is `wiki-<cli>`
# while a REASON contract is NOT (`concept-extraction`, `decision-extraction`) — so the prefix
# filter dropped **every REASON contract that did not happen to start with `wiki-`**.
#
# `wiki-query-synthesis` survived by luck of its name. `concept-extraction` and
# `decision-extraction` did not: they were installed in the REPO tree (install-project-symlinks
# globs `skills/*/`, unfiltered) and therefore worked in development — while being unreachable
# from a VAULT, which is the only place an operator actually runs these rails. The contract
# carrying the whole anti-garbage discipline never loaded on the shipped path, and the model
# improvised. Re-running this script would never have fixed it; the skills were not forgotten,
# they were filtered out.
#
# So: every directory under skills/ is a skill, and every one ships. If a skill should ever be
# repo-only, mark it IN the skill, do not encode the policy in a glob here.
link_skills_into() {
  local dest="$1" src
  for src in "$REPO"/skills/*/; do
    [[ -d "$src" ]] || continue
    safe_link "${src%/}" "$dest/$(basename "$src")"
  done
}
echo "skills → $CLAUDE_SKILLS"
link_skills_into "$CLAUDE_SKILLS"
echo "skills → $PI_SKILLS"           # TASK 043
link_skills_into "$PI_SKILLS"
echo "commands → $CLAUDE_COMMANDS"
# Same rule as the skills above: enumerate, don't guess. Every command ships. (Today they all
# happen to be `wiki-*` — which is exactly how the skills glob looked right, until it didn't.)
for src in "$REPO"/commands/*.md; do
  [[ -f "$src" ]] || continue
  safe_link "$src" "$CLAUDE_COMMANDS/$(basename "$src")"
done

echo ""
echo "global install: ${n_new} new, ${n_repaired} repaired, ${n_ok} already-ok, ${n_skip} skipped"

# Pin the resolved EXTERNAL acquire-skill bins (html/pdf/pptx/transcript) into a skills.env that
# the wiki-* CLIs AUTO-LOAD at startup (no manual sourcing). Resolution is vendor-agnostic and
# discovers skill dirs across ANY harness — this file just pins the result (fast + editable).
# Non-fatal: a resolver hiccup must not abort the install.
echo ""
echo "external acquire skills (vendor-agnostic resolve):"
SKILLS_ENV="${XDG_CONFIG_HOME:-$HOME/.config}/obsidian-llm-wiki/skills.env"
mkdir -p "$(dirname "$SKILLS_ENV")"
if PYTHONPATH="$REPO" "$REPO/.venv/bin/python" - "$SKILLS_ENV" <<'PY'
import os, sys
from pathlib import Path
from scripts.wiki_skills.wiki_import_article._fetch import resolve_skill_bin, _SKILL_BIN_SPEC
# Re-discover FRESH: drop any pin auto-loaded from an existing skills.env so a re-install that
# runs after the operator moved/switched harnesses re-resolves instead of echoing stale paths.
for _ev, *_rest in _SKILL_BIN_SPEC.values():
    os.environ.pop(_ev, None)
lines = ["# wiki-import external acquire-skill bins. Auto-LOADED by the CLIs at startup",
         "# (no manual sourcing). A value exported in your shell overrides the pin here.\n"]
for key, (env_var, _dirs, _rel) in _SKILL_BIN_SPEC.items():
    p = resolve_skill_bin(key)
    ok = Path(p).exists()
    print(f"  {'ok ' if ok else 'MISS'}  {env_var}={p}")
    if ok:
        lines.append(f'export {env_var}="{p}"')
Path(sys.argv[1]).write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
then
  echo "  → wrote $SKILLS_ENV  (auto-loaded by the wiki-* CLIs; see config/skills.env.example to pin/override)"
else
  echo "  ⚠ could not resolve skill bins (non-fatal); the CLIs still auto-scan + accept --*-bin flags"
fi

# PATH check
case ":$PATH:" in
  *":$BIN_DIR:"*) echo "✓ $BIN_DIR is on PATH" ;;
  *) echo "⚠ $BIN_DIR is NOT on PATH — add: export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac
