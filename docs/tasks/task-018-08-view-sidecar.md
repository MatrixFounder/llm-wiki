# task-018-08 — [LOGIC] generated-view sidecar detection + only-a-view guard

**Parent:** TASK 018. **Depends on:** 018-05. **RTM:** E2.2, AC-2, AC-2b. **Closes:** RC-4 (matcher), RC-5 (reuse decision).

## Goal
Skip generated-view sidecars (navigation, not knowledge) **without** over-flagging real notes.

## Design (locked)
Markers: DB Folder (`database-plugin:` frontmatter **and/or** a fenced ` ```yaml:dbfolder ` body);
Bases (a fenced ` ```base ` body **or** a sibling `.base` companion); Dataview (a fenced
` ```dataview ` / ` ```dataviewjs ` body); folder-note (stem == parent/sibling dir name).

**Only-a-view guard (RC-4, AC-2b):** skip **only** when the body is *essentially one view
block* — concrete matcher: strip frontmatter, then the non-blank body is a single fenced block
whose info-string ∈ {`yaml:dbfolder`,`base`,`dataview`,`dataviewjs`} with no material prose
outside it (a small tolerance for a leading H1/MOC line). A note that *embeds* such a block
alongside real prose is **content → not skipped**.

## Steps
1. Implement the marker scan (frontmatter key + fenced-info-string + folder-note name test).
2. Implement the only-a-view ratio matcher. **RC-5:** evaluate reusing vendored
   `wiki_ingest._classify._count_md_structure` for the body-structure count; if it fits, import
   it (acyclic); else implement a small local helper — **record the decision in a code comment**.
3. GREEN: the operator's real `yaml:dbfolder` sample + Bases + Dataview + folder-note → `skip`
   (reason = matched marker); an embedded-dataview content note → falls through (→ upsert in 09).

## Verification
- `pytest -q -k "classify or view_sidecar"` GREEN; `mypy --strict` clean.
