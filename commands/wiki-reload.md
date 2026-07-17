---
description: Reload (re-import) the OPEN note in place from its frontmatter source URL — reader-mode fetch, chrome sweep, same file, frontmatter preserved, index refreshed. Triggers: "перезагрузи заметку", "переимпортируй заметку", "reload this note", "re-fetch the article". NOT wiki-import (which creates a NEW summarized note).
---

`/wiki-reload` refreshes an EXISTING web-clipped note **in place**: resolve the open note +
its frontmatter URL (`obsidian-context read --frontmatter`) → confirm once → reader-only
fetch → sweep the site chrome → rebuild the **same file** with the original frontmatter
preserved verbatim → `wiki-index-upsert`.

**NOT `/wiki-import`** (that creates a NEW summarized note + concept pages) and **not** a
whole-page dump (reader mode + chrome sweep are mandatory).

**Execute the workflow file.** It lives in the obsidian-llm-wiki REPO, not in the current
vault — from a vault CWD a relative `workflows/…` path resolves to NOTHING. Resolve it through
this command's own symlink (works from any CWD):

```bash
WF="$(dirname "$(dirname "$(readlink -f ~/.claude/commands/wiki-reload.md)")")/workflows/wiki-reload.md"
```

Read `$WF` and follow its steps exactly, in order. (If the symlink is absent, ask the user for
the obsidian-llm-wiki repo path and use `<repo>/workflows/wiki-reload.md` — do NOT improvise
the procedure from memory.)

User's task context:
$ARGUMENTS
