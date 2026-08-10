# TASK 073 — [LIGHT] `wiki-config`: a whole-list `set` must not delete comments between list items

<!-- contract:meta -->

## 0. Meta Information

| | |
|---|---|
| **Task ID** | 073 |
| **Slug** | wiki-config-list-edit-comment-preservation |
| **Mode** | Light (`/light`) — RTM skipped per `02_analyst_prompt.md` §Light Mode Bypass |
| **Origin** | Operator report (2026-08-10): `wiki-config serve --open` refused a root save with `saved 0/1; FAILED — .: EDIT_REFUSED: a comment line would be lost by this edit` |
| **Type** | Bug fix (defect in `_apply_edits_ruamel` list handling) |
| **Files** | `scripts/wiki_skills/wiki_config/_edit.py`, `tests/test_wiki_config_doctor.py` |
| **Schema** | zero DDL, no new dependency, no CLI-contract change |
| **Predecessor** | TASK 058 (`docs/tasks/task-058-*`) shipped the ruamel sandwich this task repairs. |

<!-- contract:problem -->

## 1. Problem

`PointerEdit("set", "/exclude", [...])` assigns a plain Python list over an existing
`CommentedSeq`. ruamel then renders a new sequence, and every comment line that sat
**between** the list's items is absent from the render. The post-write comment-survival
check (`_edit.py:249-254`) detects the loss and raises `EditDowngrade`, so the whole batch
is refused and nothing is written.

The web editor renders every `array` field as one textarea and saves the field whole
(`_app_html.py:611-612`). Editing one entry of a commented list is therefore unreachable
through the editor, and through `wiki-config set`, which shares `rewrite_text`.

**Why.** The guard is correct — the render did lose comments. The defect is upstream of it:
list `set` is implemented as replace-all when the operator's intent is a per-item change.

Measured on the live vault root `.wiki/sync.yaml`
(`/Users/sergey/Library/Mobile Documents/iCloud~md~obsidian/Documents/ObsidianNotes`):
a `set` of `/exclude` to its own current value drops 6 comment lines and exits `EDIT_REFUSED`.
Of the 17 fields present in that file, `/exclude` is the only one that fails; it is the only
list carrying comments between items.

<!-- contract:use-cases -->

## 2. Use Cases

**UC-1 — append an entry to a commented list.** The operator adds `"**/Drafts/**"` to
`exclude` in the web editor and presses Save. The file gains one item, and all 6 existing
comment lines stay on the items they annotate.

**UC-2 — reorder / edit one entry.** The operator changes one item's text. The surviving
items keep their attached comments; the comment attached to the removed item goes with it.

**UC-3 — remove an entry.** The list shrinks by one. The edit removes that item's own
comments and is reported as such, and no unrelated comment is touched.

**UC-4 — no-op save.** The operator saves the form without changing the list value. The
rendered file keeps every comment line it had.

<!-- contract:acceptance -->

## 3. Acceptance Criteria

- **AC-1** — `rewrite_text` with `set` of `/exclude` to its current value on the live-vault
  fixture returns text whose comment multiset equals the input's; fails when the element-wise
  branch is reverted to plain assignment.
- **AC-2** — `set` appending one item to a commented list preserves every prior comment line
  and places the new item last; fails when the branch drops the diff and rewrites the sequence.
- **AC-3** — `set` that removes an item from a commented list still applies, and the comments
  attached to the surviving items are present in the result.
- **AC-4** — the plain-dict oracle still governs: `parsed_after == planned` holds for every
  list case above, so the value written is exactly the value requested.
- **AC-5** — the existing hardened gates are unchanged: input gate, post-gate schema check and
  the `EditDowngrade`-writes-nothing contract keep their current behaviour.
- **AC-6** — `pytest tests/` is green and `mypy --strict scripts/` is clean.

<!-- contract:open-questions -->

## 4. Open Questions

**Q-073-1 — does removing a list item exempt the comment check?** An item's own comment
must leave with the item, so the check cannot demand its survival. The decision taken:
the removal path marks the edit destructive for the comment check only when the diff
actually deletes an item, and the pre-write backup remains the record. Blocks: nothing.
Owner: implementer, resolved in this task.
