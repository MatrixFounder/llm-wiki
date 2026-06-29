# TASK 045-04 — SKILL.md update (R-7)

## Goal
Update `skills/wiki-search/SKILL.md` to document the two new JSON fields (`file_path`,
`obsidian_url`) and the `--format markdown` Obsidian link behaviour.

## Context
- File to edit: `skills/wiki-search/SKILL.md`
- Current version: `version: 1.6` (from the YAML frontmatter)
- Relevant section: "## Contract" → "Default output: JSON envelope with `hits[]`..."

## Steps

### Step 1: Bump version in frontmatter

Change:
```yaml
version: 1.6
```
to:
```yaml
version: 1.7
```

### Step 2: Update the JSON schema description

Find the line:
```
- Default output: JSON envelope with `hits[]` (each hit has `vault_id`,
  `slug`, `project`, `type`, `title`, `bm25_score`, `snippet`).
```

Replace with:
```
- Default output: JSON envelope with `hits[]` (each hit has `vault_id`,
  `slug`, `project`, `type`, `title`, `bm25_score`, `snippet`,
  `file_path: str` (path relative to vault root), and
  `obsidian_url: str | null` — see Obsidian deep-link below).
```

### Step 3: Add Obsidian deep-link documentation

After the exit-codes table (or after the contract section), add:

```markdown
## Obsidian deep-link

Each hit in the JSON envelope includes:

- **`file_path`** — path of the note relative to its vault root
  (e.g. `_sources/foo.md`, `Lessons/X/_concepts/Bar.md`). Always present.
  Use it for `Read` without reconstructing the path from `slug`/`project`.
- **`obsidian_url`** — `obsidian://open?vault=<name>&file=<path>` deep-link
  that opens the note directly in the Obsidian desktop app. `null` when the
  vault is not in the registry (stale DB / removed vault).
  `<name>` is the vault **root folder basename** (e.g. `MyObsidianVault`) —
  the identifier Obsidian uses in its URI scheme.
  Note: if you renamed the folder after registering the vault, `<name>` may
  differ from `vault_id`; re-run `wiki-init --register-existing` to sync.

**`--format markdown` output** additionally appends the link:
- **TTY** (interactive terminal — iTerm2, VS Code integrated terminal): a
  clickable `[↗]` ANSI OSC 8 hyperlink is appended after the snippet.
  Clicking it opens the note in Obsidian.
- **Piped / redirected**: the plain `obsidian://…` URI is appended as text.
  Grep-able and copy-pasteable.
```

### Step 4: Verify

- No contradictions with existing contract text.
- Version bumped to 1.7.
- Run `skill-validator` if available: check clean.

## Verification
```bash
grep "version:" skills/wiki-search/SKILL.md
# Expected: version: 1.7
grep "obsidian_url" skills/wiki-search/SKILL.md | wc -l
# Expected: ≥ 3 lines
```
