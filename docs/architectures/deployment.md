# 10. Deployment

> Part of [docs/ARCHITECTURE.md](../ARCHITECTURE.md).


### 10.1. Environments

- **Dev**: разработчик на своей машине (macOS / Linux). `tests/fixtures/minimal-vault/` для unit/integration.
- **Staging**: ad-hoc — `tmp2/` для bulk-migration validation; `/private/tmp/wiki-test-vault/` для iCloud-simulation.
- **Prod**: пользовательский Obsidian vault (`~/Library/Mobile Documents/iCloud~md~obsidian/Documents/ObsidianNotes/`). Realistic e2e на rsync-копии в `/private/tmp/wiki-validation/`.

### 10.2. CI/CD Pipeline

**Stub для MVP** — Makefile с targets:

```makefile
# Makefile
.PHONY: install test bench lint format clean

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	.venv/bin/pip install -e .

test:
	.venv/bin/pytest tests/ -v

bench:
	.venv/bin/python scripts/benchmark.py --vault-sizes 100,1000,10000

lint:
	.venv/bin/ruff check scripts/ skills/
	.venv/bin/python -m jsonschema -i schemas/wiki-config.example.yaml schemas/wiki-config.schema.yaml

format:
	.venv/bin/ruff format scripts/ skills/

clean:
	rm -rf .venv build dist *.egg-info
```

**Future**: GitHub Actions с тем же flow + matrix testing на macOS / Ubuntu.

### 10.3. Configuration

- **`~/.config/wiki-mcp/keys.env`** — API keys (gitignored).
- **`<vault>/CLAUDE.md`** — per-vault schema (под git если vault git-repo).
- **`<project>/.wiki.yaml`** — per-project override.
- **`requirements.txt`** — Python deps pinned (`python-slugify==8.x`, `python-frontmatter`, `pyyaml`, `jsonschema`). ⚠️ `anthropic` was listed here and is **NOT a dependency** — under Decision-17 `scripts/` makes no LLM-provider call (`grep -rnE '^\s*(import anthropic|from anthropic)' scripts/` → **0**, gated population-wide). Corrected 2026-08-06 (TASK 072).
- **`${XDG_CONFIG_HOME:-~/.config}/obsidian-llm-wiki/skills.env`** — OPTIONAL per-binary overrides for the external acquire skills; template at `config/skills.env.example`, auto-loaded by the `wiki-*` CLIs. Every `WIKI_*_BIN` var is documented there and that completeness is gated by `tests/test_skill_bin_resolve.py::test_env_example_documents_every_var`.
  - ★ **`WIKI_HTML_LAUNCHER_BIN` (TASK 072, new)** — the `html` skill's **verb launcher**
    (`scripts/html`), distinct from `WIKI_HTML_BIN` (`scripts/html2md.py`, a shim with no verb
    routing). `wiki-import`'s two URL-fetch call sites go through its `get` verb, which is the only
    door into the skill's SSRF-guarded ladder. **Operational requirement**: the installed `html`
    build must list `html get URL` in `--help`. An older build is **refused** with
    `DEPENDENCY_MISSING` (exit 6) naming the remediations — it never falls back to an unguarded
    fetch, so an out-of-date skill degrades loudly rather than silently re-opening the egress hole.

### 10.4. Deployment Instructions

```bash
# 1. Clone repo
cd ~/Antigravity
git clone <repo-url> obsidian-llm-wiki  # already exists

# 2. Setup Python env
cd obsidian-llm-wiki
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .  # install wiki-* skills as commands

# 3. Symlink skills to ~/.claude/skills/
for skill in skills/wiki-*; do
    ln -sf "$(pwd)/$skill" "$HOME/.claude/skills/$(basename $skill)"
done

# 4. Install summarizing-meetings (transcript adapter dep)
git submodule add https://github.com/MatrixFounder/Universal-skills.git external/Universal-skills
ln -sf "$(pwd)/external/Universal-skills/skills/summarizing-meetings" "$HOME/.claude/skills/summarizing-meetings"

# 5. Set API key
mkdir -p ~/.config/wiki-mcp
echo "ANTHROPIC_API_KEY=sk-ant-..." > ~/.config/wiki-mcp/keys.env
chmod 600 ~/.config/wiki-mcp/keys.env

# 6. Test on minimal vault
make test
make bench

# 7. Initialize a real vault
cd ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/ObsidianNotes/
claude
> /wiki-init
```

---

