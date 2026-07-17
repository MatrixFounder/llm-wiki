---
description: Reload (re-import) the OPEN note in place from its frontmatter source URL — reader-mode fetch, chrome sweep, same file, frontmatter preserved, index refreshed. Triggers: "перезагрузи заметку", "переимпортируй заметку", "reload this note", "re-fetch the article". NOT wiki-import (which creates a NEW summarized note).
---

`/wiki-reload` refreshes an EXISTING web-clipped note **in place**: resolve the open note +
its frontmatter URL (`obsidian-context read --frontmatter`) → confirm once → reader-only
fetch → sweep the site chrome → rebuild the **same file** with the original frontmatter
preserved verbatim → `wiki-index-upsert`.

**NOT `/wiki-import`** (that creates a NEW summarized note + concept pages) and **not** a
whole-page dump (reader mode + chrome sweep are mandatory).

Execute the workflow at [`workflows/wiki-reload.md`](../workflows/wiki-reload.md) — follow its
steps exactly, in order.

User's task context:
$ARGUMENTS
